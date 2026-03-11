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
conversation_sidebar.py — Panneau latéral de conversations avec dossiers

Remplace le QListWidget par un QTreeWidget à deux niveaux :
  - Niveau 0 : dossiers (repliables, icône dossier)
  - Niveau 1 : conversations dans chaque dossier
  - Section « Sans dossier » fixe en bas

Interactions :
  - Clic droit  : menu contextuel (dossier ou conversation)
  - Drag & drop : déplacer une conversation vers un dossier
  - Double-clic : renommage inline d'un dossier
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QTreeWidget, QTreeWidgetItem, QLineEdit,
    QLabel, QMenu, QInputDialog, QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QByteArray, QPoint, QMimeData
from PyQt6.QtGui import QPainter, QIcon, QPixmap, QPalette, QColor
from PyQt6.QtSvg import QSvgRenderer

from .styles import ThemeManager
from .theme_switch import ThemeSwitch
from core.config import Config

# ── Rôles UserData ───────────────────────────────────────────────────────────
_ROLE_KIND   = Qt.ItemDataRole.UserRole        # "folder"|"conv"|"unfiled_header"
_ROLE_ID     = Qt.ItemDataRole.UserRole + 1    # id BDD
_ROLE_WIDGET = Qt.ItemDataRole.UserRole + 2    # QWidget (ChatPanel)


# ── QTreeWidget sécurisé pour le drag & drop ─────────────────────────────────
class _SafeTreeWidget(QTreeWidget):
    """Exclut _ROLE_WIDGET (QWidget*) des données MIME du drag.
    QWidget* n'est pas sérialisable → QVariant::save warning + crash PyQt6."""

    def mimeData(self, items):
        # Sauvegarde par index (QTreeWidgetItem n'est pas hashable)
        saved = [(item, item.data(0, _ROLE_WIDGET)) for item in items]
        for item, w in saved:
            if w is not None:
                item.setData(0, _ROLE_WIDGET, None)
        mime = super().mimeData(items)
        for item, w in saved:
            if w is not None:
                item.setData(0, _ROLE_WIDGET, w)
        return mime

# ── SVG inline ───────────────────────────────────────────────────────────────
_HAMBURGER_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <rect x='1' y='3'    width='14' height='1.8' rx='0.9' fill='{c}'/>
  <rect x='1' y='7.1'  width='14' height='1.8' rx='0.9' fill='{c}'/>
  <rect x='1' y='11.2' width='14' height='1.8' rx='0.9' fill='{c}'/>
</svg>"""

_FOLDER_CLOSED_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <path d='M1 4.5C1 3.7 1.7 3 2.5 3H6l1.5 2H13.5C14.3 5 15 5.7 15 6.5V12.5C15 13.3 14.3 14 13.5 14H2.5C1.7 14 1 13.3 1 12.5V4.5Z'
        stroke='{c}' stroke-width='1.3' fill='none' stroke-linejoin='round'/>
</svg>"""

_FOLDER_OPEN_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <path d='M1 4.5C1 3.7 1.7 3 2.5 3H6l1.5 2H13.5C14.3 5 15 5.7 15 6.5V12.5C15 13.3 14.3 14 13.5 14H2.5C1.7 14 1 13.3 1 12.5V4.5Z'
        stroke='{c}' stroke-width='1.3' fill='{c}' fill-opacity='0.18' stroke-linejoin='round'/>
</svg>"""

_CHAT_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <path d='M2 3C2 2.45 2.45 2 3 2H13C13.55 2 14 2.45 14 3V10C14 10.55 13.55 11 13 11H9L6 14V11H3C2.45 11 2 10.55 2 10V3Z'
        stroke='{c}' stroke-width='1.3' fill='none' stroke-linejoin='round'/>
</svg>"""

_CLEAR_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <path d='M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9'
        stroke='{c}' stroke-width='1.4' stroke-linecap='round'
        stroke-linejoin='round' fill='none'/>
</svg>"""

_RAG_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <rect x='2' y='2' width='5' height='6' rx='1' stroke='{c}' stroke-width='1.4' fill='none'/>
  <rect x='9' y='2' width='5' height='6' rx='1' stroke='{c}' stroke-width='1.4' fill='none'/>
  <rect x='2' y='10' width='5' height='4' rx='1' stroke='{c}' stroke-width='1.4' fill='none'/>
  <rect x='9' y='10' width='5' height='4' rx='1' stroke='{c}' stroke-width='1.4' fill='none'/>
</svg>"""

_TOOLS_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <path d='M9.5 2a3.5 3.5 0 0 1 0 5L4 13a1.5 1.5 0 0 1-2-2L7.5 5.5A3.5 3.5 0 0 1 9.5 2z'
        stroke='{c}' stroke-width='1.4' fill='none' stroke-linecap='round' stroke-linejoin='round'/>
</svg>"""

_MONITORING_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <rect x='1' y='2' width='14' height='10' rx='1.5' stroke='{c}' stroke-width='1.4' fill='none'/>
  <path d='M4 14h8M8 12v2' stroke='{c}' stroke-width='1.4' stroke-linecap='round'/>
  <polyline points='3,9 5,5 7,7 9,4 11,6 13,3' stroke='{c}' stroke-width='1.3' fill='none' stroke-linecap='round' stroke-linejoin='round'/>
</svg>"""

_SETTINGS_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>
  <circle cx='8' cy='8' r='2.2' stroke='{c}' stroke-width='1.4' fill='none'/>
  <path d='M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M11.54 4.46l-1.41 1.41M4.46 11.54l-1.41 1.41'
        stroke='{c}' stroke-width='1.4' stroke-linecap='round' fill='none'/>
</svg>"""


def _svg_icon(template: str, color: str, size: int = 14) -> QIcon:
    """Génère un QIcon depuis un template SVG inline avec placeholder {c}."""
    svg = template.replace("{c}", color).encode()
    px  = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    try:
        r = QSvgRenderer(QByteArray(svg))
        p = QPainter(px)
        r.render(p)
        p.end()
    except Exception:
        pass
    return QIcon(px)



# ── ConvSidePanel ─────────────────────────────────────────────────────────────

class ConvSidePanel(QWidget):
    """
    Panneau latéral avec arbre de dossiers/conversations.

    Rétrocompatible avec l'ancienne API QTabWidget-like
    (addTab, removeTab, setCurrentIndex, count, setTabText, setTabToolTip).

    Signals
    -------
    new_tab_requested        : créer une nouvelle conversation
    currentChanged(int)      : conversation sélectionnée (index stack)
    tabCloseRequested(int)   : fermer une conversation
    convDeleteRequested(int) : supprimer définitivement (index stack)
    clear_requested / rag_toggle / tools_toggle / settings_requested / theme_changed
    """

    new_tab_requested   = pyqtSignal()
    currentChanged      = pyqtSignal(int)
    tabCloseRequested   = pyqtSignal(int)
    convDeleteRequested = pyqtSignal(str)   # émet le conv_id (str)
    clear_requested     = pyqtSignal()
    rag_toggle          = pyqtSignal()
    tools_toggle        = pyqtSignal()
    monitoring_toggle   = pyqtSignal()
    settings_requested  = pyqtSignal()
    theme_changed       = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible = True
        self._conv_map: dict[int, tuple[int, QTreeWidgetItem]] = {}
        self._unfiled_root: QTreeWidgetItem | None = None
        self._folder_items: dict[str, QTreeWidgetItem] = {}
        self._db = None
        self._stack = QStackedWidget()
        self._build_layout()

    # ── Injection DB ──────────────────────────────────────────────────────

    def set_db(self, db) -> None:
        self._db = db

    # ── Construction ─────────────────────────────────────────────────────

    def _build_layout(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = QWidget()
        self._sidebar.setObjectName("sidebar")
        sl = QVBoxLayout(self._sidebar)
        sl.setContentsMargins(12, 8, 12, 12)
        sl.setSpacing(8)

        # Barre d'actions
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(2)

        def _btn(svg, tip, sig):
            b = QPushButton()
            b.setObjectName("sidebar_action_btn")
            b.setFixedSize(28, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.clicked.connect(sig)
            b.setIcon(_svg_icon(svg, ThemeManager.inline("text_muted")))
            b.setIconSize(QSize(16, 16))
            return b

        self._btn_clear    = _btn(_CLEAR_SVG,      "Effacer la conversation",  self.clear_requested)
        self._btn_rag      = _btn(_RAG_SVG,        "Panneau RAG  (Ctrl+R)",    self.rag_toggle)
        self._btn_tools    = _btn(_TOOLS_SVG,      "Panneau Outils  (Ctrl+T)", self.tools_toggle)
        self._btn_monitor  = _btn(_MONITORING_SVG, "Panneau Monitoring  (Ctrl+M)", self.monitoring_toggle)
        self._action_svgs  = {
            self._btn_clear:   _CLEAR_SVG,
            self._btn_rag:     _RAG_SVG,
            self._btn_tools:   _TOOLS_SVG,
            self._btn_monitor: _MONITORING_SVG,
        }

        self._btn_settings = _btn(_SETTINGS_SVG, "Paramètres  (Ctrl+,)", self.settings_requested)
        self._action_svgs[self._btn_settings] = _SETTINGS_SVG

        top_bar.addWidget(self._btn_clear)
        top_bar.addWidget(self._btn_rag)
        top_bar.addWidget(self._btn_tools)
        top_bar.addWidget(self._btn_monitor)
        top_bar.addStretch()

        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("sidebar_toggle_btn")
        self._toggle_btn.setFixedSize(28, 28)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setToolTip("Masquer le panneau")
        self._toggle_btn.clicked.connect(self._toggle_sidebar)
        self._update_toggle_icon()
        top_bar.addWidget(self._toggle_btn)
        sl.addLayout(top_bar)

        self._new_btn = QPushButton("＋  Nouveau chat")
        self._new_btn.setObjectName("new_chat_btn")
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.clicked.connect(self.new_tab_requested.emit)
        sl.addWidget(self._new_btn)

        self._search = QLineEdit()
        self._search.setObjectName("search_bar")
        self._search.setPlaceholderText("🔍  Rechercher…")
        self._search.textChanged.connect(self._filter)
        sl.addWidget(self._search)

        # Arbre
        self._tree = _SafeTreeWidget()
        self._tree.setObjectName("conv_tree")
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setAnimated(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.currentItemChanged.connect(self._on_item_changed)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemExpanded.connect(lambda it: self._on_folder_toggled(it, True))
        self._tree.itemCollapsed.connect(lambda it: self._on_folder_toggled(it, False))
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._tree.dropEvent = self._on_drop
        self._apply_tree_palette()
        sl.addWidget(self._tree, stretch=1)

        self._model_lbl = QLabel(Config.mode_label())
        self._model_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._model_lbl.setWordWrap(True)
        self._apply_model_style()
        sl.addWidget(self._model_lbl)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 4, 0, 0)
        bottom_bar.setSpacing(4)
        self._theme_switch = ThemeSwitch()
        self._theme_switch.toggled.connect(self._on_theme_switch_toggled)
        bottom_bar.addWidget(self._theme_switch)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self._btn_settings)
        sl.addLayout(bottom_bar)

        root.addWidget(self._sidebar)

        # Bande de réouverture
        self._reopen_strip = QWidget()
        self._reopen_strip.setObjectName("sidebar_strip")
        self._reopen_strip.setFixedWidth(32)
        self._reopen_strip.setVisible(False)
        srl = QVBoxLayout(self._reopen_strip)
        srl.setContentsMargins(2, 8, 2, 0)
        srl.setSpacing(0)
        self._reopen_btn = QPushButton()
        self._reopen_btn.setObjectName("sidebar_toggle_btn")
        self._reopen_btn.setFixedSize(28, 28)
        self._reopen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reopen_btn.setToolTip("Afficher le panneau")
        self._reopen_btn.clicked.connect(self._toggle_sidebar)
        self._reopen_btn.setIcon(_svg_icon(_HAMBURGER_SVG, ThemeManager.inline("text_muted")))
        self._reopen_btn.setIconSize(QSize(16, 16))
        srl.addWidget(self._reopen_btn)
        srl.addStretch()
        root.addWidget(self._reopen_strip)

        root.addWidget(self._stack, stretch=1)




    def _apply_tree_palette(self):
        """Force la couleur Highlight du QTreeWidget = fond sidebar.
        Empêche Qt de dessiner un bloc coloré sur la zone ::branch des items sélectionnés."""
        surface = ThemeManager.inline("surface_bg")
        pal = self._tree.palette()
        col = QColor(surface)
        pal.setColor(QPalette.ColorGroup.Active,   QPalette.ColorRole.Highlight, col)
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, col)
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, col)
        self._tree.setPalette(pal)

    def _update_toggle_icon(self):
        c = ThemeManager.inline("text_muted")
        self._toggle_btn.setIcon(_svg_icon(_HAMBURGER_SVG, c))
        self._toggle_btn.setIconSize(QSize(16, 16))

    # ── Helpers items ─────────────────────────────────────────────────────

    def _make_conv_item(self, title: str, widget, conv_id: str = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title or "Sans titre"])
        item.setData(0, _ROLE_KIND, "conv")
        item.setData(0, _ROLE_WIDGET, widget)
        item.setData(0, _ROLE_ID, conv_id)
        item.setFlags(
            Qt.ItemFlag.ItemIsSelectable |
            Qt.ItemFlag.ItemIsEnabled |
            Qt.ItemFlag.ItemIsDragEnabled
        )
        item.setIcon(0, _svg_icon(_CHAT_SVG, ThemeManager.inline("text_muted")))
        return item

    def _make_folder_item(self, name: str, folder_id: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, _ROLE_KIND, "folder")
        item.setData(0, _ROLE_ID, folder_id)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled)
        self._set_folder_icon(item, expanded=False)
        self._folder_items[folder_id] = item
        return item

    def _set_folder_icon(self, item: QTreeWidgetItem, expanded: bool):
        c   = ThemeManager.inline("text_primary" if expanded else "text_muted")
        svg = _FOLDER_OPEN_SVG if expanded else _FOLDER_CLOSED_SVG
        item.setIcon(0, _svg_icon(svg, c))

    def _get_unfiled_root(self) -> QTreeWidgetItem:
        if self._unfiled_root is None:
            self._unfiled_root = QTreeWidgetItem(["Sans dossier"])
            self._unfiled_root.setData(0, _ROLE_KIND, "unfiled_header")
            self._unfiled_root.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled)
            self._unfiled_root.setIcon(0, _svg_icon(_FOLDER_CLOSED_SVG, ThemeManager.inline("text_muted")))
            font = self._unfiled_root.font(0)
            font.setItalic(True)
            self._unfiled_root.setFont(0, font)
            self._tree.addTopLevelItem(self._unfiled_root)
        return self._unfiled_root

    # ── API publique (compatible ancienne interface) ───────────────────────

    def addTab(self, widget: QWidget, title: str) -> int:
        idx  = self._stack.addWidget(widget)
        item = self._make_conv_item(title, widget)
        self._get_unfiled_root().addChild(item)
        self._get_unfiled_root().setExpanded(True)
        self._conv_map[id(widget)] = (idx, item)
        return idx

    def setCurrentIndex(self, index: int):
        widget = self._stack.widget(index)
        self._stack.setCurrentIndex(index)
        if widget is None:
            return
        entry = self._conv_map.get(id(widget))
        if entry:
            self._tree.blockSignals(True)
            self._tree.setCurrentItem(entry[1])
            self._tree.blockSignals(False)

    def currentIndex(self) -> int:
        return self._stack.currentIndex()

    def currentWidget(self) -> QWidget | None:
        return self._stack.currentWidget()

    def widget(self, index: int) -> QWidget | None:
        return self._stack.widget(index)

    def count(self) -> int:
        return self._stack.count()

    def removeTab(self, index: int):
        widget = self._stack.widget(index)
        if widget is None:
            return
        self._stack.removeWidget(widget)
        entry = self._conv_map.pop(id(widget), None)
        if entry:
            _, item = entry
            parent  = item.parent() or self._tree.invisibleRootItem()
            parent.removeChild(item)

    def setTabText(self, index: int, text: str):
        widget = self._stack.widget(index)
        if widget:
            entry = self._conv_map.get(id(widget))
            if entry:
                entry[1].setText(0, text)

    def setTabToolTip(self, index: int, tip: str):
        widget = self._stack.widget(index)
        if widget:
            entry = self._conv_map.get(id(widget))
            if entry:
                entry[1].setToolTip(0, tip)

    # ── Chargement depuis la BDD ──────────────────────────────────────────

    def load_folder_tree(self, db) -> None:
        """Charge l'arbre dossiers/conversations depuis la base.

        À appeler depuis MainWindow après ouverture de la base.
        Efface et reconstruit complètement l'arbre.
        """
        self._db = db
        self._tree.blockSignals(True)
        self._tree.clear()
        self._conv_map.clear()
        self._folder_items.clear()
        self._unfiled_root = None

        all_folders = db.get_all_folders()
        roots    = [f for f in all_folders if f["parent_id"] is None]
        children: dict[str, list] = {}
        for f in all_folders:
            if f["parent_id"]:
                children.setdefault(f["parent_id"], []).append(f)

        for folder in roots:
            fitem = self._make_folder_item(folder["name"], folder["id"])
            for sub in children.get(folder["id"], []):
                sfitem = self._make_folder_item(sub["name"], sub["id"])
                for conv in db.get_conversations_in_folder(sub["id"]):
                    sfitem.addChild(self._make_conv_item(conv["title"], None, conv["id"]))
                fitem.addChild(sfitem)
            for conv in db.get_conversations_in_folder(folder["id"]):
                fitem.addChild(self._make_conv_item(conv["title"], None, conv["id"]))
            self._tree.addTopLevelItem(fitem)

        for conv in db.get_conversations_in_folder(None):
            self._get_unfiled_root().addChild(
                self._make_conv_item(conv["title"], None, conv["id"])
            )
        if self._unfiled_root:
            self._unfiled_root.setExpanded(True)

        self._tree.blockSignals(False)

    def register_widget(self, conv_id: str, widget: QWidget, stack_index: int):
        """Associe un ChatPanel à son item dans l'arbre après chargement initial."""
        def _find(parent) -> QTreeWidgetItem | None:
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.data(0, _ROLE_KIND) == "conv" and child.data(0, _ROLE_ID) == conv_id:
                    return child
                found = _find(child)
                if found:
                    return found
            return None

        root = self._tree.invisibleRootItem()
        item = _find(root)
        if item:
            item.setData(0, _ROLE_WIDGET, widget)
            self._conv_map[id(widget)] = (stack_index, item)
        else:
            item = self._make_conv_item("Sans titre", widget, conv_id)
            self._get_unfiled_root().addChild(item)
            self._conv_map[id(widget)] = (stack_index, item)

    # ── Menu contextuel ───────────────────────────────────────────────────

    def _on_context_menu(self, pos: QPoint):
        item = self._tree.itemAt(pos)
        menu = QMenu(self)

        if item is None or item.data(0, _ROLE_KIND) == "unfiled_header":
            act_nf = menu.addAction("📁  Nouveau dossier")
            act = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if act == act_nf:
                self._create_folder(parent_id=None)
            return

        kind = item.data(0, _ROLE_KIND)

        if kind == "folder":
            folder_id = item.data(0, _ROLE_ID)
            is_root   = item.parent() is None or item.parent() is self._tree.invisibleRootItem()
            act_sub    = menu.addAction("📂  Nouveau sous-dossier") if is_root else None
            act_rename = menu.addAction("✏️  Renommer")
            menu.addSeparator()
            act_del = menu.addAction("🗑️  Supprimer le dossier")
            act = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if act == act_rename:
                self._rename_folder(item, folder_id)
            elif act_sub and act == act_sub:
                self._create_folder(parent_id=folder_id)
            elif act == act_del:
                self._delete_folder(item, folder_id)

        elif kind == "conv":
            conv_id = item.data(0, _ROLE_ID)
            widget  = item.data(0, _ROLE_WIDGET)
            stack_idx = self._conv_map.get(id(widget), (None,))[0] if widget else None

            move_menu  = menu.addMenu("➡️  Déplacer vers")
            act_uf     = move_menu.addAction("Sans dossier")
            move_menu.addSeparator()
            folder_acts: dict = {}

            def _add_acts(parent_item, indent=0):
                for i in range(parent_item.childCount()):
                    child = parent_item.child(i)
                    if child.data(0, _ROLE_KIND) == "folder":
                        a = move_menu.addAction("  " * indent + child.text(0))
                        folder_acts[a] = child.data(0, _ROLE_ID)
                        _add_acts(child, indent + 1)

            _add_acts(self._tree.invisibleRootItem())
            menu.addSeparator()
            act_del = menu.addAction("🗑️  Supprimer la conversation")

            act = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if act == act_uf:
                self._move_conv_to_folder(item, conv_id, None)
            elif act in folder_acts:
                self._move_conv_to_folder(item, conv_id, folder_acts[act])
            elif act == act_del and conv_id is not None:
                self.convDeleteRequested.emit(conv_id)

    # ── CRUD dossiers (UI) ────────────────────────────────────────────────

    def _create_folder(self, parent_id: str | None):
        if not self._db:
            return
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du dossier :")
        if not ok or not name.strip():
            return
        try:
            folder_id = self._db.create_folder(name.strip(), parent_id)
        except ValueError as e:
            QMessageBox.warning(self, "Erreur", str(e))
            return
        fitem = self._make_folder_item(name.strip(), folder_id)
        if parent_id is None:
            uf_idx = self._tree.indexOfTopLevelItem(self._get_unfiled_root())
            self._tree.insertTopLevelItem(max(0, uf_idx), fitem)
        else:
            pitem = self._folder_items.get(parent_id)
            if pitem:
                pitem.addChild(fitem)
                pitem.setExpanded(True)

    def _rename_folder(self, item: QTreeWidgetItem, folder_id: str):
        if not self._db:
            return
        name, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom :", text=item.text(0))
        if not ok or not name.strip() or name.strip() == item.text(0):
            return
        self._db.rename_folder(folder_id, name.strip())
        item.setText(0, name.strip())

    def _delete_folder(self, item: QTreeWidgetItem, folder_id: str):
        if not self._db:
            return
        reply = QMessageBox.question(
            self, "Supprimer le dossier",
            "Supprimer ce dossier ?\nLes conversations seront déplacées dans « Sans dossier ».",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def _collect_convs(parent) -> list[QTreeWidgetItem]:
            result = []
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.data(0, _ROLE_KIND) == "conv":
                    result.append(child)
                else:
                    result.extend(_collect_convs(child))
            return result

        conv_items = _collect_convs(item)
        self._db.delete_folder(folder_id)
        parent = item.parent() or self._tree.invisibleRootItem()
        parent.removeChild(item)
        self._folder_items.pop(folder_id, None)

        uf = self._get_unfiled_root()
        c  = ThemeManager.inline("text_muted")
        for ci in conv_items:
            clone = self._make_conv_item(ci.text(0), ci.data(0, _ROLE_WIDGET), ci.data(0, _ROLE_ID))
            w = ci.data(0, _ROLE_WIDGET)
            if w and id(w) in self._conv_map:
                self._conv_map[id(w)] = (self._conv_map[id(w)][0], clone)
            uf.addChild(clone)
        uf.setExpanded(True)

    def _move_conv_to_folder(self, item: QTreeWidgetItem,
                             conv_id: str | None, folder_id: str | None):
        if not self._db or not conv_id:
            return
        self._db.move_conversation_to_folder(conv_id, folder_id)
        old_parent = item.parent() or self._tree.invisibleRootItem()
        # takeChild retire l'item sans le détruire (removeChild le détruirait)
        idx = old_parent.indexOfChild(item)
        old_parent.takeChild(idx)
        new_parent = self._folder_items.get(folder_id) if folder_id else self._get_unfiled_root()
        if new_parent is None:
            new_parent = self._get_unfiled_root()
        new_parent.addChild(item)
        new_parent.setExpanded(True)
        w = item.data(0, _ROLE_WIDGET)
        if w and id(w) in self._conv_map:
            self._conv_map[id(w)] = (self._conv_map[id(w)][0], item)

    # ── Drag & Drop ───────────────────────────────────────────────────────

    def _on_drop(self, event):
        target    = self._tree.itemAt(event.position().toPoint())
        drag_item = self._tree.currentItem()
        if drag_item is None or target is None:
            event.ignore()
            return
        if drag_item.data(0, _ROLE_KIND) != "conv":
            event.ignore()
            return
        target_kind = target.data(0, _ROLE_KIND)
        if target_kind not in ("folder", "unfiled_header"):
            event.ignore()
            return
        folder_id = None if target_kind == "unfiled_header" else target.data(0, _ROLE_ID)
        conv_id   = drag_item.data(0, _ROLE_ID)
        if conv_id:
            self._move_conv_to_folder(drag_item, conv_id, folder_id)
        event.accept()

    # ── Sélection ─────────────────────────────────────────────────────────

    def _on_item_changed(self, current: QTreeWidgetItem, _prev):
        if current is None:
            return
        if current.data(0, _ROLE_KIND) != "conv":
            return
        widget = current.data(0, _ROLE_WIDGET)
        if widget is None:
            return
        idx = self._stack.indexOf(widget)
        if idx >= 0:
            self._stack.setCurrentIndex(idx)
            self.currentChanged.emit(idx)

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        if item.data(0, _ROLE_KIND) == "folder":
            self._rename_folder(item, item.data(0, _ROLE_ID))

    def _on_folder_toggled(self, item: QTreeWidgetItem, expanded: bool):
        if item.data(0, _ROLE_KIND) == "folder":
            self._set_folder_icon(item, expanded)

    # ── Recherche ─────────────────────────────────────────────────────────

    def _filter(self, text: str):
        text = text.lower()

        def _vis(item: QTreeWidgetItem) -> bool:
            match = not text or text in item.text(0).lower()
            child_visible = any(_vis(item.child(i)) for i in range(item.childCount()))
            visible = match or child_visible
            item.setHidden(not visible)
            if text and child_visible:
                item.setExpanded(True)
            return visible

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            _vis(root.child(i))

    # ── Toggle sidebar ────────────────────────────────────────────────────

    def _toggle_sidebar(self):
        self._visible = not self._visible
        self._sidebar.setVisible(self._visible)
        self._reopen_strip.setVisible(not self._visible)
        self._toggle_btn.setToolTip("Masquer le panneau" if self._visible else "Afficher le panneau")

    # ── Thème ─────────────────────────────────────────────────────────────

    def _on_theme_switch_toggled(self, _checked: bool):
        self.theme_changed.emit()

    def _apply_model_style(self):
        self._model_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('tools_panel_info')}; "
            "font-size: 10px; padding: 4px 0 0 0; border: none; background: transparent;"
        )

    def update_model(self):
        self._model_lbl.setText(Config.mode_label())
        self._apply_model_style()

    def refresh_theme(self):
        self._apply_tree_palette()
        self._apply_model_style()
        c = ThemeManager.inline("text_muted")
        self._theme_switch.sync()
        self._update_toggle_icon()
        self._reopen_btn.setIcon(_svg_icon(_HAMBURGER_SVG, c))
        self._reopen_btn.setIconSize(QSize(16, 16))
        for btn, svg in self._action_svgs.items():
            btn.setIcon(_svg_icon(svg, c))
            btn.setIconSize(QSize(16, 16))

        def _refresh(item: QTreeWidgetItem):
            kind = item.data(0, _ROLE_KIND)
            if kind == "folder":
                self._set_folder_icon(item, item.isExpanded())
            elif kind == "conv":
                item.setIcon(0, _svg_icon(_CHAT_SVG, c))
            elif kind == "unfiled_header":
                item.setIcon(0, _svg_icon(_FOLDER_CLOSED_SVG, c))
            for i in range(item.childCount()):
                _refresh(item.child(i))

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            _refresh(root.child(i))
