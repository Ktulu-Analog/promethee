# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
# Année   : 2026
# ============================================================================
"""
styles.py — ThemeManager : orchestre les thèmes depuis les templates QSS

Architecture :
  ui/widgets/themes/
    tokens.py        — palette de couleurs (seule source de vérité)
    base.qss.tpl     — template CSS principal  → éditer pour tout style widget
    tabs.qss.tpl     — template CSS des onglets

  styles.py          — ThemeManager (API publique inchangée)

Pour ajouter/modifier un style :
  → Éditer base.qss.tpl ou tabs.qss.tpl  (jamais styles.py)
  → Ajouter un token si besoin dans tokens.py
  C'est tout.

API publique (inchangée) :
  ThemeManager.is_dark()
  ThemeManager.toggle()
  ThemeManager.set_theme(name)
  ThemeManager.inline(key)
  ThemeManager.get_main_style()
  ThemeManager.get_tabs_style()
  ThemeManager.apply(widget)
  ThemeManager.topbar_style()
  ThemeManager.topbar_logo_style()
  ThemeManager.topbar_model_style()
  ThemeManager.menubar_style()
  ThemeManager.dialog_style()
  ThemeManager.small_label_style(token, bold)
  ThemeManager.checkbox_style()
"""

from __future__ import annotations
from pathlib import Path

from .themes.tokens import get as _tok, resolve as _resolve

# ── Chemins des templates ─────────────────────────────────────────────────────
_THEMES_DIR = Path(__file__).parent / "themes"
_TPL_BASE   = _THEMES_DIR / "base.qss.tpl"
_TPL_TABS   = _THEMES_DIR / "tabs.qss.tpl"


def _render(tpl_path: Path, dark: bool) -> str:
    """Charge un template .qss.tpl et substitue tous les __token_name__."""
    tpl = tpl_path.read_text(encoding="utf-8")
    for key, value in _resolve(dark).items():
        tpl = tpl.replace(f"__{key}__", value)
    return tpl


# ── Cache (invalidé à chaque toggle) ─────────────────────────────────────────
_style_cache: dict[str, str] = {}


def _cached(key: str, tpl_path: Path, dark: bool) -> str:
    full_key = f"{key}_{dark}"
    if full_key not in _style_cache:
        _style_cache[full_key] = _render(tpl_path, dark)
    return _style_cache[full_key]


def _invalidate_cache() -> None:
    _style_cache.clear()


# ══════════════════════════════════════════════════════════════════════════════
#  ThemeManager
# ══════════════════════════════════════════════════════════════════════════════

class ThemeManager:
    """
    Singleton de gestion du thème.
    L'API est identique à l'ancienne version — aucun impact sur le reste du code.
    """

    _current: str = "dark"

    # ── État ─────────────────────────────────────────────────────────

    @classmethod
    def is_dark(cls) -> bool:
        return cls._current == "dark"

    @classmethod
    def current(cls) -> str:
        return cls._current

    @classmethod
    def set_theme(cls, theme: str) -> None:
        assert theme in ("dark", "light")
        cls._current = theme
        _invalidate_cache()
        try:
            from ui.widgets.message_widget import invalidate_html_css_cache
            invalidate_html_css_cache()
        except ImportError:
            pass

    @classmethod
    def toggle(cls) -> None:
        cls._current = "light" if cls._current == "dark" else "dark"
        _invalidate_cache()
        try:
            from ui.widgets.message_widget import invalidate_html_css_cache
            invalidate_html_css_cache()
        except ImportError:
            pass

    # ── CSS principal ─────────────────────────────────────────────────

    @classmethod
    def get_main_style(cls) -> str:
        return _cached("main", _TPL_BASE, cls.is_dark())

    @classmethod
    def get_tabs_style(cls) -> str:
        return _cached("tabs", _TPL_TABS, cls.is_dark())

    @classmethod
    def apply(cls, widget) -> None:
        """Applique le style principal à un QMainWindow ou QWidget."""
        widget.setStyleSheet(cls.get_main_style())

    # ── Tokens inline ─────────────────────────────────────────────────

    @classmethod
    def inline(cls, key: str) -> str:
        """Retourne la valeur du token pour le thème actif."""
        return _tok(key, cls.is_dark())

    # ── Styles composites (CSS inline, non mis en cache) ──────────────

    @classmethod
    def topbar_style(cls) -> str:
        return (f"background-color: {cls.inline('topbar_bg')};"
                f"border-bottom: 1px solid {cls.inline('topbar_border')};")

    @classmethod
    def topbar_logo_style(cls) -> str:
        return (f"color: {cls.inline('logo_color')}; background-color: transparent;"
                "font-size: 15px; font-weight: 700; letter-spacing: -0.2px;")

    @classmethod
    def topbar_model_style(cls) -> str:
        return (f"color: {cls.inline('model_badge_color')}; font-size: 11px;"
                f" padding: 3px 10px; background-color: {cls.inline('model_badge_bg')};"
                f" border-radius: 6px; border: 1px solid {cls.inline('model_badge_border')};")

    @classmethod
    def menubar_style(cls) -> str:
        return f"""
            QMenuBar {{
                background-color: {cls.inline('topbar_bg')};
                color: {cls.inline('model_badge_color')};
                border-bottom: 1px solid {cls.inline('topbar_border')};
                padding: 1px 4px; font-size: 13px;
            }}
            QMenuBar::item:selected {{
                background: {cls.inline('tool_card_bg')};
                color: {cls.inline('logo_color')};
                border-radius: 4px;
            }}
            QMenu {{
                background: {cls.inline('menu_bg')};
                border: 1px solid {cls.inline('menu_border')};
                border-radius: 8px;
                color: {cls.inline('menu_item_color')};
                padding: 4px;
            }}
            QMenu::item {{ padding: 7px 22px; border-radius: 5px; }}
            QMenu::item:selected {{
                background: {cls.inline('menu_item_selected_bg')};
                color: {cls.inline('menu_item_selected_color')};
            }}
            QMenu::separator {{
                height: 1px;
                background: {cls.inline('menu_separator')};
                margin: 4px 8px;
            }}
        """

    @classmethod
    def dialog_style(cls) -> str:
        return f"""
            QMessageBox, QDialog {{
                background-color: {cls.inline('tool_result_bg')};
                color: {cls.inline('input_color')};
            }}
            QLabel {{ color: {cls.inline('input_color')}; }}
            QPushButton {{
                background-color: {cls.inline('input_bg')};
                color: {cls.inline('input_color')};
                border: 1px solid {cls.inline('input_border')};
                border-radius: 6px; padding: 6px 14px; min-width: 80px;
            }}
            QPushButton:hover {{ background-color: {cls.inline('tool_card_bg')}; }}
        """

    @classmethod
    def file_dialog_style(cls) -> str:
        """QSS complet pour QFileDialog non-natif (DontUseNativeDialog).
        Couvre tous les sous-widgets internes, y compris la sidebar gauche (QListView)
        qui ignore le QSS global de l'application quand le dialog natif est désactivé.
        """
        bg       = cls.inline('surface_bg')
        bg_alt   = cls.inline('base_bg')
        elevated = cls.inline('elevated_bg')
        text     = cls.inline('text_primary')
        text_sec = cls.inline('text_secondary')
        border   = cls.inline('border')
        accent   = cls.inline('accent')
        sel_bg   = cls.inline('elevated_bg')
        input_bg = cls.inline('input_bg')
        btn_bg   = cls.inline('input_bg')
        btn_brd  = cls.inline('input_border')
        return f"""
            QFileDialog {{
                background-color: {bg};
                color: {text};
            }}
            /* Sidebar gauche (répertoires favoris) */
            QFileDialog QListView,
            QFileDialog QListView::item {{
                background-color: {bg_alt};
                color: {text};
                border: none;
                outline: none;
            }}
            QFileDialog QListView::item:hover {{
                background-color: {elevated};
                color: {text};
            }}
            QFileDialog QListView::item:selected,
            QFileDialog QListView::item:selected:active {{
                background-color: {sel_bg};
                color: {text};
                border-left: 2px solid {accent};
            }}
            /* Panneau central (arborescence de fichiers) */
            QFileDialog QTreeView,
            QFileDialog QTreeView::item {{
                background-color: {bg};
                color: {text};
                border: none;
                outline: none;
            }}
            QFileDialog QTreeView::item:alternate {{
                background-color: {bg_alt};
            }}
            QFileDialog QTreeView::item:hover {{
                background-color: {elevated};
            }}
            QFileDialog QTreeView::item:selected,
            QFileDialog QTreeView::item:selected:active {{
                background-color: {sel_bg};
                color: {text};
            }}
            QFileDialog QTreeView QHeaderView::section {{
                background-color: {bg_alt};
                color: {text_sec};
                border: none;
                border-bottom: 1px solid {border};
                padding: 4px 8px;
                font-size: 11px;
            }}
            /* Barre d'adresse (chemin courant) */
            QFileDialog QLineEdit {{
                background-color: {input_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 8px;
                selection-background-color: {sel_bg};
            }}
            QFileDialog QLineEdit:focus {{
                border-color: {accent};
            }}
            /* Combobox (filtre de type) */
            QFileDialog QComboBox {{
                background-color: {input_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 8px;
                min-height: 22px;
            }}
            QFileDialog QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QFileDialog QComboBox QAbstractItemView {{
                background-color: {elevated};
                color: {text};
                border: 1px solid {border};
                selection-background-color: {sel_bg};
            }}
            /* Boutons */
            QFileDialog QPushButton {{
                background-color: {btn_bg};
                color: {text};
                border: 1px solid {btn_brd};
                border-radius: 5px;
                padding: 5px 14px;
                min-width: 70px;
            }}
            QFileDialog QPushButton:hover {{
                background-color: {elevated};
                border-color: {accent};
            }}
            QFileDialog QPushButton:pressed {{
                background-color: {bg_alt};
            }}
            /* Barre d'outils (boutons navigation) */
            QFileDialog QToolButton {{
                background-color: transparent;
                color: {text};
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 3px;
            }}
            QFileDialog QToolButton:hover {{
                background-color: {elevated};
                border-color: {border};
            }}
            /* Labels */
            QFileDialog QLabel {{
                color: {text_sec};
                background-color: transparent;
            }}
            /* Splitter entre sidebar et panneau central */
            QFileDialog QSplitter::handle {{
                background-color: {border};
                width: 1px;
            }}
            /* Scrollbars */
            QFileDialog QScrollBar:vertical {{
                background: {bg};
                width: 8px;
                border: none;
            }}
            QFileDialog QScrollBar::handle:vertical {{
                background: {border};
                border-radius: 4px;
                min-height: 20px;
            }}
            QFileDialog QScrollBar::handle:vertical:hover {{
                background: {text_sec};
            }}
            QFileDialog QScrollBar::add-line:vertical,
            QFileDialog QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QFileDialog QScrollBar:horizontal {{
                background: {bg};
                height: 8px;
                border: none;
            }}
            QFileDialog QScrollBar::handle:horizontal {{
                background: {border};
                border-radius: 4px;
                min-width: 20px;
            }}
            QFileDialog QScrollBar::handle:horizontal:hover {{
                background: {text_sec};
            }}
            QFileDialog QScrollBar::add-line:horizontal,
            QFileDialog QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """

    @classmethod
    def small_label_style(cls, token: str, bold: bool = False) -> str:
        extra = " font-weight: 600;" if bold else ""
        return f"color: {cls.inline(token)}; font-size: 11px;{extra}"

    @classmethod
    def checkbox_style(cls) -> str:
        return f"""
            QCheckBox {{ color: {cls.inline('checkbox_color')}; font-size: 12px; }}
            QCheckBox:checked {{ color: {cls.inline('checkbox_checked_color')}; font-weight: 600; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {cls.inline('checkbox_indicator_border')};
                border-radius: 3px;
                background-color: {cls.inline('checkbox_indicator_bg')};
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {cls.inline('checkbox_indicator_bg')};
                border-color: {cls.inline('checkbox_indicator_border')};
            }}
            QCheckBox::indicator:checked {{
                background-color: {cls.inline('checkbox_checked_color')};
                border-color: {cls.inline('checkbox_checked_color')};
            }}
        """
