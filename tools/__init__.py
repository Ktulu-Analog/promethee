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
tools/ — Modules d'outils pour Prométhée
=================================================

Chaque sous-module expose un ensemble d'outils thématiques et s'enregistre
automatiquement dans core.tools_engine lors de son import.

Pour activer tous les outils en une seule ligne :
    from tools import register_all
    register_all()

Pour activer uniquement certains modules :
    import tools.python_tools
    import tools.web_tools

Prérequis pour web_tools :
    pip install requests beautifulsoup4 lxml markdownify

Prérequis pour legifrance_tools (.env) (obtenir les clés via Piste):
    LEGIFRANCE_CLIENT_ID=votre_client_id
    LEGIFRANCE_CLIENT_SECRET=votre_client_secret

Prérequis pour thunderbird_tools :
    Thunderbird doit avoir été lancé au moins une fois (création du profil).
    Variable optionnelle : TB_PROFILE_PATH=/chemin/vers/profil

Note sur python_tools :
    Crée automatiquement un environnement virtuel dans ~/.promethee_python_env/
    où les packages peuvent être installés et le code exécuté en toute sécurité.
"""


def register_all() -> None:
    # Modules core (Système, Fichiers, Web, DB, etc.)
    import tools.system_tools
    import tools.data_file_tools
    import tools.web_search_tools
    import tools.web_tools
    import tools.export_tools
    import tools.data_tools
    import tools.sql_tools
    import tools.ocr_tools
    import tools.python_tools
    import tools.skill_tools
    import tools.thunderbird_tools
    
    # Sciences pures
    import tools.physics_tools
    import tools.chemistry_tools

    # Programmes et évaluations
    import tools.curriculum_tools
    import tools.lms_tools

    # Modules spécifiques PISTE / Data.gouv
    import tools.legifrance_tools
    import tools.judilibre_tools
    import tools.datagouv_tools
