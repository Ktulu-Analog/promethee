# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
# Année   : 2026
# ============================================================================

"""
scroll_helper.py — Helpers de construction de widgets UI standards.

Le même bloc de configuration apparaît dans monitoring_panel, model_usage_panel,
tools_panel et settings_dialog. Ce module le factorise en une seule fonction.

Fonctions exportées :
    make_transparent_scroll()  — QScrollArea transparente préconfigurée
    make_divider()             — séparateur horizontal 1px thémé
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QScrollArea, QWidget


_BASE_STYLE = (
    "QScrollArea { background: transparent; border: none; }"
    "QScrollArea > QWidget > QWidget { background: transparent; }"
)


def make_transparent_scroll(
    *,
    hide_horizontal: bool = True,
    extra_style: str = "",
    parent=None,
) -> QScrollArea:
    """
    Cree une QScrollArea transparente avec les reglages standard Promethee.

    Factorise le boilerplate repete dans monitoring_panel, model_usage_panel,
    tools_panel et settings_dialog.

    Parameters
    ----------
    hide_horizontal : bool
        Si True (defaut), masque la barre de defilement horizontale.
    extra_style : str
        CSS supplementaire ajoute apres le style de base.
        Utile pour personnaliser la scrollbar verticale (model_usage_panel).
    parent : QWidget or None
        Widget parent PyQt6 (optionnel).

    Returns
    -------
    QScrollArea
        Instance preconfiguree, prete a recevoir un widget via setWidget().
    """
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)

    if hide_horizontal:
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    scroll.setStyleSheet(_BASE_STYLE + extra_style)
    return scroll


def make_divider(parent=None) -> QWidget:
    """
    Crée un séparateur horizontal 1px avec la couleur du token 'divider_bg'.

    Factorise la logique identique définie indépendamment dans rag_panel et
    monitoring_panel.

    Parameters
    ----------
    parent : QWidget or None
        Widget parent PyQt6 (optionnel).

    Returns
    -------
    QWidget
        Ligne de séparation prête à insérer dans un QVBoxLayout.
    """
    from .styles import ThemeManager  # import local pour éviter la circularité
    line = QWidget(parent)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {ThemeManager.inline('divider_bg')};")
    return line
