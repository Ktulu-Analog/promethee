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
schemas.py — Modèles Pydantic partagés entre les routers

Toutes les structures JSON entrantes/sortantes de l'API sont définies ici
pour centraliser la validation et la documentation OpenAPI.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class UnlockPayload(BaseModel):
    passphrase: str = Field(..., description="Passphrase AES-256-GCM pour déchiffrer la DB")


class UnlockResponse(BaseModel):
    status: str  # "ok"
    encrypted: bool


# ── Conversations ─────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: str = Field("Nouvelle conversation", description="Titre initial")
    system_prompt: str = Field("", description="Prompt système de la conversation")
    folder_id: Optional[str] = Field(None, description="ID du dossier parent")


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    folder_id: Optional[str] = None  # None = sans dossier, chaîne vide interdite


class ConversationOut(BaseModel):
    id: str
    title: str
    system_prompt: str
    model: Optional[str] = None
    folder_id: Optional[str] = None
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    created_at: str


# ── Dossiers ──────────────────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[str] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    position: Optional[int] = None


class FolderOut(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    position: int


class ConvMovePayload(BaseModel):
    folder_id: Optional[str] = Field(None, description="None = sans dossier")


class ConvTreeOut(BaseModel):
    """Arborescence complète dossiers + conversations pour la sidebar."""
    folders: list[FolderOut]
    conversations_by_folder: dict[str, list[ConversationOut]]
    unfiled: list[ConversationOut]


# ── Chat (WebSocket) ──────────────────────────────────────────────────────────

class ChatPayload(BaseModel):
    """
    Message envoyé par le client sur le WebSocket pour lancer une génération.

    Correspond aux paramètres de AgentWorker.__init__ dans workers.py.

    Assemblage du system_prompt
    ────────────────────────────
    Le client envoie ``profile_name`` (nom du profil actif) plutôt qu'un
    system_prompt pré-assemblé. Le serveur (ws_chat.py) récupère le prompt
    du profil et y ajoute automatiquement le bloc des skills épinglés via
    SkillManager.build_pinned_block(). Cela garantit que les skills sont
    toujours injectés, indépendamment du client.

    Le champ ``system_prompt`` est conservé pour rétrocompatibilité (mode
    appels directs) : si ``profile_name`` est absent ou vide, le
    serveur utilise ``system_prompt`` tel quel.
    """
    messages: list[dict[str, Any]] = Field(
        ..., description="Historique au format OpenAI (role/content)"
    )
    profile_name: Optional[str] = Field(
        None,
        description=(
            "Nom du profil actif (ex: 'Assistant juridique'). "
            "Le serveur assemble prompt + skills épinglés depuis ce nom. "
            "Prioritaire sur system_prompt si fourni."
        ),
    )
    profile_is_personal: bool = Field(
        False,
        description="Si True, profile_name est un profil personnel de l'utilisateur courant.",
    )
    system_prompt: str = Field(
        "",
        description=(
            "Prompt système brut (rétrocompatibilité). "
            "Ignoré si profile_name est fourni et résolu côté serveur."
        ),
    )
    model: Optional[str] = Field(None, description="Modèle à utiliser (None = Config.active_model)")
    use_tools: bool = Field(True, description="Active la boucle agent avec outils")
    max_iterations: int = Field(8, description="Limite de la boucle agent")
    disable_context_management: bool = Field(
        False, description="Désactive trim/compression — débogage uniquement"
    )
    save_user_message: Optional[str] = Field(
        None, description="Si fourni, persiste ce texte en DB comme message user avant génération"
    )


class CancelPayload(BaseModel):
    action: str  # "cancel"


# ── Messages WebSocket sortants ───────────────────────────────────────────────
# (documentés ici pour référence — envoyés comme JSON brut sur le WS)
#
# { "t": "token",        "d": str }
# { "t": "tool_called",  "name": str, "args": str }
# { "t": "tool_result",  "name": str }
# { "t": "tool_image",   "mime": str, "data": str }   ← base64
# { "t": "tool_progress","msg": str }
# { "t": "context_event","msg": str }
# { "t": "memory_event", "msg": str }
# { "t": "family_routing","family": str, "label": str, "model": str, "backend": str }
# { "t": "model_usage",  "model": str, "prompt": int, "completion": int, "role": str }
# { "t": "compression_stats", "op_type": str, "before": int, "after": int, "saved": int, "pct": float }
# { "t": "usage",        "prompt": int, "completion": int, "total": int }
# { "t": "finished",     "text": str }
# { "t": "cancelled",    "text": str }
# { "t": "error",        "msg": str }


# ── RAG ───────────────────────────────────────────────────────────────────────

class RagIngestResponse(BaseModel):
    chunks: int
    filename: str


class RagSourceOut(BaseModel):
    source: str
    chunks: int
    score_avg: Optional[float] = None


class RagCollectionOut(BaseModel):
    name: str
    is_own: bool
    vector_count: Optional[int] = None


# ── Settings ──────────────────────────────────────────────────────────────────

class SettingsPatch(BaseModel):
    """
    Mise à jour d'une ou plusieurs clés .env.

    Exemple :
        { "OPENAI_MODEL": "openai/gpt-4o", "LOCAL": "OFF" }
    """
    updates: dict[str, str] = Field(
        ..., description="Dictionnaire clé→valeur à écrire dans .env"
    )


class SettingsOut(BaseModel):
    """
    Snapshot des paramètres exposés à l'interface.
    Seules les valeurs non-sensibles sont renvoyées ; les clés API sont masquées.
    """
    APP_TITLE: str
    APP_VERSION: Optional[str]
    APP_USER: str
    OPENAI_API_BASE: str
    OPENAI_API_KEY_SET: bool       # True si clé non vide, sans exposer la valeur
    OPENAI_MODEL: str
    QDRANT_URL: str
    RAG_USER_ID: str
    QDRANT_COLLECTION: str
    EMBEDDING_MODE: str
    EMBEDDING_MODEL: str
    EMBEDDING_API_BASE: str
    EMBEDDING_DIMENSION: int
    RAG_TOP_K: int
    RAG_MIN_SCORE: float
    RAG_RERANK_ENABLED: bool
    AGENT_MAX_ITERATIONS: int
    MAX_CONTEXT_TOKENS: int
    CONTEXT_HISTORY_MAX_TOKENS: int
    DB_ENCRYPTION: bool
    LTM_ENABLED: bool
    LTM_MODEL: str


# ── Monitoring ────────────────────────────────────────────────────────────────

class TokenUsageOut(BaseModel):
    prompt: int
    completion: int
    total: int
    cost_eur: float
    carbon_kgco2: float
    llm_calls: int


class ModelUsageRow(BaseModel):
    model: str
    prompt: int
    completion: int
    role: str  # "decision" | "final" | "stream"


class MonitoringOut(BaseModel):
    conversation_id: str
    session: TokenUsageOut
    history: list[TokenUsageOut]       # sparkline (une entrée par appel LLM)
    model_breakdown: list[ModelUsageRow]
    context_fill_pct: float            # % de remplissage de la fenêtre de contexte


# ── Outils ────────────────────────────────────────────────────────────────────

class FamilyUpdate(BaseModel):
    enabled: Optional[bool] = None
    model_backend: Optional[str] = None   # "openai" | ""
    model_name: Optional[str] = None
    model_base_url: Optional[str] = None


class FamilyOut(BaseModel):
    family: str
    label: str
    icon: str
    enabled: bool
    tool_count: int
    model_backend: str
    model_name: str
    model_base_url: str


class ToolOut(BaseModel):
    name: str
    description: str
    icon: str
    family: str
    family_label: str
    family_icon: str
    enabled: bool
