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
routers/auth.py — Authentification multi-utilisateurs + gestion des clés API.

Routes publiques (sans JWT)
────────────────────────────
  POST /auth/register      Création de compte
  POST /auth/login         Login → JWT (OAuth2 form)
  POST /auth/login-json    Login → JWT (JSON, pour React)
  GET  /auth/status        État DB chiffrée (rétrocompat mono-user)
  POST /auth/unlock        Déverrouille DB chiffrée (rétrocompat mono-user)
  POST /auth/lock          Verrouille DB chiffrée (rétrocompat mono-user)

Routes protégées (JWT requis)
──────────────────────────────
  GET  /auth/me            Profil de l'utilisateur courant
  GET  /auth/me/apikeys    Statut des clés API (booléens)
  PUT  /auth/me/apikeys    Met à jour les clés API d'un service
  DELETE /auth/me/apikeys/{service}/{key_name}  Supprime une clé

Création des collections Qdrant
─────────────────────────────────
À chaque login, les deux collections Qdrant de l'utilisateur sont créées
si elles n'existent pas encore :
  - promethee_{username}         → RAG documentaire
  - promethee_memory_{username}  → mémoire long terme (LTM)

Cette création est non-bloquante (asyncio.to_thread) et silencieuse en cas
d'erreur (Qdrant indisponible → on logue et on continue).
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from typing import Optional

from core import user_manager, crypto
from core.user_config import UserConfig
from core.request_context import set_user_config
from server import deps
from server.deps import get_current_user

_log = logging.getLogger(__name__)
router = APIRouter()


# ── Schémas Pydantic ──────────────────────────────────────────────────────────

class RegisterPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    email: str    = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    is_admin: bool = False


class UserOut(BaseModel):
    id: str
    username: str
    email: str
    is_admin: bool = False
    created_at: str


class ApiKeyEntry(BaseModel):
    key_name: str
    value: str = ""


class ApiKeysPayload(BaseModel):
    service: str
    keys: list[ApiKeyEntry]


class LoginJsonPayload(BaseModel):
    username: str
    password: str


class UnlockPayload(BaseModel):
    passphrase: str


# ── Création des collections Qdrant ───────────────────────────────────────────

async def _ensure_user_collections(user_cfg: UserConfig) -> None:
    """Crée les collections Qdrant de l'utilisateur si elles n'existent pas.

    Appelée à chaque login — ensure_collection() est idempotente, elle ne
    fait rien si la collection existe déjà. L'opération est non-bloquante
    et silencieuse en cas d'indisponibilité de Qdrant.
    """
    from core import rag_engine

    if not rag_engine.is_available():
        _log.debug("[auth] Qdrant non disponible — création des collections ignorée.")
        return

    set_user_config(user_cfg)
    try:
        await asyncio.to_thread(rag_engine.ensure_collection, user_cfg.QDRANT_COLLECTION)
        _log.info("[auth] Collection RAG prête : %s", user_cfg.QDRANT_COLLECTION)
        await asyncio.to_thread(rag_engine.ensure_collection, user_cfg.LTM_COLLECTION)
        _log.info("[auth] Collection LTM prête : %s", user_cfg.LTM_COLLECTION)
    except Exception as e:
        _log.warning("[auth] Impossible de créer les collections Qdrant : %s", e)
    finally:
        set_user_config(None)


# ── Rétrocompat mono-user ─────────────────────────────────────────────────────

@router.get("/status")
async def auth_status():
    """État du chiffrement (rétrocompat mono-user) + indicateur multi-user."""
    encrypted_and_locked = False
    try:
        db = deps.get_db_admin()
    except HTTPException as e:
        encrypted_and_locked = (e.headers or {}).get("X-Requires-Unlock") == "true"
    from core.config import Config
    return {
        "encryption_enabled": Config.DB_ENCRYPTION,
        "locked": encrypted_and_locked,
        "crypto_available": crypto._CRYPTO_OK,
        "multi_user": True,
    }


@router.post("/unlock")
async def unlock(payload: UnlockPayload):
    """Déverrouille la DB chiffrée (rétrocompat mono-user)."""
    db = deps._db
    if db is None:
        raise HTTPException(status_code=503, detail="Base non initialisée.")
    from core.config import Config
    if not Config.DB_ENCRYPTION:
        return {"status": "ok", "encrypted": False}
    try:
        db.set_passphrase(payload.passphrase)
        return {"status": "ok", "encrypted": True}
    except Exception:
        raise HTTPException(status_code=403, detail="Passphrase incorrecte.")


@router.post("/lock")
async def lock():
    crypto.clear_key_cache()
    return {"status": "locked"}


# ── Inscription ───────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterPayload):
    try:
        user = user_manager.create_user(payload.username, payload.email, payload.password)
        _log.info("[auth] Nouveau compte : %s", payload.username)
        return UserOut(**user)
    except user_manager.UserExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom d'utilisateur ou cet email est déjà utilisé.",
        )


@router.post("/setup-admin", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def setup_admin(payload: RegisterPayload):
    """
    Crée le premier compte administrateur.
    Cette route n'est accessible que si aucun admin n'existe encore.
    Elle est ouverte (sans JWT) pour permettre l'initialisation.
    """
    try:
        user = user_manager.create_first_admin(payload.username, payload.email, payload.password)
        _log.info("[auth] Premier admin créé : %s", payload.username)
        return UserOut(**user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except user_manager.UserExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom d'utilisateur ou cet email est déjà utilisé.",
        )


@router.get("/admin-exists")
async def admin_exists():
    """Indique si un admin a déjà été créé (pour l'écran de setup initial)."""
    return {"exists": user_manager.count_admins() > 0}


# ── Connexion ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """Login OAuth2 standard (application/x-www-form-urlencoded)."""
    try:
        user = user_manager.authenticate_user(form.username, form.password)
    except (user_manager.UserNotFoundError, user_manager.BadCredentialsError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    is_admin = bool(user.get("is_admin", 0))
    token = user_manager.create_access_token(user["id"], user["username"], is_admin)
    _log.info("[auth] Connexion : %s (admin=%s)", user["username"], is_admin)
    user_cfg = UserConfig.from_user_id(user["id"])
    await _ensure_user_collections(user_cfg)
    return TokenResponse(access_token=token, user_id=user["id"], username=user["username"], is_admin=is_admin)


@router.post("/login-json", response_model=TokenResponse)
async def login_json(payload: LoginJsonPayload):
    """Login JSON pour le client React."""
    try:
        user = user_manager.authenticate_user(payload.username, payload.password)
    except (user_manager.UserNotFoundError, user_manager.BadCredentialsError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect.",
        )
    is_admin = bool(user.get("is_admin", 0))
    token = user_manager.create_access_token(user["id"], user["username"], is_admin)
    _log.info("[auth] Connexion : %s (admin=%s)", user["username"], is_admin)
    user_cfg = UserConfig.from_user_id(user["id"])
    await _ensure_user_collections(user_cfg)
    return TokenResponse(access_token=token, user_id=user["id"], username=user["username"], is_admin=is_admin)


# ── Profil utilisateur ────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def get_me(user: dict = Depends(get_current_user)):
    return UserOut(id=user["id"], username=user["username"],
                   email=user["email"], is_admin=bool(user.get("is_admin", 0)),
                   created_at=user["created_at"])


# ── Gestion des clés API ──────────────────────────────────────────────────────

@router.get("/me/apikeys")
async def get_apikeys(user: dict = Depends(get_current_user)):
    """Statut des clés API (booléens — jamais les valeurs)."""
    return user_manager.get_secrets_status(user["id"])


@router.get("/me/apikeys/values")
async def get_apikeys_values(user: dict = Depends(get_current_user)):
    """Valeurs en clair des champs non-sensibles (URL, modèle, port…).
    Les champs sensibles (clés API, mots de passe) sont retournés comme null."""
    return user_manager.get_secrets_plaintext(user["id"])


@router.put("/me/apikeys", status_code=status.HTTP_204_NO_CONTENT)
async def put_apikeys(payload: ApiKeysPayload, user: dict = Depends(get_current_user)):
    """Enregistre les clés API d'un service. Les valeurs vides sont ignorées."""
    if payload.service not in user_manager.SERVICES:
        raise HTTPException(
            status_code=400,
            detail=f"Service inconnu : {payload.service}. "
                   f"Services supportés : {', '.join(user_manager.SERVICES)}",
        )
    for entry in payload.keys:
        if entry.key_name not in user_manager.SERVICES[payload.service]:
            raise HTTPException(
                status_code=400,
                detail=f"Clé inconnue pour {payload.service} : {entry.key_name}",
            )
        if entry.value:
            user_manager.set_secret(user["id"], payload.service, entry.key_name, entry.value)
    _log.info("[auth] Clés API mises à jour : user=%s service=%s",
              user["username"], payload.service)


@router.delete("/me/apikeys/{service}/{key_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_apikey(service: str, key_name: str, user: dict = Depends(get_current_user)):
    user_manager.delete_secret(user["id"], service, key_name)
    _log.info("[auth] Clé supprimée : user=%s %s/%s", user["username"], service, key_name)
