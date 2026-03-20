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
tools_panel.py — Panneau d'outils agent (sidebar droite)

Affiche les outils groupés par famille avec un toggle pour activer/désactiver
chaque famille entière. L'état est persisté dans ~/.promethee_disabled_families.json
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QApplication, QFrame, QPushButton,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QEnterEvent, QCursor

from core import tools_engine
from ui.widgets.styles import ThemeManager
from ui.widgets import SectionLabel
from ui.widgets.scroll_helper import make_transparent_scroll


# ── Tooltip flottant ──────────────────────────────────────────────────────────

class ToolTooltip(QFrame):
    """
    Fenêtre flottante affichant le nom complet et la description d'un outil.
    Apparaît à côté de la carte survolée, avec une légère animation de fondu.
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setWindowFlags(
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self._build_ui()
        self.hide()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)

        self._icon_name = QLabel()
        self._icon_name.setWordWrap(False)

        self._desc = QLabel()
        self._desc.setWordWrap(True)
        self._desc.setMaximumWidth(280)

        layout.addWidget(self._icon_name)
        layout.addWidget(self._desc)
        self._apply_style()

    def _apply_style(self):
        bg     = ThemeManager.inline("tools_tooltip_bg")
        border = ThemeManager.inline("tools_tooltip_border")
        title  = ThemeManager.inline("tools_tooltip_title")
        desc   = ThemeManager.inline("tools_tooltip_desc")

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel {{
                background-color: {bg};
                border: none;
            }}
        """)
        self._icon_name.setStyleSheet(
            f"color: {title}; font-size: 12px; font-weight: 700; border: none; background: transparent;"
        )
        self._desc.setStyleSheet(
            f"color: {desc}; font-size: 11px; border: none; background: transparent;"
        )

    def show_for(self, tool: dict, card_widget: QWidget):
        """Affiche le tooltip positionné à gauche de la carte."""
        self._icon_name.setText(f"{tool['icon']}  {tool['name']}")
        self._desc.setText(tool["description"])
        self._position_and_show(card_widget)

    def show_for_family(self, family: dict, tool_count: int, card_widget: QWidget):
        """Affiche le tooltip pour un en-tête de famille."""
        self._icon_name.setText(f"{family['icon']}  {family['label']}")
        status = "activée" if family.get("enabled", True) else "désactivée"
        self._desc.setText(
            f"{tool_count} outil{'s' if tool_count > 1 else ''}  ·  famille {status}"
        )
        self._position_and_show(card_widget)

    def _position_and_show(self, card_widget: QWidget):
        self._apply_style()
        self.adjustSize()

        card_global = card_widget.mapToGlobal(QPoint(0, 0))
        x = card_global.x() - self.width() - 10
        y = card_global.y() + (card_widget.height() - self.height()) // 2

        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.left() + 4, min(x, screen.right() - self.width() - 4))
        y = max(screen.top() + 4, min(y, screen.bottom() - self.height() - 4))

        self.move(x, y)
        self.show()
        self.raise_()

    def refresh_theme(self):
        self._apply_style()


# ── Carte d'outil avec gestion du survol ─────────────────────────────────────

class ToolCard(QWidget):
    """Carte représentant un outil, avec détection du survol pour le tooltip."""

    def __init__(self, tool: dict, tooltip: ToolTooltip, parent=None):
        super().__init__(parent)
        self._tool    = tool
        self._tooltip = tooltip
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(400)
        self._hover_timer.timeout.connect(self._show_tooltip)

        self.setMouseTracking(True)
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("tool_card")
        cl = QHBoxLayout(self)
        cl.setContentsMargins(10, 5, 10, 5)
        cl.setSpacing(8)

        icon_lbl = QLabel(self._tool["icon"])
        icon_lbl.setStyleSheet("font-size: 18px; border: none;")
        icon_lbl.setFixedWidth(28)
        cl.addWidget(icon_lbl)

        txt = QVBoxLayout()
        txt.setSpacing(1)

        self._name_lbl = QLabel(self._tool["name"])
        self._name_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('tools_card_name')}; "
            "font-size: 12px; font-weight: 600; border: none;"
        )
        txt.addWidget(self._name_lbl)
        cl.addLayout(txt)

        self._apply_card_style(hovered=False)

    def _apply_card_style(self, hovered: bool):
        bg     = ThemeManager.inline("tools_card_bg")
        border = ThemeManager.inline("tools_card_border")
        border_hover = ThemeManager.inline("tools_tooltip_border")
        b = border_hover if hovered else border
        self.setStyleSheet(
            f"QWidget#tool_card {{ background-color: {bg}; border: 1px solid {b}; border-radius: 7px; }}"
            f"QWidget#tool_card * {{ background-color: transparent; border: none; }}"
        )

    def enterEvent(self, event: QEnterEvent):
        self._apply_card_style(hovered=True)
        self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_card_style(hovered=False)
        self._hover_timer.stop()
        self._tooltip.hide()
        super().leaveEvent(event)

    def _show_tooltip(self):
        self._tooltip.show_for(self._tool, self)

    @property
    def name_lbl(self) -> QLabel:
        return self._name_lbl

    def set_strikethrough(self, strike: bool):
        """Affiche le nom barré quand la famille est désactivée."""
        color = ThemeManager.inline('tools_panel_info') if strike else ThemeManager.inline('tools_card_name')
        decoration = "line-through" if strike else "none"
        self._name_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 600; "
            f"text-decoration: {decoration}; border: none;"
        )

    def refresh_theme(self):
        self._apply_card_style(hovered=False)
        self._name_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('tools_card_name')}; "
            "font-size: 12px; font-weight: 600; border: none;"
        )


# ── Toggle switch compact ─────────────────────────────────────────────────────

class FamilyToggle(QWidget):
    """Mini toggle ON/OFF pour activer/désactiver une famille d'outils."""

    toggled = pyqtSignal(bool)  # True = activé

    def __init__(self, enabled: bool = True, parent=None):
        super().__init__(parent)
        self._enabled = enabled
        self.setFixedSize(36, 20)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._enabled = not self._enabled
            self.toggled.emit(self._enabled)
            self.update()
        super().mousePressEvent(event)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor, QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        radius = h / 2

        # Track
        track_color = QColor("#4CAF50") if self._enabled else QColor("#555")
        p.setBrush(track_color)
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, radius, radius)
        p.drawPath(path)

        # Thumb
        thumb_x = w - h + 2 if self._enabled else 2
        p.setBrush(QColor("#fff"))
        p.drawEllipse(int(thumb_x), 2, h - 4, h - 4)
        p.end()


# ── En-tête de famille collapsible ───────────────────────────────────────────

class FamilyHeader(QWidget):
    """En-tête d'une famille d'outils avec toggle et collapse."""

    family_toggled = pyqtSignal(str, bool)   # (family_key, enabled)
    collapse_toggled = pyqtSignal()

    def __init__(self, family: dict, collapsed: bool = False,
                 tooltip: "ToolTooltip | None" = None, tool_count: int = 0,
                 parent=None):
        super().__init__(parent)
        self._family    = family
        self._collapsed = collapsed
        self._tooltip   = tooltip
        self._tool_count = tool_count

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(500)
        self._hover_timer.timeout.connect(self._show_tooltip)

        self.setMouseTracking(True)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # Chevron collapse
        self._chevron = QPushButton("▼" if not self._collapsed else "▶")
        self._chevron.setFixedSize(16, 16)
        self._chevron.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            f"color: {ThemeManager.inline('tools_panel_info')}; font-size: 9px; }}"
            "QPushButton:hover { color: white; }"
        )
        self._chevron.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._chevron.clicked.connect(self._on_collapse)
        layout.addWidget(self._chevron)

        # Toggle — à gauche, taille fixe, toujours visible
        self._toggle = FamilyToggle(enabled=self._family["enabled"])
        self._toggle.toggled.connect(self._on_toggle)
        self._toggle.setFixedSize(36, 20)
        layout.addWidget(self._toggle, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Icône famille
        icon_lbl = QLabel(self._family["icon"])
        icon_lbl.setStyleSheet("font-size: 13px; border: none; background: transparent;")
        icon_lbl.setFixedWidth(20)
        layout.addWidget(icon_lbl)

        # Nom famille — élastique
        self._label = QLabel(self._family["label"])
        self._label.setStyleSheet(
            f"color: {ThemeManager.inline('tools_card_name')}; "
            "font-size: 11px; font-weight: 700; border: none; background: transparent;"
        )
        layout.addWidget(self._label, stretch=1)

        self._apply_style()

    def enterEvent(self, event):
        if self._tooltip:
            self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_timer.stop()
        if self._tooltip:
            self._tooltip.hide()
        super().leaveEvent(event)

    def _show_tooltip(self):
        if self._tooltip:
            self._tooltip.show_for_family(self._family, self._tool_count, self)

    def _apply_style(self):
        bg = ThemeManager.inline("tools_card_bg")
        border = ThemeManager.inline("tools_card_border")
        alpha = "88" if not self._family["enabled"] else "ff"
        self.setStyleSheet(
            f"QWidget {{ background-color: {bg}; border: 1px solid {border}; "
            f"border-radius: 7px; opacity: 1; }}"
            "QLabel, QPushButton { background: transparent; border: none; }"
        )
        self._label.setStyleSheet(
            f"color: {ThemeManager.inline('tools_card_name')}; "
            f"font-size: 11px; font-weight: 700; border: none; background: transparent; "
            f"{'opacity: 0.5;' if not self._family['enabled'] else ''}"
        )

    def _on_toggle(self, enabled: bool):
        self._family["enabled"] = enabled
        self._apply_style()
        self.family_toggled.emit(self._family["family"], enabled)

    def _on_collapse(self):
        self._collapsed = not self._collapsed
        self._chevron.setText("▶" if self._collapsed else "▼")
        self.collapse_toggled.emit()

    def set_enabled(self, enabled: bool):
        self._family["enabled"] = enabled
        self._toggle.set_enabled(enabled)
        self._apply_style()

    def refresh_theme(self):
        self._apply_style()
        self._chevron.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            f"color: {ThemeManager.inline('tools_panel_info')}; font-size: 9px; }}"
            "QPushButton:hover { color: white; }"
        )


# ── Groupe famille ────────────────────────────────────────────────────────────

class FamilyGroup(QWidget):
    """Un groupe famille = header + liste de ToolCard, collapsible."""

    family_toggled = pyqtSignal(str, bool)

    def __init__(self, family: dict, tools: list[dict], tooltip: ToolTooltip, parent=None):
        super().__init__(parent)
        self._family = family
        self._cards: list[ToolCard] = []
        self._collapsed = False
        self._build_ui(tools, tooltip)

    def _build_ui(self, tools: list[dict], tooltip: ToolTooltip):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._header = FamilyHeader(self._family, tooltip=tooltip, tool_count=len(tools))
        self._header.family_toggled.connect(self._on_family_toggled)
        self._header.collapse_toggled.connect(self._on_collapse)
        layout.addWidget(self._header)

        # Conteneur des cartes
        self._cards_container = QWidget()
        self._cards_container.setStyleSheet("background: transparent;")
        cards_layout = QVBoxLayout(self._cards_container)
        cards_layout.setContentsMargins(8, 2, 0, 4)
        cards_layout.setSpacing(2)

        for t in tools:
            card = ToolCard(t, tooltip)
            self._cards.append(card)
            cards_layout.addWidget(card)
            if not self._family["enabled"]:
                card.set_strikethrough(True)

        layout.addWidget(self._cards_container)

    def _on_family_toggled(self, family: str, enabled: bool):
        for card in self._cards:
            card.set_strikethrough(not enabled)
        self.family_toggled.emit(family, enabled)

    def _on_collapse(self):
        self._collapsed = not self._collapsed
        self._cards_container.setVisible(not self._collapsed)

    def refresh_theme(self):
        self._header.refresh_theme()
        for card in self._cards:
            card.refresh_theme()


# ── Panneau principal ─────────────────────────────────────────────────────────

class ToolsPanel(QWidget):
    """Panneau d'outils agent (sidebar droite) avec gestion par famille."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rag_panel")
        self.setMinimumWidth(220)
        self._tooltip = ToolTooltip()
        self._groups: list[FamilyGroup] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("🛠️"))
        title = QLabel("Outils Agent")
        title.setObjectName("rag_title")
        hdr.addWidget(title)
        hdr.addStretch()
        layout.addLayout(hdr)

        hint = QLabel("Activez le mode Agent dans la zone de saisie.")
        hint.setStyleSheet(f"color: {ThemeManager.inline('tools_badge_idle')}; font-size: 11px;")
        hint.setWordWrap(True)
        self._hint = hint
        layout.addWidget(hint)

        self._div1 = QWidget()
        self._div1.setFixedHeight(1)
        self._div1.setStyleSheet(f"background: {ThemeManager.inline('tools_panel_div')};")
        layout.addWidget(self._div1)

        layout.addWidget(SectionLabel("Familles d'outils"))

        # Conteneur scrollable
        scroll = make_transparent_scroll()

        groups_widget = QWidget()
        groups_widget.setStyleSheet("background: transparent;")
        groups_layout = QVBoxLayout(groups_widget)
        groups_layout.setContentsMargins(0, 0, 8, 0)
        groups_layout.setSpacing(6)

        # Construire les groupes par famille
        all_tools = tools_engine.list_tools()
        families = tools_engine.list_families()

        # Indexer les outils par famille
        tools_by_family: dict[str, list] = {}
        for t in all_tools:
            fam = t.get("family", "unknown")
            tools_by_family.setdefault(fam, []).append(t)

        for family in families:
            fam_tools = tools_by_family.get(family["family"], [])
            if not fam_tools:
                continue
            group = FamilyGroup(family, fam_tools, self._tooltip)
            group.family_toggled.connect(self._on_family_toggled)
            self._groups.append(group)
            groups_layout.addWidget(group)

        groups_layout.addStretch()
        scroll.setWidget(groups_widget)
        layout.addWidget(scroll, stretch=1)

        self._div2 = QWidget()
        self._div2.setFixedHeight(1)
        self._div2.setStyleSheet(f"background: {ThemeManager.inline('tools_panel_div')};")
        layout.addWidget(self._div2)

        self._info = QLabel("Les outils s'exécutent\nlocalement sur votre machine.")
        self._info.setStyleSheet(f"color: {ThemeManager.inline('tools_panel_info')}; font-size: 10px;")
        self._info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info)

    def _on_family_toggled(self, family: str, enabled: bool):
        """Applique l'activation/désactivation dans le moteur d'outils."""
        if enabled:
            tools_engine.enable_family(family)
        else:
            tools_engine.disable_family(family)

    def refresh_families(self):
        """Rafraîchit l'état des toggles et du barré après un changement de profil.

        Appelé quand un profil est sélectionné et a modifié les familles actives.
        Met à jour chaque FamilyGroup selon l'état réel dans tools_engine.
        """
        for group in self._groups:
            family_key = group._family["family"]
            enabled = not tools_engine.is_family_disabled(family_key)
            # Mettre à jour l'état interne du groupe
            group._family["enabled"] = enabled
            group._header.set_enabled(enabled)
            for card in group._cards:
                card.set_strikethrough(not enabled)

    def refresh_theme(self):
        """Rafraîchit les styles après un changement de thème."""
        self._hint.setStyleSheet(f"color: {ThemeManager.inline('tools_badge_idle')}; font-size: 11px;")
        self._div1.setStyleSheet(f"background: {ThemeManager.inline('tools_panel_div')};")
        self._div2.setStyleSheet(f"background: {ThemeManager.inline('tools_panel_div')};")
        self._info.setStyleSheet(f"color: {ThemeManager.inline('tools_panel_info')}; font-size: 10px;")
        self._tooltip.refresh_theme()
        for group in self._groups:
            group.refresh_theme()
