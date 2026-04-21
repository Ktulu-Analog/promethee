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
routers/ws_chat.py — WebSocket de streaming LLM (multi-utilisateurs)

Changements v2 (multi-user)
─────────────────────────────
  - Authentification JWT via query param ?token=<jwt>
  - DB isolée par utilisateur (data/{user_id}/history.db)
  - UserConfig injectée dans le contexte via request_context.set_user_config()
    → propagée automatiquement dans le thread agent_loop via asyncio.to_thread()
  - Suppression du _generation_lock global : chaque session a son propre
    contexte d'exécution. Les utilisateurs peuvent générer en parallèle.

Assemblage du system_prompt (v3)
──────────────────────────────────
  - Le client envoie profile_name (nom du profil actif).
  - ws_chat résout le profil, assemble le prompt complet via build_system_prompt()
    (prompt de base + directive outils + skills épinglés) et le passe à agent_loop.
  - Le champ system_prompt du payload est réservé au contexte RAG éventuel,
    concaténé après le prompt de profil.
  - Rétrocompatibilité : si profile_name est absent, system_prompt est utilisé tel quel.

Isolation des callbacks (v3)
──────────────────────────────
  Les callbacks llm_events (set_cancel_callback, etc.) utilisent des
  contextvars.ContextVar — chaque session WebSocket a ses propres callbacks,
  propagés automatiquement dans le thread agent_loop via asyncio.to_thread().
  Pas de collision possible entre utilisateurs simultanés.
"""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.websockets import WebSocketState
from jose import JWTError

from core import llm_service, tools_engine, llm_events
from core.database import HistoryDB
from core.user_config import UserConfig
from core.request_context import set_user_config
from core import user_manager
from server.schemas import ChatPayload
from server.routers.monitoring import update_session_stats, update_model_usage
from server.routers.profiles_skills import _profile_store, _personal_profile_store, build_system_prompt

_log = logging.getLogger(__name__)
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


async def _safe_send(ws: WebSocket, payload: dict) -> None:
    """Envoie un message JSON sur le WebSocket. Silencieux si la connexion est fermée."""
    try:
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        _log.debug("[ws] send error (connexion fermée ?) : %s", e)


@router.websocket("/ws/chat/{conv_id}")
async def ws_chat(
    conv_id: str,
    ws: WebSocket,
    token: str = Query(..., description="JWT d'authentification"),
):
    """
    WebSocket de streaming LLM pour une conversation.

    Authentification : token JWT fourni en query param (?token=<jwt>).

    Protocole :
      → Client envoie  : ChatPayload JSON (une seule fois pour démarrer)
      → Client peut envoyer : {"action": "cancel"} pour interrompre
      ← Serveur émet   : messages JSON typés (token, tool_called, finished…)
    """
    # ── Authentification ────────────────────────────────────────────────────
    try:
        payload_jwt = user_manager.decode_access_token(token)
        user_id = payload_jwt.get("sub")
        username = payload_jwt.get("username", "?")
        if not user_id:
            raise ValueError("sub manquant")
        user = user_manager.get_user_by_id(user_id)
        if not user:
            raise ValueError("utilisateur introuvable")
    except (JWTError, ValueError, Exception) as e:
        await ws.accept()
        await ws.send_text(json.dumps({"t": "error", "msg": "Non authentifié."}))
        await ws.close(code=4001)
        _log.warning("[ws] Connexion refusée (auth) : %s", e)
        return

    await ws.accept()
    _log.info("[ws] Connexion ouverte user=%s conv_id=%s", username, conv_id)

    # ── DB isolée par utilisateur ────────────────────────────────────────────
    user_dir = _DATA_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    db = HistoryDB(db_path=str(user_dir / "history.db"))

    # ── UserConfig pour les credentials ──────────────────────────────────────
    user_cfg = UserConfig.from_user_id(user_id)

    # ── Lecture du payload de démarrage ──────────────────────────────────────
    try:
        raw = await ws.receive_text()
        data = json.loads(raw)
    except (WebSocketDisconnect, json.JSONDecodeError) as e:
        _log.warning("[ws] Payload invalide : %s", e)
        await ws.close(code=1003)
        return

    try:
        payload = ChatPayload(**data)
    except Exception as e:
        await _safe_send(ws, {"t": "error", "msg": f"Payload invalide : {e}"})
        await ws.close()
        return

    # ── Persistance du message utilisateur ───────────────────────────────────
    if payload.save_user_message:
        try:
            db.add_message(conv_id, "user", payload.save_user_message)
            db.update_conversation_touched(conv_id)
        except Exception as e:
            _log.warning("[ws] Impossible de persister le message user : %s", e)

    # ── État d'annulation partagé ─────────────────────────────────────────────
    cancelled = False

    async def _listen_for_cancel():
        nonlocal cancelled
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    obj = json.loads(msg)
                    if obj.get("action") == "cancel":
                        cancelled = True
                        _log.info("[ws] Annulation demandée user=%s conv_id=%s", username, conv_id)
                        return
                except json.JSONDecodeError:
                    pass
        except (WebSocketDisconnect, Exception):
            cancelled = True

    cancel_task = asyncio.create_task(_listen_for_cancel())

    # ── Callbacks ─────────────────────────────────────────────────────────────
    loop = asyncio.get_event_loop()

    def _schedule(payload_dict: dict):
        loop.call_soon_threadsafe(asyncio.ensure_future, _safe_send(ws, payload_dict))

    def on_token(tok: str):
        if not cancelled:
            _schedule({"t": "token", "d": tok})

    def on_tool_called(name: str, args: str):
        if not cancelled:
            _schedule({"t": "tool_called", "name": name, "args": args})

    def on_tool_result(name: str, result: str):
        if not cancelled:
            _schedule({"t": "tool_result", "name": name})

    def on_image(mime: str, b64: str):
        if not cancelled:
            _schedule({"t": "tool_image", "mime": mime, "data": b64})

    def on_tool_progress(msg: str):
        if not cancelled:
            _schedule({"t": "tool_progress", "msg": msg})

    def on_usage(u):
        if not cancelled:
            # Extraction CO₂ : nouveau format impacts (Albert v0.4.2) en priorité,
            # fallback sur l'ancien champ carbon déprécié.
            impacts = getattr(u, "impacts", None) or {}
            if isinstance(impacts, dict):
                kgco2 = impacts.get("kgCO2eq", 0.0) or 0.0
            else:
                kgco2 = getattr(impacts, "kgCO2eq", 0.0) or 0.0

            if kgco2 == 0.0:
                # fallback ancien format carbon.kgCO2eq.{min,max} → moyenne
                carbon = getattr(u, "carbon", None) or {}
                if isinstance(carbon, dict) and "kgCO2eq" in carbon:
                    lo = carbon["kgCO2eq"].get("min", 0.0) or 0.0
                    hi = carbon["kgCO2eq"].get("max", 0.0) or 0.0
                    kgco2 = (lo + hi) / 2.0

            usage_dict = {
                "prompt":         u.prompt,
                "completion":     u.completion,
                "total":          u.total,
                "cost_eur":       getattr(u, "cost", 0.0) or 0.0,
                "carbon_kgco2":   kgco2,
            }
            update_session_stats(conv_id, usage_dict)
            _schedule({"t": "usage", "prompt": u.prompt,
                       "completion": u.completion, "total": u.total})

    def on_context_event(msg: str):
        if not cancelled:
            _schedule({"t": "context_event", "msg": msg})

    def on_memory_event(msg: str):
        if not cancelled:
            _schedule({"t": "memory_event", "msg": msg})

    def on_compression_stats(stats: dict):
        if not cancelled:
            _schedule({"t": "compression_stats", **stats})

    def on_family_routing(info: dict):
        if not cancelled:
            _schedule({"t": "family_routing", **info})

    def on_model_usage(info: dict):
        if not cancelled:
            update_model_usage(conv_id, info)
            _schedule({"t": "model_usage", **info})

    # ── Assemblage du system_prompt côté serveur ─────────────────────────────
    # Si le client envoie un profile_name, on récupère le profil depuis le
    # store et on construit le prompt complet (profil + skills épinglés +
    # directive d'usage des outils). Cela garantit que les skills épinglés
    # sont toujours injectés, quelle que soit la version du client.
    # En l'absence de profile_name, on utilise system_prompt tel quel
    # (rétrocompatibilité mono-user / appels directs).
    #
    # Le champ system_prompt du payload peut contenir un contexte RAG
    # assemblé côté client : il est concaténé APRÈS le prompt de profil.
    final_system_prompt = payload.system_prompt
    if payload.profile_name:
        if payload.profile_is_personal:
            profile = _personal_profile_store.get(user["id"], payload.profile_name)
        else:
            _profile_store._load()
            profile = _profile_store.get(payload.profile_name)
        if profile:
            # ── Filtrage des familles d'outils selon le profil ────────────
            # CORRECTION BUG 1 : apply_profile_families() n'était jamais
            # appelée ici, ce qui laissait _DISABLED_FAMILIES dans l'état
            # de la session précédente et envoyait tous les outils au LLM
            # quel que soit le profil actif.
            tf = (profile.get("tool_families") or {})
            tools_engine.apply_profile_families(
                enabled=list(tf.get("enabled", [])),
                disabled=list(tf.get("disabled", [])),
                user_id=user["id"],
            )
            _log.debug(
                "[ws] familles d'outils appliquées pour profil '%s' "
                "(enabled=%s, disabled=%s)",
                payload.profile_name,
                tf.get("enabled", []),
                tf.get("disabled", []),
            )

            profile_prompt = build_system_prompt(profile)
            # Concaténer le contexte RAG client s'il est présent
            if payload.system_prompt.strip():
                final_system_prompt = f"{profile_prompt}\n\n{payload.system_prompt}".strip()
            else:
                final_system_prompt = profile_prompt
            _log.debug(
                "[ws] system_prompt assemblé depuis profil '%s' "
                "(%d chars, skills: %s)",
                payload.profile_name,
                len(final_system_prompt),
                profile.get("pinned_skills") or [],
            )
        else:
            _log.warning(
                "[ws] profil '%s' introuvable — system_prompt brut utilisé, "
                "familles d'outils non filtrées",
                payload.profile_name,
            )

    # ── Génération (sans lock global) ────────────────────────────────────────
    llm_events.set_cancel_callback(lambda: cancelled)
    tools_engine.set_tool_progress_callback(on_tool_progress)
    llm_service.set_context_event_callback(on_context_event)
    llm_service.set_memory_event_callback(on_memory_event)
    llm_service.set_compression_stats_callback(on_compression_stats)
    llm_service.set_family_routing_callback(on_family_routing)
    llm_service.set_model_usage_callback(on_model_usage)

    # Positionne le UserConfig dans le contexte asyncio courant
    # → propagé automatiquement dans le thread via asyncio.to_thread()
    set_user_config(user_cfg)

    try:
        final_text = await asyncio.to_thread(
            llm_service.agent_loop,
            messages=payload.messages,
            system_prompt=final_system_prompt,
            model=payload.model,
            use_tools=payload.use_tools,
            max_iterations=payload.max_iterations,
            disable_context_management=payload.disable_context_management,
            on_tool_call=on_tool_called,
            on_tool_result=on_tool_result,
            on_image=on_image,
            on_token=on_token,
            on_usage=on_usage,
        )

        if final_text.strip():
            try:
                db.add_message(conv_id, "assistant", final_text)
                db.update_conversation_touched(conv_id)
            except Exception as e:
                _log.warning("[ws] Impossible de persister la réponse : %s", e)

        if cancelled:
            await _safe_send(ws, {"t": "cancelled", "text": final_text})
        else:
            await _safe_send(ws, {"t": "finished", "text": final_text})

    except Exception as e:
        _log.exception("[ws] Erreur agent_loop user=%s conv_id=%s", username, conv_id)
        await _safe_send(ws, {"t": "error", "msg": str(e)})

    finally:
        set_user_config(None)
        llm_events.set_cancel_callback(None)
        tools_engine.set_tool_progress_callback(None)
        llm_service.set_context_event_callback(None)
        llm_service.set_memory_event_callback(None)
        llm_service.set_compression_stats_callback(None)
        llm_service.set_family_routing_callback(None)
        llm_service.set_model_usage_callback(None)

    cancel_task.cancel()
    try:
        await cancel_task
    except asyncio.CancelledError:
        pass

    try:
        await ws.close()
    except Exception:
        pass

    _log.info("[ws] Connexion fermée user=%s conv_id=%s (cancelled=%s)",
              username, conv_id, cancelled)
