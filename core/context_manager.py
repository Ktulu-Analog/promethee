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
context_manager.py — Gestion de la taille du contexte LLM.

Responsabilité unique
─────────────────────
Ce module contient toutes les fonctions qui réduisent mécaniquement la
taille du contexte envoyé au LLM. Aucune logique d'appel LLM ici — les
opérations sont purement textuelles et testables sans client.

Trois niveaux d'intervention
─────────────────────────────
Les trois fonctions s'appliquent dans cet ordre, à des moments différents
de la boucle agent :

  1. truncate_tool_result(result)
     ┌─ Quand  : à la réception de chaque résultat d'outil, avant de
     │           l'ajouter aux messages.
     └─ Quoi   : troncature symétrique d'un résultat trop long.
                 Exception : code source et exports bureautiques → jamais
                 tronqués (risque de corruption sémantique).

  2. compress_agent_msgs(msgs, current_turn, …)
     ┌─ Quand  : au début de chaque itération de la boucle agent.
     └─ Quoi   : condense les tool_results des tours anciens
                 (< current_turn - compress_after) en un résumé court.
                 Respecte le marquage _pinned posé par SessionMemory.

  3. trim_history(messages, …)
     ┌─ Quand  : avant le premier appel LLM et entre chaque itération
     │           (avec les tokens réels connus).
     └─ Quoi   : fenêtre glissante — retire les paires de messages
                 anciennes pour rester sous le plafond de tokens/chars.
                 Préserve toujours le premier message utilisateur.

Règles de non-troncature pour les résultats d'outils
─────────────────────────────────────────────────────
Deux catégories sont systématiquement préservées intégralement :

  a) Code source (SessionMemory._is_code)
     Tronquer du code produit du code invalide ou trompeur — risque
     sémantique inacceptable. Le pinning de SessionMemory protège en
     outre ces résultats contre la compression in-loop.

  b) Exports bureautiques (_is_office_result)
     Les outils d'export retournent un JSON {"path": "...", "status": "ok"}.
     Tronquer ce JSON corrompt le chemin ou les métadonnées transmises
     au LLM, ce qui casse le fil de conversation.
"""

import json
import logging
from pathlib import Path

from .config import Config
from .llm_events import emit_context_event, emit_compression_stats
from .llm_logging import get_token_logger
from .session_memory import SessionMemory

_log = logging.getLogger(__name__)
_token_log = get_token_logger()


# ── Extensions bureautiques protégées ─────────────────────────────────────────

_OFFICE_EXTENSIONS: frozenset[str] = frozenset({
    ".docx", ".doc", ".odt",           # Traitement de texte
    ".xlsx", ".xls", ".ods", ".csv",   # Tableur
    ".pptx", ".ppt", ".odp",           # Présentation
    ".pdf",                            # PDF
})


# ── Détection des résultats protégés ─────────────────────────────────────────


def _is_office_result(result: str) -> bool:
    """
    Retourne True si le résultat JSON contient un champ 'path' pointant
    vers un fichier bureautique (export Word, Excel, PowerPoint, PDF…).

    Ces résultats sont compacts par nature (métadonnées uniquement), mais
    leur troncature casserait le chemin ou les champs structurels transmis
    au LLM.

    Parameters
    ----------
    result : str
        Résultat brut retourné par l'outil (supposé être du JSON).

    Returns
    -------
    bool
        True si le résultat décrit un export bureautique.
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


# ── Estimation de taille ──────────────────────────────────────────────────────


def estimate_chars(msgs: list[dict]) -> int:
    """
    Estime la taille totale d'une liste de messages en caractères.

    Prend en compte les contenus textuels, les contenus multi-part (images)
    et les arguments des tool_calls côté assistant.

    Parameters
    ----------
    msgs : list[dict]
        Liste de messages au format OpenAI.

    Returns
    -------
    int
        Estimation de la taille totale en caractères.
    """
    total = 0
    for m in msgs:
        c = m.get("content") or ""
        if isinstance(c, list):           # contenu multi-part (texte + image)
            total += sum(len(str(p)) for p in c)
        else:
            total += len(c)
        for tc in m.get("tool_calls", []) or []:
            total += len(tc.get("function", {}).get("arguments", ""))
    return total


# ── Niveau 1 : troncature d'un résultat d'outil ───────────────────────────────


def truncate_tool_result(
    result: str,
    max_chars: int = Config.TOOL_RESULT_MAX_CHARS,
) -> str:
    """
    Tronque un résultat d'outil trop long pour éviter de dépasser le contexte.

    Deux catégories de résultats ne sont **jamais** tronquées :

    1. **Code source** (``SessionMemory._is_code → True``)
       Tronquer du code produit du code syntaxiquement invalide ou
       sémantiquement trompeur. Le pinning de SessionMemory protège en
       outre ces résultats contre la compression in-loop.

    2. **Exports bureautiques** (``_is_office_result → True``)
       Les outils d'export retournent un JSON ``{"path": "…", "status": "ok"}``.
       Tronquer ce JSON corrompt le chemin ou les métadonnées transmises au LLM.

    Pour tous les autres résultats dépassant ``max_chars``, une **troncature
    symétrique** est appliquée : début + fin, avec un indicateur central.

    Parameters
    ----------
    result : str
        Résultat brut retourné par l'outil.
    max_chars : int
        Limite de taille en caractères. Défaut : Config.TOOL_RESULT_MAX_CHARS.

    Returns
    -------
    str
        Résultat inchangé si code, export bureautique, ou taille dans la
        limite ; sinon version tronquée symétriquement.
    """
    if len(result) <= max_chars:
        return result

    # ── Code source : jamais tronqué ─────────────────────────────────────────
    if SessionMemory._is_code(result):
        _token_log.info(
            "[truncate_tool_result] code détecté (%d cars.) — troncature ignorée.",
            len(result),
        )
        emit_context_event(
            f"Code volumineux ({len(result):,} car.) — conservé intégralement"
        )
        return result

    # ── Export bureautique : jamais tronqué ──────────────────────────────────
    if _is_office_result(result):
        _token_log.info(
            "[truncate_tool_result] export bureautique (%d cars.) — troncature ignorée.",
            len(result),
        )
        emit_context_event(
            f"Export bureautique ({len(result):,} car.) — conservé intégralement"
        )
        return result

    # ── Troncature symétrique générique ──────────────────────────────────────
    half      = max_chars // 2
    truncated = (
        result[:half]
        + f"\n\n[… résultat tronqué : {len(result):,} caractères → {max_chars:,} …]\n\n"
        + result[-half:]
    )
    saved = len(result) - len(truncated)
    pct   = int(saved / len(result) * 100) if len(result) > 0 else 0
    _token_log.info(
        "[truncate_tool_result] texte — symétrique : %d → %d cars.",
        len(result), len(truncated),
    )
    emit_context_event(
        f"Troncature résultat : {len(result):,} → {len(truncated):,} car. (-{pct}%)"
    )
    emit_compression_stats("truncate_text", len(result), len(truncated))
    return truncated


# ── Niveau 2 : compression in-loop des tool_results anciens ──────────────────


def compress_agent_msgs(
    msgs: list[dict],
    current_turn: int,
    compress_after: int,
    summary_chars: int,
) -> list[dict]:
    """
    Condense les tool_results des tours anciens dans la boucle agent.

    Stratégie
    ─────────
    Les tool_results des tours strictement antérieurs à
    ``current_turn - compress_after`` sont remplacés par une version
    condensée (début + indicateur de troncature).

    Les tool_results du tour courant et des ``compress_after`` derniers
    tours restent intacts. Les messages non-outil ne sont jamais touchés.

    Correspondance tour ↔ messages
    ────────────────────────────────
    Un "tour" correspond à un bloc assistant avec tool_calls suivi de ses
    N messages role=tool. Si un seul assistant génère N appels en parallèle,
    tous les N messages role=tool partagent le même numéro de tour.

    L'algorithme utilise deux passes :
      1. Associer chaque tool_call_id au numéro de tour de l'assistant parent.
      2. Attribuer à chaque message role=tool le turn_idx de son assistant.

    Protection par pinning
    ──────────────────────
    Les messages portant le champ ``_pinned=True`` (posé par
    ``SessionMemory.apply_pinned_protection``) sont exclus de la compression,
    quelle que soit leur ancienneté.

    Parameters
    ----------
    msgs : list[dict]
        Liste complète des messages de la boucle agent.
    current_turn : int
        Numéro du tour actuel (0-based).
    compress_after : int
        Nombre de tours à conserver intacts. 0 = désactivé.
    summary_chars : int
        Longueur maximale d'un tool_result condensé (en caractères).

    Returns
    -------
    list[dict]
        Messages avec les tool_results anciens éventuellement condensés.
    """
    if compress_after <= 0 or current_turn <= compress_after:
        return msgs

    # ── Passe 1 : mapper chaque tool_call_id → numéro de tour ────────────────
    tc_to_turn: dict[str, int] = {}
    t = 0
    for m in msgs:
        if m["role"] == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tc_to_turn[tc["id"]] = t
            t += 1

    # ── Passe 2 : construire turn_map (un entier par message) ─────────────────
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

    # ── Compression sélective ─────────────────────────────────────────────────
    result = []
    for m, t_idx in zip(msgs, turn_map):
        if (
            m["role"] == "tool"
            and t_idx < current_turn - compress_after
            and len(m.get("content", "")) > summary_chars
            and not m.get("_pinned", False)
        ):
            original  = m["content"]
            condensed = original[:summary_chars].rstrip() + f"… [condensé, {len(original)} car.]"
            saved     = len(original) - len(condensed)
            pct       = int(saved / len(original) * 100) if len(original) > 0 else 0
            result.append({**m, "content": condensed})
            _token_log.info(
                "[compress_agent] tool_result tour %d condensé : %d → %d car.",
                t_idx, len(original), len(condensed),
            )
            emit_context_event(
                f"Compression outil (tour {t_idx}) : "
                f"{len(original):,} → {len(condensed):,} car. (-{pct}%)"
            )
            emit_compression_stats("compress_tool", len(original), len(condensed))
        else:
            result.append(m)

    return result


# ── Niveau 3 : fenêtre glissante sur l'historique ────────────────────────────


def trim_history(
    messages: list[dict],
    max_chars: int,
    max_tokens: int = 0,
    known_prompt_tokens: int = 0,
) -> list[dict]:
    """
    Fenêtre glissante sur l'historique de conversation.

    Critère actif
    ─────────────
    - Si ``max_tokens > 0`` ET ``known_prompt_tokens > 0`` : utilise les tokens
      réels (disponibles après le premier appel LLM).
    - Sinon : fallback sur l'estimation en caractères (``max_chars``).

    Garanties
    ─────────
    - Le premier message utilisateur est **toujours conservé** (ancrage
      thématique : le LLM ne doit jamais perdre le sujet initial).
    - Les messages sont retirés par **paires** (user + assistant suivant)
      depuis le début pour ne jamais laisser un tour incomplet.
    - Désactivé si les deux limites sont <= 0.

    Parameters
    ----------
    messages : list[dict]
        Liste complète des messages à filtrer.
    max_chars : int
        Limite de taille en caractères (fallback).
    max_tokens : int
        Limite de taille en tokens réels. 0 = désactivé.
    known_prompt_tokens : int
        Tokens prompt du dernier appel LLM connu. 0 = inconnu.

    Returns
    -------
    list[dict]
        Liste réduite ou identique si elle était dans les limites.
    """
    use_tokens = max_tokens > 0 and known_prompt_tokens > 0

    # Vérification rapide : déjà dans les limites ?
    if use_tokens:
        if known_prompt_tokens <= max_tokens:
            return messages
    else:
        if max_chars <= 0 or estimate_chars(messages) <= max_chars:
            return messages

    # Index du premier message utilisateur (ancre à préserver)
    anchor_idx = next(
        (i for i, m in enumerate(messages) if m["role"] == "user"),
        None,
    )

    trimmed = list(messages)
    start   = (anchor_idx + 1) if anchor_idx is not None else 0

    def _over_limit() -> bool:
        if use_tokens:
            # Estimation de la réduction proportionnelle aux caractères retirés
            removed_chars   = estimate_chars(messages) - estimate_chars(trimmed)
            estimated_tokens = known_prompt_tokens - removed_chars // 4
            return estimated_tokens > max_tokens
        return estimate_chars(trimmed) > max_chars

    while _over_limit() and start + 1 < len(trimmed):
        trimmed.pop(start)
        if start < len(trimmed):
            trimmed.pop(start)

    n_dropped = len(messages) - len(trimmed)
    if n_dropped > 0:
        chars_before = estimate_chars(messages)
        chars_after  = estimate_chars(trimmed)
        saved        = chars_before - chars_after
        pct          = int(saved / chars_before * 100) if chars_before > 0 else 0
        _token_log.info(
            "[trim_history] %d message(s) retirés — historique réduit de %d → %d msgs",
            n_dropped, len(messages), len(trimmed),
        )
        emit_context_event(
            f"Trim : {n_dropped} msg écarté(s) — "
            f"{chars_before:,} → {chars_after:,} car. (-{pct}%)"
        )
        emit_compression_stats("trim_msgs", chars_before, chars_after)

    return trimmed
