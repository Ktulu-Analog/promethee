# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
llm_service.py — Service LLM (business logic sans PyQt6)
Fournit les fonctions pures pour interagir avec les LLMs.
"""
import base64
import json
import logging
import logging.handlers
import time
from pathlib import Path
from openai import OpenAI
from typing import Iterator, Callable, Any
from .config import Config
from . import tools_engine
from .session_memory import SessionMemory

# Taille max d'un résultat d'outil — lue depuis Config pour être configurable via .env.
_TOOL_RESULT_MAX_CHARS = Config.TOOL_RESULT_MAX_CHARS

# ── Callback compression de contexte ─────────────────────────────────────
_context_event_callback = None

def set_context_event_callback(fn) -> None:
    """Installe un callback appelé quand la compression de contexte se déclenche."""
    global _context_event_callback
    _context_event_callback = fn

def _context_event(msg: str) -> None:
    """Émet un événement de compression vers l'UI si un callback est installé."""
    if _context_event_callback is not None:
        _context_event_callback(msg)

# ── Callback statistiques de compression ──────────────────────────────────
# Émet un dict structuré à chaque opération de compression/troncature :
#   { "type": str, "before": int, "after": int, "saved": int, "pct": float }
# Types possibles : "compress_tool", "truncate_text", "trim_msgs"
_compression_stats_callback = None

def set_compression_stats_callback(fn) -> None:
    """Installe un callback recevant les stats détaillées de chaque compression."""
    global _compression_stats_callback
    _compression_stats_callback = fn

def _compression_stats_event(op_type: str, before: int, after: int) -> None:
    """Émet les stats structurées d'une opération de compression."""
    if _compression_stats_callback is None:
        return
    saved = before - after
    pct   = (saved / before * 100) if before > 0 else 0.0
    _compression_stats_callback({
        "type":   op_type,
        "before": before,
        "after":  after,
        "saved":  saved,
        "pct":    pct,
    })

# ── Callback mémoire de session ────────────────────────────────────────────
_memory_event_callback = None

def set_memory_event_callback(fn) -> None:
    """Installe un callback appelé quand la mémoire de session génère un événement
    (consolidation déclenchée, résultat d'outil marqué critique)."""
    global _memory_event_callback
    _memory_event_callback = fn

def _memory_event(msg: str) -> None:
    """Émet un événement mémoire vers l'UI si un callback est installé."""
    if _memory_event_callback is not None:
        _memory_event_callback(msg)


# ── Répertoire de logs de l'application ───────────────────────────────────
# Les logs sont stockés dans ~/.promethee/logs/ au lieu de la racine ~
_LOG_DIR = Path.home() / ".promethee" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

def _make_rotating_handler(log_path: Path) -> logging.handlers.RotatingFileHandler:
    """
    Crée un RotatingFileHandler avec rotation automatique :
      - maxBytes  : 5 Mo par fichier
      - backupCount : 5 archives conservées (.log.1 … .log.5)
    """
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 Mo
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    return handler


# ── Logger tokens ─────────────────────────────────────────────────────────
_token_log = logging.getLogger("promethee.tokens")
_token_log.setLevel(logging.DEBUG)
_token_log.propagate = False

def _setup_token_logger():
    """Configure le logger de tokens si ce n'est pas déjà fait."""
    if _token_log.handlers:
        return
    log_path = _LOG_DIR / "tokens.log"
    _token_log.addHandler(_make_rotating_handler(log_path))

_setup_token_logger()


# ── Logger session_memory — même fichier que les tokens ───────────────────────
_sm_log = logging.getLogger("promethee.session_memory")
_sm_log.setLevel(logging.DEBUG)
_sm_log.propagate = False

def _setup_sm_logger():
    """Configure le logger session_memory sur le même fichier que les tokens."""
    if _sm_log.handlers:
        return
    log_path = _LOG_DIR / "tokens.log"
    _sm_log.addHandler(_make_rotating_handler(log_path))

_setup_sm_logger()


class TokenUsage:
    """
    Cumul de tokens pour une requête (stream_chat ou agent_loop).

    Champs spécifiques à l'API Albert :
      cost   — coût en euros (float)
      carbon — empreinte carbone : {'kWh': {min, max}, 'kgCO2eq': {min, max}}

    En streaming, Albert retourne deux chunks avec usage :
      - Chunk intermédiaire : tokens partiels, sans cost/carbon
      - Chunk final         : tokens complets + cost + carbon + requests=1
    Seul le chunk final (détecté par la présence de requests >= 1) est pris en compte.
    """
    __slots__ = ("prompt", "completion", "calls", "cost", "carbon")

    def __init__(self):
        self.prompt:     int   = 0
        self.completion: int   = 0
        self.calls:      int   = 0
        self.cost:       float = 0.0
        self.carbon:     dict  = {}

    @staticmethod
    def _is_final_chunk(usage) -> bool:
        """
        Détecte si un chunk usage est le chunk final d'Albert.
        Le chunk final contient requests >= 1 et cost (même à 0.0).
        Le chunk intermédiaire n'a pas ces champs.
        """
        return getattr(usage, "requests", None) is not None

    def add(self, usage, streaming: bool = False) -> None:
        """
        Ajoute les tokens d'un objet usage renvoyé par l'API.

        En mode streaming, ignore les chunks intermédiaires d'Albert
        (ceux sans le champ 'requests') pour éviter le double comptage.
        """
        if usage is None:
            return
        if streaming and not self._is_final_chunk(usage):
            return   # chunk intermédiaire Albert — ignorer

        self.prompt     += getattr(usage, "prompt_tokens",     0) or 0
        self.completion += getattr(usage, "completion_tokens", 0) or 0
        self.calls      += 1
        self.cost       += getattr(usage, "cost",   0.0) or 0.0
        carbon = getattr(usage, "carbon", None)
        if carbon and isinstance(carbon, dict):
            # Cumuler min/max kWh et kgCO2eq
            for unit in ("kWh", "kgCO2eq"):
                if unit in carbon:
                    existing = self.carbon.setdefault(unit, {"min": 0.0, "max": 0.0})
                    existing["min"] += carbon[unit].get("min", 0.0)
                    existing["max"] += carbon[unit].get("max", 0.0)

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    def pct(self, model_max: int = 0) -> float:
        """Pourcentage de la fenêtre du modèle consommé (basé sur prompt_tokens)."""
        if model_max <= 0:
            return 0.0
        return min(100.0, self.prompt * 100 / model_max)

    def log(self, context: str = "") -> None:
        """Écrit une ligne dans le fichier log tokens."""
        co2_str = ""
        if self.carbon.get("kgCO2eq"):
            lo = self.carbon["kgCO2eq"]["min"]
            hi = self.carbon["kgCO2eq"]["max"]
            co2_str = f" co2=[{lo:.6f}-{hi:.6f}]kgCO2"
        _token_log.debug(
            "[%s] prompt=%d completion=%d total=%d calls=%d pct=%.1f%% cost=%.6f€%s",
            context or "?",
            self.prompt, self.completion, self.total, self.calls,
            self.pct(Config.CONTEXT_MODEL_MAX_TOKENS),
            self.cost,
            co2_str,
        )

    def __str__(self) -> str:
        return (
            f"{self.prompt:,} prompt + {self.completion:,} completion "
            f"= {self.total:,} tokens"
        )


def _estimate_chars(msgs: list[dict]) -> int:
    """Estime la taille totale d'une liste de messages en caractères."""
    total = 0
    for m in msgs:
        c = m.get("content") or ""
        if isinstance(c, list):           # contenu multi-part
            total += sum(len(str(p)) for p in c)
        else:
            total += len(c)
        # tool_calls côté assistant
        for tc in m.get("tool_calls", []) or []:
            total += len(tc.get("function", {}).get("arguments", ""))
    return total


def _trim_history(messages: list[dict], max_chars: int,
                  max_tokens: int = 0, known_prompt_tokens: int = 0) -> list[dict]:
    """
    Fenêtre glissante sur l'historique de conversation.

    Priorité :
      - Si max_tokens > 0 ET known_prompt_tokens > 0, utilise les tokens réels.
      - Sinon, fallback sur l'estimation en caractères (max_chars).

    Garanties :
      - Le premier message utilisateur est toujours conservé (ancrage thématique).
      - Les messages sont retirés par paires (user + assistant) depuis le début
        pour ne pas laisser de tour incomplet.
      - Désactivé si les deux limites sont <= 0.
    """
    # Choisir le critère actif
    use_tokens = max_tokens > 0 and known_prompt_tokens > 0
    if use_tokens:
        if known_prompt_tokens <= max_tokens:
            return messages
    else:
        if max_chars <= 0 or _estimate_chars(messages) <= max_chars:
            return messages

    # Trouver le 1er message user à préserver comme ancre
    anchor_idx = next((i for i, m in enumerate(messages) if m["role"] == "user"), None)

    trimmed = list(messages)
    start = (anchor_idx + 1) if anchor_idx is not None else 0

    def _over_limit():
        if use_tokens:
            # On estime la réduction proportionnelle aux caractères retirés
            removed_chars = _estimate_chars(messages) - _estimate_chars(trimmed)
            estimated_tokens = known_prompt_tokens - removed_chars // 4
            return estimated_tokens > max_tokens
        return _estimate_chars(trimmed) > max_chars

    while _over_limit() and start + 1 < len(trimmed):
        trimmed.pop(start)
        if start < len(trimmed):
            trimmed.pop(start)

    n_dropped = len(messages) - len(trimmed)
    if n_dropped > 0:
        chars_before = _estimate_chars(messages)
        chars_after  = _estimate_chars(trimmed)
        saved        = chars_before - chars_after
        pct          = int(saved / chars_before * 100) if chars_before > 0 else 0
        _token_log.info(
            "[trim_history] %d message(s) retirés — historique réduit de %d → %d msgs",
            n_dropped, len(messages), len(trimmed),
        )
        _context_event(
            f"Trim : {n_dropped} msg écarté(s) — "
            f"{chars_before:,} → {chars_after:,} car. (-{pct}%)"
        )
        _compression_stats_event("trim_msgs", chars_before, chars_after)

    return trimmed


def _compress_agent_msgs(msgs: list[dict], current_turn: int,
                         compress_after: int, summary_chars: int) -> list[dict]:
    """
    Compression in-loop des tool_results anciens dans la boucle agent.

    Stratégie :
      - Les tool_results des tours < (current_turn - compress_after) sont remplacés
        par une version condensée (début + '…').
      - Les tool_results du tour courant et des compress_after derniers tours
        restent intacts.
      - Les messages non-tool ne sont pas touchés.

    Un "tour" = une itération de la boucle agent (un bloc assistant + ses N tool_results).

    Correction P2 : le compteur turn_idx est incrémenté sur les blocs assistant
    (role=assistant avec tool_calls) et non sur chaque message role=tool individuel.
    Un tour générant N tool_calls en parallèle produit N messages role=tool qui
    appartiennent tous au même tour — ils doivent partager le même turn_idx.
    """
    if compress_after <= 0 or current_turn <= compress_after:
        return msgs

    # Pré-calculer le turn_idx de chaque message en deux passes.
    #
    # Passe 1 : associer chaque tool_call_id au numéro de tour de son assistant.
    #   Un tour = un bloc assistant avec tool_calls. Les N messages role=tool
    #   suivants partagent le même turn_idx via leur tool_call_id.
    #
    # Passe 2 : construire turn_map en attribuant à chaque message role=tool
    #   le turn_idx de son assistant parent (lookup par tool_call_id).
    tc_to_turn: dict[str, int] = {}
    t = 0
    for m in msgs:
        if m["role"] == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tc_to_turn[tc["id"]] = t
            t += 1

    turn_map: list[int] = []
    cur_turn = 0
    for m in msgs:
        if m["role"] == "assistant" and m.get("tool_calls"):
            turn_map.append(cur_turn)
            cur_turn += 1
        elif m["role"] == "tool":
            turn_map.append(tc_to_turn.get(m.get("tool_call_id", ""), cur_turn - 1))
        else:
            turn_map.append(cur_turn)

    result = []
    for m, t_idx in zip(msgs, turn_map):
        if (m["role"] == "tool"
                and t_idx < current_turn - compress_after
                and len(m.get("content", "")) > summary_chars
                and not m.get("_pinned", False)):  # protégé par SessionMemory.apply_pinned_protection
            # Condenser le résultat de ce tour ancien
            original = m["content"]
            condensed = original[:summary_chars].rstrip() + f"… [condensé, {len(original)} car.]"
            saved = len(original) - len(condensed)
            pct   = int(saved / len(original) * 100) if len(original) > 0 else 0
            result.append({**m, "content": condensed})
            _token_log.info(
                "[compress_agent] tool_result tour %d condensé : %d → %d car.",
                t_idx, len(original), len(condensed),
            )
            _context_event(
                f"Compression outil (tour {t_idx}) : "
                f"{len(original):,} → {len(condensed):,} car. (-{pct}%)"
            )
            _compression_stats_event("compress_tool", len(original), len(condensed))
        else:
            result.append(m)
    return result


def build_client(local: bool = None) -> OpenAI:
    """Construit un client OpenAI ou Ollama."""
    use_local = Config.LOCAL if local is None else local
    if use_local:
        base_url = Config.OLLAMA_BASE_URL.rstrip("/") + "/v1"
        return OpenAI(base_url=base_url, api_key="ollama")
    return OpenAI(
        base_url=Config.OPENAI_API_BASE,
        api_key=Config.OPENAI_API_KEY or "none",
    )


# Extensions de fichiers bureautiques dont le résultat ne doit jamais être tronqué.
# Les outils d'export retournent un JSON {"path": "...", "status": "ok", ...} ;
# tronquer ce JSON corromprait le chemin ou les métadonnées transmises au LLM.
_OFFICE_EXTENSIONS = {
    ".docx", ".doc", ".odt",          # Traitement de texte
    ".xlsx", ".xls", ".ods", ".csv",  # Tableur
    ".pptx", ".ppt", ".odp",          # Présentation
    ".pdf",                           # PDF
}


def _is_office_result(result: str) -> bool:
    """
    Retourne True si le résultat JSON contient un champ 'path' pointant
    vers un fichier bureautique (export Word, Excel, PowerPoint, PDF…).

    Ces résultats sont compacts par nature (juste des métadonnées) mais
    leur troncature casserait le chemin ou les champs structurels transmis
    au LLM, ce qui est inacceptable.
    """
    try:
        parsed = json.loads(result)
        if not isinstance(parsed, dict):
            return False
        path_val = parsed.get("path", "")
        if not isinstance(path_val, str):
            return False
        return Path(path_val).suffix.lower() in _OFFICE_EXTENSIONS
    except (json.JSONDecodeError, TypeError):
        return False


def _truncate_tool_result(result: str, max_chars: int = _TOOL_RESULT_MAX_CHARS) -> str:
    """
    Tronque un résultat d'outil trop long pour éviter de dépasser le contexte.

    Deux catégories de résultats ne sont JAMAIS tronquées :

    1. Code source (_is_code → True)
       Une troncature partielle produit du code syntaxiquement invalide ou
       sémantiquement trompeur. Le pinning (SessionMemory) protège en outre
       ces résultats contre la compression in-loop des tours suivants.

    2. Résultats d'export bureautique (_is_office_result → True)
       Les outils d'export (Word, Excel, PowerPoint, PDF…) retournent un JSON
       {"path": "...", "status": "ok", ...}. Tronquer ce JSON corromprait le
       chemin ou les métadonnées transmises au LLM.

    Pour les résultats textuels génériques (texte, JSON, CSV, logs…) :
    troncature symétrique classique début + fin, avec indicateur central.

    Parameters
    ----------
    result : str
        Résultat brut retourné par l'outil.
    max_chars : int
        Limite de taille en caractères (défaut : 12 000).

    Returns
    -------
    str
        Résultat inchangé si code, export bureautique, ou taille dans la limite ;
        sinon troncature symétrique.
    """
    if len(result) <= max_chars:
        return result

    if SessionMemory._is_code(result):
        # Le code n'est jamais tronqué : risque de cohérence trop élevé.
        # Le pinning protégera ce résultat contre la compression in-loop.
        _token_log.info(
            "[truncate_tool_result] code détecté (%d cars.) — troncature ignorée, résultat conservé intégralement.",
            len(result),
        )
        _context_event(
            f"Code volumineux ({len(result):,} car.) — conservé intégralement (pas de troncature)"
        )
        return result

    if _is_office_result(result):
        # Les résultats d'export bureautique ne sont jamais tronqués.
        _token_log.info(
            "[truncate_tool_result] export bureautique détecté (%d cars.) — troncature ignorée.",
            len(result),
        )
        _context_event(
            f"Export bureautique ({len(result):,} car.) — conservé intégralement (pas de troncature)"
        )
        return result

    # Troncature symétrique générique
    half = max_chars // 2
    truncated = (
        result[:half]
        + f"\n\n[… résultat tronqué : {len(result):,} caractères → {max_chars:,} …]\n\n"
        + result[-half:]
    )
    _token_log.info(
        "[truncate_tool_result] texte — symétrique : %d → %d cars.",
        len(result), len(truncated),
    )
    saved = len(result) - len(truncated)
    pct   = int(saved / len(result) * 100) if len(result) > 0 else 0
    _context_event(
        f"Troncature résultat : "
        f"{len(result):,} → {len(truncated):,} car. (-{pct}%)"
    )
    _compression_stats_event("truncate_text", len(result), len(truncated))
    return truncated


def stream_chat(
    messages: list[dict],
    system_prompt: str = "",
    model: str = None,
    on_token: Callable[[str], None] = None,
    on_error: Callable[[str], None] = None,
    on_usage: Callable[["TokenUsage"], None] = None,
) -> str:
    """
    Streaming simple sans outils.
    Supporte les messages multi-part (texte + images).
    Retourne le texte complet généré.
    Appelle on_usage(TokenUsage) en fin de génération si disponible.
    """
    try:
        client = build_client()
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})

        msgs.extend(messages)

        usage = TokenUsage()
        full_text = ""

        # stream_options pour récupérer l'usage en mode streaming
        resp = client.chat.completions.create(
            model=model or Config.active_model(),
            messages=msgs,
            stream=True,
            temperature=0.7,
            stream_options={"include_usage": True},
        )

        for chunk in resp:
            if hasattr(chunk, "usage") and chunk.usage:
                usage.add(chunk.usage, streaming=True)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_text += delta.content
                if on_token:
                    on_token(delta.content)

        usage.log("stream_chat")
        if on_usage:
            on_usage(usage)

        return full_text
    except Exception as e:
        if on_error:
            on_error(str(e))
        raise


def agent_loop(
    messages: list[dict],
    system_prompt: str = "",
    model: str = None,
    use_tools: bool = True,
    max_iterations: int | None = None,
    disable_context_management: bool = False,
    on_tool_call: Callable[[str, str], None] = None,
    on_tool_result: Callable[[str, str], None] = None,
    on_image: Callable[[str, str], None] = None,
    on_token: Callable[[str], None] = None,
    on_error: Callable[[str], None] = None,
    on_usage: Callable[["TokenUsage"], None] = None,
) -> str:
    """
    Boucle agent avec tool-use.
    Supporte les messages multi-part (texte + images).
    Retourne la réponse finale complète.

    Paramètre disable_context_management
    ──────────────────────────────────────
    Si True, désactive intégralement toutes les formes de gestion du contexte :
      - Fenêtre glissante (_trim_history) — l'historique complet est conservé.
      - Compression in-loop (_compress_agent_msgs) — aucun tool_result n'est condensé.
      - Troncature des résultats d'outils (_truncate_tool_result) — résultats bruts.
      - Consolidation de mémoire (maybe_consolidate) — aucun résumé LLM secondaire.
      - Pinning (apply_pinned_protection / flush_pending) — sans effet (déjà no-op).
    Utile pour le débogage ou les sessions critiques nécessitant une fidélité totale.
    Attention : sur de longues sessions, le contexte peut dépasser la fenêtre du modèle.
    """
    try:
        client = build_client()
        # Résolution de max_iterations : valeur explicite ou Config (configurable via .env)
        if max_iterations is None:
            max_iterations = Config.AGENT_MAX_ITERATIONS
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})

        # Tokens cumulés sur toute la session agent
        usage = TokenUsage()

        # Mémoire de session : consolidation périodique + pinning des tool_results critiques
        memory = SessionMemory(
            client=client,
            model=model or Config.active_model(),
            consolidation_every=Config.CONTEXT_CONSOLIDATION_EVERY,
            consolidation_max_chars=Config.CONTEXT_CONSOLIDATION_MAX_CHARS,
            pinning_enabled=Config.CONTEXT_PINNING_ENABLED,
            pressure_threshold=Config.CONTEXT_CONSOLIDATION_PRESSURE_THRESHOLD,
            model_max_tokens=Config.CONTEXT_MODEL_MAX_TOKENS,
        )

        # Fenêtre glissante : écrêter l'historique si trop long.
        # Au 1er appel, known_prompt_tokens=0 → fallback sur les caractères.
        # Désactivée si disable_context_management=True.
        if disable_context_management:
            msgs.extend(list(messages))
        else:
            trimmed = _trim_history(
                list(messages),
                max_chars=Config.CONTEXT_HISTORY_MAX_CHARS,
                max_tokens=Config.CONTEXT_HISTORY_MAX_TOKENS,
                known_prompt_tokens=0,
            )
            if len(trimmed) < len(messages):
                n_dropped = len(messages) - len(trimmed)
                trimmed.insert(0, {
                    "role": "user",
                    "content": (
                        f"[Note système : {n_dropped} ancien(s) message(s) ont été omis "
                        f"pour respecter la limite de contexte. "
                        f"La conversation ci-dessous en est la suite.]"
                    ),
                })
                trimmed.insert(1, {
                    "role": "assistant",
                    "content": "Compris, je poursuis la conversation à partir du contexte disponible.",
                })
            msgs.extend(trimmed)

        tools = tools_engine.get_tool_schemas() if use_tools else None
        final_text = ""

        for iteration in range(max_iterations):
            if not disable_context_management:
                # Réévaluation différée du pinning : les tool_results enregistrés au tour
                # précédent sans texte assistant sont réévalués maintenant que la réponse
                # finale du tour N-1 est présente dans msgs.
                memory.flush_pending(msgs)

                # Consolidation périodique : résumé LLM de la session + pinning
                msgs = memory.maybe_consolidate(msgs, iteration, on_event=_memory_event, usage=usage)
                msgs = memory.apply_pinned_protection(msgs)

                # Compression in-loop : condenser les tool_results des tours anciens
                # (les tool_results marqués _pinned=True sont exclus de la compression)
                msgs = _compress_agent_msgs(
                    msgs,
                    current_turn=iteration,
                    compress_after=Config.CONTEXT_AGENT_COMPRESS_AFTER,
                    summary_chars=Config.CONTEXT_TOOL_RESULT_SUMMARY_CHARS,
                )

                # Re-évaluer la fenêtre glissante avec les tokens réels du tour précédent
                if iteration > 0 and usage.prompt > 0:
                    re_trimmed = _trim_history(
                        msgs,
                        max_chars=Config.CONTEXT_HISTORY_MAX_CHARS,
                        max_tokens=Config.CONTEXT_HISTORY_MAX_TOKENS,
                        known_prompt_tokens=usage.prompt,
                    )
                    if len(re_trimmed) < len(msgs):
                        msgs = re_trimmed

            # Étape 1: détection tool_calls
            # Retirer les marqueurs internes (_is_consolidation, _pinned) avant l'envoi
            api_msgs = memory.strip_internal_markers(msgs)
            kw = dict(
                model=model or Config.active_model(),
                messages=api_msgs,
                temperature=0.7,
                stream=False,
                max_tokens=Config.MAX_CONTEXT_TOKENS,
            )
            if tools:
                kw["tools"] = tools
                kw["tool_choice"] = "auto"

            resp = client.chat.completions.create(**kw)
            # Capturer l'usage tokens dès que disponible
            if hasattr(resp, "usage") and resp.usage:
                usage.add(resp.usage)
                if on_usage:
                    on_usage(usage)

            choice = resp.choices[0]
            msg = choice.message
            finish_reason = choice.finish_reason  # "stop", "tool_calls", "length", None

            # Étape 2: exécution des outils
            # On entre dans ce bloc seulement si le modèle a réellement demandé des outils
            # ET que finish_reason n'est pas "stop" (certains backends incohérents).
            if msg.tool_calls and finish_reason != "stop":
                # content=None (pas "") : certains backends (Albert, vLLM)
                # rejettent explicitement content='' avec tool_calls présents.
                assistant_msg = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                if msg.content:  # n'ajouter content que s'il est non vide
                    assistant_msg["content"] = msg.content
                msgs.append(assistant_msg)

                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}

                    if on_tool_call:
                        on_tool_call(name, tc.function.arguments)

                    result = tools_engine.call_tool(name, args)

                    # ── Extraction et diffusion des images générées ───────────
                    # Si l'outil retourne un JSON avec "image_path", on lit le
                    # fichier image, on l'encode en base64, et on :
                    #   1. Notifie l'UI via on_image pour affichage immédiat.
                    #   2. Remplace image_path par image_data (base64) dans le
                    #      tool_result envoyé au LLM (format vision multimodal).
                    #   3. Supprime image_path du JSON pour éviter que la
                    #      compression/troncature ne détruise la donnée utile.
                    image_b64: str | None = None
                    image_mime: str = "image/png"
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, dict) and "image_path" in parsed:
                            img_path = Path(parsed["image_path"])
                            if img_path.exists() and img_path.stat().st_size > 0:
                                suffix = img_path.suffix.lower()
                                _mime_map = {
                                    ".png": "image/png", ".jpg": "image/jpeg",
                                    ".jpeg": "image/jpeg", ".gif": "image/gif",
                                    ".webp": "image/webp",
                                }
                                image_mime = _mime_map.get(suffix, "image/png")
                                image_b64 = base64.b64encode(
                                    img_path.read_bytes()
                                ).decode("ascii")
                                # Retirer image_path du résultat JSON pour le LLM
                                # (le LLM reçoit le texte + l'image séparément)
                                parsed.pop("image_path")
                                parsed["image_generated"] = True
                                result = json.dumps(parsed, ensure_ascii=False, indent=2)
                    except (json.JSONDecodeError, OSError, TypeError):
                        pass  # résultat non-JSON ou erreur I/O → on passe

                    if not disable_context_management:
                        result = _truncate_tool_result(result)  # évite le dépassement de contexte

                    # Notifier l'UI de l'image AVANT on_tool_result
                    if image_b64 and on_image:
                        on_image(image_mime, image_b64)

                    if on_tool_result:
                        on_tool_result(name, result)

                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

                    # Enregistrer dans la mémoire de session pour le pinning.
                    # assistant_text est vide ici (la réponse finale arrive après) ;
                    # le pinning sera réévalué au tour suivant si nécessaire.
                    memory.record_tool_result(
                        tool_name=name,
                        result=result,
                        assistant_text=msg.content or "",
                        turn=iteration,
                    )

            # Étape 3: réponse finale
            else:
                # Cas A : le modèle a déjà fourni du contenu texte dans cette réponse
                # (finish_reason="stop" avec ou sans tool_calls, ou réponse directe)
                if msg.content:
                    final_text = msg.content
                    if on_token:
                        on_token(final_text)
                    return final_text

                # Cas B : pas de contenu texte → on relance en streaming pour obtenir
                # la synthèse finale (comportement original)
                stream_resp = client.chat.completions.create(
                    model=model or Config.active_model(),
                    messages=memory.strip_internal_markers(msgs),
                    temperature=0.7,
                    stream=True,
                    max_tokens=Config.MAX_CONTEXT_TOKENS,
                    stream_options={"include_usage": True},
                )

                for chunk in stream_resp:
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage.add(chunk.usage, streaming=True)
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        final_text += delta.content
                        if on_token:
                            on_token(delta.content)

                usage.log("agent_loop/final_stream")
                if on_usage:
                    on_usage(usage)
                return final_text

        # Max itérations atteint : on force une synthèse plutôt que le message d'erreur
        if not final_text:
            try:
                msgs.append({
                    "role": "user",
                    "content": "Résume les résultats obtenus et réponds à la question initiale.",
                })
                stream_resp = client.chat.completions.create(
                    model=model or Config.active_model(),
                    messages=memory.strip_internal_markers(msgs),
                    temperature=0.7,
                    stream=True,
                    max_tokens=Config.MAX_CONTEXT_TOKENS,
                    stream_options={"include_usage": True},
                )
                for chunk in stream_resp:
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage.add(chunk.usage, streaming=True)
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        final_text += delta.content
                        if on_token:
                            on_token(delta.content)
            except Exception:
                pass

        usage.log("agent_loop/max_iter")
        if on_usage:
            on_usage(usage)
        return final_text or "(Aucune réponse générée après exécution des outils)"

    except Exception as e:
        if on_error:
            on_error(str(e))
        raise


def list_local_models() -> list[str]:
    """Liste les modèles Ollama disponibles."""
    try:
        import ollama
        return [m["name"] for m in ollama.list().get("models", [])]
    except Exception:
        return [Config.OLLAMA_MODEL]


def list_remote_models() -> list[str]:
    """Liste les modèles OpenAI disponibles."""
    try:
        client = build_client(local=False)
        return sorted([m.id for m in client.models.list().data])
    except Exception:
        return [Config.OPENAI_MODEL]
