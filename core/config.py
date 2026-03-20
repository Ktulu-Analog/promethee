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


def _safe_user_id() -> str:
    """Retourne l'identifiant utilisateur normalisé (partagé par les deux fonctions de nommage).

    Priorité :
      1. RAG_USER_ID dans .env     → utilisé tel quel (normalisé)
      2. Nom d'utilisateur système → getpass.getuser()
      3. Nom de machine            → platform.node()
      4. Fallback                  → "default"

    Normalisé : minuscules, caractères non-alphanumériques → _, pas de _ en bord.
    """
    user_id = os.getenv("RAG_USER_ID", "").strip()
    if not user_id:
        try:
            user_id = getpass.getuser()
        except Exception:
            user_id = platform.node()
    return re.sub(r"[^a-z0-9]+", "_", user_id.lower()).strip("_") or "default"


def get_safe_user_id() -> str:
    """Retourne l'identifiant utilisateur normalisé — API publique de _safe_user_id().

    À utiliser depuis les modules externes (rag_engine, etc.) pour éviter
    de dupliquer la logique de résolution du user_id.
    """
    return _safe_user_id()


def _qdrant_collection() -> str:
    """Calcule le nom de la collection RAG documentaire de l'utilisateur courant.

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
    return f"promethee_{_safe_user_id()}"


def _ltm_collection() -> str:
    """Calcule le nom de la collection Qdrant dédiée à la mémoire long terme (LTM).

    Séparée de la collection RAG documentaire pour éviter toute pollution
    croisée entre souvenirs de conversations et documents ingérés manuellement.

    Priorité :
      1. LTM_COLLECTION dans .env     → respecté tel quel
      2. RAG_USER_ID / getuser() / hostname → promethee_memory_<user_id>
      3. Fallback                     → promethee_memory_default

    Le suffixe "_memory" distingue clairement cette collection des collections
    documentaires ("promethee_<user>") aux yeux d'un administrateur Qdrant
    supervisant plusieurs instances.
    """
    explicit = os.getenv("LTM_COLLECTION", "").strip()
    if explicit:
        return explicit
    return f"promethee_memory_{_safe_user_id()}"


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

    # Nom de la collection Qdrant dédiée à la mémoire long terme (LTM).
    # Séparée de QDRANT_COLLECTION pour éviter la pollution croisée entre
    # souvenirs de conversations et documents ingérés manuellement.
    # Format automatique : promethee_memory_<user_id> (même logique que QDRANT_COLLECTION).
    LTM_COLLECTION: str = _ltm_collection()

    # Embeddings
    EMBEDDING_MODE: str = os.getenv("EMBEDDING_MODE", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "")
    EMBEDDING_API_BASE: str = os.getenv("EMBEDDING_API_BASE", "")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

    # Audio / Whisper
    AUDIO_MODEL: str = os.getenv("AUDIO_MODEL", "")

    # ── Modèles spécialisés par tâche ────────────────────────────────────────
    # Permettent de router certaines tâches vers un modèle dédié (code, résumé…)
    # sans changer le modèle principal de conversation.
    #
    # Format de chaque variable :
    #   SPECIALIST_<TACHE>_BACKEND  : "openai" | "ollama" | "" (hérite du mode principal)
    #   SPECIALIST_<TACHE>_MODEL    : nom du modèle (ex: qwen2.5-coder:14b)
    #   SPECIALIST_<TACHE>_BASE_URL : endpoint si différent de OPENAI_API_BASE / OLLAMA_BASE_URL
    #
    # Tâches disponibles :
    #   CODE     → génération / analyse de code (create_tool, python_tools…)
    #   SUMMARY  → résumés, synthèses (aliasé sur LTM_MODEL si absent)
    #
    # Si SPECIALIST_<TACHE>_MODEL est vide, active_model() est utilisé (pas de routing).
    #
    # Exemple Ollama local pour le code :
    #   SPECIALIST_CODE_BACKEND=ollama
    #   SPECIALIST_CODE_MODEL=qwen2.5-coder:14b
    #   SPECIALIST_CODE_BASE_URL=      ← vide = hérite de OLLAMA_BASE_URL
    #
    # Exemple même endpoint Albert mais modèle différent :
    #   SPECIALIST_CODE_BACKEND=openai
    #   SPECIALIST_CODE_MODEL=mistralai/Devstral-Small-2505
    #   SPECIALIST_CODE_BASE_URL=      ← vide = hérite de OPENAI_API_BASE

    SPECIALIST_CODE_BACKEND:  str = os.getenv("SPECIALIST_CODE_BACKEND",  "").strip().lower()
    SPECIALIST_CODE_MODEL:    str = os.getenv("SPECIALIST_CODE_MODEL",    "").strip()
    SPECIALIST_CODE_BASE_URL: str = os.getenv("SPECIALIST_CODE_BASE_URL", "").strip()

    SPECIALIST_SUMMARY_BACKEND:  str = os.getenv("SPECIALIST_SUMMARY_BACKEND",  "").strip().lower()
    SPECIALIST_SUMMARY_MODEL:    str = os.getenv("SPECIALIST_SUMMARY_MODEL",    "").strip()
    SPECIALIST_SUMMARY_BASE_URL: str = os.getenv("SPECIALIST_SUMMARY_BASE_URL", "").strip()

    @classmethod
    def specialist_config(cls, task: str) -> dict | None:
        """
        Retourne la configuration du modèle spécialisé pour une tâche donnée.

        Paramètre :
            task : identifiant de tâche en majuscules ("CODE", "SUMMARY"…)

        Retourne un dict avec les clés :
            backend  : "openai" | "ollama"
            model    : nom du modèle
            base_url : endpoint (peut hériter de la config principale)

        Retourne None si aucun modèle spécialisé n'est configuré pour cette tâche
        (l'appelant doit alors utiliser build_client() + active_model() normalement).
        """
        t = task.upper()
        model    = getattr(cls, f"SPECIALIST_{t}_MODEL",    "")
        backend  = getattr(cls, f"SPECIALIST_{t}_BACKEND",  "")
        base_url = getattr(cls, f"SPECIALIST_{t}_BASE_URL", "")

        if not model:
            return None  # Pas de modèle spécialisé configuré pour cette tâche

        # Résolution du backend
        if not backend:
            backend = "ollama" if cls.LOCAL else "openai"

        # Résolution de l'URL de base
        if not base_url:
            base_url = cls.OLLAMA_BASE_URL if backend == "ollama" else cls.OPENAI_API_BASE

        return {
            "backend":  backend,
            "model":    model,
            "base_url": base_url,
        }

    # Grist
    GRIST_API_KEY: str = os.getenv("GRIST_API_KEY", "")
    GRIST_BASE_URL: str = os.getenv("GRIST_BASE_URL", "https://docs.getgrist.com")

    # Thunderbird
    TB_PROFILE_PATH: str = os.getenv("TB_PROFILE_PATH", "")

    # App
    APP_TITLE: str = os.getenv("APP_TITLE", "Prométhée AI")
    APP_VERSION: str = os.getenv("APP_VERSION")
    APP_USER: str = os.getenv("APP_USER", "Vous")
    HISTORY_DB: str = os.getenv("HISTORY_DB", "history.db")
    # Taille max de la réponse générée (tokens).
    # Pas de valeur par défaut dans l'API OpenAI — on utilise 8 000 comme
    # garde-fou raisonnable si la variable n'est pas définie dans .env.
    MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "") or "8000")

    # Taille max d'un résultat d'outil avant troncature symétrique (caractères).
    # Les résultats contenant du code source ou des exports bureautiques sont
    # toujours conservés intégralement, quelle que soit cette limite.
    TOOL_RESULT_MAX_CHARS: int = int(os.getenv("TOOL_RESULT_MAX_CHARS", "12000"))

    # Nombre maximum d'itérations de la boucle agent (appels LLM + outils).
    # Au-delà, une synthèse forcée est générée depuis les résultats disponibles.
    # Augmenter cette valeur pour les tâches complexes multi-étapes.
    AGENT_MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "8"))

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

    # ── RAG — Recherche sémantique (rag_engine.py) ───────────────────────────
    # Nombre de chunks candidats récupérés avant filtrage/reranking.
    # En mode Albert : candidats passés au reranker BGE-Reranker-v2-M3.
    # En mode Qdrant : résultats vectoriels bruts avant filtrage.
    # Recommandé : 12–20. Défaut : 15.
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "15"))
    # Score minimal pour qu'un chunk soit retenu (mode Qdrant uniquement).
    # En mode Albert, le reranker produit ses propres scores — utiliser RAG_RERANK_MIN_SCORE.
    # Plage : 0.0–1.0. Recommandé : 0.55–0.70. Défaut : 0.60.
    RAG_MIN_SCORE: float = float(os.getenv("RAG_MIN_SCORE", "0.60"))
    # Nombre maximum de chunks retenus par source (document).
    # Limite la sur-représentation d'un seul document dans le contexte injecté.
    # Recommandé : 2–3. Défaut : 2.
    RAG_MAX_CHUNKS_PER_SOURCE: int = int(os.getenv("RAG_MAX_CHUNKS_PER_SOURCE", "2"))
    # Nombre maximum de chunks total injectés dans le prompt après filtrage/reranking.
    # Doit être ≤ RAG_TOP_K. Recommandé : 6–10. Défaut : 8.
    RAG_MAX_CHUNKS_TOTAL: int = int(os.getenv("RAG_MAX_CHUNKS_TOTAL", "8"))

    # ── RAG — Recherche hybride Albert (albert_search dans rag_engine.py) ────
    # Méthode de recherche Albert : "hybrid" (dense BGE-M3 + sparse BM25 via RRF),
    # "semantic" (dense uniquement), "lexical" (BM25 uniquement).
    # "hybrid" est recommandé pour les corpus métier avec termes rares/codes.
    RAG_SEARCH_METHOD: str = os.getenv("RAG_SEARCH_METHOD", "hybrid")
    # Constante k du Reciprocal Rank Fusion (RRF) en mode hybrid.
    # Plage : 10–100. Une valeur basse favorise les tops résultats,
    # une valeur haute lisse les scores. Défaut Albert : 60.
    RAG_RFF_K: int = int(os.getenv("RAG_RFF_K", "60"))
    # IDs des collections Albert à interroger (entiers, séparés par des virgules).
    # Ex : RAG_ALBERT_COLLECTION_IDS=12,47
    # Laisser vide pour n'utiliser que Qdrant.
    RAG_ALBERT_COLLECTION_IDS: list[int] = [
        int(x.strip())
        for x in os.getenv("RAG_ALBERT_COLLECTION_IDS", "").split(",")
        if x.strip().isdigit()
    ]
    # Modèle de reranking exposé par Albert.
    # Doit correspondre à un modèle de type "text-classification" disponible sur /v1/models.
    RAG_RERANK_MODEL: str = os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    # Score de pertinence minimal retourné par le reranker pour conserver un chunk.
    # Le reranker BGE-Reranker-v2-M3 produit des scores logit (non bornés à [0,1]).
    # Valeurs typiques : < 0 = non pertinent, > 0 = pertinent, > 5 = très pertinent.
    # Défaut : -2.0 (filtre les chunks vraiment hors-sujet, garde le reste).
    RAG_RERANK_MIN_SCORE: float = float(os.getenv("RAG_RERANK_MIN_SCORE", "-2.0"))
    # Activer le reranking Albert. ON = actif si RAG_ALBERT_COLLECTION_IDS défini.
    # Mettre OFF pour désactiver sans toucher aux autres paramètres Albert.
    RAG_RERANK_ENABLED: bool = os.getenv("RAG_RERANK_ENABLED", "ON").strip().upper() == "ON"

    # ── RAG — Reformulation HyDE (Hypothetical Document Embedding) ───────────
    # Génère un document hypothétique à partir de la requête avant l'embedding,
    # pour mieux aligner l'espace sémantique query ↔ chunks indexés.
    # ON = actif (1 appel LLM supplémentaire par requête RAG).
    # OFF = comportement historique (embedding de la requête brute).
    RAG_HYDE_ENABLED: bool = os.getenv("RAG_HYDE_ENABLED", "OFF").strip().upper() == "ON"
    # Nombre maximum de tokens alloués au document hypothétique HyDE.
    # Recommandé : 150–300. Défaut : 200.
    RAG_HYDE_MAX_TOKENS: int = int(os.getenv("RAG_HYDE_MAX_TOKENS", "200"))

    # ── RAG — Chunking contextuel (Anthropic Contextual Retrieval) ───────────
    # Enrichit chaque chunk avec un préfixe contextuel généré par LLM décrivant
    # sa position dans le document parent. Améliore fortement la précision pour
    # les chunks hors-contexte (tableaux, listes, sous-sections).
    # ON = actif lors de l'ingestion (réingestion des docs existants requise).
    # OFF = comportement historique.
    RAG_CONTEXTUAL_CHUNKING: bool = os.getenv("RAG_CONTEXTUAL_CHUNKING", "OFF").strip().upper() == "ON"
    # Nombre maximum de tokens pour le préfixe contextuel généré.
    # Recommandé : 80–150. Défaut : 100.
    RAG_CONTEXTUAL_PREFIX_MAX_TOKENS: int = int(os.getenv("RAG_CONTEXTUAL_PREFIX_MAX_TOKENS", "100"))
    # Nombre maximum de caractères du document parent envoyés au LLM pour la
    # génération du contexte. Tronquer évite de dépasser la fenêtre de contexte.
    # Recommandé : 8000–16000. Défaut : 10000.
    RAG_CONTEXTUAL_DOC_MAX_CHARS: int = int(os.getenv("RAG_CONTEXTUAL_DOC_MAX_CHARS", "10000"))
    # Modèle LLM dédié au chunking contextuel (génération des préfixes à l'ingestion).
    # Permet d'utiliser un modèle léger/rapide pour cette tâche répétitive et simple,
    # sans mobiliser le modèle principal (OPENAI_MODEL) à chaque chunk.
    # Si vide, OPENAI_MODEL est utilisé (modèle principal).
    # Exemple : RAG_INGESTION_MODEL=mistralai/Mistral-Small-3.2-24B-Instruct-2506
    RAG_INGESTION_MODEL: str = os.getenv("RAG_INGESTION_MODEL", "").strip()

    # ── RAG — Seuil de score adaptatif (mode Qdrant) ─────────────────────────
    # Calcule dynamiquement le seuil minimum à partir de la distribution des
    # scores retournés, au lieu d'utiliser un seuil fixe (RAG_MIN_SCORE).
    # ON  = seuil = max(RAG_MIN_SCORE, mean - RAG_ADAPTIVE_SIGMA * std).
    # OFF = comportement historique (seuil fixe RAG_MIN_SCORE).
    RAG_ADAPTIVE_THRESHOLD: bool = os.getenv("RAG_ADAPTIVE_THRESHOLD", "ON").strip().upper() == "ON"
    # Facteur σ contrôlant l'agressivité du filtre adaptatif.
    # 0.5 → filtre large (garde plus de chunks)
    # 1.0 → filtre moyen (recommandé)
    # 1.5 → filtre strict (ne garde que les meilleurs)
    RAG_ADAPTIVE_SIGMA: float = float(os.getenv("RAG_ADAPTIVE_SIGMA", "1.0"))

    # ── Mémoire long terme inter-conversations (long_term_memory.py) ─────────
    # Indexe automatiquement les conversations fermées dans Qdrant (collection
    # dédiée LTM_COLLECTION) pour un rappel sémantique dans les sessions futures.
    # Nécessite que Qdrant et les embeddings soient configurés (RAG actif).
    LTM_ENABLED: bool = os.getenv("LTM_ENABLED", "OFF").strip().upper() == "ON"
    # Nombre d'échanges user/assistant regroupés dans un chunk Qdrant.
    LTM_EXCHANGES_PER_CHUNK: int = int(os.getenv("LTM_EXCHANGES_PER_CHUNK", "6"))
    # Troncature appliquée à chaque message individuel avant embedding (caractères).
    LTM_MAX_CHARS_PER_MSG: int = int(os.getenv("LTM_MAX_CHARS_PER_MSG", "600"))
    # Nombre de souvenirs remontés par recall().
    LTM_TOP_K: int = int(os.getenv("LTM_TOP_K", "4"))
    # Score de similarité cosinus minimum pour qu'un souvenir soit retenu.
    LTM_MIN_SCORE: float = float(os.getenv("LTM_MIN_SCORE", "0.45"))
    # Nombre minimal de messages (user+assistant) pour indexer une conversation.
    LTM_MIN_MESSAGES: int = int(os.getenv("LTM_MIN_MESSAGES", "4"))
    # Nombre de conversations récentes toujours injectées dans le contexte,
    # indépendamment du score sémantique (0 = désactivé).
    LTM_RECENT_K: int = int(os.getenv("LTM_RECENT_K", "2"))

    # Modèle LLM dédié aux opérations LTM (résumés de conversation, consolidation
    # thématique). Permet d'utiliser un modèle léger/rapide pour ces tâches de
    # synthèse en arrière-plan, sans mobiliser le modèle principal.
    # Si vide, Config.active_model() est utilisé (modèle principal).
    # Exemple : LTM_MODEL=mistralai/Mistral-Small-3.2-24B-Instruct-2506
    LTM_MODEL: str = os.getenv("LTM_MODEL", "").strip()

    # ── Mémoire long terme — Résumés LLM et consolidation ────────────────────
    # Générer un résumé LLM structuré de chaque conversation au lieu de stocker
    # les échanges bruts. Réduit le bruit sémantique et améliore la qualité des
    # vecteurs d'embedding. Nécessite que client et model soient passés à LongTermMemory().
    # OFF = comportement historique (chunks bruts). Recommandé : ON si LLM disponible.
    LTM_USE_SUMMARY: bool = os.getenv("LTM_USE_SUMMARY", "OFF").strip().upper() == "ON"
    # Taille maximale du résumé LLM généré par conversation (caractères).
    # Le dialogue brut envoyé au LLM est plafonné à LTM_SUMMARY_MAX_CHARS * 6.
    # Recommandé : 800–1500. Défaut : 1200.
    LTM_SUMMARY_MAX_CHARS: int = int(os.getenv("LTM_SUMMARY_MAX_CHARS", "1200"))
    # Consolidation LTM : tous les N cycles d'indexation, regrouper les anciens
    # souvenirs en résumés thématiques via un LLM secondaire.
    # Réduit la croissance indéfinie de LTM_COLLECTION.
    # 0 = désactivé. Recommandé : 15–30 (selon la fréquence de clôture de conversations).
    LTM_CONSOLIDATION_EVERY: int = int(os.getenv("LTM_CONSOLIDATION_EVERY", "20"))
    # Nombre de chunks anciens fusionnés lors d'un cycle de consolidation.
    # Ces chunks sont remplacés par un unique chunk consolidé marqué _consolidated=True.
    # Recommandé : 20–40. Défaut : 30.
    LTM_CONSOLIDATION_MAX_CHUNKS: int = int(os.getenv("LTM_CONSOLIDATION_MAX_CHUNKS", "30"))

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
