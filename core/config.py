# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
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
"""
import getpass
import os
import platform
import re
from pathlib import Path
from dotenv import load_dotenv

# Cherche le .env à la racine du projet (dossier parent de core/)
_env_path = Path(__file__).parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(".env")
load_dotenv(_env_path)


def _qdrant_collection() -> str:
    """Calcule le nom de collection Qdrant de l'utilisateur courant.

    Priorité :
      1. QDRANT_COLLECTION dans .env  → respecté tel quel (rétro-compatibilité)
      2. RAG_USER_ID dans .env        → promethee_<rag_user_id>
      3. Nom d'utilisateur système    → promethee_<getuser()>
      4. Nom de machine               → promethee_<hostname>
      5. Fallback                     → promethee_default

    Le résultat est normalisé : minuscules, caractères non-alphanumériques → _.
    Calculée une seule fois au chargement du module (le .env est déjà chargé).
    """
    explicit = os.getenv("QDRANT_COLLECTION", "").strip()
    if explicit:
        return explicit

    user_id = os.getenv("RAG_USER_ID", "").strip()
    if not user_id:
        try:
            user_id = getpass.getuser()
        except Exception:
            user_id = platform.node()

    safe = re.sub(r"[^a-z0-9]+", "_", user_id.lower()).strip("_") or "default"
    return f"promethee_{safe}"


class Config:
    # Mode
    LOCAL: bool = os.getenv("LOCAL", "OFF").strip().upper() == "ON"

    # OpenAI-compatible
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "")

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "")

    # Qdrant
    QDRANT_URL: str = os.getenv("QDRANT_URL", "")

    # Identifiant utilisateur pour la collection Qdrant.
    # Priorité : RAG_USER_ID dans .env > nom d'utilisateur système > nom de machine.
    # Permet à plusieurs postes de partager un serveur Qdrant sans collision.
    RAG_USER_ID: str = os.getenv("RAG_USER_ID", "").strip()

    # Nom de la collection Qdrant calculé une fois au démarrage (voir _qdrant_collection()).
    # Rétro-compatible : tout accès à Config.QDRANT_COLLECTION continue de fonctionner.
    QDRANT_COLLECTION: str = _qdrant_collection()

    # Embeddings
    EMBEDDING_MODE: str = os.getenv("EMBEDDING_MODE", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "")
    EMBEDDING_API_BASE: str = os.getenv("EMBEDDING_API_BASE", "")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

    # Audio / Whisper
    AUDIO_MODEL: str = os.getenv("AUDIO_MODEL", "")

    # Grist
    GRIST_API_KEY: str = os.getenv("GRIST_API_KEY", "")
    GRIST_BASE_URL: str = os.getenv("GRIST_BASE_URL", "https://docs.getgrist.com")

    # Thunderbird
    TB_PROFILE_PATH: str = os.getenv("TB_PROFILE_PATH", "")

    # App
    APP_TITLE: str = os.getenv("APP_TITLE", "Prométhée AI")
    APP_USER: str = os.getenv("APP_USER", "Vous")
    HISTORY_DB: str = os.getenv("HISTORY_DB", "history.db")
    MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", ""))

    # Chiffrement de la base SQLite (AES-256-GCM, cle derivee via Scrypt)
    # DB_ENCRYPTION=ON  -> colonnes sensibles chiffrees (title, content, system_prompt, metadata)
    # DB_ENCRYPTION=OFF -> comportement identique a v2, aucune dependance crypto
    DB_ENCRYPTION: bool = os.getenv("DB_ENCRYPTION", "OFF").strip().upper() == "ON"
    # DB_ENCRYPTION_SEARCH=ON  -> index FTS5 peuples en clair (recherche fonctionnelle)
    # DB_ENCRYPTION_SEARCH=OFF -> index FTS5 non peuples (securite maximale, pas de recherche)
    # Ignore si DB_ENCRYPTION=OFF.
    DB_ENCRYPTION_SEARCH: bool = os.getenv("DB_ENCRYPTION_SEARCH", "ON").strip().upper() == "ON"

    # Compression de contexte
    # Fenêtre de contexte totale du modèle (tokens).
    # Utilisée pour afficher la jauge et calibrer les seuils.
    CONTEXT_MODEL_MAX_TOKENS: int = int(os.getenv("CONTEXT_MODEL_MAX_TOKENS", "128000"))
    # Taille max de l'historique entrant (tokens réels via usage API).
    # Au-delà, les anciens messages sont écartés (fenêtre glissante).
    # 0 = désactivé. Remplace CONTEXT_HISTORY_MAX_CHARS si non nul.
    CONTEXT_HISTORY_MAX_TOKENS: int = int(os.getenv("CONTEXT_HISTORY_MAX_TOKENS", "100000"))
    # Fallback en caractères si les tokens réels ne sont pas encore connus.
    CONTEXT_HISTORY_MAX_CHARS: int = int(os.getenv("CONTEXT_HISTORY_MAX_CHARS", "400000"))
    # Après combien de tours agent on compresse les tool_results anciens.
    # 0 = désactivé.
    CONTEXT_AGENT_COMPRESS_AFTER: int = int(os.getenv("CONTEXT_AGENT_COMPRESS_AFTER", "8"))
    # Taille max d'un tool_result compressé (résumé de l'ancien résultat).
    CONTEXT_TOOL_RESULT_SUMMARY_CHARS: int = int(os.getenv("CONTEXT_TOOL_RESULT_SUMMARY_CHARS", "2600"))

    # ── Mémoire de session (session_memory.py) ────────────────────────────────
    # Consolidation périodique : résumé LLM généré tous les N tours agent.
    # 0 = désactivé. Recommandé : 8 (sessions longues) ou 5 (outils lourds).
    CONTEXT_CONSOLIDATION_EVERY: int = int(os.getenv("CONTEXT_CONSOLIDATION_EVERY", "8"))
    # Taille max du résumé de consolidation injecté en contexte (caractères).
    CONTEXT_CONSOLIDATION_MAX_CHARS: int = int(os.getenv("CONTEXT_CONSOLIDATION_MAX_CHARS", "2500"))
    # Marquage des tool_results critiques (cités dans la réponse assistant).
    # ON = protège les résultats cités contre la compression mécanique.
    CONTEXT_PINNING_ENABLED: bool = os.getenv("CONTEXT_PINNING_ENABLED", "ON").strip().upper() == "ON"

    # Consolidation adaptative : déclenche une consolidation dès que la pression
    # sur le contexte dépasse ce seuil (ratio prompt_tokens / CONTEXT_MODEL_MAX_TOKENS).
    # 0.0 = désactivé (seulement la fréquence fixe).
    # Recommandé : 0.70 (consolidation à 70% de la fenêtre occupée).
    CONTEXT_CONSOLIDATION_PRESSURE_THRESHOLD: float = float(
        os.getenv("CONTEXT_CONSOLIDATION_PRESSURE_THRESHOLD", "0.70")
    )

    # ── Interface ─────────────────────────────────────────────────────────────
    # Nombre maximum de conversations rouvertes au démarrage dans la sidebar.
    # Correspond aux onglets restaurés depuis l'historique.
    SIDEBAR_MAX_CONVERSATIONS: int = int(os.getenv("SIDEBAR_MAX_CONVERSATIONS", "10"))

    @classmethod
    def active_model(cls) -> str:
        return cls.OLLAMA_MODEL if cls.LOCAL else cls.OPENAI_MODEL

    @classmethod
    def mode_label(cls) -> str:
        if cls.LOCAL:
            return f"🟢 Ollama · {cls.OLLAMA_MODEL}"
        return f"🔵 Albert (OpenAI) · {cls.OPENAI_MODEL}"
