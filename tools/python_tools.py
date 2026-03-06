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
tools/python_tools.py — Outils d'exécution de code Python
==========================================================

Outils exposés (5) :
  - python_exec          : exécute du code Python complet avec imports,
                           état persistant entre les appels de la session
  - python_install       : installe un package pip dans l'environnement virtuel
  - python_run_script    : exécute un script Python depuis un fichier
  - python_list_packages : liste les packages installés dans l'environnement
  - python_reset_env     : réinitialise l'environnement virtuel

python_eval a été supprimé et fusionné dans python_exec, qui gère maintenant
aussi bien les expressions simples que le code complet avec imports.

L'état est persistant entre les appels : les variables, imports et fonctions
définis dans un appel sont disponibles dans les suivants (même session).
Pour réinitialiser l'état de session, appelez python_exec avec reset_state=True.
"""

import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from core.tools_engine import tool, set_current_family, _TOOL_ICONS

set_current_family("python_tools", "Python", "🐍")

# ── Configuration ──────────────────────────────────────────────────────────
VENV_DIR    = Path.home() / ".promethee_python_env"
VENV_PYTHON = VENV_DIR / "bin" / "python"
VENV_PIP    = VENV_DIR / "bin" / "pip"

# Fichier de persistence de l'état de session (variables entre appels)
_STATE_FILE = Path(tempfile.gettempdir()) / "promethee_python_state.pkl"

# ── Icônes UI ──────────────────────────────────────────────────────────────
_TOOL_ICONS.update({
    "python_exec":          "🐍",
    "python_install":       "📦",
    "python_run_script":    "📜",
    "python_list_packages": "📋",
    "python_reset_env":     "♻️",
})


# ── Gestion de l'environnement virtuel ─────────────────────────────────────

def _ensure_venv() -> tuple[bool, str]:
    if VENV_PYTHON.exists() and VENV_PIP.exists():
        return True, "Environnement virtuel prêt"
    try:
        VENV_DIR.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return False, f"Échec création venv : {result.stderr}"
        subprocess.run([str(VENV_PIP), "install", "--upgrade", "pip"],
                       capture_output=True, timeout=60)
        return True, "Environnement virtuel créé avec succès"
    except subprocess.TimeoutExpired:
        return False, "Timeout lors de la création de l'environnement virtuel"
    except Exception as e:
        return False, f"Erreur création environnement : {e}"


def _run_in_venv(code: str, timeout: int = 30) -> tuple[int, str, str]:
    success, msg = _ensure_venv()
    if not success:
        return 1, "", msg
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", code],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(Path.home()),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Timeout après {timeout}s"
    except Exception as e:
        return 1, "", f"Erreur d'exécution : {e}"


def _run_script_in_venv(script_path: str, timeout: int = 30) -> tuple[int, str, str]:
    success, msg = _ensure_venv()
    if not success:
        return 1, "", msg
    path = Path(script_path).expanduser().resolve()
    if not path.exists():
        return 1, "", f"Fichier introuvable : {script_path}"
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), str(path)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(path.parent),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Timeout après {timeout}s"
    except Exception as e:
        return 1, "", f"Erreur d'exécution : {e}"


# ── Persistance de l'état entre appels ─────────────────────────────────────
#
# L'état est sérialisé dans un fichier pickle temporaire après chaque appel
# réussi. Les objets non-sérialisables (modules, connexions, fichiers ouverts)
# sont silencieusement ignorés lors de la sauvegarde.

def _build_exec_wrapper(code: str, img_path: Path) -> str:
    state_file_repr = repr(str(_STATE_FILE))
    img_path_repr   = repr(str(img_path))
    return f"""
import sys as _sys, pickle as _pkl, os as _os

# ── Chargement de l'état de session ──
_state_file = {state_file_repr}
_ns = {{}}
if _os.path.exists(_state_file):
    try:
        with open(_state_file, 'rb') as _f:
            _ns = _pkl.load(_f)
    except Exception:
        _ns = {{}}

# ── Backend matplotlib non-interactif ──
_matplotlib_used = False
try:
    import matplotlib as _mpl
    _mpl.use("Agg")
    import matplotlib.pyplot as _plt_orig
    _matplotlib_used = True
    _savefig_called = False
    _orig_savefig = _plt_orig.savefig
    _orig_show    = _plt_orig.show

    def _patched_savefig(fname=None, *a, **kw):
        global _savefig_called
        _savefig_called = True
        _orig_savefig(fname if fname is not None else {img_path_repr}, *a, **kw)

    def _patched_show(*a, **kw):
        global _savefig_called
        if not _savefig_called:
            _orig_savefig({img_path_repr}, bbox_inches="tight", dpi=150)
            _savefig_called = True
        _plt_orig.close("all")

    _plt_orig.savefig = _patched_savefig
    _plt_orig.show    = _patched_show
except ImportError:
    pass

# Injecter l'état précédent dans le namespace local
locals().update(_ns)

# ── Code utilisateur ──
{code}
# ── Fin code utilisateur ──

# Auto-save matplotlib si aucun show/savefig explicite
if _matplotlib_used:
    try:
        if not _savefig_called:
            import matplotlib.pyplot as _plt_check
            if _plt_check.get_fignums():
                _plt_check.savefig({img_path_repr}, bbox_inches="tight", dpi=150)
    except Exception:
        pass

# ── Sauvegarde de l'état de session ──
_to_save = {{}}
for _k, _v in list(locals().items()):
    if _k.startswith('_'):
        continue
    try:
        _pkl.dumps(_v)
        _to_save[_k] = _v
    except Exception:
        pass
try:
    with open(_state_file, 'wb') as _f:
        _pkl.dump(_to_save, _f)
except Exception:
    pass
"""


# ── Outils ─────────────────────────────────────────────────────────────────

@tool(
    name="python_exec",
    description=(
        "Exécute du code Python dans un environnement virtuel isolé. "
        "Supporte tous les imports, expressions simples et programmes complets. "
        "L'état est PERSISTANT entre les appels : variables, fonctions et imports "
        "définis restent disponibles lors des appels suivants de la même session. "
        "TRÈS IMPORTANT POUR LA PHYSIQUE-CHIMIE : Utilisez cet outil pour l'analyse "
        "de données de TP (incertitudes, régressions linéaires, tracés de courbes) "
        "en utilisant 'numpy', 'scipy' et 'matplotlib'. N'hésitez pas à demander "
        "à l'utilisateur d'importer un CSV via les outils data, puis utilisez Python "
        "pour faire le travail. "
        "Pour les packages manquants, utilisez python_install d'abord (ex: scipy). "
        "Si le code génère un graphique matplotlib, il sera automatiquement affiché dans le chat."
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Code Python à exécuter. Supporte imports, fonctions, classes, "
                    "expressions simples et programmes multi-lignes. "
                    "Utilisez print() pour afficher des résultats. "
                    "Les variables définies ici seront disponibles dans les appels suivants."
                ),
            },
            "timeout": {
                "type": "integer",
                "default": 30,
                "description": "Timeout en secondes (défaut: 30). Augmenter pour les traitements longs.",
            },
            "reset_state": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Si True, efface l'état de session avant d'exécuter le code. "
                    "Utile pour repartir d'un environnement propre."
                ),
            },
        },
        "required": ["code"],
    },
)
def python_exec(code: str, timeout: int = 30, reset_state: bool = False) -> dict:
    """Exécution Python complète dans un venv avec état persistant entre les appels."""

    if reset_state:
        _STATE_FILE.unlink(missing_ok=True)

    img_dir  = Path(tempfile.mkdtemp(prefix="promethee_plot_"))
    img_path = img_dir / "plot.png"

    wrapper = _build_exec_wrapper(code, img_path)
    returncode, stdout, stderr = _run_in_venv(wrapper, timeout)

    _DATA_URI_RE = re.compile(
        r'src=["\']?(data:(image/(?:png|gif|jpeg|webp));base64,([A-Za-z0-9+/=]+))["\']?',
        re.IGNORECASE,
    )

    image_path: str | None = None
    clean_stdout = (stdout or "").strip()

    m = _DATA_URI_RE.search(clean_stdout)
    if m:
        mime_type = m.group(2).lower()
        ext = mime_type.split("/")[1]
        try:
            out_path = img_dir / f"plot.{ext}"
            out_path.write_bytes(base64.b64decode(m.group(3)))
            image_path   = str(out_path)
            clean_stdout = _DATA_URI_RE.sub("[image générée — affichée dans le chat]", clean_stdout)
            clean_stdout = re.sub(r"<img\b[^>]*>\s*", "", clean_stdout, flags=re.IGNORECASE).strip()
        except Exception:
            pass

    if img_path.exists() and img_path.stat().st_size > 0:
        image_path = str(img_path)

    if returncode == 0:
        out = {"status": "success", "output": clean_stdout or "(aucune sortie)"}
        if image_path:
            out["image_path"] = image_path
        return out
    else:
        return {"status": "error", "error": (stderr or "").strip() or "(erreur inconnue)",
                "returncode": returncode}


@tool(
    name="python_install",
    description=(
        "Installe un package Python via pip dans l'environnement virtuel dédié. "
        "Les packages installés seront disponibles pour python_exec et python_run_script."
    ),
    parameters={
        "type": "object",
        "properties": {
            "package": {
                "type": "string",
                "description": (
                    "Nom du package à installer (ex: 'requests', 'pandas==2.0.0', 'numpy>=1.24'). "
                    "Supporte les versions spécifiques et les opérateurs de version."
                ),
            },
            "upgrade": {
                "type": "boolean",
                "default": False,
                "description": "Mettre à jour le package s'il est déjà installé.",
            },
        },
        "required": ["package"],
    },
)
def python_install(package: str, upgrade: bool = False) -> dict:
    """Installe un package pip dans l'environnement virtuel."""
    success, msg = _ensure_venv()
    if not success:
        return {"status": "error", "error": msg}
    cmd = [str(VENV_PIP), "install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.append(package)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return {"status": "success",
                    "message": f"Package '{package}' installé avec succès",
                    "output": result.stdout.strip()[-200:]}
        return {"status": "error", "error": result.stderr.strip()[-300:],
                "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Timeout lors de l'installation (120s)"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="python_run_script",
    description=(
        "Exécute un script Python depuis un fichier dans l'environnement virtuel. "
        "Le script a accès à tous les packages installés via python_install. "
        "Contrairement à python_exec, ce mode n'utilise pas l'état persistant de session."
    ),
    parameters={
        "type": "object",
        "properties": {
            "script_path": {
                "type": "string",
                "description": "Chemin vers le fichier .py à exécuter.",
            },
            "timeout": {
                "type": "integer",
                "default": 30,
                "description": "Timeout en secondes (défaut: 30).",
            },
        },
        "required": ["script_path"],
    },
)
def python_run_script(script_path: str, timeout: int = 30) -> dict:
    """Exécute un script Python depuis un fichier."""
    returncode, stdout, stderr = _run_script_in_venv(script_path, timeout)
    if returncode == 0:
        return {"status": "success", "output": stdout.strip() if stdout else "(aucune sortie)"}
    return {"status": "error", "error": stderr.strip() or "(erreur inconnue)",
            "returncode": returncode}


@tool(
    name="python_list_packages",
    description="Liste tous les packages Python installés dans l'environnement virtuel avec leurs versions.",
    parameters={"type": "object", "properties": {}, "required": []},
)
def python_list_packages() -> dict:
    """Liste les packages installés."""
    success, msg = _ensure_venv()
    if not success:
        return {"status": "error", "error": msg}
    try:
        result = subprocess.run([str(VENV_PIP), "list", "--format=json"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            packages = json.loads(result.stdout)
            return {"status": "success", "count": len(packages),
                    "packages": [f"{p['name']}=={p['version']}" for p in packages]}
        return {"status": "error", "error": result.stderr}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Timeout"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="python_reset_env",
    description=(
        "Réinitialise complètement l'environnement virtuel Python ET l'état de session. "
        "ATTENTION : Supprime tous les packages installés et recrée l'environnement. "
        "À utiliser en cas de problème ou pour repartir à zéro."
    ),
    parameters={
        "type": "object",
        "properties": {
            "confirm": {
                "type": "boolean",
                "description": "Doit être true pour confirmer la réinitialisation.",
            },
        },
        "required": ["confirm"],
    },
)
def python_reset_env(confirm: bool) -> dict:
    """Réinitialise l'environnement virtuel et l'état de session."""
    if not confirm:
        return {"status": "cancelled", "message": "Passez confirm=true pour confirmer."}
    try:
        import shutil
        _STATE_FILE.unlink(missing_ok=True)
        if VENV_DIR.exists():
            shutil.rmtree(VENV_DIR)
        success, msg = _ensure_venv()
        if success:
            return {"status": "success",
                    "message": "Environnement virtuel et état de session réinitialisés"}
        return {"status": "error", "error": f"Échec recréation : {msg}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}
