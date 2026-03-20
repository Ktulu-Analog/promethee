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
UI Widgets module
"""

from .message_widget import MessageWidget
from .typing_indicator import TypingIndicator
from .section_label import SectionLabel
from .theme_switch import ThemeSwitch
from .conversation_sidebar import ConvSidePanel
from .skill_editor import SkillEditorDialog, SkillManagerDialog

__all__ = [
    "MessageWidget",
    "ToolCallWidget",
    "TypingIndicator",
    "SectionLabel",
    "ThemeSwitch",
    "ConvSidePanel",
    "SkillEditorDialog",
    "SkillManagerDialog",
]
from .scroll_helper import make_transparent_scroll, make_divider

__all__ += ["make_transparent_scroll", "make_divider"]
