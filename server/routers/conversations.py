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
routers/conversations.py — Gestion des conversations et dossiers

Équivalent de ConvSidePanel (conversation_sidebar.py) côté données.

Routes conversations :
    GET    /conversations               Liste toutes les conversations
    POST   /conversations               Crée une nouvelle conversation
    GET    /conversations/tree          Arborescence dossiers + convs (pour la sidebar)
    GET    /conversations/{id}          Détail d'une conversation
    PATCH  /conversations/{id}          Mise à jour titre / system_prompt / folder
    DELETE /conversations/{id}          Supprime une conversation
    GET    /conversations/{id}/messages Historique des messages
    DELETE /conversations/{id}/messages Efface les messages (garde la conversation)
    PATCH  /conversations/{id}/folder   Déplace vers un dossier (ou sans dossier)

Routes dossiers :
    GET    /conversations/folders       Liste les dossiers
    POST   /conversations/folders       Crée un dossier
    PATCH  /conversations/folders/{id}  Renomme / réordonne
    DELETE /conversations/folders/{id}  Supprime (les convs sont déplacées en Sans dossier)

Routes recherche :
    GET    /conversations/search?q=...  Recherche plein-texte FTS5
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.database import HistoryDB
from server.deps import get_db
from server.schemas import (
    ConversationCreate, ConversationOut, ConversationUpdate,
    MessageOut, FolderCreate, FolderOut, FolderUpdate,
    ConvMovePayload, ConvTreeOut,
)

_log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _conv_out(row: dict) -> ConversationOut:
    return ConversationOut(
        id=row["id"],
        title=row.get("title", ""),
        system_prompt=row.get("system_prompt", ""),
        model=row.get("model"),
        folder_id=row.get("folder_id"),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )


def _msg_out(row: dict) -> MessageOut:
    return MessageOut(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row.get("content", ""),
        created_at=str(row.get("created_at", "")),
    )


def _folder_out(row: dict) -> FolderOut:
    return FolderOut(
        id=row["id"],
        name=row["name"],
        parent_id=row.get("parent_id"),
        position=row.get("position", 0),
    )


def _get_conv_or_404(cid: str, db: HistoryDB) -> dict:
    conv = db.get_conversation(cid)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversation {cid!r} introuvable.")
    return conv


# ── Conversations ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[ConversationOut])
async def list_conversations(db: HistoryDB = Depends(get_db)):
    """Retourne toutes les conversations, triées par date de mise à jour desc."""
    return [_conv_out(r) for r in db.get_conversations()]


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    db: HistoryDB = Depends(get_db),
):
    """Crée une nouvelle conversation. Équivalent de MainWindow._new_tab()."""
    cid = db.create_conversation(
        title=payload.title,
        system_prompt=payload.system_prompt,
        folder_id=payload.folder_id,
    )
    return _conv_out(db.get_conversation(cid))


@router.get("/tree", response_model=ConvTreeOut)
async def get_conversation_tree(db: HistoryDB = Depends(get_db)):
    """
    Retourne l'arborescence complète pour la sidebar React.

    Équivalent de ConvSidePanel.load_folder_tree() dans conversation_sidebar.py.
    """
    folders = db.get_all_folders()
    conv_by_folder: dict[str, list[ConversationOut]] = {}
    for folder in folders:
        fid = folder["id"]
        conv_by_folder[fid] = [
            _conv_out(r) for r in db.get_conversations_in_folder(fid)
        ]
    unfiled = [_conv_out(r) for r in db.get_conversations_in_folder(None)]
    return ConvTreeOut(
        folders=[_folder_out(f) for f in folders],
        conversations_by_folder=conv_by_folder,
        unfiled=unfiled,
    )


@router.get("/search", response_model=list[ConversationOut])
async def search_conversations(
    q: str = Query(..., min_length=1, description="Terme de recherche FTS5"),
    db: HistoryDB = Depends(get_db),
):
    """Recherche plein-texte dans les titres et messages (FTS5 SQLite)."""
    results = db.search_conversations(q)
    return [_conv_out(r) for r in results]


@router.get("/{conv_id}", response_model=ConversationOut)
async def get_conversation(conv_id: str, db: HistoryDB = Depends(get_db)):
    return _conv_out(_get_conv_or_404(conv_id, db))


@router.patch("/{conv_id}", response_model=ConversationOut)
async def update_conversation(
    conv_id: str,
    payload: ConversationUpdate,
    db: HistoryDB = Depends(get_db),
):
    """Mise à jour partielle (titre, system_prompt, dossier)."""
    _get_conv_or_404(conv_id, db)
    if payload.title is not None:
        db.update_conversation_title(conv_id, payload.title)
    if payload.folder_id is not None:
        db.move_conversation_to_folder(conv_id, payload.folder_id or None)
    db.update_conversation_touched(conv_id)
    return _conv_out(db.get_conversation(conv_id))


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conv_id: str, db: HistoryDB = Depends(get_db)):
    """Supprime la conversation et tous ses messages."""
    _get_conv_or_404(conv_id, db)
    db.delete_conversation(conv_id)




# ── Suppression globale ───────────────────────────────────────────────────────

@router.delete("", status_code=status.HTTP_200_OK)
async def delete_all_conversations(db: HistoryDB = Depends(get_db)):
    """
    Supprime TOUTES les conversations (et leurs messages) de l'utilisateur courant.
    Retourne le nombre de conversations supprimées.
    """
    convs = db.get_conversations()
    count = 0
    for conv in convs:
        db.delete_conversation(conv["id"])
        count += 1
    return {"deleted": count}

# ── Messages ──────────────────────────────────────────────────────────────────

@router.get("/{conv_id}/messages", response_model=list[MessageOut])
async def get_messages(conv_id: str, db: HistoryDB = Depends(get_db)):
    """Retourne l'historique complet des messages d'une conversation."""
    _get_conv_or_404(conv_id, db)
    return [_msg_out(r) for r in db.get_messages(conv_id)]


@router.delete("/{conv_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_messages(conv_id: str, db: HistoryDB = Depends(get_db)):
    """Efface tous les messages sans supprimer la conversation."""
    _get_conv_or_404(conv_id, db)
    db.clear_messages(conv_id)


# ── Déplacement vers un dossier ───────────────────────────────────────────────

@router.patch("/{conv_id}/folder", response_model=ConversationOut)
async def move_to_folder(
    conv_id: str,
    payload: ConvMovePayload,
    db: HistoryDB = Depends(get_db),
):
    """
    Déplace une conversation vers un dossier (ou sans dossier si folder_id=null).

    Équivalent du drag & drop dans ConvSidePanel._on_drop().
    """
    _get_conv_or_404(conv_id, db)
    db.move_conversation_to_folder(conv_id, payload.folder_id)
    return _conv_out(db.get_conversation(conv_id))


# ── Dossiers ──────────────────────────────────────────────────────────────────

@router.get("/folders/all", response_model=list[FolderOut])
async def list_folders(db: HistoryDB = Depends(get_db)):
    return [_folder_out(f) for f in db.get_all_folders()]


@router.post("/folders", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(payload: FolderCreate, db: HistoryDB = Depends(get_db)):
    fid = db.create_folder(name=payload.name, parent_id=payload.parent_id)
    return _folder_out(db.get_folder(fid))


@router.patch("/folders/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: str,
    payload: FolderUpdate,
    db: HistoryDB = Depends(get_db),
):
    folder = db.get_folder(folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Dossier {folder_id!r} introuvable.")
    if payload.name is not None:
        db.rename_folder(folder_id, payload.name)
    if payload.position is not None:
        db.reorder_folder(folder_id, payload.position)
    return _folder_out(db.get_folder(folder_id))


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: str, db: HistoryDB = Depends(get_db)):
    """Supprime le dossier. Les conversations sont automatiquement déplacées en 'Sans dossier'."""
    if db.get_folder(folder_id) is None:
        raise HTTPException(status_code=404, detail=f"Dossier {folder_id!r} introuvable.")
    db.delete_folder(folder_id)
