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
routers/ws_libreoffice.py — WebSocket de pilotage LibreOffice Writer en temps réel
====================================================================================

Route :
    GET /ws/writer/{session_id}?token=<jwt>

L'extension "Prométhée Bridge" se connecte ici. Les outils writer_tools
poussent des événements JSON dans la queue de session ; ce routeur les
relaie au client LibreOffice connecté.

Protocole événements (serveur → client LibreOffice) :
  {"type": "new_document",  "title": "..."}
  {"type": "insert_text",   "text": "...", "style": "heading1|paragraph|..."}
  {"type": "insert_table",  "caption": "...", "headers": [...], "rows": [[...]]}
  {"type": "insert_chart",  "caption": "...", "echarts_option": {...}, "width": 800, "height": 400}
  {"type": "save_document", "filename": "..."}
  {"type": "ping"}

Protocole client → serveur :
  {"action": "ready"}        — confirme la connexion
  {"action": "ack",          "event_type": "..."}  — accusé de réception optionnel
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.websockets import WebSocketState
from jose import JWTError

from core import user_manager

_log = logging.getLogger(__name__)
router = APIRouter()

# ── Registre des sessions actives ─────────────────────────────────────────────
# session_id → {"ws": WebSocket, "queue": asyncio.Queue, "user_id": str}
_SESSIONS: dict[str, dict] = {}


def get_writer_session(session_id: str) -> Optional[dict]:
    """Retourne la session Writer ou None si déconnectée."""
    return _SESSIONS.get(session_id)


def push_writer_event(session_id: str, event: dict) -> None:
    """
    Pousse un événement dans la queue de la session Writer.
    Appelé depuis writer_tools (thread LLM agent_loop).
    Thread-safe : asyncio.Queue est safe depuis n'importe quel thread
    via put_nowait (pas d'attente).
    """
    session = _SESSIONS.get(session_id)
    if session:
        try:
            session["queue"].put_nowait(event)
        except asyncio.QueueFull:
            _log.warning("[ws_writer] Queue pleine pour session %s, événement ignoré.", session_id)
    else:
        _log.debug("[ws_writer] Session %s introuvable pour push.", session_id)


def list_writer_sessions() -> list[dict]:
    """Liste les sessions Writer actives (pour l'API de monitoring)."""
    return [
        {"session_id": sid, "user_id": s["user_id"]}
        for sid, s in _SESSIONS.items()
    ]


# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/ws/writer/{session_id}")
async def ws_writer(
    session_id: str,
    ws: WebSocket,
    token: str = Query(..., description="JWT d'authentification"),
):
    """
    WebSocket de l'extension LibreOffice Prométhée Bridge.

    L'extension se connecte avec son token JWT et reçoit en temps réel
    les événements produits par les outils writer_tools du LLM.
    """
    # ── Authentification ─────────────────────────────────────────────────────
    try:
        payload_jwt = user_manager.decode_access_token(token)
        user_id = payload_jwt.get("sub")
        if not user_id:
            raise ValueError("sub manquant")
        user = user_manager.get_user_by_id(user_id)
        if not user:
            raise ValueError("utilisateur inconnu")
    except (JWTError, ValueError) as e:
        _log.warning("[ws_writer] Auth échouée pour session %s : %s", session_id, e)
        await ws.close(code=1008)
        return

    await ws.accept()
    _log.info("[ws_writer] Extension connectée : session=%s user=%s", session_id, user_id)

    # ── Enregistrement de la session ─────────────────────────────────────────
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _SESSIONS[session_id] = {"ws": ws, "queue": queue, "user_id": user_id}

    try:
        # Confirmation de connexion
        await ws.send_text(json.dumps({"type": "connected", "session_id": session_id}))

        # ── Boucle principale ────────────────────────────────────────────────
        # Deux tâches concurrentes :
        #   1. relay_task : dépile la queue et envoie au client Writer
        #   2. listen_task : reçoit les ack/actions du client Writer

        async def relay_task():
            """Relaie les événements de la queue vers le WebSocket Writer."""
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if ws.client_state == WebSocketState.CONNECTED:
                        await ws.send_text(json.dumps(event, ensure_ascii=False))
                        queue.task_done()
                    else:
                        break
                except asyncio.TimeoutError:
                    # Ping keepalive
                    if ws.client_state == WebSocketState.CONNECTED:
                        await ws.send_text(json.dumps({"type": "ping"}))
                    else:
                        break

        async def listen_task():
            """Reçoit les messages du client Writer (ack, ready, etc.)."""
            while True:
                try:
                    raw = await ws.receive_text()
                    msg = json.loads(raw)
                    action = msg.get("action", "")
                    if action == "ready":
                        _log.debug("[ws_writer] Writer prêt : session=%s", session_id)
                    elif action == "ack":
                        _log.debug("[ws_writer] Ack event=%s session=%s",
                                   msg.get("event_type"), session_id)
                    else:
                        _log.debug("[ws_writer] Message inconnu : %s", msg)
                except WebSocketDisconnect:
                    break
                except json.JSONDecodeError:
                    _log.warning("[ws_writer] Message JSON invalide ignoré.")

        relay = asyncio.create_task(relay_task())
        listen = asyncio.create_task(listen_task())

        done, pending = await asyncio.wait(
            [relay, listen],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        _log.info("[ws_writer] Extension déconnectée : session=%s", session_id)
    except Exception as e:
        _log.error("[ws_writer] Erreur inattendue session=%s : %s", session_id, e)
    finally:
        _SESSIONS.pop(session_id, None)
        _log.info("[ws_writer] Session Writer fermée : %s", session_id)


# ── Route HTTP : sessions actives ─────────────────────────────────────────────

@router.get("/writer/sessions")
async def get_writer_sessions():
    """Liste les sessions LibreOffice Writer actuellement connectées."""
    return {"sessions": list_writer_sessions()}
