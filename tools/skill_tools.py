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
tools/skill_tools.py — Outils de consultation dynamique des skills
===================================================================

Outils exposés (2) :

  skill_list  : liste tous les skills disponibles avec leur nom, description
                et tags. À appeler avant skill_read pour découvrir les guides
                existants.

  skill_read  : lit le contenu complet d'un skill par son slug.
                À utiliser quand le LLM a besoin de consulter un guide de
                bonnes pratiques avant de produire un output (document,
                requête SQL, protocole métier).

Philosophie
───────────
Ces deux outils reproduisent pour le LLM de Prométhée le comportement que
Claude adopte spontanément : lire un SKILL.md avant de générer du code ou
un document. Le LLM décide lui-même de consulter un skill selon la nature
de la tâche demandée.

Exemples d'usage automatique par le LLM :
  - « Génère un compte-rendu de réunion »
    → skill_list() pour découvrir → skill_read("template_cr_reunion")
  - « Écris une requête SQL sur la base clients »
    → skill_read("schema_bdd_production")
  - « Exporte le rapport en docx »
    → skill_read("conventions_nommage") + skill_read("style_redactionnel")

Les skills épinglés dans le profil actif sont déjà injectés dans le prompt
système : il est inutile (mais inoffensif) de les relire via skill_read.
"""

import json

from core.tools_engine import tool, set_current_family
from core.skill_manager import get_skill_manager

set_current_family("skill_tools", "Skills & guides", "📚")


@tool(
    name="skill_list",
    description=(
        "Liste tous les guides de bonnes pratiques (skills) disponibles dans "
        "Prométhée. Retourne le slug, le nom, la description courte et les tags "
        "de chaque skill. "
        "À appeler en premier pour découvrir quels guides sont disponibles avant "
        "de produire un document, une requête SQL ou tout output formaté. "
        "Exemple : avant de générer un rapport, appeler skill_list pour voir "
        "s'il existe un guide de style ou un template."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tag_filter": {
                "type": "string",
                "description": (
                    "Filtrer les skills par tag (optionnel). "
                    "Ex: 'sql', 'rédaction', 'juridique'. "
                    "Si omis, retourne tous les skills."
                )
            }
        },
        "required": []
    }
)
def skill_list(tag_filter: str = "") -> str:
    try:
        sm     = get_skill_manager()
        skills = sm.list_skills()

        if tag_filter:
            tf     = tag_filter.lower().strip()
            skills = [s for s in skills if any(tf in t.lower() for t in s.tags)]

        if not skills:
            if tag_filter:
                return json.dumps({
                    "skills": [],
                    "message": f"Aucun skill avec le tag '{tag_filter}'. "
                               "Appelez skill_list() sans filtre pour voir tous les skills."
                }, ensure_ascii=False)
            return json.dumps({
                "skills": [],
                "message": (
                    "Aucun skill disponible. "
                    f"Créez des fichiers .md dans {sm.skills_dir}"
                )
            }, ensure_ascii=False)

        return json.dumps({
            "skills": [s.to_dict() for s in skills],
            "count":  len(skills),
            "skills_dir": str(sm.skills_dir),
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool(
    name="skill_read",
    description=(
        "Lit le contenu complet d'un guide de bonnes pratiques (skill) par son slug. "
        "Un skill contient des instructions et un protocole à suivre étape par étape. "
        "TOUJOURS appeler ce tool avant de produire un document ou un output formaté. "
        "CAS OBLIGATOIRES — appeler skill_read AVANT tout appel d'outil export, "
        "puis suivre scrupuleusement le protocole décrit dans le skill : "
        "• skill_read('guide_creation_powerpoint') avant tout export .pptx — "
        "  le protocole impose de chercher un gabarit avec list_files('~/Modèles') "
        "  AVANT de choisir l'outil d'export ; "
        "• skill_read('guide_export_excel') avant export_xlsx_* ; "
        "• skill_read('guide_redactionnel_administratif') avant export_docx_*, export_pdf ; "
        "• skill_read('guide_utilisation_templates') avant export_docx_template ou export_pptx_template. "
        "Autres exemples : skill_read('schema_bdd_production') avant une requête SQL."
    ),
    parameters={
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": (
                    "Identifiant du skill (nom du fichier sans .md). "
                    "Obtenir la liste des slugs via skill_list."
                )
            }
        },
        "required": ["slug"]
    }
)
def skill_read(slug: str) -> str:
    try:
        sm      = get_skill_manager()
        content = sm.read_skill(slug)
        info    = sm.get_info(slug)

        header = (
            f"── Skill : {info.name} (slug: {slug}) "
            f"{'· v' + info.version if info.version != '1.0' else ''} ──\n\n"
        )
        return header + content

    except FileNotFoundError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"skill_read : {e}"}, ensure_ascii=False)
