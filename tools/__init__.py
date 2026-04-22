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

Système de fichiers :
    vfs_tools (actif par défaut) — espace de fichiers virtuel par utilisateur,
    stocké en SQLite pour la structure et Garage pour les blobs. Le LLM n'accède jamais au disque réel du serveur.

Prérequis pour legifrance_tools (obtenir les clés via Piste):
    LEGIFRANCE_CLIENT_ID=votre_client_id
    LEGIFRANCE_CLIENT_SECRET=votre_client_secret

Prérequis pour grist_tools :
    GRIST_API_KEY=votre_clé_api_grist
    GRIST_BASE_URL=https://votre-instance.grist.com   # défaut: https://docs.getgrist.com
"""


def register_all() -> None:
    """Importe tous les modules d'outils pour les enregistrer dans tools_engine."""
    from tools import vfs_tools
    from tools import export_tools
    from tools import export_template_tools
    from tools import reformulation_tools
    from tools import data_tools
    from tools import data_file_tools
    from tools import ocr_tools
    from tools import web_tools
    from tools import legifrance_tools
    from tools import judilibre_tools
    from tools import datagouv_tools
    from tools import imap_tools
    from tools import skill_tools
    from tools import grist_tools
    from tools import tool_creator_tools
    from tools import meteo_tools


