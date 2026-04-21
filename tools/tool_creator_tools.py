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
tools/tool_creator_tools.py — Génération automatique d'outils Prométhée
========================================================================

Outils exposés (1) :

  - create_tool : génère un fichier tools/*.py complet à partir d'une
                  description en langage naturel ou d'une spécification
                  JSON/YAML, avec validation syntaxique et d'import.

Stratégie :
  1. Charge le skill `skill_tool_creator` pour obtenir le protocole de
     génération (structure, patterns, checklist qualité).
  2. Envoie au LLM un prompt structuré combinant le skill + la demande
     utilisateur (description NL et/ou spécification JSON/YAML).
  3. Extrait le code Python généré du bloc ```python … ```.
  4. Valide la syntaxe via `ast.parse`.
  5. Simule un import en isolation (exec dans un namespace contrôlé) pour
     détecter les erreurs de référence évidentes.
  6. Retourne le code validé + le bloc .env + la ligne __init__.py +
     une description utilisateur de l'outil généré.

Le fichier n'est PAS écrit automatiquement sur disque : il est retourné
dans le résultat pour que l'utilisateur valide avant intégration.

Usage :
    import tools.tool_creator_tools
"""

import ast
import json
import os
import re
import textwrap
from pathlib import Path
from typing import Optional

from core.tools_engine import tool, set_current_family, _TOOL_ICONS
from core.skill_manager import get_skill_manager

set_current_family("tool_creator_tools", "Créateur d'outils", "🛠️")

_TOOL_ICONS.update({
    "create_tool": "🛠️",
})

# ══════════════════════════════════════════════════════════════════════════════
# Helpers internes
# ══════════════════════════════════════════════════════════════════════════════

def _load_skill() -> str:
    """Charge le skill skill_tool_creator. Retourne son contenu ou une chaîne vide."""
    try:
        sm = get_skill_manager()
        return sm.read_skill("skill_tool_creator")
    except Exception:
        return ""


def _build_system_prompt(skill_content: str) -> str:
    """Construit le prompt système pour la génération d'outil."""
    base = textwrap.dedent("""\
        Tu es un expert Python qui génère des outils pour l'application Prométhée.
        Tu dois produire un fichier tools/*.py complet, valide et de qualité production.

        RÈGLES DE GÉNÉRATION :
        - Retourner EXACTEMENT trois blocs délimités, dans cet ordre :

          ```python
          # contenu complet du fichier tools/<nom>_tools.py
          ```

          ```env
          # variables .env à ajouter (commentées et documentées)
          # et lignes config.py à ajouter dans la classe Config
          ```

          ```doc
          # description utilisateur en français :
          # - ce que fait l'outil
          # - comment le configurer (.env)
          # - exemples de demandes que l'utilisateur peut faire
          # - ligne à ajouter dans tools/__init__.py
          ```

        - Ne rien écrire en dehors de ces trois blocs.
        - Le code Python doit être complet et directement utilisable.
        - Respecter scrupuleusement le protocole décrit dans le skill ci-dessous.
    """)

    if skill_content:
        base += f"\n\n---\n\n# SKILL : Créateur d'outils Prométhée\n\n{skill_content}"

    return base


def _extract_block(text: str, lang: str) -> str:
    """Extrait le contenu d'un bloc ```lang … ``` dans le texte généré."""
    pattern = rf"```{lang}\s*\n(.*?)```"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _validate_syntax(code: str) -> tuple[bool, str]:
    """Vérifie la syntaxe Python via ast.parse."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"Erreur syntaxe ligne {e.lineno} : {e.msg}"


def _validate_import(code: str) -> tuple[bool, str, list[str]]:
    """
    Simule un import du code généré dans un namespace isolé.

    Remplace les imports locaux Prométhée (core.*, tools.*) par des stubs
    minimalistes pour permettre l'exécution sans l'environnement complet.
    Détecte les NameError, AttributeError évidents au niveau module.

    Returns (ok, error_message, outils_détectés)
    """
    # Stub des imports Prométhée
    stub_code = textwrap.dedent("""\
        import sys, types

        # Stub core.tools_engine
        _te = types.ModuleType("core.tools_engine")
        _current_family = ["", "", ""]
        _TOOLS_STUB = {}
        _ICONS_STUB = {}

        def _tool_stub(name, description, parameters):
            def decorator(fn):
                _TOOLS_STUB[name] = fn
                return fn
            return decorator

        def _set_family_stub(family, label="", icon="🔧"):
            _current_family[:] = [family, label, icon]

        _te.tool = _tool_stub
        _te.set_current_family = _set_family_stub
        _te._TOOL_ICONS = _ICONS_STUB
        sys.modules["core"] = types.ModuleType("core")
        sys.modules["core.tools_engine"] = _te

        # Stub core.config
        _cfg_mod = types.ModuleType("core.config")
        class _Config:
            def __getattr__(self, name):
                return ""
        _cfg_mod.Config = _Config()
        sys.modules["core.config"] = _cfg_mod

        # Stub core.skill_manager (non utilisé dans les outils générés)
        _sm_mod = types.ModuleType("core.skill_manager")
        sys.modules["core.skill_manager"] = _sm_mod

        # Stub core.llm_service
        _llm_mod = types.ModuleType("core.llm_service")
        _llm_mod.build_client = lambda **kw: None
        sys.modules["core.llm_service"] = _llm_mod
    """)

    full_code = stub_code + "\n" + code
    namespace: dict = {}

    try:
        exec(compile(full_code, "<generated_tool>", "exec"), namespace)
    except ImportError as e:
        # Import tiers manquant : avertissement non bloquant
        return True, f"⚠️ Dépendance externe non installée (non bloquant) : {e}", list(namespace.get("_TOOLS_STUB", {}).keys())
    except Exception as e:
        return False, f"Erreur à l'exécution du module : {type(e).__name__} — {e}", []

    tools_found = list(namespace.get("_TOOLS_STUB", {}).keys())
    return True, "", tools_found


def _detect_tool_names_from_ast(code: str) -> list[str]:
    """Extrait les noms d'outils depuis le code via ast (fallback si import simulé échoue)."""
    names = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Chercher tool(name="...")
                if isinstance(func, ast.Name) and func.id == "tool":
                    for kw in node.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            names.append(kw.value.value)
    except Exception:
        pass
    return names


def _call_llm(system_prompt: str, user_prompt: str) -> tuple[bool, str]:
    """
    Appelle le modèle assigné à la famille 'tool_creator_tools' si configuré
    depuis l'UI (onglet Outils > Modèle), sinon le modèle principal.

    La résolution est déléguée à llm_service.build_family_client(), qui
    consulte le registre tools_engine._FAMILY_MODELS persisté dans
    ~/.promethee_family_models.json.
    """
    try:
        from core.llm_service import build_family_client

        client, model = build_family_client("tool_creator_tools")

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        return True, resp.choices[0].message.content

    except Exception as e:
        return False, f"Erreur LLM : {e}"


# ══════════════════════════════════════════════════════════════════════════════
# Outil exposé
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="create_tool",
    description=(
        "Génère automatiquement un outil Prométhée complet à partir d'une description "
        "en langage naturel ou d'une spécification JSON/YAML. "
        "Produit : le code Python du fichier tools/*.py, le bloc .env à ajouter, "
        "et une description utilisateur avec les exemples d'usage. "
        "Le code est validé syntaxiquement et par simulation d'import avant d'être retourné. "
        "Utilise automatiquement le modèle assigné à la famille 'tool_creator_tools' "
        "depuis l'onglet Outils des paramètres, sinon le modèle principal. "
        "À utiliser quand l'utilisateur demande de créer un nouvel outil pour Prométhée, "
        "d'intégrer un nouveau service ou une nouvelle API."
    ),
    parameters={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": (
                    "Description en langage naturel de l'outil à créer. "
                    "Préciser : le service ou l'API ciblé, les opérations souhaitées "
                    "(lecture, écriture, recherche…), les paramètres importants, "
                    "les contraintes (auth, dépendances…). "
                    "Exemple : 'Outil pour interroger l'API Légifrance — rechercher des textes "
                    "de loi par mots-clés et lire l'article complet. Nécessite une clé API OAuth2.'"
                ),
            },
            "specification": {
                "type": "string",
                "description": (
                    "Spécification structurée en JSON ou YAML décrivant les outils à générer "
                    "(optionnel, complète ou remplace la description). "
                    "Format libre : liste des outils avec leurs paramètres, types de retour, "
                    "endpoints API, variables d'env nécessaires."
                ),
            },
            "nom_fichier": {
                "type": "string",
                "description": (
                    "Nom souhaité pour le fichier généré, sans extension ni chemin "
                    "(ex: 'meteo_tools', 'gitlab_tools'). "
                    "Si absent, déduit automatiquement depuis la description."
                ),
            },
            "forcer_regeneration": {
                "type": "boolean",
                "description": (
                    "Si true et qu'un fichier du même nom existe déjà dans tools/, "
                    "génère quand même sans bloquer. Défaut : false (avertit si conflit)."
                ),
            },
        },
        "required": ["description"],
    },
)
def create_tool(
    description: str,
    specification: Optional[str] = None,
    nom_fichier: Optional[str] = None,
    forcer_regeneration: bool = False,
) -> dict:
    """
    Orchestre la génération d'un outil Prométhée :
      1. Charge le skill skill_tool_creator
      2. Construit le prompt système + utilisateur
      3. Appelle le LLM
      4. Extrait les trois blocs (python, env, doc)
      5. Valide syntaxe + import simulé
      6. Retourne le résultat structuré
    """

    # ── 1. Charger le skill ────────────────────────────────────────────────
    skill_content = _load_skill()

    # ── 2. Vérifier conflit de nom de fichier ──────────────────────────────
    tools_dir = Path(__file__).parent
    conflict_warning = None
    if nom_fichier:
        candidate = tools_dir / f"{nom_fichier}.py"
        if candidate.exists() and not forcer_regeneration:
            return {
                "status": "error",
                "error": (
                    f"Le fichier tools/{nom_fichier}.py existe déjà. "
                    "Utilisez forcer_regeneration=true pour générer quand même, "
                    "ou choisissez un autre nom via nom_fichier."
                ),
            }
        if candidate.exists():
            conflict_warning = f"⚠️ tools/{nom_fichier}.py existe déjà — le fichier généré remplacera l'existant si vous l'intégrez."

    # ── 3. Construire le prompt ────────────────────────────────────────────
    system_prompt = _build_system_prompt(skill_content)

    user_parts = [f"Génère un outil Prométhée avec les caractéristiques suivantes :\n\n{description}"]

    if specification:
        user_parts.append(
            f"\nSpécification complémentaire (JSON/YAML) :\n```\n{specification}\n```"
        )
    if nom_fichier:
        user_parts.append(f"\nNom de fichier souhaité : `{nom_fichier}.py`")

    user_prompt = "\n".join(user_parts)

    # ── 4. Appeler le LLM ─────────────────────────────────────────────────
    ok_llm, llm_output = _call_llm(system_prompt, user_prompt)
    if not ok_llm:
        return {"status": "error", "error": llm_output}

    # ── 5. Extraire les blocs ──────────────────────────────────────────────
    code_python = _extract_block(llm_output, "python")
    bloc_env    = _extract_block(llm_output, "env")
    bloc_doc    = _extract_block(llm_output, "doc")

    if not code_python:
        return {
            "status": "error",
            "error": (
                "Le LLM n'a pas produit de bloc ```python```. "
                "Résultat brut retourné pour inspection."
            ),
            "llm_output_brut": llm_output[:3000],
        }

    # ── 6. Valider la syntaxe ──────────────────────────────────────────────
    ok_syntax, syntax_error = _validate_syntax(code_python)
    if not ok_syntax:
        return {
            "status":       "error",
            "error":        f"Syntaxe Python invalide : {syntax_error}",
            "code_brut":    code_python,
            "conseil":      (
                "Le code généré contient une erreur de syntaxe. "
                "Relancez create_tool en précisant davantage la description, "
                "ou corrigez manuellement l'erreur indiquée."
            ),
        }

    # ── 7. Simuler l'import ────────────────────────────────────────────────
    ok_import, import_warning, tools_found = _validate_import(code_python)

    if not ok_import:
        return {
            "status":    "error",
            "error":     f"Erreur à l'import simulé : {import_warning}",
            "code_brut": code_python,
            "conseil":   (
                "Le module généré produit une erreur à l'exécution. "
                "Vérifiez les références aux variables et fonctions dans le code."
            ),
        }

    # Fallback : détecter les noms via AST si l'import simulé n'a rien capturé
    if not tools_found:
        tools_found = _detect_tool_names_from_ast(code_python)

    # ── 8. Déduire le nom de fichier depuis le code si non fourni ─────────
    if not nom_fichier:
        # Chercher set_current_family("xxx_tools", ...) dans le code
        m = re.search(r'set_current_family\(\s*["\'](\w+)["\']', code_python)
        nom_fichier = m.group(1) if m else "nouveau_tools"

    # ── 9. Construire la réponse ───────────────────────────────────────────
    init_line = f"import tools.{nom_fichier}"

    result = {
        "status":          "success",
        "nom_fichier":     f"tools/{nom_fichier}.py",
        "outils_generes":  tools_found,
        "nb_outils":       len(tools_found),
        "validation": {
            "syntaxe_ok":    True,
            "import_ok":     True,
            "avertissement": import_warning or None,
        },
        "code_python":     code_python,
        "bloc_env":        bloc_env or "(aucune variable d'environnement nécessaire)",
        "doc_utilisateur": bloc_doc or "",
        "init_py":         init_line,
        "instructions": (
            f"1. Enregistrez le code dans `{nom_fichier}.py` dans le dossier `tools/`.\n"
            f"2. Ajoutez les variables dans votre `.env` (voir bloc_env).\n"
            f"3. Ajoutez `{init_line}` dans `tools/__init__.py`.\n"
            f"4. Redémarrez Prométhée pour activer les nouveaux outils."
        ),
    }

    if conflict_warning:
        result["avertissement_fichier"] = conflict_warning

    return result
