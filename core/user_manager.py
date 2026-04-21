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
user_manager.py — Gestion des utilisateurs et authentification JWT.

Responsabilités
───────────────
  - Création / vérification des comptes (bcrypt)
  - Émission / validation des JWT (HS256, python-jose)
  - CRUD des secrets utilisateur (clés API chiffrées via core.crypto)

Base de données
───────────────
  Fichier séparé : data/users.db (ne jamais mélanger avec history.db)

  Tables :
    users         — comptes (id, username, email, password_hash, created_at)
    user_secrets  — clés API chiffrées (user_id, service, key_name, value)

Chiffrement des secrets
────────────────────────
  Les valeurs (clés API) sont chiffrées avec AES-256-GCM via core.crypto.
  La clé de chiffrement est dérivée d'un SECRET_KEY serveur (config.py ou
  variable d'environnement PROMETHEE_SECRET_KEY).
  En l'absence de SECRET_KEY, un avertissement est émis et un fallback
  non-sécurisé est utilisé (dev uniquement).

Rétrocompatibilité Qt6
───────────────────────
  Ce module n'est importé que par le serveur FastAPI. L'interface Qt6
  continue d'utiliser Config et .env directement — aucune interaction.
"""

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt as _bcrypt_lib
from jose import JWTError, jwt

from .config import Config
from . import crypto

_log = logging.getLogger(__name__)

# ── Configuration JWT ─────────────────────────────────────────────────────────

_SECRET_KEY: str = os.getenv("PROMETHEE_SECRET_KEY", "")
if not _SECRET_KEY:
    _log.warning(
        "[user_manager] PROMETHEE_SECRET_KEY non défini — utilisation d'une clé "
        "de développement non-sécurisée. DÉFINISSEZ CETTE VARIABLE EN PRODUCTION."
    )
    _SECRET_KEY = "dev-insecure-key-change-me-in-production"

_ALGORITHM       = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h

# ── Hachage des mots de passe ─────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return _bcrypt_lib.hashpw(plain.encode(), _bcrypt_lib.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt_lib.checkpw(plain.encode(), hashed.encode())


# ── Chiffrement des secrets utilisateur ──────────────────────────────────────

def _encrypt_secret(value: str) -> str:
    """Chiffre une clé API avec AES-256-GCM (réutilise core.crypto)."""
    return crypto.encrypt(value, _SECRET_KEY)


def _decrypt_secret(value: str) -> str:
    """Déchiffre une clé API. Retourne la valeur brute si non chiffrée (migration)."""
    try:
        return crypto.decrypt(value, _SECRET_KEY)
    except Exception:
        return value


# ── Base de données utilisateurs ─────────────────────────────────────────────

_DATA_DIR = Path(__file__).parent.parent / "data"
_USERS_DB  = _DATA_DIR / "users.db"


def _conn() -> sqlite3.Connection:
    _DATA_DIR.mkdir(exist_ok=True)
    c = sqlite3.connect(str(_USERS_DB))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


_DEFAULT_VFS_QUOTA_BYTES: int = int(os.getenv("DEFAULT_VFS_QUOTA_BYTES", str(500 * 1024 * 1024)))  # 500 Mo par défaut


def init_db() -> None:
    """Crée les tables si elles n'existent pas. Appelé au démarrage du serveur."""
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id           TEXT PRIMARY KEY,
                username     TEXT NOT NULL UNIQUE,
                email        TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin     INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_secrets (
                user_id   TEXT NOT NULL,
                service   TEXT NOT NULL,
                key_name  TEXT NOT NULL,
                value     TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, service, key_name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        # Migration : ajout de la colonne vfs_quota_bytes si elle n'existe pas
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
        if "vfs_quota_bytes" not in cols:
            c.execute(
                f"ALTER TABLE users ADD COLUMN vfs_quota_bytes INTEGER NOT NULL DEFAULT {_DEFAULT_VFS_QUOTA_BYTES}"
            )
            _log.info("[user_manager] Colonne vfs_quota_bytes ajoutée à la table users.")
    _log.info("[user_manager] Base users.db initialisée.")


# ── CRUD utilisateurs ─────────────────────────────────────────────────────────

class UserExistsError(Exception):
    """Un compte avec ce username ou cet email existe déjà."""


class UserNotFoundError(Exception):
    """Aucun utilisateur trouvé."""


class BadCredentialsError(Exception):
    """Mot de passe incorrect."""


def create_user(username: str, email: str, password: str, is_admin: bool = False,
                vfs_quota_bytes: Optional[int] = None) -> dict:
    """
    Crée un nouvel utilisateur.

    Returns
    -------
    dict : l'utilisateur créé (sans password_hash)

    Raises
    ------
    UserExistsError : si username ou email déjà utilisés.
    """
    uid  = str(uuid.uuid4())
    now  = datetime.now(timezone.utc).isoformat()
    phash = hash_password(password)
    quota = vfs_quota_bytes if vfs_quota_bytes is not None else _DEFAULT_VFS_QUOTA_BYTES
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (id, username, email, password_hash, is_admin, created_at, vfs_quota_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, username.strip(), email.strip().lower(), phash, int(is_admin), now, quota),
            )
        _log.info("[user_manager] Utilisateur créé : %s (%s) admin=%s quota=%d", username, uid, is_admin, quota)
        return {"id": uid, "username": username, "email": email, "is_admin": is_admin,
                "created_at": now, "vfs_quota_bytes": quota}
    except sqlite3.IntegrityError as e:
        raise UserExistsError(str(e)) from e


def get_user_by_username(username: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def authenticate_user(username: str, password: str) -> dict:
    """
    Vérifie les credentials et retourne l'utilisateur.

    Raises
    ------
    UserNotFoundError, BadCredentialsError
    """
    user = get_user_by_username(username)
    if not user:
        raise UserNotFoundError(username)
    if not verify_password(password, user["password_hash"]):
        raise BadCredentialsError()
    return user


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(user_id: str, username: str, is_admin: bool = False) -> str:
    """Émet un JWT signé HS256 avec expiration."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Décode et valide un JWT.

    Returns
    -------
    dict : payload (contient 'sub' = user_id, 'username')

    Raises
    ------
    JWTError : token invalide ou expiré.
    """
    return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])


# ── Secrets utilisateur (clés API) ───────────────────────────────────────────

# Services reconnus → liste des key_names attendus
# Champs sensibles : jamais renvoyés en clair vers le frontend.
# Tout ce qui n'est pas dans cette liste peut être pré-rempli en clair.
SENSITIVE_KEYS: set[str] = {
    "OPENAI_API_KEY",
    "LEGIFRANCE_CLIENT_ID",
    "LEGIFRANCE_CLIENT_SECRET",
    "JUDILIBRE_CLIENT_ID",
    "JUDILIBRE_CLIENT_SECRET",
    "GRIST_API_KEY",
    "IMAP_PASSWORD",
}

SERVICES: dict[str, list[str]] = {
    "albert": [
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "OPENAI_MODEL",
    ],
    "legifrance": [
        "LEGIFRANCE_CLIENT_ID",
        "LEGIFRANCE_CLIENT_SECRET",
        "LEGIFRANCE_OAUTH_URL",
        "LEGIFRANCE_API_URL",
    ],
    "judilibre": [
        "JUDILIBRE_CLIENT_ID",
        "JUDILIBRE_CLIENT_SECRET",
    ],
    "grist": [
        "GRIST_API_KEY",
        "GRIST_BASE_URL",
    ],
    "imap": [
        "IMAP_HOST",
        "IMAP_PORT",
        "IMAP_USER",
        "IMAP_PASSWORD",
        "IMAP_SSL",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_SSL",
    ],
    "embedding": [
        "EMBEDDING_API_BASE",
        "EMBEDDING_MODEL",
    ],
}


def set_secret(user_id: str, service: str, key_name: str, value: str) -> None:
    """Enregistre ou met à jour un secret chiffré."""
    now = datetime.now(timezone.utc).isoformat()
    encrypted = _encrypt_secret(value) if value else ""
    with _conn() as c:
        c.execute(
            "INSERT INTO user_secrets (user_id, service, key_name, value, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, service, key_name) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (user_id, service, key_name, encrypted, now),
        )


def get_secret(user_id: str, service: str, key_name: str) -> Optional[str]:
    """Retourne la valeur déchiffrée d'un secret, ou None."""
    with _conn() as c:
        row = c.execute(
            "SELECT value FROM user_secrets WHERE user_id=? AND service=? AND key_name=?",
            (user_id, service, key_name),
        ).fetchone()
    if not row or not row[0]:
        return None
    return _decrypt_secret(row[0])


def get_all_secrets(user_id: str) -> dict[str, dict[str, str]]:
    """
    Retourne tous les secrets d'un utilisateur sous forme
    {service: {key_name: value_déchiffré}}.
    """
    with _conn() as c:
        rows = c.execute(
            "SELECT service, key_name, value FROM user_secrets WHERE user_id=?",
            (user_id,),
        ).fetchall()
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        svc, kname, val = row["service"], row["key_name"], row["value"]
        result.setdefault(svc, {})[kname] = _decrypt_secret(val) if val else ""
    return result


def get_secrets_status(user_id: str) -> dict[str, dict[str, bool]]:
    """
    Retourne pour chaque service quelles clés sont configurées (booléen).
    Ne retourne jamais les valeurs — safe pour l'API publique.
    """
    secrets = get_all_secrets(user_id)
    status: dict[str, dict[str, bool]] = {}
    for service, keys in SERVICES.items():
        status[service] = {
            k: bool(secrets.get(service, {}).get(k, ""))
            for k in keys
        }
    return status


def get_secrets_plaintext(user_id: str) -> dict[str, dict[str, str | None]]:
    """
    Retourne pour chaque service les valeurs des champs NON sensibles en clair,
    et None pour les champs sensibles (clés API, mots de passe).
    Safe pour l'API publique : les secrets restent masqués.
    """
    secrets = get_all_secrets(user_id)
    result: dict[str, dict[str, str | None]] = {}
    for service, keys in SERVICES.items():
        result[service] = {}
        for k in keys:
            if k in SENSITIVE_KEYS:
                result[service][k] = None  # masqué
            else:
                result[service][k] = secrets.get(service, {}).get(k) or None
    return result


def delete_secret(user_id: str, service: str, key_name: str) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM user_secrets WHERE user_id=? AND service=? AND key_name=?",
            (user_id, service, key_name),
        )


# ── Administration ────────────────────────────────────────────────────────────

def list_users() -> list[dict]:
    """Retourne la liste de tous les utilisateurs (sans password_hash)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT id, username, email, is_admin, created_at, vfs_quota_bytes FROM users ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def count_users() -> int:
    """Retourne le nombre total d'utilisateurs."""
    with _conn() as c:
        row = c.execute("SELECT COUNT(*) FROM users").fetchone()
    return row[0] if row else 0


def count_admins() -> int:
    """Retourne le nombre d'admins."""
    with _conn() as c:
        row = c.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()
    return row[0] if row else 0


def set_admin(user_id: str, is_admin: bool) -> None:
    """Accorde ou révoque les droits admin d'un utilisateur."""
    with _conn() as c:
        c.execute(
            "UPDATE users SET is_admin=? WHERE id=?",
            (int(is_admin), user_id),
        )
    _log.info("[user_manager] is_admin=%s pour user_id=%s", is_admin, user_id)


def get_vfs_quota(user_id: str) -> int:
    """Retourne le quota VFS (en octets) d'un utilisateur."""
    with _conn() as c:
        row = c.execute(
            "SELECT vfs_quota_bytes FROM users WHERE id=?", (user_id,)
        ).fetchone()
    if not row:
        raise UserNotFoundError(user_id)
    return row["vfs_quota_bytes"] if row["vfs_quota_bytes"] is not None else _DEFAULT_VFS_QUOTA_BYTES


def set_vfs_quota(user_id: str, quota_bytes: int) -> None:
    """Définit le quota VFS (en octets) d'un utilisateur."""
    if quota_bytes < 0:
        raise ValueError("Le quota doit être un entier positif.")
    with _conn() as c:
        cur = c.execute(
            "UPDATE users SET vfs_quota_bytes=? WHERE id=?",
            (quota_bytes, user_id),
        )
    if cur.rowcount == 0:
        raise UserNotFoundError(user_id)
    _log.info("[user_manager] vfs_quota_bytes=%d pour user_id=%s", quota_bytes, user_id)


def set_default_vfs_quota(quota_bytes: int) -> None:
    """
    Met à jour le quota VFS par défaut (variable globale du module).
    Affecte uniquement les nouveaux utilisateurs créés après cet appel.
    Les utilisateurs existants conservent leur quota individuel.
    """
    global _DEFAULT_VFS_QUOTA_BYTES
    if quota_bytes < 0:
        raise ValueError("Le quota doit être un entier positif.")
    _DEFAULT_VFS_QUOTA_BYTES = quota_bytes
    _log.info("[user_manager] Quota VFS par défaut mis à jour : %d octets", quota_bytes)


def reset_password(user_id: str, new_password: str) -> None:
    """Réinitialise le mot de passe d'un utilisateur (action admin)."""
    phash = hash_password(new_password)
    with _conn() as c:
        c.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (phash, user_id),
        )
    _log.info("[user_manager] Mot de passe réinitialisé pour user_id=%s", user_id)


def delete_user(user_id: str) -> None:
    """
    Supprime un utilisateur et tous ses secrets (CASCADE).

    Raises
    ------
    UserNotFoundError : si l'utilisateur n'existe pas.
    """
    with _conn() as c:
        cur = c.execute("DELETE FROM users WHERE id=?", (user_id,))
    if cur.rowcount == 0:
        raise UserNotFoundError(user_id)
    _log.info("[user_manager] Utilisateur supprimé : user_id=%s", user_id)


def create_first_admin(username: str, email: str, password: str) -> dict:
    """
    Crée le premier compte admin uniquement si aucun admin n'existe.

    Raises
    ------
    ValueError      : si un admin existe déjà.
    UserExistsError : si username/email déjà pris.
    """
    if count_admins() > 0:
        raise ValueError("Un administrateur existe déjà.")
    return create_user(username, email, password, is_admin=True)
