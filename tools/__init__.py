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

Prérequis pour grist_tools (.env) :
    GRIST_API_KEY=votre_clé_api_grist
    GRIST_BASE_URL=https://votre-instance.grist.com   # défaut: https://docs.getgrist.com
"""


def register_all() -> None:
    """Importe tous les modules d'outils pour les enregistrer dans tools_engine."""
    from tools import system_tools
    from tools import export_tools
    from tools import export_template_tools
    from tools import python_tools
    from tools import data_tools
    from tools import data_file_tools
    from tools import sql_tools
    from tools import ocr_tools
    from tools import web_tools
    from tools import legifrance_tools
    from tools import judilibre_tools
    from tools import datagouv_tools
    from tools import thunderbird_tools
    from tools import skill_tools
    from tools import grist_tools

