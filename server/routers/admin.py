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
routers/admin.py — Routes de gestion des utilisateurs (admin only).

Toutes les routes de ce module nécessitent un JWT valide avec is_admin=True.

Routes
──────
  GET    /admin/users                              Liste tous les utilisateurs
  POST   /admin/users                              Crée un utilisateur (avec option is_admin)
  DELETE /admin/users/{user_id}                    Supprime un utilisateur
  PATCH  /admin/users/{user_id}/admin              Accorde/révoque les droits admin
  POST   /admin/users/{user_id}/reset-password     Réinitialise le mot de passe
  GET    /admin/users/{user_id}/vfs-usage          Quota + utilisation VFS d'un utilisateur
  PATCH  /admin/users/{user_id}/vfs-quota          Définit le quota VFS d'un utilisateur
  GET    /admin/vfs-default-quota                  Quota par défaut
  PATCH  /admin/vfs-default-quota                  Modifie le quota par défaut
"""

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional

from core import user_manager
from core.virtual_fs import VirtualFS
from server.deps import require_admin

_log = logging.getLogger(__name__)
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


# ── Schémas ───────────────────────────────────────────────────────────────────

class AdminUserOut(BaseModel):
    id: str
    username: str
    email: str
    is_admin: bool
    created_at: str
    vfs_quota_bytes: int = 524288000  # 500 Mo par défaut


class AdminCreateUser(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    email: str    = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=8)
    is_admin: bool = False
    vfs_quota_bytes: Optional[int] = None  # None = quota par défaut du serveur


class AdminSetAdmin(BaseModel):
    is_admin: bool


class AdminResetPassword(BaseModel):
    new_password: str = Field(..., min_length=8)


class AdminSetVfsQuota(BaseModel):
    quota_bytes: int = Field(..., ge=0, description="Quota en octets (0 = illimité)")


class AdminSetDefaultVfsQuota(BaseModel):
    quota_bytes: int = Field(..., ge=0)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserOut])
async def list_users(admin: dict = Depends(require_admin)):
    """Liste tous les comptes utilisateurs."""
    users = user_manager.list_users()
    result = []
    for u in users:
        quota = u.get("vfs_quota_bytes")
        if quota is None:
            quota = 524288000
        result.append(AdminUserOut(
            id=u["id"], username=u["username"], email=u["email"],
            is_admin=bool(u.get("is_admin", 0)),
            created_at=u["created_at"],
            vfs_quota_bytes=quota,
        ))
    return result


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: AdminCreateUser, admin: dict = Depends(require_admin)):
    """Crée un compte utilisateur (possibilité de créer un autre admin)."""
    try:
        user = user_manager.create_user(
            payload.username, payload.email, payload.password, payload.is_admin,
            vfs_quota_bytes=payload.vfs_quota_bytes,
        )
        _log.info("[admin] Compte créé par %s : %s (admin=%s)",
                  admin["username"], payload.username, payload.is_admin)
        return AdminUserOut(
            id=user["id"], username=user["username"], email=user["email"],
            is_admin=bool(user.get("is_admin", False)),
            created_at=user["created_at"],
            vfs_quota_bytes=user.get("vfs_quota_bytes", 524288000),
        )
    except user_manager.UserExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom d'utilisateur ou cet email est déjà utilisé.",
        )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    """
    Supprime un utilisateur et toutes ses données (secrets, historique).
    L'admin ne peut pas se supprimer lui-même.
    """
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas supprimer votre propre compte.",
        )

    target = user_manager.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    # Supprimer le répertoire de données de l'utilisateur (historique, VFS…)
    user_data_dir = _DATA_DIR / user_id
    if user_data_dir.exists():
        shutil.rmtree(user_data_dir, ignore_errors=True)
        _log.info("[admin] Répertoire data/%s supprimé.", user_id)

    try:
        user_manager.delete_user(user_id)
        _log.info("[admin] Utilisateur supprimé par %s : %s", admin["username"], user_id)
    except user_manager.UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")


@router.patch("/users/{user_id}/admin", status_code=status.HTTP_204_NO_CONTENT)
async def set_admin(user_id: str, payload: AdminSetAdmin, admin: dict = Depends(require_admin)):
    """
    Accorde ou révoque les droits administrateur d'un utilisateur.
    Un admin ne peut pas se rétrograder lui-même.
    """
    if user_id == admin["id"] and not payload.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas vous retirer vos propres droits admin.",
        )

    target = user_manager.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    user_manager.set_admin(user_id, payload.is_admin)
    _log.info("[admin] %s a défini is_admin=%s pour %s",
              admin["username"], payload.is_admin, target["username"])


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(user_id: str, payload: AdminResetPassword, admin: dict = Depends(require_admin)):
    """Réinitialise le mot de passe d'un utilisateur."""
    target = user_manager.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    user_manager.reset_password(user_id, payload.new_password)
    _log.info("[admin] Mot de passe réinitialisé par %s pour %s",
              admin["username"], target["username"])


# ── Routes quota VFS ──────────────────────────────────────────────────────────

@router.get("/users/{user_id}/vfs-usage")
async def get_user_vfs_usage(user_id: str, admin: dict = Depends(require_admin)):
    """Retourne le quota et l'utilisation VFS d'un utilisateur."""
    target = user_manager.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    try:
        vfs = VirtualFS(user_id)
        return vfs.quota()
    except Exception as e:
        _log.warning("[admin] Impossible de lire le VFS de %s : %s", user_id, e)
        # Retourner des stats vides si le VFS n'est pas encore initialisé
        quota_bytes = user_manager.get_vfs_quota(user_id)
        return {
            "user_id": user_id,
            "total_files": 0,
            "total_size": "0 B",
            "total_bytes": 0,
            "quota_limit_bytes": quota_bytes,
            "quota_limit": _fmt_bytes(quota_bytes),
            "quota_used_pct": 0.0,
            "quota_exceeded": False,
            "backend": "garage",
        }


@router.patch("/users/{user_id}/vfs-quota", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_vfs_quota(user_id: str, payload: AdminSetVfsQuota, admin: dict = Depends(require_admin)):
    """Définit le quota VFS (en octets) d'un utilisateur."""
    target = user_manager.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    try:
        user_manager.set_vfs_quota(user_id, payload.quota_bytes)
        _log.info("[admin] Quota VFS de %s défini à %d o par %s",
                  target["username"], payload.quota_bytes, admin["username"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/vfs-default-quota")
async def get_default_vfs_quota(admin: dict = Depends(require_admin)):
    """Retourne le quota VFS par défaut (en octets)."""
    import os
    default_bytes = int(os.getenv("DEFAULT_VFS_QUOTA_BYTES", str(500 * 1024 * 1024)))
    return {"quota_bytes": default_bytes, "quota_label": _fmt_bytes(default_bytes)}


@router.patch("/vfs-default-quota", status_code=status.HTTP_204_NO_CONTENT)
async def set_default_vfs_quota(payload: AdminSetDefaultVfsQuota, admin: dict = Depends(require_admin)):
    """Modifie le quota VFS par défaut (nouveaux utilisateurs uniquement)."""
    try:
        user_manager.set_default_vfs_quota(payload.quota_bytes)
        _log.info("[admin] Quota VFS par défaut mis à %d o par %s",
                  payload.quota_bytes, admin["username"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _fmt_bytes(n: int) -> str:
    for unit in ["o", "Ko", "Mo", "Go", "To"]:
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} To"
