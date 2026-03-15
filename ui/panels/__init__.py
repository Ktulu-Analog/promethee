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
UI Panels module
"""
# Panels existants (NE PAS MODIFIER)
from .chat import ChatPanel
from .rag_panel import RagPanel

# Nouveau panel extrait de main_window.py
from .tools_panel import ToolsPanel

# Panneau de monitoring tokens / coût / carbone
from .monitoring_panel import MonitoringPanel

# Panneau de consommation par modèle LLM
from .model_usage_panel import ModelUsagePanel

__all__ = [
    "ChatPanel",
    "RagPanel",
    "ToolsPanel",
    "MonitoringPanel",
    "ModelUsagePanel",
]
