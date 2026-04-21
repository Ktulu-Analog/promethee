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
routers/tools_router.py — Gestion des familles d'outils et modèles assignés

Équivalent de l'onglet « Outils » du SettingsDialog + ToolsPanel.

Routes :
    GET    /tools                       Liste tous les outils enregistrés
    GET    /tools/families              Liste les familles avec état enabled/disabled
    PATCH  /tools/families/{family}     Active/désactive, assigne un modèle
    DELETE /tools/families/{family}/model  Réinitialise le modèle de la famille
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from core import tools_engine
from server.deps import get_db, require_auth
from server.schemas import FamilyOut, FamilyUpdate, ToolOut

_log = logging.getLogger(__name__)
router = APIRouter()


# ── Outils ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ToolOut])
async def list_tools(_ = Depends(require_auth)):
    """
    Liste tous les outils enregistrés (actifs et désactivés).
    Équivalent de ToolsPanel._populate() dans tools_panel.py.
    """
    return [ToolOut(**t) for t in tools_engine.list_tools()]


# ── Familles ──────────────────────────────────────────────────────────────────

@router.get("/families", response_model=list[FamilyOut])
async def list_families(user: dict = Depends(require_auth)):
    """
    Liste les familles d'outils avec leur état et modèle assigné.
    Charge d'abord les prefs de cet utilisateur (familles désactivées +
    modèles assignés) pour que la réponse reflète son état personnel.
    """
    tools_engine.load_user_families(user["id"])
    tools_engine.load_user_family_models(user["id"])
    return [FamilyOut(**f) for f in tools_engine.list_families()]


@router.patch("/families/{family}", response_model=FamilyOut)
async def update_family(
    family: str,
    payload: FamilyUpdate,
    user: dict = Depends(require_auth),
):
    """
    Met à jour l'état activé/désactivé et/ou le modèle assigné d'une famille.

    Équivalent des QCheckBox + QComboBox du SettingsDialog onglet Outils.
    - enabled=true  → tools_engine.enable_family()
    - enabled=false → tools_engine.disable_family()
    - model_name fourni → tools_engine.set_family_model()
    - model_name=""    → tools_engine.clear_family_model()
    """
    families = {f["family"]: f for f in tools_engine.list_families()}
    if family not in families:
        raise HTTPException(status_code=404, detail=f"Famille {family!r} inconnue.")

    if payload.enabled is True:
        tools_engine.enable_family(family, user_id=user["id"])
    elif payload.enabled is False:
        tools_engine.disable_family(family, user_id=user["id"])

    if payload.model_name is not None:
        if payload.model_name.strip():
            tools_engine.set_family_model(
                family=family,
                backend=payload.model_backend or "openai",
                model=payload.model_name,
                base_url=payload.model_base_url or "",
                user_id=user["id"],
            )
        else:
            tools_engine.clear_family_model(family, user_id=user["id"])

    # Retourner l'état mis à jour
    updated = next(f for f in tools_engine.list_families() if f["family"] == family)
    return FamilyOut(**updated)


@router.delete("/families/{family}/model")
async def clear_family_model(family: str, user: dict = Depends(require_auth)):
    """Supprime le modèle assigné à une famille (retour au modèle principal)."""
    families = {f["family"] for f in tools_engine.list_families()}
    if family not in families:
        raise HTTPException(status_code=404, detail=f"Famille {family!r} inconnue.")
    tools_engine.clear_family_model(family, user_id=user["id"])
    return {"status": "ok", "family": family, "model": ""}
