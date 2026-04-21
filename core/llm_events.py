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
llm_events.py — Bus d'événements interne vers l'UI.

Responsabilité unique
─────────────────────
Ce module centralise **tous** les callbacks qui permettent au moteur LLM
(llm_service) de notifier l'interface graphique d'événements internes sans
créer de couplage direct entre les deux couches.

Architecture (thread-safe multi-utilisateurs)
─────────────────────────────────────────────
Chaque callback est stocké dans un ``contextvars.ContextVar`` au lieu d'un
global module-level. Cela garantit l'isolation complète entre les requêtes
concurrentes :

  • asyncio.to_thread() propage automatiquement le contexte asyncio vers le
    thread worker → les callbacks enregistrés dans la coroutine ws_chat sont
    visibles depuis agent_loop() dans le thread, sans interférence avec les
    autres utilisateurs.

  • Côté UI   : appelle set_*_callback(fn) pour s'abonner.
  • Côté core : appelle emit_*() — ne lève jamais d'exception même si
    aucun callback n'est installé dans le contexte courant.
  • Désabonnement : set_*_callback(None) — utilisé en finally de ws_chat
    pour éviter les appels fantômes.

Callbacks disponibles
─────────────────────
  context_event       Compression ou trim du contexte (message textuel).
  compression_stats   Stats structurées de chaque opération de compression.
  memory_event        Événements de la mémoire de session (consolidation…).
  family_routing      Routing vers un modèle de famille pour la réponse finale.
  model_usage         Consommation de tokens par modèle et par rôle.
  cancel              Vérification de l'annulation du stream courant.

Usage typique (dans ws_chat.py)
────────────────────────────────
    from core import llm_events

    llm_events.set_context_event_callback(on_context_event)
    llm_events.set_cancel_callback(lambda: cancelled)
    try:
        await asyncio.to_thread(llm_service.agent_loop, ...)
    finally:
        llm_events.set_context_event_callback(None)
        llm_events.set_cancel_callback(None)
"""

import contextvars
import logging
from typing import Callable

_log = logging.getLogger(__name__)


# ── ContextVars ───────────────────────────────────────────────────────────────
#
# Chaque variable est initialisée à None (pas de callback installé).
# Elles sont scopées à l'exécution asyncio courante — propagées automatiquement
# dans les threads via asyncio.to_thread().

_CTX_CONTEXT_EVENT:     contextvars.ContextVar["Callable[[str], None] | None"] = \
    contextvars.ContextVar("llm_ctx_event",      default=None)

_CTX_COMPRESSION_STATS: contextvars.ContextVar["Callable[[dict], None] | None"] = \
    contextvars.ContextVar("llm_compression",    default=None)

_CTX_MEMORY_EVENT:      contextvars.ContextVar["Callable[[str], None] | None"] = \
    contextvars.ContextVar("llm_memory_event",   default=None)

_CTX_FAMILY_ROUTING:    contextvars.ContextVar["Callable[[dict], None] | None"] = \
    contextvars.ContextVar("llm_family_routing", default=None)

_CTX_MODEL_USAGE:       contextvars.ContextVar["Callable[[dict], None] | None"] = \
    contextvars.ContextVar("llm_model_usage",    default=None)

_CTX_CANCEL:            contextvars.ContextVar["Callable[[], bool] | None"] = \
    contextvars.ContextVar("llm_cancel",         default=None)


# ── Callback : compression / trim de contexte ────────────────────────────────
#
# Émis chaque fois qu'une opération modifie la taille du contexte.
# Payload : str — message lisible décrivant l'opération.

def set_context_event_callback(fn: "Callable[[str], None] | None") -> None:
    """Installe (ou retire si None) le callback de compression de contexte."""
    _CTX_CONTEXT_EVENT.set(fn)


def emit_context_event(msg: str) -> None:
    """Émet un événement de compression vers l'UI. Sans effet si non abonné."""
    fn = _CTX_CONTEXT_EVENT.get()
    if fn is not None:
        fn(msg)


# ── Callback : statistiques de compression ───────────────────────────────────
#
# Payload dict :
#   type   : "compress_tool" | "truncate_text" | "trim_msgs"
#   before : int  (caractères avant)
#   after  : int  (caractères après)
#   saved  : int
#   pct    : float

def set_compression_stats_callback(fn: "Callable[[dict], None] | None") -> None:
    """Installe (ou retire si None) le callback de statistiques de compression."""
    _CTX_COMPRESSION_STATS.set(fn)


def emit_compression_stats(op_type: str, before: int, after: int) -> None:
    """Calcule et émet les statistiques d'une opération de compression."""
    fn = _CTX_COMPRESSION_STATS.get()
    if fn is None:
        return
    saved = before - after
    pct   = (saved / before * 100) if before > 0 else 0.0
    fn({"type": op_type, "before": before, "after": after, "saved": saved, "pct": pct})


# ── Callback : événements de la mémoire de session ───────────────────────────
#
# Payload : str — message lisible.

def set_memory_event_callback(fn: "Callable[[str], None] | None") -> None:
    """Installe (ou retire si None) le callback d'événements mémoire de session."""
    _CTX_MEMORY_EVENT.set(fn)


def emit_memory_event(msg: str) -> None:
    """Émet un événement mémoire vers l'UI. Sans effet si non abonné."""
    fn = _CTX_MEMORY_EVENT.get()
    if fn is not None:
        fn(msg)


# ── Callback : routing de modèle par famille ─────────────────────────────────
#
# Payload dict : { family, label, model, backend }
# family == "" → retour au modèle principal.

def set_family_routing_callback(fn: "Callable[[dict], None] | None") -> None:
    """Installe (ou retire si None) le callback de routing de modèle par famille."""
    _CTX_FAMILY_ROUTING.set(fn)


def emit_family_routing(family: str, label: str, model: str, backend: str) -> None:
    """Émet un événement de routing de famille vers l'UI."""
    if family:
        _log.debug("[family_routing] %s (%s) → %s:%s", family, label, backend, model)
    fn = _CTX_FAMILY_ROUTING.get()
    if fn is not None:
        fn({"family": family, "label": label, "model": model, "backend": backend})


# ── Callback : consommation de tokens par modèle ─────────────────────────────
#
# Payload dict : { model, prompt, completion, role }
# role : "decision" | "final" | "stream"

def set_model_usage_callback(fn: "Callable[[dict], None] | None") -> None:
    """Installe (ou retire si None) le callback de consommation par modèle."""
    _CTX_MODEL_USAGE.set(fn)


def emit_model_usage(model: str, prompt: int, completion: int, role: str) -> None:
    """Émet un événement de consommation de tokens pour un appel LLM donné."""
    fn = _CTX_MODEL_USAGE.get()
    if fn is not None:
        fn({"model": model, "prompt": prompt, "completion": completion, "role": role})


# ── Callback d'annulation du stream ──────────────────────────────────────────
#
# is_cancelled() retourne True si un callback est installé dans le contexte
# courant et renvoie True.

def set_cancel_callback(fn: "Callable[[], bool] | None") -> None:
    """Installe (ou retire si None) le callback de vérification d'annulation."""
    _CTX_CANCEL.set(fn)


def is_cancelled() -> bool:
    """Retourne True si le stream courant doit être interrompu."""
    fn = _CTX_CANCEL.get()
    return fn is not None and fn()
