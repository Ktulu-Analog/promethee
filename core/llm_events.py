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
llm_events.py — Bus d'événements interne vers l'UI.

Responsabilité unique
─────────────────────
Ce module centralise **tous** les callbacks qui permettent au moteur LLM
(llm_service) de notifier l'interface graphique d'événements internes sans
créer de couplage direct entre les deux couches.

Architecture
────────────
Chaque callback est un simple global module-level (pattern intentionnel) :

  • Côté UI   : appelle set_*_callback(fn) pour s'abonner.
  • Côté core : appelle emit_*() — ne lève jamais d'exception même si
    aucun callback n'est installé.
  • Désabonnement : set_*_callback(None) — pattern utilisé par AgentWorker
    dans son bloc finally pour éviter les appels fantômes après la fin
    d'un worker.

Les globals sont volontairement module-level et non encapsulés dans une
classe, car stream_chat() et agent_loop() peuvent s'exécuter dans des
threads différents (QThread) et partager ces références nativement.

Callbacks disponibles
─────────────────────
  context_event       Compression ou trim du contexte (message textuel).
  compression_stats   Stats structurées de chaque opération de compression.
  memory_event        Événements de la mémoire de session (consolidation…).
  family_routing      Routing vers un modèle de famille pour la réponse finale.
  model_usage         Consommation de tokens par modèle et par rôle.

Usage typique (dans AgentWorker)
────────────────────────────────
    from core import llm_events

    llm_events.set_context_event_callback(self._on_context_event)
    llm_events.set_model_usage_callback(self._on_model_usage)
    try:
        llm_service.agent_loop(...)
    finally:
        llm_events.set_context_event_callback(None)
        llm_events.set_model_usage_callback(None)
"""

from typing import Callable


# ── Callback : compression / trim de contexte ────────────────────────────────
#
# Émis chaque fois qu'une opération modifie la taille du contexte :
# fenêtre glissante (_trim_history), compression in-loop (_compress_agent_msgs),
# troncature d'un résultat d'outil (_truncate_tool_result).
#
# Payload : str — message lisible décrivant l'opération.

_context_event_callback: Callable[[str], None] | None = None


def set_context_event_callback(fn: Callable[[str], None] | None) -> None:
    """Installe (ou retire si None) le callback de compression de contexte."""
    global _context_event_callback
    _context_event_callback = fn


def emit_context_event(msg: str) -> None:
    """Émet un événement de compression vers l'UI. Sans effet si non abonné."""
    if _context_event_callback is not None:
        _context_event_callback(msg)


# ── Callback : statistiques de compression ───────────────────────────────────
#
# Émis à chaque opération de compression avec des métriques structurées.
# Utilisé par MonitoringPanel pour afficher les jauges de réduction.
#
# Payload : dict avec les clés :
#   type   : str  — "compress_tool" | "truncate_text" | "trim_msgs"
#   before : int  — taille avant (caractères)
#   after  : int  — taille après (caractères)
#   saved  : int  — caractères économisés
#   pct    : float — pourcentage de réduction

_compression_stats_callback: Callable[[dict], None] | None = None


def set_compression_stats_callback(fn: Callable[[dict], None] | None) -> None:
    """Installe (ou retire si None) le callback de statistiques de compression."""
    global _compression_stats_callback
    _compression_stats_callback = fn


def emit_compression_stats(op_type: str, before: int, after: int) -> None:
    """
    Calcule et émet les statistiques d'une opération de compression.

    Parameters
    ----------
    op_type : str
        Type d'opération : "compress_tool", "truncate_text" ou "trim_msgs".
    before : int
        Taille avant l'opération (en caractères).
    after : int
        Taille après l'opération (en caractères).
    """
    if _compression_stats_callback is None:
        return
    saved = before - after
    pct   = (saved / before * 100) if before > 0 else 0.0
    _compression_stats_callback({
        "type":   op_type,
        "before": before,
        "after":  after,
        "saved":  saved,
        "pct":    pct,
    })


# ── Callback : événements de la mémoire de session ───────────────────────────
#
# Émis par SessionMemory lors des opérations de consolidation ou de pinning.
#
# Payload : str — message lisible (ex : "Mémoire : consolidation en cours…").

_memory_event_callback: Callable[[str], None] | None = None


def set_memory_event_callback(fn: Callable[[str], None] | None) -> None:
    """Installe (ou retire si None) le callback d'événements mémoire de session."""
    global _memory_event_callback
    _memory_event_callback = fn


def emit_memory_event(msg: str) -> None:
    """Émet un événement mémoire vers l'UI. Sans effet si non abonné."""
    if _memory_event_callback is not None:
        _memory_event_callback(msg)


# ── Callback : routing de modèle par famille ─────────────────────────────────
#
# Émis quand agent_loop bascule sur le modèle assigné à une famille d'outils
# pour produire la réponse finale d'un tour.
# family == "" signifie retour au modèle principal (fin de tour ou conflit).
#
# Payload : dict avec les clés :
#   family  : str — identifiant de la famille (ex: "imap_tools"), vide si principal
#   label   : str — nom lisible (ex: "Messagerie"), vide si principal
#   model   : str — nom du modèle résolu
#   backend : str — "openai" | "ollama"

_family_routing_callback: Callable[[dict], None] | None = None


def set_family_routing_callback(fn: Callable[[dict], None] | None) -> None:
    """
    Installe (ou retire si None) le callback de routing de modèle par famille.

    Le callback reçoit un dict :
        { "family": str, "label": str, "model": str, "backend": str }
    family == "" indique le retour au modèle principal.
    """
    global _family_routing_callback
    _family_routing_callback = fn


def emit_family_routing(family: str, label: str, model: str, backend: str) -> None:
    """
    Émet un événement de routing de famille vers l'UI et loggue en console.

    Parameters
    ----------
    family : str
        Identifiant de la famille active, vide si modèle principal.
    label : str
        Nom lisible de la famille, vide si modèle principal.
    model : str
        Nom exact du modèle résolu.
    backend : str
        "openai" ou "ollama".
    """
    if family:
        print(f"[family_routing] {family} ({label}) → {backend}:{model}")
    if _family_routing_callback is not None:
        _family_routing_callback({
            "family":  family,
            "label":   label,
            "model":   model,
            "backend": backend,
        })


# ── Callback : consommation de tokens par modèle ─────────────────────────────
#
# Émis à chaque appel LLM dans agent_loop avec le modèle exact utilisé.
# Permet à ModelUsagePanel de différencier la consommation du modèle principal
# (décision) de celle du modèle de famille (réponse finale).
#
# Payload : dict avec les clés :
#   model      : str — nom exact du modèle (ex: "openai/gpt-oss-120b")
#   prompt     : int — tokens prompt de cet appel
#   completion : int — tokens completion de cet appel
#   role       : str — "decision" | "final" | "stream"
#
# Sémantique des rôles :
#   decision : appel étape 1 — le modèle principal lit le contexte et décide
#              (tool_calls ou réponse directe).
#   final    : réponse finale non-streamée (cas A : msg.content non vide).
#   stream   : réponse finale streamée (cas B : second appel en streaming).

_model_usage_callback: Callable[[dict], None] | None = None


def set_model_usage_callback(fn: Callable[[dict], None] | None) -> None:
    """
    Installe (ou retire si None) le callback de consommation par modèle.

    Le callback reçoit un dict :
        { "model": str, "prompt": int, "completion": int, "role": str }
    """
    global _model_usage_callback
    _model_usage_callback = fn


def emit_model_usage(model: str, prompt: int, completion: int, role: str) -> None:
    """
    Émet un événement de consommation de tokens pour un appel LLM donné.

    Parameters
    ----------
    model : str
        Nom exact du modèle utilisé.
    prompt : int
        Tokens prompt consommés.
    completion : int
        Tokens completion consommés.
    role : str
        Rôle de l'appel : "decision", "final" ou "stream".
    """
    if _model_usage_callback is not None:
        _model_usage_callback({
            "model":      model,
            "prompt":     prompt,
            "completion": completion,
            "role":       role,
        })


# ── Callback d'annulation du stream ──────────────────────────────────────────
#
# Permet à un worker Qt d'interrompre la boucle de streaming dans llm_service
# dès que l'utilisateur clique sur Stop. Sans ce mécanisme, _stream_response
# consomme le stream réseau jusqu'au bout même si _cancelled=True côté worker.
#
# Usage :
#   set_cancel_callback(lambda: self._cancelled)   # dans le worker
#   set_cancel_callback(None)                       # en finally du worker
#
# is_cancelled() retourne True si un callback est installé et renvoie True.

_cancel_callback: "Callable[[], bool] | None" = None


def set_cancel_callback(fn: "Callable[[], bool] | None") -> None:
    """Installe (ou retire si None) le callback de vérification d'annulation."""
    global _cancel_callback
    _cancel_callback = fn


def is_cancelled() -> bool:
    """Retourne True si le stream courant doit être interrompu."""
    return _cancel_callback is not None and _cancel_callback()
