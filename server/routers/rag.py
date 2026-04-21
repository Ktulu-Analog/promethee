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
routers/rag.py — Gestion RAG (ingestion, sources, collections)

Équivalent de RagPanel (ui/panels/rag_panel.py) + IngestWorker (ui/workers.py).

Routes :
    POST   /rag/ingest              Ingère un fichier (multipart/form-data)
    GET    /rag/sources             Liste les sources indexées
    DELETE /rag/sources             Supprime une source par nom
    GET    /rag/collections         Liste les collections Qdrant disponibles
    GET    /rag/status              État de disponibilité de Qdrant
    GET    /rag/albert/collections  Collections Albert disponibles

Streaming de progression
─────────────────────────
IngestWorker émettait un pyqtSignal progress(done, total) par fichier ingéré.
Ici on expose un endpoint SSE /rag/ingest/stream pour les clients qui veulent
suivre la progression. Pour les cas simples (1 fichier), POST /rag/ingest
suffit (réponse synchrone).
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

from core.request_context import set_user_config
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse

from core import rag_engine
from core.database import HistoryDB
from server.deps import require_auth, get_current_user_config, get_db
from server.schemas import RagIngestResponse, RagSourceOut, RagCollectionOut

_log = logging.getLogger(__name__)
router = APIRouter()


# ── Ingestion ─────────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=RagIngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    conv_id: Optional[str] = Query(None, description="ID de conversation (None = global)"),
    user_cfg = Depends(get_current_user_config),
):
    """
    Ingère un fichier dans Qdrant.

    Équivalent de IngestWorker.run() + rag_engine.ingest_file().
    Écrit le fichier uploadé dans un répertoire temporaire puis appelle
    ingest_file() de manière synchrone dans un thread pour ne pas bloquer
    la boucle asyncio.

    Pour plusieurs fichiers avec suivi de progression, utiliser
    POST /rag/ingest/stream (SSE).
    """
    set_user_config(user_cfg)
    if not rag_engine.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant n'est pas disponible. Vérifiez QDRANT_URL dans .env.",
        )

    # Sauvegarde temporaire du fichier uploadé
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        chunks = await asyncio.to_thread(
            rag_engine.ingest_file, tmp_path, conv_id
        )
        _log.info("[rag] Ingéré %s → %d chunks (conv_id=%s)", file.filename, chunks, conv_id)
        return RagIngestResponse(chunks=chunks, filename=file.filename or "")
    except Exception as e:
        _log.exception("[rag] Erreur ingestion %s", file.filename)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/ingest/stream")
async def ingest_files_stream(
    files: list[UploadFile] = File(...),
    conv_id: Optional[str] = Query(None),
    user_cfg = Depends(get_current_user_config),
):
    """
    Ingère plusieurs fichiers avec progression SSE.

    Équivalent de IngestWorker avec le signal progress(done, total).
    Chaque événement SSE est au format :
        data: {"done": 1, "total": 3, "filename": "doc.pdf", "chunks": 42}

    Utilisation côté React :
        const es = new EventSource('/rag/ingest/stream');
        es.onmessage = e => console.log(JSON.parse(e.data));
    """
    if not rag_engine.is_available():
        raise HTTPException(status_code=503, detail="Qdrant non disponible.")

    # Sauvegarder tous les fichiers uploadés avant de streamer
    tmp_files: list[tuple[str, str]] = []
    for f in files:
        suffix = Path(f.filename or "upload").suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await f.read())
            tmp_files.append((tmp.name, f.filename or ""))

    import json as _json

    async def _generator():
        total = len(tmp_files)
        for i, (tmp_path, filename) in enumerate(tmp_files):
            try:
                chunks = await asyncio.to_thread(rag_engine.ingest_file, tmp_path, conv_id)
                event = _json.dumps(
                    {"done": i + 1, "total": total, "filename": filename, "chunks": chunks}
                )
                yield f"data: {event}\n\n"
            except Exception as e:
                event = _json.dumps(
                    {"done": i + 1, "total": total, "filename": filename, "error": str(e)}
                )
                yield f"data: {event}\n\n"
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(_generator(), media_type="text/event-stream")


# ── Sources ───────────────────────────────────────────────────────────────────

@router.get("/sources", response_model=list[RagSourceOut])
async def list_sources(
    conv_id: Optional[str] = Query(None),
    collection_name: Optional[str] = Query(None),
    user_cfg = Depends(get_current_user_config),
):
    """Liste les sources indexées dans une collection."""
    set_user_config(user_cfg)
    try:
        sources = await asyncio.to_thread(
            rag_engine.list_sources, conv_id, collection_name
        )
        return [
            RagSourceOut(
                source=s.get("source", ""),
                chunks=s.get("count", 0),
                score_avg=s.get("score_avg"),
            )
            for s in sources
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sources", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source: str = Query(..., description="Nom de la source à supprimer"),
    conv_id: Optional[str] = Query(None),
    collection_name: Optional[str] = Query(None),
    user_cfg = Depends(get_current_user_config),
):
    """Supprime tous les chunks d'une source de la collection."""
    set_user_config(user_cfg)
    try:
        await asyncio.to_thread(
            rag_engine.delete_by_source, source, conv_id, collection_name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Collections ───────────────────────────────────────────────────────────────

@router.get("/collections", response_model=list[RagCollectionOut])
async def list_collections(user_cfg = Depends(get_current_user_config)):
    """Liste les collections Qdrant visibles par l'utilisateur courant.

    Règles de visibilité :
      - La collection RAG de l'utilisateur (promethee_{username}) → toujours incluse, is_own=True
      - La collection LTM de l'utilisateur (promethee_memory_{username}) → exclue (usage interne)
      - Les collections externes (sans préfixe promethee_) → incluses, is_own=False
      - Les collections des autres utilisateurs (promethee_<autre>) → exclues
    """
    set_user_config(user_cfg)
    try:
        names = await asyncio.to_thread(rag_engine.list_collections)

        own_rag = user_cfg.QDRANT_COLLECTION   # ex: promethee_bob
        own_ltm = user_cfg.LTM_COLLECTION      # ex: promethee_memory_bob — usage interne, non affiché

        result = []
        for n in names:
            if n == own_rag:
                # Collection RAG de l'utilisateur courant
                result.append(RagCollectionOut(name=n, is_own=True))
            elif n == own_ltm:
                # Collection LTM : usage interne uniquement, ne pas exposer
                pass
            elif n.startswith("promethee_"):
                # Collection d'un autre utilisateur → masquée
                pass
            else:
                # Collection externe partagée (Albert, corpus commun…)
                result.append(RagCollectionOut(name=n, is_own=False))

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def rag_status(user_cfg = Depends(get_current_user_config)):
    """Vérifie la disponibilité de Qdrant."""
    available = await asyncio.to_thread(rag_engine.is_available)
    return {"available": available}


@router.get("/albert/collections")
async def list_albert_collections(user_cfg = Depends(get_current_user_config)):
    """Liste les collections Albert disponibles (API externe)."""
    set_user_config(user_cfg)
    try:
        cols = await asyncio.to_thread(rag_engine.list_albert_collections)
        return cols
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Contexte RAG pour le chat ─────────────────────────────────────────────
# Appelé par ChatPanel.tsx avant l'envoi du WebSocket payload.
# Équivalent de rag_engine.build_rag_context() dans chat_panel.py._build_system_prompt()

@router.get("/context")
async def get_rag_context(
    query: str = Query(..., description="Requête utilisateur"),
    conv_id: Optional[str] = Query(None),
    collection_name: Optional[str] = Query(None),
    user_cfg = Depends(get_current_user_config),
):
    """
    Construit le contexte RAG pour une requête.
    Retourne {"context": ""} si Qdrant n'est pas disponible.
    """
    if not rag_engine.is_available():
        return {"context": ""}
    set_user_config(user_cfg)
    try:
        ctx = await asyncio.to_thread(
            rag_engine.build_rag_context, query, conv_id, collection_name
        )
        return {"context": ctx or ""}
    except Exception as e:
        _log.warning("[rag] context error: %s", e)
        return {"context": ""}


# ── Suppression LTM ──────────────────────────────────────────────────────────

@router.delete("/ltm", status_code=status.HTTP_200_OK)
async def clear_ltm(
    user_cfg = Depends(get_current_user_config),
    db: "HistoryDB" = Depends(get_db),
):
    """
    Vide entièrement la mémoire long terme (LTM) de l'utilisateur courant :
    - Supprime tous les chunks de la collection LTM dans Qdrant en passant
      par delete_by_source() sur chaque conversation indexée.
    - Remet à zéro les marqueurs d'indexation dans le kv_store.
    """
    from core import rag_engine as _rag

    collection = user_cfg.LTM_COLLECTION

    # Récupérer toutes les conversations et supprimer leurs chunks LTM
    convs = db.get_conversations()
    total_deleted = 0
    cleared_markers = 0

    for conv in convs:
        cid = conv["id"]
        source_name = f"memory:{cid}"
        try:
            n = await asyncio.to_thread(
                _rag.delete_by_source,
                source_name,
                None,          # conversation_id (scope) = None pour LTM
                collection,    # collection LTM de l'utilisateur
            )
            total_deleted += n
        except Exception:
            pass

        # Supprimer le marqueur d'indexation kv
        db.kv_delete(f"ltm:indexed:{cid}")
        cleared_markers += 1

    # Remettre à zéro le compteur de consolidation
    db.kv_delete("ltm:consolidation_counter")

    return {
        "cleared": True,
        "collection": collection,
        "chunks_deleted": total_deleted,
        "markers_cleared": cleared_markers,
    }
