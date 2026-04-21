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
config.py — Chargement de la configuration depuis .env

Paramètres système partagés entre tous les utilisateurs du serveur.

Les collections Qdrant (QDRANT_COLLECTION, LTM_COLLECTION) sont intentionnellement
absentes de cette classe — elles sont propres à chaque utilisateur et calculées
dynamiquement par UserConfig (core/user_config.py) à partir du username.
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

# Cherche le .env à la racine du projet (dossier parent de core/)
_env_path = Path(__file__).parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(".env")
load_dotenv(_env_path)


class Config:
    # OpenAI-compatible (valeurs par défaut serveur — peuvent être surchargées par UserConfig)
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "")
    OPENAI_API_KEY: str  = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str    = os.getenv("OPENAI_MODEL", "")

    # Qdrant — URL et clé d'API partagées entre tous les utilisateurs
    QDRANT_URL:     str = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    # NOTE : QDRANT_COLLECTION et LTM_COLLECTION sont absents volontairement.
    # Chaque utilisateur a ses propres collections, calculées par UserConfig :
    #   QDRANT_COLLECTION → f"promethee_{username}"
    #   LTM_COLLECTION    → f"promethee_memory_{username}"

    # Embeddings
    EMBEDDING_MODE: str      = os.getenv("EMBEDDING_MODE", "")
    EMBEDDING_MODEL: str     = os.getenv("EMBEDDING_MODEL", "")
    EMBEDDING_API_BASE: str  = os.getenv("EMBEDDING_API_BASE", "")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

    # Audio / Whisper
    AUDIO_MODEL: str = os.getenv("AUDIO_MODEL", "")

    # ── Modèles spécialisés par tâche ────────────────────────────────────────
    SPECIALIST_CODE_BACKEND:  str = os.getenv("SPECIALIST_CODE_BACKEND",  "").strip().lower()
    SPECIALIST_CODE_MODEL:    str = os.getenv("SPECIALIST_CODE_MODEL",    "").strip()
    SPECIALIST_CODE_BASE_URL: str = os.getenv("SPECIALIST_CODE_BASE_URL", "").strip()

    SPECIALIST_SUMMARY_BACKEND:  str = os.getenv("SPECIALIST_SUMMARY_BACKEND",  "").strip().lower()
    SPECIALIST_SUMMARY_MODEL:    str = os.getenv("SPECIALIST_SUMMARY_MODEL",    "").strip()
    SPECIALIST_SUMMARY_BASE_URL: str = os.getenv("SPECIALIST_SUMMARY_BASE_URL", "").strip()

    @classmethod
    def specialist_config(cls, task: str) -> dict | None:
        t = task.upper()
        model    = getattr(cls, f"SPECIALIST_{t}_MODEL",    "")
        backend  = getattr(cls, f"SPECIALIST_{t}_BACKEND",  "")
        base_url = getattr(cls, f"SPECIALIST_{t}_BASE_URL", "")

        if not model:
            return None

        if not backend:
            backend = "openai"

        if not base_url:
            base_url = cls.OPENAI_API_BASE

        return {"backend": backend, "model": model, "base_url": base_url}

    # Grist
    GRIST_API_KEY: str  = os.getenv("GRIST_API_KEY", "")
    GRIST_BASE_URL: str = os.getenv("GRIST_BASE_URL", "https://docs.getgrist.com")

    # Thunderbird
    TB_PROFILE_PATH: str = os.getenv("TB_PROFILE_PATH", "")

    # App
    APP_TITLE: str   = os.getenv("APP_TITLE", "Prométhée AI")
    APP_VERSION: str = os.getenv("APP_VERSION", "3.0.0")
    APP_USER: str    = os.getenv("APP_USER", "Vous")
    HISTORY_DB: str  = os.getenv("HISTORY_DB", "history.db")

    MAX_CONTEXT_TOKENS: int    = int(os.getenv("MAX_CONTEXT_TOKENS", "") or "8000")
    TOOL_RESULT_MAX_CHARS: int = int(os.getenv("TOOL_RESULT_MAX_CHARS", "12000"))
    AGENT_MAX_ITERATIONS: int  = int(os.getenv("AGENT_MAX_ITERATIONS", "8"))

    # Chiffrement de la base SQLite
    DB_ENCRYPTION: bool        = os.getenv("DB_ENCRYPTION", "OFF").strip().upper() == "ON"
    DB_ENCRYPTION_SEARCH: bool = os.getenv("DB_ENCRYPTION_SEARCH", "ON").strip().upper() == "ON"

    # Compression de contexte
    CONTEXT_MODEL_MAX_TOKENS: int       = int(os.getenv("CONTEXT_MODEL_MAX_TOKENS", "128000"))
    CONTEXT_HISTORY_MAX_TOKENS: int     = int(os.getenv("CONTEXT_HISTORY_MAX_TOKENS", "100000"))
    CONTEXT_HISTORY_MAX_CHARS: int      = int(os.getenv("CONTEXT_HISTORY_MAX_CHARS", "400000"))
    CONTEXT_AGENT_COMPRESS_AFTER: int   = int(os.getenv("CONTEXT_AGENT_COMPRESS_AFTER", "8"))
    CONTEXT_TOOL_RESULT_SUMMARY_CHARS: int = int(os.getenv("CONTEXT_TOOL_RESULT_SUMMARY_CHARS", "2600"))
    CONTEXT_CONSOLIDATION_EVERY: int    = int(os.getenv("CONTEXT_CONSOLIDATION_EVERY", "8"))
    CONTEXT_CONSOLIDATION_MAX_CHARS: int = int(os.getenv("CONTEXT_CONSOLIDATION_MAX_CHARS", "2500"))
    CONTEXT_PINNING_ENABLED: bool       = os.getenv("CONTEXT_PINNING_ENABLED", "ON").strip().upper() == "ON"
    CONTEXT_CONSOLIDATION_PRESSURE_THRESHOLD: float = float(
        os.getenv("CONTEXT_CONSOLIDATION_PRESSURE_THRESHOLD", "0.70")
    )

    # RAG
    RAG_TOP_K: int                = int(os.getenv("RAG_TOP_K", "15"))
    RAG_MIN_SCORE: float          = float(os.getenv("RAG_MIN_SCORE", "0.60"))
    RAG_MAX_CHUNKS_PER_SOURCE: int = int(os.getenv("RAG_MAX_CHUNKS_PER_SOURCE", "2"))
    RAG_MAX_CHUNKS_TOTAL: int     = int(os.getenv("RAG_MAX_CHUNKS_TOTAL", "8"))
    RAG_SEARCH_METHOD: str        = os.getenv("RAG_SEARCH_METHOD", "hybrid")
    RAG_RFF_K: int                = int(os.getenv("RAG_RFF_K", "60"))
    RAG_ALBERT_COLLECTION_IDS: list[int] = [
        int(x.strip())
        for x in os.getenv("RAG_ALBERT_COLLECTION_IDS", "").split(",")
        if x.strip().isdigit()
    ]
    RAG_RERANK_MODEL: str         = os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    RAG_RERANK_MIN_SCORE: float   = float(os.getenv("RAG_RERANK_MIN_SCORE", "-2.0"))
    RAG_RERANK_ENABLED: bool      = os.getenv("RAG_RERANK_ENABLED", "ON").strip().upper() == "ON"
    RAG_RERANK_API_BASE: str      = os.getenv("RAG_RERANK_API_BASE", "").strip().rstrip("/")
    RAG_HYDE_ENABLED: bool        = os.getenv("RAG_HYDE_ENABLED", "OFF").strip().upper() == "ON"
    RAG_HYDE_MAX_TOKENS: int      = int(os.getenv("RAG_HYDE_MAX_TOKENS", "200"))
    RAG_CONTEXTUAL_CHUNKING: bool = os.getenv("RAG_CONTEXTUAL_CHUNKING", "OFF").strip().upper() == "ON"
    RAG_CONTEXTUAL_PREFIX_MAX_TOKENS: int = int(os.getenv("RAG_CONTEXTUAL_PREFIX_MAX_TOKENS", "100"))
    RAG_CONTEXTUAL_DOC_MAX_CHARS: int     = int(os.getenv("RAG_CONTEXTUAL_DOC_MAX_CHARS", "10000"))
    RAG_INGESTION_MODEL: str      = os.getenv("RAG_INGESTION_MODEL", "").strip()
    RAG_ADAPTIVE_THRESHOLD: bool  = os.getenv("RAG_ADAPTIVE_THRESHOLD", "ON").strip().upper() == "ON"
    RAG_ADAPTIVE_SIGMA: float     = float(os.getenv("RAG_ADAPTIVE_SIGMA", "1.0"))

    # Mémoire long terme
    LTM_ENABLED: bool               = os.getenv("LTM_ENABLED", "OFF").strip().upper() == "ON"
    LTM_EXCHANGES_PER_CHUNK: int    = int(os.getenv("LTM_EXCHANGES_PER_CHUNK", "6"))
    LTM_MAX_CHARS_PER_MSG: int      = int(os.getenv("LTM_MAX_CHARS_PER_MSG", "600"))
    LTM_TOP_K: int                  = int(os.getenv("LTM_TOP_K", "4"))
    LTM_MIN_SCORE: float            = float(os.getenv("LTM_MIN_SCORE", "0.45"))
    LTM_MIN_MESSAGES: int           = int(os.getenv("LTM_MIN_MESSAGES", "4"))
    LTM_RECENT_K: int               = int(os.getenv("LTM_RECENT_K", "2"))
    LTM_MODEL: str                  = os.getenv("LTM_MODEL", "").strip()
    LTM_USE_SUMMARY: bool           = os.getenv("LTM_USE_SUMMARY", "OFF").strip().upper() == "ON"
    LTM_SUMMARY_MAX_CHARS: int      = int(os.getenv("LTM_SUMMARY_MAX_CHARS", "1200"))
    LTM_CONSOLIDATION_EVERY: int    = int(os.getenv("LTM_CONSOLIDATION_EVERY", "20"))
    LTM_CONSOLIDATION_MAX_CHUNKS: int = int(os.getenv("LTM_CONSOLIDATION_MAX_CHUNKS", "30"))

    # Interface
    SIDEBAR_MAX_CONVERSATIONS: int = int(os.getenv("SIDEBAR_MAX_CONVERSATIONS", "10"))

    # Garage — stockage objets S3-compatible (VFS)
    GARAGE_ENDPOINT:   str  = os.getenv("GARAGE_ENDPOINT",   "http://localhost:3900")
    GARAGE_ACCESS_KEY: str  = os.getenv("GARAGE_ACCESS_KEY", "")
    GARAGE_SECRET_KEY: str  = os.getenv("GARAGE_SECRET_KEY", "")
    GARAGE_BUCKET:     str  = os.getenv("GARAGE_BUCKET",     "promethee-vfs")
    GARAGE_REGION:     str  = os.getenv("GARAGE_REGION",     "Analog")

    @classmethod
    def active_model(cls) -> str:
        return cls.OPENAI_MODEL

    @classmethod
    def mode_label(cls) -> str:
        return f"🔵 Albert (OpenAI) · {cls.OPENAI_MODEL}"
