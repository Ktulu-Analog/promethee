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
deps.py — Injection de dépendances FastAPI

Dépendances disponibles
───────────────────────
  get_current_user(token)  → dict utilisateur (depuis JWT)
  get_user_config()        → UserConfig avec les secrets de l'utilisateur
  get_db()                 → HistoryDB isolée par utilisateur (data/{user_id}/history.db)
  get_db_admin()           → HistoryDB globale (routes admin / legacy Qt unlock)

Rétrocompatibilité
───────────────────
  _db / set_db() sont conservés pour la route /auth/unlock (mode mono-user).
  En mode multi-user, get_db() crée une HistoryDB par user_id.
"""

import logging
from pathlib import Path

from fastapi import Depends, HTTPException, status, Header, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from core.database import HistoryDB
from core.config import Config
from core import user_manager
from core.user_config import UserConfig

_log = logging.getLogger(__name__)

# ── DB globale (mode mono-user / admin) ───────────────────────────────────
_db: HistoryDB | None = None


def set_db(db: HistoryDB) -> None:
    """Appelé par le lifespan pour la DB globale (mode admin)."""
    global _db
    _db = db


# ── Auth JWT ──────────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _decode_token(token: str | None) -> dict:
    """Décode le JWT et retourne le payload. Lève HTTP 401 si invalide."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Non authentifié. Connectez-vous via POST /auth/login.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return user_manager.decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
) -> dict:
    """
    Dépendance FastAPI : retourne le dict utilisateur depuis le JWT.

    Le token peut être fourni :
      - En header  : Authorization: Bearer <token>
      - (WS)       : query param ?token=<token>  — géré séparément dans ws_chat.py
    """
    payload = _decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token malformé.")
    user = user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable.")
    return user


async def get_current_user_config(
    user: dict = Depends(get_current_user),
) -> UserConfig:
    """Retourne le UserConfig complet (paramètres + secrets) de l'utilisateur courant."""
    return UserConfig.from_user_id(user["id"])


# ── DB par utilisateur ────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).parent.parent / "data"


async def get_db(
    user: dict = Depends(get_current_user),
) -> HistoryDB:
    """
    Retourne la HistoryDB isolée de l'utilisateur courant.
    Chemin : data/{user_id}/history.db (créé à la première connexion).
    """
    user_dir = _DATA_DIR / user["id"]
    user_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(user_dir / "history.db")
    return HistoryDB(db_path=db_path)


# ── DB globale (admin / legacy Qt unlock) ────────────────────────────────────

def get_db_admin() -> HistoryDB:
    """
    Retourne la DB globale (mode mono-user).
    Utilisée uniquement par /auth/status et /auth/unlock.
    """
    if _db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de données non initialisée.",
        )
    if Config.DB_ENCRYPTION and not _db.is_encrypted():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La base de données est chiffrée. Déverrouillez-la via POST /auth/unlock.",
            headers={"X-Requires-Unlock": "true"},
        )
    return _db


# ── Auth sans DB (pour les routes qui n'utilisent pas la DB) ─────────────────

async def require_auth(user: dict = Depends(get_current_user)) -> dict:
    """
    Dépendance légère : valide le JWT et retourne l'utilisateur,
    sans ouvrir ni créer la HistoryDB.
    
    À utiliser dans les routes qui ont besoin de l'auth mais pas de la DB
    (settings, tools, rag, profiles, upload, monitoring).
    """
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Dépendance : valide le JWT et vérifie que l'utilisateur est admin.
    Lève HTTP 403 si ce n'est pas le cas.
    """
    if not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs.",
        )
    return user
