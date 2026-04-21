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
routers/monitoring.py — Tableau de bord de consommation

Équivalent de MonitoringPanel + ModelUsagePanel (ui/panels/).

Contrairement à Qt où les panneaux sont alimentés par les signaux
token_usage_updated et model_usage_updated émis par ChatPanel en temps réel,
ici les données sont :

  1. Persistées en DB (table kv_store) au fil des WebSocket sessions.
  2. Exposées via REST pour affichage dans le composant React Monitoring.

Le stockage en mémoire (in-process) est maintenu pour la session courante
et mis à jour par ws_chat.py via update_session_stats(). Les données sont
aussi persistées en DB pour la reprise inter-sessions.

Routes :
    GET  /monitoring/{conv_id}         Stats de la conversation courante
    POST /monitoring/{conv_id}/reset   Remet à zéro les stats de session
    GET  /monitoring/session/current   Stats agrégées de la session serveur
"""

import logging
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from server.deps import get_db, require_auth
from server.schemas import MonitoringOut, TokenUsageOut, ModelUsageRow

_log = logging.getLogger(__name__)
router = APIRouter()


# ── Stockage in-process des stats de session ─────────────────────────────────
#
# Structure :
#   _session_stats[conv_id] = {
#       "prompt": int, "completion": int, "total": int,
#       "cost_eur": float, "carbon_kgco2": float, "llm_calls": int,
#       "history": [{"prompt": int, "completion": int, "total": int, ...}],
#       "model_breakdown": [{"model": str, "prompt": int, "completion": int, "role": str}],
#   }

_session_stats: dict[str, dict] = defaultdict(lambda: {
    "prompt": 0, "completion": 0, "total": 0,
    "cost_eur": 0.0, "carbon_kgco2": 0.0, "llm_calls": 0,
    "history": [],
    "model_breakdown": [],
})


def update_session_stats(conv_id: str, usage_dict: dict) -> None:
    """
    Appelé par ws_chat.py à chaque événement 'usage' reçu du WebSocket.

    Équivalent de MonitoringPanel.on_usage_updated() en Qt.

    Parameters
    ----------
    conv_id : str
        ID de la conversation active.
    usage_dict : dict
        { "prompt": int, "completion": int, "total": int,
          "cost_eur": float, "carbon_kgco2": float }
    """
    s = _session_stats[conv_id]
    prompt     = usage_dict.get("prompt", 0)
    completion = usage_dict.get("completion", 0)
    total      = usage_dict.get("total", prompt + completion)

    cost_eur      = usage_dict.get("cost_eur", 0.0) or 0.0
    carbon_kgco2  = usage_dict.get("carbon_kgco2", 0.0) or 0.0

    s["prompt"]       += prompt
    s["completion"]   += completion
    s["total"]        += total
    s["llm_calls"]    += 1
    s["cost_eur"]     += cost_eur
    s["carbon_kgco2"] += carbon_kgco2

    # Snapshot pour le sparkline
    s["history"].append({
        "prompt":        prompt,
        "completion":    completion,
        "total":         total,
        "cost_eur":      cost_eur,
        "carbon_kgco2":  carbon_kgco2,
        "llm_calls":     1,
    })


def update_model_usage(conv_id: str, model_dict: dict) -> None:
    """
    Enregistre la consommation par modèle et par rôle.

    Équivalent de ModelUsagePanel.on_model_usage_updated().
    """
    _session_stats[conv_id]["model_breakdown"].append(model_dict)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/session/current")
async def get_session_stats(_ = Depends(require_auth)):
    """Stats agrégées de toutes les conversations de la session serveur."""
    total_prompt     = sum(s["prompt"]     for s in _session_stats.values())
    total_completion = sum(s["completion"] for s in _session_stats.values())
    total_calls      = sum(s["llm_calls"]  for s in _session_stats.values())
    return {
        "conversations_active": len(_session_stats),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "total_llm_calls": total_calls,
    }


@router.get("/{conv_id}", response_model=MonitoringOut)
async def get_monitoring(conv_id: str, _ = Depends(require_auth)):
    """
    Retourne les stats de consommation pour une conversation.

    Combine les stats in-process (session courante) avec les données persistées.
    """
    from core.config import Config

    s = _session_stats[conv_id]
    total_tokens = s["total"]
    context_fill = (total_tokens / Config.CONTEXT_MODEL_MAX_TOKENS * 100) \
        if Config.CONTEXT_MODEL_MAX_TOKENS > 0 else 0.0

    return MonitoringOut(
        conversation_id=conv_id,
        session=TokenUsageOut(
            prompt=s["prompt"],
            completion=s["completion"],
            total=s["total"],
            cost_eur=s["cost_eur"],
            carbon_kgco2=s["carbon_kgco2"],
            llm_calls=s["llm_calls"],
        ),
        history=[
            TokenUsageOut(**h) for h in s["history"]
        ],
        model_breakdown=[
            ModelUsageRow(**m) for m in s["model_breakdown"]
        ],
        context_fill_pct=min(context_fill, 100.0),
    )


@router.post("/{conv_id}/reset")
async def reset_monitoring(conv_id: str, _ = Depends(require_auth)):
    """Remet à zéro les stats de session pour une conversation."""
    if conv_id in _session_stats:
        del _session_stats[conv_id]
    return {"status": "reset", "conv_id": conv_id}


