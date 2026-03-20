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

import json
from pathlib import Path
from typing import Callable


# ── Registre global ────────────────────────────────────────────────────────

_TOOLS: dict[str, dict] = {}

_TOOL_ICONS: dict[str, str] = {}

# Mapping outil → famille (clé du module, ex: "legifrance_tools")
_TOOL_FAMILY: dict[str, str] = {}

# ── Persistance des familles désactivées ───────────────────────────────────

_DISABLED_FAMILIES: set[str] = set()
_PREFS_FILE = Path.home() / ".promethee_disabled_families.json"


def _json_load(path: Path, default):
    """
    Charge un fichier JSON depuis ``path``.

    Retourne ``default`` si le fichier est absent, illisible ou si le type
    du contenu ne correspond pas à celui de ``default`` (validation légère).

    Parameters
    ----------
    path : Path
        Chemin vers le fichier JSON.
    default : list | dict
        Valeur de repli — détermine aussi le type attendu.
    """
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, type(default)):
                return data
    except Exception:
        pass
    return default


def _json_save(path: Path, data) -> None:
    """
    Persiste ``data`` en JSON dans ``path``.

    Silencieux en cas d'erreur (permissions, disque plein…) : la perte
    d'une préférence utilisateur ne doit pas faire crasher l'application.

    Parameters
    ----------
    path : Path
        Chemin cible (créé ou écrasé).
    data : list | dict
        Données sérialisables en JSON.
    """
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_disabled_families() -> None:
    global _DISABLED_FAMILIES
    _DISABLED_FAMILIES = set(_json_load(_PREFS_FILE, []))


def _save_disabled_families() -> None:
    _json_save(_PREFS_FILE, sorted(_DISABLED_FAMILIES))


_load_disabled_families()


# ── Registre des modèles assignés par famille ──────────────────────────────
#
# Persistance dans ~/.promethee_family_models.json
# Format : { "imap_tools": { "backend": "ollama", "model": "mistral-small:7b",
#                             "base_url": "" }, ... }
#
# Les familles absentes du fichier héritent du modèle principal (build_client).

_FAMILY_MODELS: dict[str, dict] = {}
_FAMILY_MODELS_FILE = Path.home() / ".promethee_family_models.json"


def _load_family_models() -> None:
    global _FAMILY_MODELS
    _FAMILY_MODELS = _json_load(_FAMILY_MODELS_FILE, {})


def _save_family_models() -> None:
    _json_save(_FAMILY_MODELS_FILE, _FAMILY_MODELS)


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


def set_family_model(family: str, backend: str, model: str, base_url: str = "") -> None:
    """
    Assigne un modèle à une famille. Passer model="" pour supprimer l'assignation
    et revenir au modèle principal.
    """
    if not model.strip():
        _FAMILY_MODELS.pop(family, None)
    else:
        _FAMILY_MODELS[family] = {
            "backend":  backend.strip().lower(),
            "model":    model.strip(),
            "base_url": base_url.strip(),
        }
    _save_family_models()


def clear_family_model(family: str) -> None:
    """Supprime l'assignation de modèle pour une famille (retour au modèle principal)."""
    _FAMILY_MODELS.pop(family, None)
    _save_family_models()


_load_family_models()


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

def apply_profile_families(enabled: list[str], disabled: list[str]) -> None:
    """
    Applique les familles définies par un profil, en préservant les
    surcharges manuelles de l'utilisateur stockées dans le fichier de prefs.

    Logique :
      - Si 'enabled' et 'disabled' sont tous deux vides → aucune contrainte,
        on restaure toutes les familles (retour à l'état des prefs utilisateur).
      - Sinon, on applique les disabled du profil, on force les enabled du profil,
        et on laisse les familles non mentionnées à leur état utilisateur.

    L'état résultant est immédiatement persisté.
    """
    if not enabled and not disabled:
        # Pas de contrainte de profil : restaurer les prefs utilisateur pures
        _load_disabled_families()
        return

    # Partir des prefs utilisateur existantes
    _load_disabled_families()

    for fam in disabled:
        _DISABLED_FAMILIES.add(fam)
    for fam in enabled:
        _DISABLED_FAMILIES.discard(fam)

    _save_disabled_families()


def disable_family(family: str) -> None:
    """Désactive tous les outils d'une famille (ils ne seront plus envoyés au LLM)."""
    _DISABLED_FAMILIES.add(family)
    _save_disabled_families()


def enable_family(family: str) -> None:
    """Réactive tous les outils d'une famille."""
    _DISABLED_FAMILIES.discard(family)
    _save_disabled_families()


def is_family_disabled(family: str) -> bool:
    """Retourne True si la famille est désactivée."""
    return family in _DISABLED_FAMILIES


def list_families() -> list[dict]:
    """
    Retourne la liste des familles connues avec leur état activé/désactivé
    et le modèle éventuellement assigné.

    Chaque entrée :
        { family, label, icon, enabled, tool_count,
          model_backend, model_name, model_base_url }

    model_name == "" signifie "modèle principal" (aucune assignation).
    """
    families: dict[str, dict] = {}
    for name, t in _TOOLS.items():
        fam = t.get("family", "unknown")
        if fam not in families:
            assigned = _FAMILY_MODELS.get(fam, {})
            families[fam] = {
                "family":         fam,
                "label":          t.get("family_label", fam),
                "icon":           t.get("family_icon", "🔧"),
                "enabled":        fam not in _DISABLED_FAMILIES,
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
    """
    return [
        t["schema"]
        for name, t in _TOOLS.items()
        if t.get("family", "unknown") not in _DISABLED_FAMILIES
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
    """
    return [
        {
            "name": name,
            "description": t["schema"]["function"]["description"],
            "icon": _TOOL_ICONS.get(name, t.get("family_icon", "🔧")),
            "family": t.get("family", "unknown"),
            "family_label": t.get("family_label", "unknown"),
            "family_icon": t.get("family_icon", "🔧"),
            "enabled": t.get("family", "unknown") not in _DISABLED_FAMILIES,
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
