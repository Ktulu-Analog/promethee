# ============================================================================
# ============================================================================
# Prométhée — Assistant IA avancé
# ============================================================================
# Auteur  : Pierre COUGET ktulu.analog@gmail.com
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
llm_service.py — Service LLM : point d'entrée public.

Responsabilité
──────────────
Ce module orchestre les appels au LLM. Il expose **deux fonctions** :

  stream_chat()   Chat simple sans outils, avec streaming vers l'UI.
  agent_loop()    Boucle agent complète : tool-use, gestion de contexte,
                  routing de modèle par famille, mémoire de session.

Tout le reste est délégué à des sous-modules dédiés :

  llm_events.py      Bus de callbacks vers l'UI (set_*/emit_*).
  llm_logging.py     Logs rotatifs + TokenUsage.
  llm_clients.py     Fabrique de clients OpenAI/Ollama.
  context_manager.py Trim, compression, troncature du contexte.
  session_memory.py  Consolidation périodique + pinning des tool_results.

Re-exports de compatibilité
────────────────────────────
Pour que le code existant (workers.py, tool_creator_tools.py, rag_engine.py)
continue de fonctionner sans modification, toutes les symboles qui étaient
précédemment définis ici sont ré-exportés depuis leurs nouveaux modules.

  from core.llm_service import set_context_event_callback  → fonctionne
  from core.llm_service import build_family_client          → fonctionne
  from core.llm_service import TokenUsage                  → fonctionne

Flux de agent_loop
──────────────────
Pour chaque message utilisateur :

  1. Enrichissement du contexte (RAG, LTM) — géré en amont par ChatPanel.
  2. Fenêtre glissante initiale sur l'historique (trim_history).
  3. Boucle sur max_iterations :
       a. Réévaluation du pinning (flush_pending).
       b. Consolidation de session si seuil atteint (maybe_consolidate).
       c. Application de la protection pinning (apply_pinned_protection).
       d. Compression in-loop des tours anciens (compress_agent_msgs).
       e. Ré-évaluation fenêtre glissante avec tokens réels.
       f. Appel LLM (modèle principal, décision).
       g. Si tool_calls → exécution des outils, retour en a.
       h. Si réponse texte → streaming vers l'UI, retour.
  4. Si max_iterations atteint → synthèse forcée.

Paramètre disable_context_management
──────────────────────────────────────
Si True, désactive intégralement les étapes a–e. Utile pour le débogage
ou les sessions nécessitant une fidélité totale au contexte brut.
Attention : sur de longues sessions, le contexte peut dépasser la fenêtre
du modèle et provoquer une erreur API.
"""

import base64
import json
import logging
from pathlib import Path
from typing import Callable

from .config import Config
from . import tools_engine

# ── Sous-modules ──────────────────────────────────────────────────────────────
from .llm_events import (
    emit_context_event,  # noqa: F401 — utilisé indirectement via context_manager
    emit_family_routing,
    emit_memory_event,
    emit_model_usage,
    is_cancelled,
)
from .llm_logging import TokenUsage
from .llm_clients import build_client, build_family_client
from .context_manager import trim_history, compress_agent_msgs, truncate_tool_result
from .session_memory import SessionMemory

_log = logging.getLogger(__name__)


# ── Re-exports de compatibilité ascendante ────────────────────────────────────
#
# Ces re-exports permettent au code existant de continuer à importer depuis
# core.llm_service sans modification, même si les symboles ont migré.

# Callbacks (workers.py les importe via llm_service.set_*_callback)
from .llm_events import (
    set_context_event_callback,
    set_compression_stats_callback,
    set_memory_event_callback,
    set_family_routing_callback,
    set_model_usage_callback,
)

# Clients (tool_creator_tools.py et rag_engine.py importent build_family_client)
from .llm_clients import (
    build_specialist_client,
    list_remote_models,
)


# ── stream_chat ───────────────────────────────────────────────────────────────


# ── Helper interne : consommation d'un stream LLM ────────────────────────────


def _stream_response(
    stream_resp,
    usage: "TokenUsage",
    on_token: Callable[[str], None] | None,
    on_usage: Callable[["TokenUsage"], None] | None,
    *,
    log_context: str = "",
    emit_usage_as: str | None = None,
    model_name: str = "",
) -> tuple[str, int, int]:
    """
    Consomme un stream LLM, accumule les tokens et diffuse vers l'UI.

    Factorise la boucle de streaming commune à stream_chat, au cas B de
    agent_loop (réponse finale) et à la synthèse forcée (max_iterations).

    Parameters
    ----------
    stream_resp
        Itérateur de chunks retourné par client.chat.completions.create(stream=True).
    usage : TokenUsage
        Objet de cumul de tokens de la session courante — modifié en place.
    on_token : Callable | None
        Callback appelé pour chaque token de texte (streaming vers l'UI).
    on_usage : Callable | None
        Callback appelé une fois en fin de stream avec le TokenUsage mis à jour.
    log_context : str
        Étiquette passée à usage.log() en fin de stream. Vide = pas de log.
    emit_usage_as : str | None
        Si fourni ("stream", "final"…), appelle emit_model_usage() en fin de
        stream avec ce rôle. Ignoré si model_name est vide.
    model_name : str
        Nom du modèle utilisé, transmis à emit_model_usage(). Ignoré si
        emit_usage_as est None.

    Returns
    -------
    tuple[str, int, int]
        (texte_complet, prompt_tokens_du_chunk_final, completion_tokens_du_chunk_final)
        Les deux derniers entiers sont utiles pour émettre les métriques
        par modèle (emit_model_usage) après l'appel.
    """
    text               = ""
    _stream_prompt     = 0
    _stream_completion = 0

    for chunk in stream_resp:
        # Vérifier l'annulation à chaque chunk pour interrompre le stream réseau
        # dès que l'utilisateur clique Stop, sans attendre la fin de la réponse.
        if is_cancelled():
            try:
                stream_resp.close()
            except Exception:
                pass
            break
        if hasattr(chunk, "usage") and chunk.usage:
            usage.add(chunk.usage, streaming=True)
            _stream_prompt     = getattr(chunk.usage, "prompt_tokens",     0) or 0
            _stream_completion = getattr(chunk.usage, "completion_tokens", 0) or 0
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            text += delta.content
            if on_token:
                on_token(delta.content)

    if log_context:
        usage.log(log_context)
    if on_usage:
        on_usage(usage)
    if emit_usage_as and model_name:
        emit_model_usage(model_name, _stream_prompt, _stream_completion, emit_usage_as)

    return text, _stream_prompt, _stream_completion


def stream_chat(
    messages: list[dict],
    system_prompt: str = "",
    model: str | None = None,
    on_token: Callable[[str], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_usage: Callable[["TokenUsage"], None] | None = None,
) -> str:
    """
    Chat en streaming sans outils.

    Mode de fonctionnement simplifié : un seul appel LLM en streaming,
    pas de boucle agent, pas de tool-use. Adapté aux requêtes directes
    qui n'ont pas besoin d'outils (reformulation, résumé simple…).

    Supporte les messages multi-part (texte + images base64).

    Parameters
    ----------
    messages : list[dict]
        Historique de la conversation au format OpenAI.
    system_prompt : str
        Prompt système injecté en tête (optionnel).
    model : str | None
        Modèle à utiliser. None → Config.active_model().
    on_token : Callable[[str], None] | None
        Callback appelé à chaque token reçu (streaming vers l'UI).
    on_error : Callable[[str], None] | None
        Callback appelé en cas d'exception avant de la relancer.
    on_usage : Callable[[TokenUsage], None] | None
        Callback appelé en fin de génération avec le bilan de tokens.

    Returns
    -------
    str
        Texte complet généré.

    Raises
    ------
    Exception
        Toute exception de l'API LLM est relancée après appel à on_error.
    """
    try:
        client = build_client()
        msgs: list[dict] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)

        usage        = TokenUsage()
        active_model = model or Config.active_model()

        resp = client.chat.completions.create(
            model=active_model,
            messages=msgs,
            stream=True,
            temperature=0.7,
            stream_options={"include_usage": True},
        )

        full_text, _, _ = _stream_response(
            resp, usage, on_token, on_usage, log_context="stream_chat"
        )
        return full_text

    except Exception as e:
        if on_error:
            on_error(str(e))
        raise


# ── agent_loop ────────────────────────────────────────────────────────────────


def agent_loop(
    messages: list[dict],
    system_prompt: str = "",
    model: str | None = None,
    use_tools: bool = True,
    max_iterations: int | None = None,
    disable_context_management: bool = False,
    on_tool_call: Callable[[str, str], None] | None = None,
    on_tool_result: Callable[[str, str], None] | None = None,
    on_image: Callable[[str, str], None] | None = None,
    on_token: Callable[[str], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_usage: Callable[["TokenUsage"], None] | None = None,
) -> str:
    """
    Boucle agent avec tool-use, gestion de contexte et routing de modèle.

    Supporte les messages multi-part (texte + images base64).

    Parameters
    ----------
    messages : list[dict]
        Historique de la conversation au format OpenAI.
    system_prompt : str
        Prompt système injecté en tête (optionnel).
    model : str | None
        Modèle principal. None → Config.active_model().
    use_tools : bool
        Si False, aucun outil n'est proposé au LLM (mode sans agent).
    max_iterations : int | None
        Limite de la boucle agent. None → Config.AGENT_MAX_ITERATIONS.
    disable_context_management : bool
        Si True, désactive trim, compression, troncature et consolidation.
        Utile pour le débogage. Voir module docstring pour les risques.
    on_tool_call : Callable[[str, str], None] | None
        Appelé avant l'exécution de chaque outil : (nom, arguments_json).
    on_tool_result : Callable[[str, str], None] | None
        Appelé après l'exécution de chaque outil : (nom, résultat).
    on_image : Callable[[str, str], None] | None
        Appelé quand un outil génère une image : (mime_type, base64_data).
    on_token : Callable[[str], None] | None
        Appelé pour chaque token de la réponse finale (streaming UI).
    on_error : Callable[[str], None] | None
        Appelé en cas d'exception avant de la relancer.
    on_usage : Callable[[TokenUsage], None] | None
        Appelé à chaque mise à jour du bilan de tokens.

    Returns
    -------
    str
        Réponse finale complète de l'agent.

    Raises
    ------
    Exception
        Toute exception de l'API LLM est relancée après appel à on_error.
    """
    try:
        client         = build_client()
        max_iterations = max_iterations if max_iterations is not None else Config.AGENT_MAX_ITERATIONS
        active_model   = model or Config.active_model()

        msgs: list[dict] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})

        usage = TokenUsage()

        memory = SessionMemory(
            client=client,
            model=active_model,
            consolidation_every=Config.CONTEXT_CONSOLIDATION_EVERY,
            consolidation_max_chars=Config.CONTEXT_CONSOLIDATION_MAX_CHARS,
            pinning_enabled=Config.CONTEXT_PINNING_ENABLED,
            pressure_threshold=Config.CONTEXT_CONSOLIDATION_PRESSURE_THRESHOLD,
            model_max_tokens=Config.CONTEXT_MODEL_MAX_TOKENS,
        )

        # Client/modèle pour la réponse finale — mis à jour après chaque tour
        # avec tool_calls. Le modèle principal reste utilisé pour la décision.
        _final_client = client
        _final_model  = active_model

        # ── Fenêtre glissante initiale ────────────────────────────────────────
        if disable_context_management:
            msgs.extend(list(messages))
        else:
            trimmed = trim_history(
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

        tools      = tools_engine.get_tool_schemas() if use_tools else None
        final_text = ""

        # ── Boucle agent ──────────────────────────────────────────────────────
        for iteration in range(max_iterations):

            # ── Préparation du contexte (désactivable) ────────────────────────
            if not disable_context_management:
                memory.flush_pending(msgs)
                msgs = memory.maybe_consolidate(
                    msgs, iteration, on_event=emit_memory_event, usage=usage
                )
                msgs = memory.apply_pinned_protection(msgs)
                msgs = compress_agent_msgs(
                    msgs,
                    current_turn=iteration,
                    compress_after=Config.CONTEXT_AGENT_COMPRESS_AFTER,
                    summary_chars=Config.CONTEXT_TOOL_RESULT_SUMMARY_CHARS,
                )
                if iteration > 0 and usage.prompt > 0:
                    re_trimmed = trim_history(
                        msgs,
                        max_chars=Config.CONTEXT_HISTORY_MAX_CHARS,
                        max_tokens=Config.CONTEXT_HISTORY_MAX_TOKENS,
                        known_prompt_tokens=usage.prompt,
                    )
                    if len(re_trimmed) < len(msgs):
                        msgs = re_trimmed

            # ── Garde-fou anti-boucle : signal d'arrêt avant-dernière itération ──
            # Si le LLM n'a pas encore produit de texte et approche la limite,
            # on lui injecte un avertissement explicite pour qu'il synthétise
            # au lieu de continuer à appeler des outils indéfiniment.
            #
            # IMPORTANT — contraintes Albert/vLLM sur l'ordre des rôles :
            #   • role=system  interdit après role=tool  → HTTP 400
            #   • role=user    interdit après role=tool  → HTTP 400
            #   • role=assistant interdit en dernier     → HTTP 400
            # Solution : si le dernier message est un tool, on intercale un
            # assistant vide pour "fermer" le bloc, puis on injecte le signal
            # en user. La séquence tool → assistant → user est universellement
            # acceptée par Albert/vLLM.
            if iteration == max_iterations - 2 and not final_text:
                if msgs and msgs[-1].get("role") == "tool":
                    msgs.append({"role": "assistant", "content": ""})
                msgs.append({
                    "role": "user",
                    "content": (
                        "[Garde-fou] L'agent a effectué de nombreux appels d'outils sans "
                        "produire de réponse. À partir de maintenant, NE PAS appeler d'autres "
                        "outils. Rédiger immédiatement la réponse finale en texte en synthétisant "
                        "les résultats déjà obtenus."
                    ),
                })

            # ── Appel LLM (décision) ──────────────────────────────────────────
            api_msgs = memory.strip_internal_markers(msgs)

            if not tools:
                # Sans outils : streaming direct token par token vers l'UI.
                stream_resp = client.chat.completions.create(
                    model=active_model,
                    messages=api_msgs,
                    temperature=0.7,
                    stream=True,
                    max_tokens=Config.MAX_CONTEXT_TOKENS,
                    stream_options={"include_usage": True},
                )
                final_text, _, _ = _stream_response(
                    stream_resp, usage, on_token, on_usage,
                    log_context="agent_loop/direct_stream",
                    emit_usage_as="final",
                    model_name=active_model,
                )
                return final_text

            # Avec outils : stream=False obligatoire pour détecter les tool_calls
            # avant d'accumuler les tokens (l'API stream ne permet pas de rollback).
            #
            # CORRECTION BUG 2 — Politique tool_choice par itération :
            #
            #   iteration == 0            → "required"
            #     Force le LLM à appeler au moins un outil sur le premier tour.
            #     Évite la hallucination "j'enregistre le fichier" sans appel réel.
            #
            #   0 < iteration < max-1     → "auto"
            #     Après le premier outil, le LLM choisit librement : chaîner
            #     d'autres appels ou synthétiser. Comportement agent normal.
            #
            #   iteration == max-1        → "none"
            #     Garde-fou : bloque tout nouvel appel et force la réponse finale.
            #
            # Note : "required" est supporté par OpenAI et les backends vLLM/Albert
            # compatibles. Si le backend renvoie une erreur 400, passer
            # disable_context_management=True pour forcer "auto" partout.
            if iteration == max_iterations - 1:
                _tool_choice = "none"
            elif iteration == 0:
                _tool_choice = "required"
            else:
                _tool_choice = "auto"

            kw: dict = dict(
                model=active_model,
                messages=api_msgs,
                temperature=0.7,
                stream=False,
                max_tokens=Config.MAX_CONTEXT_TOKENS,
                tools=tools,
                tool_choice=_tool_choice,
            )

            resp          = client.chat.completions.create(**kw)

            # Certains backends (Albert/vLLM) renvoient HTTP 200 mais avec
            # choices=null ou choices=[] quand ils sont surchargés ou qu'une
            # erreur interne silencieuse s'est produite côté serveur.
            # On lève une exception explicite plutôt que de laisser crasher
            # sur TypeError: 'NoneType' object is not subscriptable.
            if not resp.choices:
                raise RuntimeError(
                    f"[agent_loop] Le backend a renvoyé une réponse vide "
                    f"(choices={resp.choices!r}) à l'itération {iteration}. "
                    f"Modèle: {active_model}. "
                    f"Vérifiez la charge du serveur Albert ou la validité de la requête."
                )

            choice        = resp.choices[0]
            msg           = choice.message
            finish_reason = choice.finish_reason  # "stop", "tool_calls", "length", None

            if hasattr(resp, "usage") and resp.usage:
                usage.add(resp.usage)
                if on_usage:
                    on_usage(usage)
                emit_model_usage(
                    model=active_model,
                    prompt=getattr(resp.usage, "prompt_tokens", 0) or 0,
                    completion=getattr(resp.usage, "completion_tokens", 0) or 0,
                    role="decision",
                )

            # ── Exécution des outils ──────────────────────────────────────────
            # On entre dans ce bloc seulement si le modèle a réellement demandé
            # des outils ET que finish_reason n'est pas "stop" (certains backends
            # incohérents retournent tool_calls avec finish_reason="stop").
            if msg.tool_calls and finish_reason != "stop":
                # content=None (pas "") : certains backends (Albert, vLLM)
                # rejettent explicitement content='' avec tool_calls présents.
                assistant_msg: dict = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name":      tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                if msg.content:
                    assistant_msg["content"] = msg.content
                msgs.append(assistant_msg)

                _called_this_turn: list[str] = []

                for tc in msg.tool_calls:
                    name = tc.function.name
                    _called_this_turn.append(name)
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}

                    if on_tool_call:
                        on_tool_call(name, tc.function.arguments)

                    result = tools_engine.call_tool(name, args)

                    # ── Extraction d'images générées ──────────────────────────
                    # Si l'outil retourne {"image_path": "..."}, on lit l'image,
                    # on la diffuse en base64 via on_image et on la retire du JSON
                    # pour ne pas exposer un chemin local au LLM.
                    image_b64:  str | None = None
                    image_mime: str        = "image/png"
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, dict) and "image_path" in parsed:
                            img_path = Path(parsed["image_path"])
                            if img_path.exists() and img_path.stat().st_size > 0:
                                _mime_map = {
                                    ".png":  "image/png",
                                    ".jpg":  "image/jpeg",
                                    ".jpeg": "image/jpeg",
                                    ".gif":  "image/gif",
                                    ".webp": "image/webp",
                                }
                                image_mime = _mime_map.get(
                                    img_path.suffix.lower(), "image/png"
                                )
                                image_b64 = base64.b64encode(
                                    img_path.read_bytes()
                                ).decode("ascii")
                                parsed.pop("image_path")
                                parsed["image_generated"] = True
                                parsed["image_display_note"] = (
                                    "L'image a été transmise automatiquement à l'interface "
                                    "et s'affiche dans la bulle de réponse. "
                                    "NE PAS reproduire la data-URI base64 dans le texte — "
                                    "elle est déjà affichée et serait corrompue si réécrite."
                                )
                                result = json.dumps(parsed, ensure_ascii=False, indent=2)
                    except (json.JSONDecodeError, OSError, TypeError):
                        pass

                    if not disable_context_management:
                        result = truncate_tool_result(result)

                    if image_b64 and on_image:
                        on_image(image_mime, image_b64)

                    if on_tool_result:
                        on_tool_result(name, result)

                    msgs.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      result,
                    })

                    # Enregistrement pour le pinning. assistant_text est vide ici
                    # (la réponse finale arrive après) ; le pinning sera réévalué
                    # au tour suivant via flush_pending().
                    memory.record_tool_result(
                        tool_name=name,
                        result=result,
                        assistant_text=msg.content or "",
                        turn=iteration,
                    )

                # Résoudre client/modèle pour la réponse finale de ce tour
                _final_client, _final_model = _resolve_final_client(
                    _called_this_turn, client, model
                )

            # ── Réponse finale (après tool_calls) ────────────────────────────
            # Le modèle a terminé ses appels d'outils et doit maintenant
            # synthétiser une réponse. On stream pour un affichage progressif.
            else:
                # Vérifier l'annulation AVANT d'ouvrir le stream : si le client
                # WebSocket s'est déconnecté pendant l'exécution des outils,
                # is_cancelled() est déjà True. Ouvrir le stream quand même
                # provoquerait un GeneratorExit immédiat par GC côté Albert.
                if is_cancelled():
                    return final_text or ""
                _final_msgs = memory.strip_internal_markers(msgs)
                # Si le LLM de synthèse est différent du LLM principal,
                # certains backends (vLLM/Albert) rejettent role=system quand
                # l'historique se termine par role=tool → HTTP 400.
                # On réécrit le contexte pour éliminer ce cas.
                if _final_client is not client:
                    _final_msgs = _sanitize_msgs_for_secondary_backend(_final_msgs)
                stream_resp = _final_client.chat.completions.create(
                    model=_final_model,
                    messages=_final_msgs,
                    temperature=0.7,
                    stream=True,
                    max_tokens=Config.MAX_CONTEXT_TOKENS,
                    stream_options={"include_usage": True},
                )

                final_text, _, _ = _stream_response(
                    stream_resp, usage, on_token, on_usage,
                    log_context="agent_loop/final_stream",
                    emit_usage_as="stream",
                    model_name=_final_model,
                )
                emit_family_routing("", "", active_model, "")
                return final_text

        # ── Max itérations atteint : synthèse forcée ──────────────────────────
        if not final_text:
            # Même garde : ne pas ouvrir un stream si le client est déjà parti.
            if is_cancelled():
                return ""
            try:
                msgs.append({
                    "role":    "user",
                    "content": "Résume les résultats obtenus et réponds à la question initiale.",
                })
                _final_msgs = memory.strip_internal_markers(msgs)
                # Même correction que pour la réponse finale normale :
                # le backend secondaire rejette role=system avant role=tool.
                if _final_client is not client:
                    _final_msgs = _sanitize_msgs_for_secondary_backend(_final_msgs)
                stream_resp = _final_client.chat.completions.create(
                    model=_final_model,
                    messages=_final_msgs,
                    temperature=0.7,
                    stream=True,
                    max_tokens=Config.MAX_CONTEXT_TOKENS,
                    stream_options={"include_usage": True},
                )
                final_text, _, _ = _stream_response(
                    stream_resp, usage, on_token, on_usage,
                    emit_usage_as="stream",
                    model_name=_final_model,
                )
            except Exception as e:
                _log.error(
                    "[agent_loop] Synthèse forcée échouée (max_iterations=%d, modèle=%s) : %s",
                    max_iterations, _final_model, e,
                )
                if on_error:
                    on_error(f"Erreur lors de la synthèse finale : {e}")

        usage.log("agent_loop/max_iter")
        if on_usage:
            on_usage(usage)
        return final_text or "(Aucune réponse générée après exécution des outils)"

    except Exception as e:
        if on_error:
            on_error(str(e))
        raise


# ── Helper privé : nettoyage du contexte pour backend secondaire ─────────────


def _sanitize_msgs_for_secondary_backend(msgs: list[dict]) -> list[dict]:
    """
    Réécrit l'historique pour les backends secondaires (LLM de famille) qui
    rejettent role=system lorsque l'historique se termine par role=tool.

    Certains backends vLLM/Albert appliquent une contrainte stricte sur l'ordre
    des rôles. En particulier, un message role=system présent n'importe où dans
    l'historique est rejeté avec HTTP 400 "Unexpected role 'system' after role
    'tool'" dès lors que le dernier message est un role=tool.

    Stratégie : extraire tous les messages role=system, concaténer leur contenu,
    et le réinjecter comme une paire user/assistant en tête de l'historique.
    Cela préserve le prompt système tout en respectant l'alternance attendue.

    Parameters
    ----------
    msgs : list[dict]
        Historique au format OpenAI, potentiellement terminé par role=tool.

    Returns
    -------
    list[dict]
        Historique sans role=system, avec le contenu système réinjecté en tête
        sous forme de paire user/assistant si nécessaire.
    """
    system_parts: list[str] = []
    non_system: list[dict]  = []

    for m in msgs:
        if m.get("role") == "system":
            content = m.get("content", "")
            if content:
                system_parts.append(content)
        else:
            non_system.append(m)

    if not system_parts:
        return msgs  # Rien à réécrire

    result: list[dict] = [
        {"role": "user",      "content": "\n\n".join(system_parts)},
        {"role": "assistant", "content": "Compris."},
    ]
    result.extend(non_system)
    return result


# ── Helper privé : résolution du modèle de famille ───────────────────────────


def _resolve_final_client(
    called_tool_names: list[str],
    default_client,
    model: str | None,
) -> tuple:
    """
    Résout le client et le modèle pour la réponse finale d'un tour agent.

    Logique de sélection
    ─────────────────────
    - Aucun outil appelé → modèle principal.
    - Une seule famille avec modèle assigné → modèle de la famille.
    - Plusieurs familles avec modèles (conflit) → modèle principal + log.
    - Famille sans modèle assigné → modèle principal.

    Parameters
    ----------
    called_tool_names : list[str]
        Noms des outils appelés pendant ce tour.
    default_client : OpenAI
        Client du modèle principal (fallback).
    model : str | None
        Nom du modèle principal (None → Config.active_model()).

    Returns
    -------
    tuple[OpenAI, str]
        (client résolu, nom du modèle résolu).
    """
    if not called_tool_names:
        return default_client, model or Config.active_model()

    families_seen: set[str] = set()
    for tool_name in called_tool_names:
        fam = tools_engine._TOOL_FAMILY.get(tool_name)
        if fam and tools_engine.get_family_model(fam):
            families_seen.add(fam)

    if len(families_seen) != 1:
        if families_seen:
            _log.debug(
                "[_resolve_final_client] conflit %s → modèle principal",
                sorted(families_seen),
            )
        emit_family_routing("", "", Config.active_model(), "")
        return default_client, model or Config.active_model()

    dominant_family       = next(iter(families_seen))
    fam_client, fam_model = build_family_client(dominant_family)

    assigned    = tools_engine.get_family_model(dominant_family) or {}
    fam_label   = next(
        (f["label"] for f in tools_engine.list_families()
         if f["family"] == dominant_family),
        dominant_family,
    )
    fam_backend = assigned.get("backend", "")
    emit_family_routing(dominant_family, fam_label, fam_model, fam_backend)

    return fam_client, fam_model
