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
user_config.py — Configuration dynamique par utilisateur.

Hiérarchie de résolution pour chaque clé sensible :
  Secret utilisateur > Config globale (.env) > os.getenv() > vide
"""

from __future__ import annotations

import os
import re

from .config import Config
from . import user_manager


def _safe_username(username: str) -> str:
    """Normalise un username pour l'utiliser dans un nom de collection Qdrant.

    Règles Qdrant : caractères autorisés = [a-zA-Z0-9_], longueur max 255.
    On passe tout en minuscules et on remplace les caractères non autorisés par _.
    """
    return re.sub(r"[^a-z0-9]+", "_", username.lower()).strip("_") or "user"


class UserConfig:
    """Configuration contextuelle d'un utilisateur."""

    def __init__(self, user_id: str, secrets: dict, username: str = ""):
        self._user_id  = user_id
        self._secrets  = secrets   # {service: {key_name: value}}
        self._username = username  # stocké pour éviter un aller-retour DB à chaque accès

    @classmethod
    def from_user_id(cls, user_id: str) -> "UserConfig":
        secrets = user_manager.get_all_secrets(user_id)
        user    = user_manager.get_user_by_id(user_id)
        username = user["username"] if user else user_id
        return cls(user_id, secrets, username)

    def _get(self, service: str, key: str, fallback: str = "") -> str:
        val = self._secrets.get(service, {}).get(key, "")
        return val if val else fallback

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    # ── Albert / LLM ──────────────────────────────────────────────────────────

    @property
    def OPENAI_API_KEY(self) -> str:
        return self._get("albert", "OPENAI_API_KEY", Config.OPENAI_API_KEY)

    @property
    def OPENAI_API_BASE(self) -> str:
        return self._get("albert", "OPENAI_API_BASE", Config.OPENAI_API_BASE)

    @property
    def OPENAI_MODEL(self) -> str:
        return self._get("albert", "OPENAI_MODEL", Config.OPENAI_MODEL)

    def active_model(self) -> str:
        return self.OPENAI_MODEL

    # ── Légifrance (fallback os.getenv — absent de Config) ────────────────────

    @property
    def LEGIFRANCE_CLIENT_ID(self) -> str:
        return self._get("legifrance", "LEGIFRANCE_CLIENT_ID",
                         os.getenv("LEGIFRANCE_CLIENT_ID", ""))

    @property
    def LEGIFRANCE_CLIENT_SECRET(self) -> str:
        return self._get("legifrance", "LEGIFRANCE_CLIENT_SECRET",
                         os.getenv("LEGIFRANCE_CLIENT_SECRET", ""))

    @property
    def LEGIFRANCE_OAUTH_URL(self) -> str:
        return self._get("legifrance", "LEGIFRANCE_OAUTH_URL",
                         os.getenv("LEGIFRANCE_OAUTH_URL",
                                   "https://oauth.piste.gouv.fr/api/oauth/token"))

    @property
    def LEGIFRANCE_API_URL(self) -> str:
        return self._get("legifrance", "LEGIFRANCE_API_URL",
                         os.getenv("LEGIFRANCE_API_URL",
                                   "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"))

    # ── Judilibre ─────────────────────────────────────────────────────────────

    @property
    def JUDILIBRE_CLIENT_ID(self) -> str:
        return self._get("judilibre", "JUDILIBRE_CLIENT_ID",
                         os.getenv("JUDILIBRE_CLIENT_ID", ""))

    @property
    def JUDILIBRE_CLIENT_SECRET(self) -> str:
        return self._get("judilibre", "JUDILIBRE_CLIENT_SECRET",
                         os.getenv("JUDILIBRE_CLIENT_SECRET", ""))

    # ── Grist ─────────────────────────────────────────────────────────────────

    @property
    def GRIST_API_KEY(self) -> str:
        return self._get("grist", "GRIST_API_KEY", Config.GRIST_API_KEY)

    @property
    def GRIST_BASE_URL(self) -> str:
        return self._get("grist", "GRIST_BASE_URL", Config.GRIST_BASE_URL)

    # ── IMAP / SMTP ───────────────────────────────────────────────────────────

    @property
    def IMAP_HOST(self) -> str:
        return self._get("imap", "IMAP_HOST", os.getenv("IMAP_HOST", ""))

    @property
    def IMAP_PORT(self) -> int:
        val = self._get("imap", "IMAP_PORT")
        return int(val) if val else int(os.getenv("IMAP_PORT", "993"))

    @property
    def IMAP_USER(self) -> str:
        return self._get("imap", "IMAP_USER", os.getenv("IMAP_USER", ""))

    @property
    def IMAP_PASSWORD(self) -> str:
        return self._get("imap", "IMAP_PASSWORD", os.getenv("IMAP_PASSWORD", ""))

    @property
    def IMAP_SSL(self) -> bool:
        val = self._get("imap", "IMAP_SSL")
        if val:
            return val.upper() == "ON"
        return os.getenv("IMAP_SSL", "ON").upper() == "ON"

    @property
    def SMTP_HOST(self) -> str:
        return self._get("imap", "SMTP_HOST", os.getenv("SMTP_HOST", ""))

    @property
    def SMTP_PORT(self) -> int:
        val = self._get("imap", "SMTP_PORT")
        return int(val) if val else int(os.getenv("SMTP_PORT", "465"))

    @property
    def SMTP_SSL(self) -> bool:
        val = self._get("imap", "SMTP_SSL")
        if val:
            return val.upper() == "ON"
        return os.getenv("SMTP_SSL", "ON").upper() == "ON"

    # ── Embedding ─────────────────────────────────────────────────────────────

    @property
    def EMBEDDING_API_BASE(self) -> str:
        return self._get("embedding", "EMBEDDING_API_BASE", Config.EMBEDDING_API_BASE)

    @property
    def EMBEDDING_MODEL(self) -> str:
        return self._get("embedding", "EMBEDDING_MODEL", Config.EMBEDDING_MODEL)

    # ── Qdrant / RAG ──────────────────────────────────────────────────────────

    @property
    def QDRANT_URL(self) -> str:
        return Config.QDRANT_URL

    @property
    def QDRANT_COLLECTION(self) -> str:
        """Collection RAG isolée par utilisateur, nommée d'après son username.

        Exemple : username "pierre" → "promethee_pierre"
                  username "alice"  → "promethee_alice"

        Le username est normalisé (minuscules, caractères spéciaux → _)
        pour respecter les contraintes de nommage Qdrant.
        Les usernames étant immuables dans Prométhée, ce nom de collection
        est stable pour toute la durée de vie du compte.
        """
        return f"promethee_{_safe_username(self._username)}"

    @property
    def LTM_COLLECTION(self) -> str:
        """Collection mémoire long terme isolée par utilisateur.

        Exemple : username "pierre" → "promethee_memory_pierre"
        """
        return f"promethee_memory_{_safe_username(self._username)}"

    # ── Fallback Config pour tout le reste ────────────────────────────────────

    def __getattr__(self, name: str):
        """
        Délègue à Config pour les paramètres système non surchargés
        (AGENT_MAX_ITERATIONS, MAX_CONTEXT_TOKENS, etc.).
        Lève AttributeError proprement si absent de Config aussi.
        """
        try:
            return getattr(Config, name)
        except AttributeError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}' "
                f"(absent de UserConfig et de Config)"
            )
