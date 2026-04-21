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
routers/settings.py — Lecture et écriture des paramètres (.env)

Équivalent de SettingsDialog (ui/dialogs/settings_dialog.py).

Onglets du SettingsDialog Qt → endpoints :
    Modèle    → GET/PATCH /settings + GET /settings/models
    Outils    → géré par tools_router.py (familles + modèles par famille)
    Système   → GET/PATCH /settings (clés CONTEXT_*, AGENT_*)
    RAG       → GET/PATCH /settings (clés RAG_*, QDRANT_*, EMBEDDING_*)
    Interface → GET/PATCH /settings (clés APP_*, DB_ENCRYPTION)
    Mes clés  → GET/PUT /auth/me/apikeys  (router auth.py — secrets chiffrés par user)

Routes :
    GET    /settings          Snapshot des paramètres non-sensibles
    PATCH  /settings          Mise à jour d'une ou plusieurs clés
                              → clés système → .env
                              → clés personnelles → user_secrets (chiffré)
    GET    /settings/models   Découverte des modèles (Ollama ou OpenAI-compat)
    POST   /settings/reload   Force le rechargement de Config depuis .env

Migration multi-utilisateurs
─────────────────────────────
Les clés personnelles (identifiants de services, mots de passe, clés API)
ne sont JAMAIS écrites dans .env. Elles sont stockées chiffrées dans
data/users.db (table user_secrets) via user_manager.set_secret().

La résolution à l'exécution est assurée par UserConfig (core/user_config.py)
qui applique la cascade : secret user > Config(.env) > os.getenv.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.config import Config
from core import user_manager
from server.deps import get_db, require_auth, get_current_user_config, get_current_user
from server.schemas import SettingsPatch, SettingsOut

_log = logging.getLogger(__name__)
router = APIRouter()

_ROOT = Path(__file__).parent.parent.parent
_ENV_PATH = _ROOT / ".env"


# ── Clés personnelles → user_secrets (jamais dans .env) ──────────────────────
#
# Chaque entrée : "CLE_ENV": ("service", "key_name")
# Doit correspondre exactement au dictionnaire SERVICES dans user_manager.py.
#
_USER_SECRET_KEYS: dict[str, tuple[str, str]] = {
    # Albert / OpenAI-compatible
    "OPENAI_API_KEY":            ("albert",      "OPENAI_API_KEY"),
    "OPENAI_API_BASE":           ("albert",      "OPENAI_API_BASE"),
    "OPENAI_MODEL":              ("albert",      "OPENAI_MODEL"),
    # Légifrance
    "LEGIFRANCE_CLIENT_ID":      ("legifrance",  "LEGIFRANCE_CLIENT_ID"),
    "LEGIFRANCE_CLIENT_SECRET":  ("legifrance",  "LEGIFRANCE_CLIENT_SECRET"),
    "LEGIFRANCE_OAUTH_URL":      ("legifrance",  "LEGIFRANCE_OAUTH_URL"),
    "LEGIFRANCE_API_URL":        ("legifrance",  "LEGIFRANCE_API_URL"),
    # Judilibre
    "JUDILIBRE_CLIENT_ID":       ("judilibre",   "JUDILIBRE_CLIENT_ID"),
    "JUDILIBRE_CLIENT_SECRET":   ("judilibre",   "JUDILIBRE_CLIENT_SECRET"),
    # Grist
    "GRIST_API_KEY":             ("grist",       "GRIST_API_KEY"),
    "GRIST_BASE_URL":            ("grist",       "GRIST_BASE_URL"),
    # IMAP / SMTP
    "IMAP_HOST":                 ("imap",        "IMAP_HOST"),
    "IMAP_PORT":                 ("imap",        "IMAP_PORT"),
    "IMAP_USER":                 ("imap",        "IMAP_USER"),
    "IMAP_PASSWORD":             ("imap",        "IMAP_PASSWORD"),
    "IMAP_SSL":                  ("imap",        "IMAP_SSL"),
    "SMTP_HOST":                 ("imap",        "SMTP_HOST"),
    "SMTP_PORT":                 ("imap",        "SMTP_PORT"),
    "SMTP_SSL":                  ("imap",        "SMTP_SSL"),
    # Embeddings
    "EMBEDDING_API_BASE":        ("embedding",   "EMBEDDING_API_BASE"),
    "EMBEDDING_MODEL":           ("embedding",   "EMBEDDING_MODEL"),
}


def _save_env(key: str, value: str) -> None:
    """Écrit une clé dans .env (crée le fichier depuis .env.example si absent)."""
    from dotenv import set_key
    if not _ENV_PATH.exists():
        src = _ROOT / ".env.example"
        if src.exists():
            import shutil
            shutil.copy(src, _ENV_PATH)
        else:
            _ENV_PATH.touch()
    set_key(str(_ENV_PATH), key, value)
    _log.info("[settings] .env ← %s=%s", key, value if "KEY" not in key and "SECRET" not in key and "PASSWORD" not in key else "***")


# ── Snapshot des paramètres ───────────────────────────────────────────────────

@router.get("", response_model=SettingsOut)
async def get_settings(user_cfg = Depends(get_current_user_config)):
    """
    Retourne un snapshot des paramètres courants.

    En mode multi-utilisateurs, les valeurs sensibles (clé API, modèle,
    URL de base) reflètent la configuration personnelle de l'utilisateur
    connecté — avec fallback sur Config (.env) si non configurées.
    OPENAI_API_KEY_SET indique si la clé est configurée pour cet utilisateur.
    """
    from core.long_term_memory import is_enabled as ltm_enabled
    from core.config import Config as C

    return SettingsOut(
        APP_TITLE=C.APP_TITLE,
        APP_VERSION=C.APP_VERSION or "3.0.0",
        APP_USER=user_cfg.user_id,
        OPENAI_API_BASE=user_cfg.OPENAI_API_BASE,
        OPENAI_API_KEY_SET=bool(user_cfg.OPENAI_API_KEY),
        OPENAI_MODEL=user_cfg.OPENAI_MODEL,
        QDRANT_URL=user_cfg.QDRANT_URL,
        RAG_USER_ID=user_cfg.user_id,
        QDRANT_COLLECTION=user_cfg.QDRANT_COLLECTION,
        EMBEDDING_MODE=C.EMBEDDING_MODE,
        EMBEDDING_MODEL=user_cfg.EMBEDDING_MODEL,
        EMBEDDING_API_BASE=user_cfg.EMBEDDING_API_BASE,
        EMBEDDING_DIMENSION=C.EMBEDDING_DIMENSION,
        RAG_TOP_K=C.RAG_TOP_K,
        RAG_MIN_SCORE=C.RAG_MIN_SCORE,
        RAG_RERANK_ENABLED=C.RAG_RERANK_ENABLED,
        AGENT_MAX_ITERATIONS=C.AGENT_MAX_ITERATIONS,
        MAX_CONTEXT_TOKENS=C.MAX_CONTEXT_TOKENS,
        CONTEXT_HISTORY_MAX_TOKENS=C.CONTEXT_HISTORY_MAX_TOKENS,
        DB_ENCRYPTION=C.DB_ENCRYPTION,
        LTM_ENABLED=ltm_enabled(),
        LTM_MODEL=getattr(C, "LTM_MODEL", ""),
    )


# ── Mise à jour des paramètres ────────────────────────────────────────────────

@router.patch("")
async def patch_settings(
    payload: SettingsPatch,
    user: dict = Depends(get_current_user),
):
    """
    Met à jour une ou plusieurs clés de configuration.

    Routage automatique selon le type de clé :
      • Clés personnelles (API keys, credentials) → user_secrets en base (chiffré AES-256-GCM)
      • Clés système (URLs partagées, flags, seuils) → .env

    Ce routage garantit que les secrets ne sont jamais écrits dans le .env
    partagé entre tous les utilisateurs du serveur.

    Exemple de body :
        { "updates": { "OPENAI_MODEL": "openai/gpt-4o", "LOCAL": "OFF" } }
    """
    if not payload.updates:
        return {"status": "no_changes"}

    system_updates: dict[str, str] = {}
    user_secret_updates: list[tuple[str, str, str]] = []  # (service, key_name, value)

    for key, value in payload.updates.items():
        if key in _USER_SECRET_KEYS:
            service, key_name = _USER_SECRET_KEYS[key]
            if value.strip():
                user_secret_updates.append((service, key_name, value.strip()))
            # Valeur vide → on ignore (ne pas écraser un secret existant avec "")
        else:
            system_updates[key] = value

    # Écriture des secrets personnels en base (chiffrés)
    for service, key_name, value in user_secret_updates:
        user_manager.set_secret(user["id"], service, key_name, value)
        _log.info("[settings] user_secrets ← user=%s %s/%s", user["username"], service, key_name)

    # Écriture des paramètres système dans .env
    for key, value in system_updates.items():
        _save_env(key, value)

    if system_updates:
        _reload_config()

    return {
        "status": "ok",
        "updated": list(payload.updates.keys()),
        "routed_to_db": [f"{s}/{k}" for s, k, _ in user_secret_updates],
        "routed_to_env": list(system_updates.keys()),
    }


def _reload_config():
    """
    Recharge Config depuis .env sans redémarrer le serveur.

    Config est une classe avec des attributs de classe — on recharge le module
    entier pour que load_dotenv() relise le fichier.

    NOTE : Les clients LLM déjà instanciés (openai.OpenAI()) ne sont PAS
    mis à jour automatiquement — ils seront recréés au prochain appel via
    build_client() qui lit Config à chaque appel.
    """
    import importlib
    import core.config as cfg_module
    try:
        importlib.reload(cfg_module)
        # Propager dans core/__init__.py qui réexporte Config
        import core
        importlib.reload(core)
        _log.info("[settings] Config rechargée depuis .env")
    except Exception as e:
        _log.warning("[settings] Impossible de recharger Config : %s", e)


# ── Découverte des modèles ────────────────────────────────────────────────────

@router.get("/models")
async def list_models(
    backend: str = Query("openai", description="'openai' (seul backend supporté)"),
    api_base: Optional[str] = Query(None),
    api_key: Optional[str] = Query(None),
    user_cfg = Depends(get_current_user_config),
):
    """
    Découvre les modèles disponibles sur le serveur OpenAI-compatible (Albert).

    Paramètres :
        backend   : ignoré, toujours 'openai'
        api_base  : surcharge OPENAI_API_BASE
        api_key   : surcharge OPENAI_API_KEY
    """
    try:
        models = await asyncio.to_thread(
            _fetch_openai_models,
            api_base or user_cfg.OPENAI_API_BASE,
            api_key or user_cfg.OPENAI_API_KEY,
        )
        return {"backend": "openai", "models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_openai_models(api_base: str, api_key: str) -> list[str]:
    """Récupère les modèles disponibles sur un serveur OpenAI-compatible."""
    try:
        from openai import OpenAI
        client = OpenAI(base_url=api_base, api_key=api_key or "dummy", timeout=10.0)
        return sorted(m.id for m in client.models.list().data)
    except Exception as e:
        _log.warning("[settings] OpenAI models fetch error: %s", e)
        return []


# ── Rechargement forcé ────────────────────────────────────────────────────────

@router.post("/reload")
async def reload_settings(_ = Depends(require_auth)):
    """Force le rechargement de Config depuis .env. Utile après édition manuelle."""
    _reload_config()
    return {"status": "reloaded"}
