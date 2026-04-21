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
tools_engine.py — Moteur d'enregistrement et d'exécution des outils
====================================================================

Ce module ne contient AUCUN outil. Son unique responsabilité est :
  - Fournir le décorateur @tool pour enregistrer des outils depuis n'importe
    quel module externe.
  - Exposer get_tool_schemas() et call_tool() pour que l'agent LLM puisse
    les invoquer.
  - Fournir list_tools() pour l'affichage dans l'interface utilisateur.
  - Gérer l'activation/désactivation par famille d'outils (module).

Les outils sont définis dans des modules spécialisés et s'enregistrent
automatiquement à l'import.

Usage dans main.py / app.py :
    from tools import register_all
    register_all()                       # enregistre tous les outils

    from core.tools_engine import get_tool_schemas, call_tool, list_tools
"""

import contextvars
import json
from pathlib import Path
from typing import Callable


# ── Registre global ────────────────────────────────────────────────────────

_TOOLS: dict[str, dict] = {}

_TOOL_ICONS: dict[str, str] = {}

# Mapping outil → famille (clé du module, ex: "legifrance_tools")
_TOOL_FAMILY: dict[str, str] = {}

# ── État en mémoire des familles désactivées ──────────────────────────────
#
# Historique des architectures :
#
#   v1 – fichier global   ~/.promethee_disabled_families.json
#         Problème : partagé entre tous les utilisateurs (/ = /root dans le
#         conteneur), perdu à chaque recréation, race conditions.
#
#   v2 – variable globale _DISABLED_FAMILIES: set[str]
#         Problème : partagée entre toutes les coroutines FastAPI simultanées.
#         Une requête de l'utilisateur A écrasait l'état de B dès que
#         load_user_families() était appelé dans n'importe quel handler
#         concurrent. Résultat : la liste des outils visible dans la sidebar
#         pouvait différer de la sélection enregistrée dans l'éditeur de profil.
#
#   v3 (actuelle) – ContextVar par coroutine/thread
#         Chaque requête FastAPI s'exécute dans son propre contexte asyncio.
#         _DISABLED_FAMILIES_VAR est isolé par contexte : les requêtes
#         concurrentes ne peuvent pas se polluer mutuellement.
#         asyncio.to_thread() propage le contexte vers les threads workers,
#         donc les outils exécutés dans agent_loop() voient le bon état.
#
# Interface publique inchangée : load_user_families(), save_user_families(),
# apply_profile_families(), enable_family(), disable_family(),
# is_family_disabled() — les appelants n'ont rien à modifier.

_DISABLED_FAMILIES_VAR: contextvars.ContextVar[set[str]] = contextvars.ContextVar(
    "disabled_families", default=None  # type: ignore[arg-type]
)


def _get_disabled() -> set[str]:
    """Retourne l'ensemble des familles désactivées pour le contexte courant.
    Crée un ensemble vide si le ContextVar n'a pas encore été initialisé
    dans ce contexte (première requête ou contexte hors FastAPI)."""
    val = _DISABLED_FAMILIES_VAR.get(None)
    if val is None:
        val = set()
        _DISABLED_FAMILIES_VAR.set(val)
    return val


def _set_disabled(families: set[str]) -> None:
    """Remplace l'ensemble des familles désactivées pour le contexte courant."""
    _DISABLED_FAMILIES_VAR.set(families)


def load_user_families(user_id: str) -> None:
    """
    Charge l'état des familles désactivées depuis le kv_store SQLite de
    l'utilisateur (clé "disabled_families") et l'installe dans le ContextVar
    de la coroutine courante.

    Remplace l'ancien _load_disabled_families() sur fichier JSON global.
    Isolation par requête garantie : deux requêtes concurrentes ne peuvent
    pas se polluer mutuellement.
    """
    try:
        from pathlib import Path as _Path
        data_dir = _Path(__file__).resolve().parent.parent / "data" / user_id
        db_path = str(data_dir / "history.db")
        from core.database import HistoryDB
        db = HistoryDB(db_path=db_path)
        raw = db.kv_get("disabled_families")
        _set_disabled(set(json.loads(raw)) if raw else set())
    except Exception:
        _set_disabled(set())


def save_user_families(user_id: str) -> None:
    """
    Persiste l'état courant des familles désactivées (depuis le ContextVar)
    dans le kv_store SQLite de l'utilisateur (clé "disabled_families").

    Remplace l'ancien _save_disabled_families() sur fichier JSON global.
    """
    try:
        from pathlib import Path as _Path
        data_dir = _Path(__file__).resolve().parent.parent / "data" / user_id
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(data_dir / "history.db")
        from core.database import HistoryDB
        db = HistoryDB(db_path=db_path)
        db.kv_set("disabled_families", json.dumps(sorted(_get_disabled())))
    except Exception:
        pass



# ── Registre des modèles assignés par famille ──────────────────────────────
#
# Persistance dans le kv_store SQLite par utilisateur (clé "family_models").
# Remplace ~/.promethee_family_models.json (vestige desktop mono-utilisateur).
# Format stocké : { "imap_tools": { "backend": "openai", "model": "...",
#                                    "base_url": "" }, ... }
#
# Les familles absentes héritent du modèle principal (build_client).

_FAMILY_MODELS: dict[str, dict] = {}


def load_user_family_models(user_id: str) -> None:
    """Charge les modèles de familles depuis le kv_store de l'utilisateur."""
    global _FAMILY_MODELS
    try:
        from pathlib import Path as _Path
        data_dir = _Path(__file__).resolve().parent.parent / "data" / user_id
        db_path = str(data_dir / "history.db")
        from core.database import HistoryDB
        db = HistoryDB(db_path=db_path)
        raw = db.kv_get("family_models")
        _FAMILY_MODELS = json.loads(raw) if raw else {}
    except Exception:
        _FAMILY_MODELS = {}


def save_user_family_models(user_id: str) -> None:
    """Persiste les modèles de familles dans le kv_store de l'utilisateur."""
    try:
        from pathlib import Path as _Path
        data_dir = _Path(__file__).resolve().parent.parent / "data" / user_id
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(data_dir / "history.db")
        from core.database import HistoryDB
        db = HistoryDB(db_path=db_path)
        db.kv_set("family_models", json.dumps(_FAMILY_MODELS))
    except Exception:
        pass


def get_family_model(family: str) -> dict | None:
    """
    Retourne la configuration du modèle assigné à une famille, ou None si
    aucun modèle n'est configuré (l'appelant doit utiliser le modèle principal).

    Retourne un dict :
        { "backend": "openai"|"ollama", "model": str, "base_url": str }
    """
    entry = _FAMILY_MODELS.get(family)
    if not entry or not entry.get("model", "").strip():
        return None
    return entry


def set_family_model(family: str, backend: str, model: str, base_url: str = "", user_id: str | None = None) -> None:
    """
    Assigne un modèle à une famille. Passer model="" pour supprimer l'assignation
    et revenir au modèle principal.
    Persiste dans le kv_store SQLite de l'utilisateur si user_id est fourni.
    """
    if not model.strip():
        _FAMILY_MODELS.pop(family, None)
    else:
        _FAMILY_MODELS[family] = {
            "backend":  backend.strip().lower(),
            "model":    model.strip(),
            "base_url": base_url.strip(),
        }
    if user_id:
        save_user_family_models(user_id)


def clear_family_model(family: str, user_id: str | None = None) -> None:
    """Supprime l'assignation de modèle pour une famille (retour au modèle principal)."""
    _FAMILY_MODELS.pop(family, None)
    if user_id:
        save_user_family_models(user_id)



# ── Famille courante (positionnée par chaque module avant ses @tool) ───────

_current_family: str = "Inconnu"
_current_family_label: str = "Inconnu"
_current_family_icon: str = "🔧"


def set_current_family(family: str, label: str = "", icon: str = "🔧") -> None:
    """
    À appeler depuis chaque module de tools AVANT la déclaration des @tool.
    Exemple :
        set_current_family("legifrance_tools", "Légifrance", "⚖️")
    """
    global _current_family, _current_family_label, _current_family_icon
    _current_family = family
    _current_family_label = label or family
    _current_family_icon = icon


# ── Décorateur d'enregistrement ────────────────────────────────────────────

def tool(name: str, description: str, parameters: dict):
    """
    Décorateur pour enregistrer une fonction comme outil LLM.

    Usage dans un module d'outils :

        from core.tools_engine import tool, set_current_family

        set_current_family("legifrance_tools", "Légifrance", "⚖️")

        @tool(
            name="mon_outil",
            description="Ce que fait l'outil.",
            parameters={
                "type": "object",
                "properties": {
                    "param": {"type": "string", "description": "..."}
                },
                "required": ["param"]
            }
        )
        def mon_outil(param: str) -> str:
            return f"Résultat : {param}"

    L'outil est immédiatement disponible via call_tool() dès que le module
    qui le contient a été importé.
    """
    def decorator(fn: Callable) -> Callable:
        _TOOLS[name] = {
            "fn": fn,
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "family": _current_family,
            "family_label": _current_family_label,
            "family_icon": _current_family_icon,
        }
        _TOOL_FAMILY[name] = _current_family
        return fn
    return decorator


# ── API familles ───────────────────────────────────────────────────────────

def apply_profile_families(
    enabled: list[str],
    disabled: list[str],
    user_id: str | None = None,
) -> None:
    """
    Applique les familles définies par un profil de manière ÉPHÉMÈRE pour
    la durée de la requête en cours. Ne persiste pas sur disque.

    Logique :
      - Si 'enabled' et 'disabled' sont tous deux vides → aucune contrainte :
        on charge les prefs persistées de l'utilisateur (état "neutre").
      - Sinon, on part des prefs persistées, on applique les overrides du
        profil (disabled → ajoutés, enabled → retirés), mais on ne sauvegarde
        PAS : l'état est éphémère et propre à la requête en cours.

    Parameters
    ----------
    enabled  : familles forcées actives par le profil.
    disabled : familles forcées inactives par le profil.
    user_id  : identifiant de l'utilisateur courant (pour charger ses prefs).
               Peut être None en mode anonyme/admin (aucune pref chargée).

    NOTE : ne jamais appeler save_user_families() ici — intentionnel.
    La persistance est réservée aux actions manuelles (enable/disable_family).
    Isolation par requête : opère sur le ContextVar, pas sur un global partagé.
    """
    # Toujours partir des prefs persistées de cet utilisateur
    if user_id:
        load_user_families(user_id)
    else:
        _set_disabled(set())

    if not enabled and not disabled:
        # Aucun override de profil : on garde les prefs utilisateur telles quelles
        return

    # Appliquer les overrides du profil dans une copie locale (sans sauvegarder)
    current = set(_get_disabled())
    for fam in disabled:
        current.add(fam)
    for fam in enabled:
        current.discard(fam)
    _set_disabled(current)


def disable_family(family: str, user_id: str | None = None) -> None:
    """
    Désactive une famille d'outils et persiste le choix.

    Parameters
    ----------
    user_id : identifiant de l'utilisateur courant (pour la persistance SQLite).
    """
    current = set(_get_disabled())
    current.add(family)
    _set_disabled(current)
    if user_id:
        save_user_families(user_id)


def enable_family(family: str, user_id: str | None = None) -> None:
    """
    Réactive une famille d'outils et persiste le choix.

    Parameters
    ----------
    user_id : identifiant de l'utilisateur courant (pour la persistance SQLite).
    """
    current = set(_get_disabled())
    current.discard(family)
    _set_disabled(current)
    if user_id:
        save_user_families(user_id)


def is_family_disabled(family: str) -> bool:
    """Retourne True si la famille est désactivée dans le contexte courant."""
    return family in _get_disabled()


def list_families() -> list[dict]:
    """
    Retourne la liste des familles connues avec leur état activé/désactivé
    et le modèle éventuellement assigné.

    Chaque entrée :
        { family, label, icon, enabled, tool_count,
          model_backend, model_name, model_base_url }

    model_name == "" signifie "modèle principal" (aucune assignation).
    L'état enabled/disabled reflète le ContextVar de la requête courante.
    """
    disabled = _get_disabled()
    families: dict[str, dict] = {}
    for name, t in _TOOLS.items():
        fam = t.get("family", "unknown")
        if fam not in families:
            assigned = _FAMILY_MODELS.get(fam, {})
            families[fam] = {
                "family":         fam,
                "label":          t.get("family_label", fam),
                "icon":           t.get("family_icon", "🔧"),
                "enabled":        fam not in disabled,
                "tool_count":     0,
                "model_backend":  assigned.get("backend",  ""),
                "model_name":     assigned.get("model",    ""),
                "model_base_url": assigned.get("base_url", ""),
            }
        families[fam]["tool_count"] += 1
    return list(families.values())


# ── API publique ────────────────────────────────────────────────────────────

def get_tool_schemas() -> list[dict]:
    """
    Retourne la liste des schémas de tous les outils ACTIVÉS.
    Les outils appartenant à une famille désactivée sont exclus.
    Passez directement ce résultat au champ ``tools`` de l'API Anthropic.
    L'état reflète le ContextVar de la requête courante (isolation par requête).
    """
    disabled = _get_disabled()
    return [
        t["schema"]
        for name, t in _TOOLS.items()
        if t.get("family", "unknown") not in disabled
    ]


def call_tool(name: str, arguments: dict) -> str:
    """
    Appelle un outil par son nom avec les arguments fournis par le LLM.

    Retourne toujours une chaîne (les dict/list sont sérialisés en JSON).
    En cas d'erreur, retourne un message d'erreur lisible plutôt que de lever.
    """
    if name not in _TOOLS:
        return f"Outil inconnu : {name}"
    try:
        result = _TOOLS[name]["fn"](**arguments)
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return str(result)
    except Exception as e:
        return f"Erreur lors de l'exécution de {name} : {e}"


def list_tools() -> list[dict]:
    """
    Retourne la liste de TOUS les outils enregistrés (actifs et désactivés)
    avec nom, description, icône et famille.
    Destiné à l'affichage dans l'interface utilisateur.
    L'état enabled reflète le ContextVar de la requête courante.
    """
    disabled = _get_disabled()
    return [
        {
            "name": name,
            "description": t["schema"]["function"]["description"],
            "icon": _TOOL_ICONS.get(name, t.get("family_icon", "🔧")),
            "family": t.get("family", "unknown"),
            "family_label": t.get("family_label", "unknown"),
            "family_icon": t.get("family_icon", "🔧"),
            "enabled": t.get("family", "unknown") not in disabled,
        }
        for name, t in _TOOLS.items()
    ]


def registered_tool_names() -> list[str]:
    """Retourne la liste des noms des outils actuellement enregistrés (tous, même désactivés)."""
    return list(_TOOLS.keys())


# ── Progression en cours d'exécution d'outil ───────────────────────────────

_progress_callback: Callable[[str], None] | None = None


def set_tool_progress_callback(fn: Callable[[str], None] | None) -> None:
    """
    Installe un callback appelé par les outils pour signaler leur progression.
    Passer None pour désinstaller.
    Appelé par AgentWorker avant/après agent_loop.
    """
    global _progress_callback
    _progress_callback = fn


def report_progress(message: str) -> None:
    """
    À appeler depuis un outil pour signaler une étape de progression.
    Sans effet si aucun callback n'est installé.
    """
    if _progress_callback is not None:
        try:
            _progress_callback(message)
        except Exception:
            pass
