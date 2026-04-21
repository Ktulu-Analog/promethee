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
server/routers/vfs_router.py — API REST du système de fichiers virtuel
=======================================================================

Routes exposées :

    GET    /vfs/list?path=/          → liste un dossier
    GET    /vfs/search?q=...         → recherche récursive dans le VFS
    GET    /vfs/tree?path=/          → arborescence
    GET    /vfs/info?path=/...       → métadonnées
    GET    /vfs/download?path=/...   → téléchargement d'un fichier
    GET    /vfs/quota                → statistiques d'utilisation
    DELETE /vfs/delete?path=/...     → suppression

Ce router complète upload.py en ajoutant la persistance dans le VFS :
    POST /upload/file  →  stocke dans le VFS ET retourne le contenu extrait

Intégration dans server/main.py :
    from server.routers import vfs_router
    app.include_router(vfs_router.router)

Modification de server/routers/upload.py :
    Appeler vfs_router.persist_upload(user_id, name, raw, mime_type)
    après l'extraction du contenu existant. Voir la section
    "Intégration upload" en bas de ce fichier.
"""

import logging
import mimetypes
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import io

from server.deps import require_auth
from core.virtual_fs import VirtualFS, VFSNotFound, VFSError, VFSExists, \
    VFSPermission, VFSTooBig

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/vfs", tags=["vfs"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _vfs(user: dict) -> VirtualFS:
    """Retourne le VFS de l'utilisateur courant."""
    return VirtualFS(user["id"])


def _http_err(e: Exception) -> HTTPException:
    """Convertit une exception VFS en HTTPException."""
    if isinstance(e, VFSNotFound):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, VFSExists):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, VFSPermission):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, VFSTooBig):
        return HTTPException(status_code=413, detail=str(e))
    return HTTPException(status_code=500, detail=str(e))


# ── Routes de lecture ─────────────────────────────────────────────────────────

@router.get("/list")
async def vfs_list(
    path: str = Query(default="/", description="Chemin virtuel du dossier"),
    user: dict = Depends(require_auth),
):
    """Liste le contenu d'un dossier virtuel."""
    try:
        vfs = _vfs(user)
        entries = vfs.listdir(path)
        return {"path": path, "entries": entries, "count": len(entries)}
    except VFSError as e:
        raise _http_err(e)


@router.get("/search")
async def vfs_search(
    q: str = Query(default="", description="Terme de recherche (nom de fichier/dossier)"),
    path: str = Query(default="/", description="Dossier racine de la recherche"),
    include_dirs: bool = Query(default=True, description="Inclure les dossiers dans les résultats"),
    max_results: int = Query(default=200, ge=1, le=500),
    user: dict = Depends(require_auth),
):
    """
    Recherche récursive de fichiers/dossiers par nom dans le VFS.

    Retourne tous les nœuds dont le nom contient `q` (insensible à la casse),
    en parcourant récursivement l'arborescence à partir de `path`.
    """
    try:
        vfs = _vfs(user)
        q_lower = q.strip().lower()
        results: list[dict] = []

        def _walk(current: str) -> None:
            if len(results) >= max_results:
                return
            try:
                entries = vfs.listdir(current)
            except Exception:
                return
            for entry in entries:
                if len(results) >= max_results:
                    break
                matches = not q_lower or q_lower in entry["name"].lower()
                if entry["type"] == "dir":
                    if matches and include_dirs:
                        results.append(entry)
                    _walk(entry["path"])
                elif matches:
                    results.append(entry)

        _walk(path)
        return {
            "q": q,
            "path": path,
            "results": results,
            "count": len(results),
            "truncated": len(results) >= max_results,
        }
    except VFSError as e:
        raise _http_err(e)


@router.get("/tree")
async def vfs_tree(
    path: str = Query(default="/"),
    max_depth: int = Query(default=3, ge=1, le=10),
    user: dict = Depends(require_auth),
):
    """Retourne l'arborescence en texte."""
    try:
        vfs = _vfs(user)
        tree = vfs.tree(path, max_depth=max_depth)
        return {"path": path, "tree": tree}
    except VFSError as e:
        raise _http_err(e)


@router.get("/info")
async def vfs_info(
    path: str = Query(..., description="Chemin virtuel"),
    user: dict = Depends(require_auth),
):
    """Retourne les métadonnées d'un nœud."""
    try:
        vfs = _vfs(user)
        return vfs.get_info(path)
    except VFSError as e:
        raise _http_err(e)


@router.get("/quota")
async def vfs_quota_route(user: dict = Depends(require_auth)):
    """Retourne les statistiques d'utilisation du VFS."""
    vfs = _vfs(user)
    return vfs.quota()


# ── Téléchargement ────────────────────────────────────────────────────────────

@router.get("/download")
async def vfs_download(
    path: str = Query(..., description="Chemin virtuel du fichier"),
    user: dict = Depends(require_auth),
):
    """
    Télécharge un fichier depuis le VFS.

    Retourne le contenu brut avec les bons en-têtes Content-Type
    et Content-Disposition pour déclencher le téléchargement dans le navigateur.
    """
    try:
        vfs = _vfs(user)
        if not vfs.is_file(path):
            raise HTTPException(status_code=404,
                                detail=f"Fichier introuvable : {path}")
        content = vfs.read_bytes(path)
        info = vfs.get_info(path)

        filename = PurePosixPath(path).name
        mime = info.get("mime_type") or "application/octet-stream"

        # Détecter le mime si manquant
        if mime in ("application/octet-stream", "text/plain"):
            guessed, _ = mimetypes.guess_type(filename)
            if guessed:
                mime = guessed

        return StreamingResponse(
            io.BytesIO(content),
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(content)),
            },
        )
    except HTTPException:
        raise
    except VFSError as e:
        raise _http_err(e)


# ── Suppression ───────────────────────────────────────────────────────────────

@router.delete("/delete")
async def vfs_delete(
    path: str = Query(..., description="Chemin virtuel à supprimer"),
    user: dict = Depends(require_auth),
):
    """Supprime un fichier ou dossier du VFS."""
    try:
        vfs = _vfs(user)
        vfs.delete(path, confirm=True)
        return {"status": "success", "deleted": path}
    except VFSError as e:
        raise _http_err(e)


# ── Vérification intégrité Garage ─────────────────────────────────────────────

@router.get("/check")
async def vfs_check(
    path: str = Query(default="/", description="Dossier à vérifier"),
    user: dict = Depends(require_auth),
):
    """
    Vérifie quels fichiers du dossier sont effectivement présents dans Garage.
    Retourne la liste des fichiers orphelins (référencés en SQLite, absents de Garage).
    """
    from botocore.exceptions import ClientError as _S3Error
    try:
        vfs = _vfs(user)
        entries = vfs.listdir(path)
        files = [e for e in entries if e["type"] == "file"]

        orphans = []
        for entry in files:
            try:
                vfs.read_bytes(entry["path"])
            except Exception as e:
                if "NoSuchKey" in str(e) or "Erreur Garage" in str(e):
                    orphans.append(entry["path"])

        return {
            "path": path,
            "checked": len(files),
            "orphans": orphans,
        }
    except VFSError as e:
        raise _http_err(e)


# ── Création de dossier ───────────────────────────────────────────────────────

@router.post("/mkdir")
async def vfs_mkdir(
    path: str = Query(..., description="Chemin virtuel du nouveau dossier"),
    user: dict = Depends(require_auth),
):
    """Crée un dossier dans le VFS."""
    try:
        vfs = _vfs(user)
        vfs.mkdir(path, exist_ok=False)
        return {"status": "success", "created": path}
    except VFSError as e:
        raise _http_err(e)


# ── Déplacement / Renommage ───────────────────────────────────────────────────

@router.post("/move")
async def vfs_move(
    src: str = Query(..., description="Chemin source"),
    dst: str = Query(..., description="Chemin destination"),
    user: dict = Depends(require_auth),
):
    """Déplace ou renomme un fichier/dossier dans le VFS."""
    try:
        vfs = _vfs(user)
        vfs.move(src, dst)
        return {"status": "success", "src": src, "dst": dst}
    except VFSError as e:
        raise _http_err(e)


# ==============================================================================
# Intégration avec upload.py
# ==============================================================================

def persist_upload(user_id: str, filename: str, raw: bytes,
                   mime_type: str = "application/octet-stream") -> str:
    """
    Persiste un fichier uploadé dans le VFS de l'utilisateur.

    À appeler depuis server/routers/upload.py après l'extraction du contenu.

    Paramètres
    ----------
    user_id  : str   — identifiant de l'utilisateur
    filename : str   — nom du fichier original
    raw      : bytes — contenu brut du fichier
    mime_type: str   — type MIME

    Retourne
    --------
    str — chemin VFS du fichier persisté (ex: "/uploads/rapport.pdf")

    Exemple d'intégration dans upload.py :
    ----------------------------------------
    from server.routers.vfs_router import persist_upload

    @router.post("/file")
    async def upload_file(file: UploadFile, user=Depends(require_auth)):
        name = file.filename or "fichier"
        raw  = await file.read()

        # ... extraction existante (texte, PDF, etc.) ...
        result = { "type": "file", "name": name, "content": extracted_content }

        # Nouveau : persistance dans le VFS
        vfs_path = persist_upload(user["id"], name, raw, mime_type)
        result["vfs_path"] = vfs_path   # communiqué au frontend

        return result
    """
    vfs = VirtualFS(user_id)
    # Résoudre les conflits de noms : rapport.pdf → rapport_1.pdf, etc.
    base_path = f"/uploads/{filename}"
    target_path = base_path
    stem = PurePosixPath(filename).stem
    suffix = PurePosixPath(filename).suffix
    counter = 1

    while vfs.exists(target_path):
        target_path = f"/uploads/{stem}_{counter}{suffix}"
        counter += 1

    vfs.write_bytes(target_path, raw, mime_type=mime_type)
    _log.info("[VFS] Upload persisté : %s → %s", filename, target_path)
    return target_path
