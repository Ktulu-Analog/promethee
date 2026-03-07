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
rag_panel.py — Panneau RAG avec sélection de collection Qdrant pour la base globale
"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QProgressBar,
    QTextEdit, QMenu, QMessageBox, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction

from core import rag_engine
from core.config import Config
from ui.widgets import SectionLabel
from ui.workers import IngestWorker
from ui.widgets.styles import ThemeManager

# Scope constants
GLOBAL = None          # conversation_id=None → "global" dans Qdrant
CONV   = "conv"        # sentinel, remplacé par self.conv_id au runtime


class RagPanel(QWidget):
    """Panneau latéral droit : gestion des documents RAG."""

    status_message = pyqtSignal(str)
    collection_changed = pyqtSignal(str)  # Émet le nom de la collection sélectionnée

    def __init__(self, conversation_id: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("rag_panel")
        self.conv_id = conversation_id
        self.selected_collection = None  # Collection sélectionnée pour la base globale
        self._setup_ui()
        self._load_collections()

    # ── Construction ──────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(10)

        # Titre
        title_row = QHBoxLayout()
        icon = QLabel("📚")
        icon.setStyleSheet("font-size: 16px;")
        title_row.addWidget(icon)
        title = QLabel("Base documentaire")
        title.setObjectName("rag_title")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Statut Qdrant
        self._status_label = QLabel()
        self._update_status()
        layout.addWidget(self._status_label)

        self._div1 = self._make_divider()
        layout.addWidget(self._div1)

        # ── Sélection de collection globale ──
        layout.addWidget(SectionLabel("🌐 Base globale (Collections Qdrant)"))

        # Combo box pour sélectionner la collection
        collection_row = QHBoxLayout()
        collection_row.setSpacing(6)

        collection_label = QLabel("Collection :")
        collection_label.setStyleSheet(f"color: {ThemeManager.inline('model_badge_color')}; font-size: 12px;")
        collection_row.addWidget(collection_label)

        self._collection_combo = QComboBox()
        self._collection_combo.setObjectName("tool_btn")
        self._collection_combo.setMinimumHeight(28)
        self._collection_combo.currentTextChanged.connect(self._on_collection_changed)
        collection_row.addWidget(self._collection_combo, stretch=1)

        self._refresh_btn = QPushButton("🔄")
        self._refresh_btn.setObjectName("tool_btn")
        self._refresh_btn.setFixedSize(34, 34)
        self._refresh_btn.setStyleSheet("font-size: 16px;")
        self._refresh_btn.setToolTip("Actualiser la liste des collections")
        self._refresh_btn.clicked.connect(self._load_collections)
        collection_row.addWidget(self._refresh_btn)

        layout.addLayout(collection_row)

        # Info sur la collection sélectionnée
        self._collection_info = QLabel("Aucune collection sélectionnée")
        self._collection_info.setStyleSheet(
            f"color: {ThemeManager.inline('rag_info_color')}; font-size: 10px; padding: 4px 0;"
        )
        self._collection_info.setWordWrap(True)
        layout.addWidget(self._collection_info)

        # ── Ajout par conversation ──
        self._div1_5 = self._make_divider()
        layout.addWidget(self._div1_5)

        layout.addWidget(SectionLabel("💬 Cette conversation"))

        btn_conv = QHBoxLayout()
        btn_conv.setSpacing(6)

        self._add_files_conv_btn = QPushButton("📄 Fichiers")
        self._add_files_conv_btn.setObjectName("tool_btn")
        self._add_files_conv_btn.setToolTip("Indexer uniquement pour cette conversation")
        self._add_files_conv_btn.clicked.connect(lambda: self._add_files(scope=CONV))
        btn_conv.addWidget(self._add_files_conv_btn)

        self._add_text_conv_btn = QPushButton("✏️ Texte")
        self._add_text_conv_btn.setObjectName("tool_btn")
        self._add_text_conv_btn.setToolTip("Indexer du texte pour cette conversation uniquement")
        self._add_text_conv_btn.clicked.connect(lambda: self._toggle_text_input(scope=CONV))
        btn_conv.addWidget(self._add_text_conv_btn)
        layout.addLayout(btn_conv)

        # Zone texte libre (pour la conversation uniquement)
        self._text_scope = CONV
        self._text_scope_lbl = QLabel()
        self._text_scope_lbl.setStyleSheet("color: #888; font-size: 10px;")
        self._text_scope_lbl.setVisible(False)
        layout.addWidget(self._text_scope_lbl)

        self._text_input = QTextEdit()
        self._text_input.setObjectName("input_box")
        self._text_input.setPlaceholderText("Collez du texte à indexer…")
        self._text_input.setMaximumHeight(110)
        self._text_input.setVisible(False)
        layout.addWidget(self._text_input)

        self._ingest_text_btn = QPushButton("Indexer →")
        self._ingest_text_btn.setObjectName("send_btn")
        self._ingest_text_btn.setFixedHeight(30)
        self._ingest_text_btn.setVisible(False)
        self._ingest_text_btn.clicked.connect(self._ingest_text)
        layout.addWidget(self._ingest_text_btn)

        # Barre de progression
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        layout.addWidget(self._progress)

        self._div2 = self._make_divider()
        layout.addWidget(self._div2)

        # ── Liste docs ──
        section_row = QHBoxLayout()
        section_row.addWidget(SectionLabel("Documents indexés"))
        section_row.addStretch()

        self._delete_btn = QPushButton("🗑️")
        self._delete_btn.setObjectName("tool_btn")
        self._delete_btn.setFixedSize(34, 32)
        self._delete_btn.setStyleSheet("font-size: 16px;")
        self._delete_btn.setToolTip("Supprimer le document sélectionné")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_selected)
        section_row.addWidget(self._delete_btn)
        layout.addLayout(section_row)

        self._doc_list = QListWidget()
        self._doc_list.setObjectName("doc_list")
        self._doc_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._doc_list.customContextMenuRequested.connect(self._show_context_menu)
        self._doc_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._doc_list, stretch=1)

        self._div3 = self._make_divider()
        layout.addWidget(self._div3)

        # Légende
        legend = QHBoxLayout()
        legend.setSpacing(12)
        for icon, text in [("🌐", "Collection"), ("💬", "Conversation")]:
            lbl = QLabel(f"{icon} {text}")
            lbl.setStyleSheet(f"color: {ThemeManager.inline('rag_info_color')}; font-size: 10px;")
            legend.addWidget(lbl)
        legend.addStretch()
        layout.addLayout(legend)

        self._info_lbl = QLabel("🌐 dans la collection  ·  💬 cette conversation")
        self._info_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('rag_info_color')}; font-size: 10px;"
        )
        self._info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info_lbl)

    # ── Collections Qdrant ────────────────────────────────────────────

    def _load_collections(self):
        """Charge la liste des collections depuis Qdrant, filtrée pour l'utilisateur courant."""
        all_collections = rag_engine.list_collections()

        # Ne conserver que :
        #  - la collection de l'utilisateur courant (promethee_<user_id>)
        #  - les collections externes (sans préfixe promethee_), qui sont des
        #    sources documentaires partagées intentionnellement
        own = Config.QDRANT_COLLECTION
        collections = [
            c for c in all_collections
            if c == own or not c.startswith("promethee_")
        ]

        self._collection_combo.clear()

        if not collections:
            self._collection_combo.addItem("Aucune collection disponible")
            self._collection_combo.setEnabled(False)
            self._collection_info.setText("Aucune collection disponible dans Qdrant")
            self.selected_collection = None
        else:
            self._collection_combo.setEnabled(True)
            self._collection_combo.addItem("-- Sélectionner une collection --")
            for coll in sorted(collections):
                self._collection_combo.addItem(coll)

            # Sélectionner automatiquement la collection par défaut si elle existe
            default_idx = self._collection_combo.findText(own)
            if default_idx > 0:
                self._collection_combo.setCurrentIndex(default_idx)

            self._collection_info.setText(f"{len(collections)} collection(s) disponible(s)")

        self._refresh_doc_list()

    def _on_collection_changed(self, collection_name: str):
        """Appelé quand l'utilisateur change de collection."""
        if collection_name == "-- Sélectionner une collection --" or \
           collection_name == "Aucune collection disponible":
            self.selected_collection = None
            self._collection_info.setText("Aucune collection sélectionnée")
        else:
            self.selected_collection = collection_name
            self._collection_info.setText(f"Collection active : {collection_name}")
            # Émettre le signal pour informer les autres composants
            self.collection_changed.emit(collection_name)

        self._refresh_doc_list()

    # ── Helpers UI ────────────────────────────────────────────────────

    def _make_divider(self) -> QWidget:
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {ThemeManager.inline('divider_bg')};")
        return line

    def _update_status(self):
        if rag_engine.is_available():
            ok = rag_engine.ensure_collection()
            if ok:
                self._status_label.setText("● Qdrant connecté")
                self._status_label.setStyleSheet("color: #5a9a5a; font-size: 11px; font-weight: 600;")
            else:
                self._status_label.setText("○ Qdrant non disponible")
                self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        else:
            self._status_label.setText("○ RAG désactivé")
            self._status_label.setStyleSheet("color: #666; font-size: 11px;")

    def refresh_theme(self):
        for div in (self._div1, self._div1_5, self._div2, self._div3):
            div.setStyleSheet(f"background-color: {ThemeManager.inline('divider_bg')};")
        color = ThemeManager.inline('rag_info_color')
        self._info_lbl.setStyleSheet(f"color: {color}; font-size: 10px;")
        self._collection_info.setStyleSheet(f"color: {color}; font-size: 10px; padding: 4px 0;")

    def _on_selection_changed(self):
        self._delete_btn.setEnabled(bool(self._doc_list.selectedItems()))

    # ── Liste depuis Qdrant ───────────────────────────────────────────

    def _refresh_doc_list(self):
        """Affiche les documents de la conversation courante uniquement."""
        self._doc_list.clear()
        if not rag_engine.is_available():
            return

        # Afficher uniquement les documents de cette conversation
        for entry in rag_engine.list_sources(self.conv_id):
            badge = "🌐" if entry["scope"] == "global" else "💬"
            label = f"{badge} {entry['source']}  ({entry['count']} chunks)"
            item = QListWidgetItem(label)
            # Stocker source + scope pour la suppression
            item.setData(Qt.ItemDataRole.UserRole, {
                "source": entry["source"],
                "scope":  entry["scope"],
            })
            scope_text = f"Collection : {self.selected_collection}" if entry['scope'] == 'global' and self.selected_collection \
                        else 'Cette conversation' if entry['scope'] != 'global' else 'Base globale'
            item.setToolTip(
                f"{scope_text}\n"
                f"{entry['source']}  —  {entry['count']} chunk(s)"
            )
            self._doc_list.addItem(item)
        self._delete_btn.setEnabled(False)

    # ── Suppression ───────────────────────────────────────────────────

    def _show_context_menu(self, pos):
        item = self._doc_list.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        scope_label = "la collection" if data.get("scope") == "global" else "cette conversation"
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#1a1a1e; border:1px solid #2e2e33;
                    border-radius:7px; color:#ccc; padding:4px; }
            QMenu::item { padding:6px 18px; border-radius:4px; }
            QMenu::item:selected { background:#3a2020; color:#e07070; }
        """)
        act = QAction(f"🗑  Supprimer de {scope_label}", self)
        act.triggered.connect(lambda: self._delete_item(item))
        menu.addAction(act)
        menu.exec(self._doc_list.mapToGlobal(pos))

    def _delete_selected(self):
        items = self._doc_list.selectedItems()
        if items:
            self._delete_item(items[0])

    def _delete_item(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        source = data.get("source")
        scope  = data.get("scope", "global")
        if not source:
            return

        scope_label = "la collection" if scope == "global" else "cette conversation"
        msg = QMessageBox(self)
        msg.setWindowTitle("Confirmer la suppression")
        msg.setText(f"Supprimer <b>{source}</b><br>de <b>{scope_label}</b> ?")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        msg.button(QMessageBox.StandardButton.Yes).setText("Supprimer")
        msg.button(QMessageBox.StandardButton.Cancel).setText("Annuler")
        msg.setStyleSheet("""
            QMessageBox { background-color:#161618; color:#e8e6e1; }
            QLabel { color:#e8e6e1; }
            QPushButton { background-color:#252528; color:#ccc; border:1px solid #333;
                          border-radius:6px; padding:6px 14px; min-width:80px; }
            QPushButton:hover { background-color:#2e2e32; }
        """)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        conv_id = None if scope == "global" else self.conv_id
        deleted = rag_engine.delete_by_source(source, conv_id)
        self.status_message.emit(f"🗑 '{source}' supprimé ({deleted} chunks)")
        self._refresh_doc_list()

    # ── Ingestion ─────────────────────────────────────────────────────

    def _resolve_scope(self, scope) -> str | None:
        """Retourne le conv_id effectif : None=global, str=conversation."""
        return None if scope is GLOBAL else self.conv_id

    def _toggle_text_input(self, scope):
        # Seulement pour la conversation maintenant
        if scope is not CONV:
            return

        # Si déjà visible, masquer
        if self._text_input.isVisible():
            self._text_input.setVisible(False)
            self._text_scope_lbl.setVisible(False)
            self._ingest_text_btn.setVisible(False)
            return

        self._text_scope = scope
        label = "💬 Indexer pour cette conversation"
        self._text_scope_lbl.setText(label)
        self._text_scope_lbl.setVisible(True)
        self._text_input.setVisible(True)
        self._ingest_text_btn.setVisible(True)
        self._text_input.setFocus()

    def _add_files(self, scope):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Sélectionner des fichiers",
            filter="Documents (*.txt *.md *.pdf *.csv *.py *.js *.json);;Tous (*)",
        )
        if not paths:
            return
        self._start_ingestion(paths, scope)

    def _ingest_text(self):
        text = self._text_input.toPlainText().strip()
        if not text:
            return
        self._text_input.clear()
        self._text_input.setVisible(False)
        self._text_scope_lbl.setVisible(False)
        self._ingest_text_btn.setVisible(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        conv_id = self._resolve_scope(self._text_scope)
        try:
            chunks = rag_engine.ingest_text(
                text, source="texte libre", conversation_id=conv_id
            )
            self._progress.setVisible(False)
            scope_label = "collection" if conv_id is None else "conversation"
            self.status_message.emit(f"✅ {chunks} chunks indexés ({scope_label})")
            self._refresh_doc_list()
        except Exception as e:
            self._progress.setVisible(False)
            self.status_message.emit(f"Erreur : {e}")

    def _start_ingestion(self, paths: list[str], scope):
        conv_id = self._resolve_scope(scope)
        self._add_files_conv_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, len(paths))
        self._progress.setValue(0)

        self._worker = IngestWorker(paths, conv_id)
        self._worker.progress.connect(lambda done, total: self._progress.setValue(done))
        self._worker.finished.connect(self._on_ingest_done)
        self._worker.error.connect(lambda e: self.status_message.emit(f"Erreur : {e}"))
        self._worker.start()

    def _on_ingest_done(self, total_chunks: int):
        self._progress.setVisible(False)
        self._add_files_conv_btn.setEnabled(True)
        self.status_message.emit(f"✅ {total_chunks} chunks indexés")
        self._refresh_doc_list()

    # ── Changement de conversation ────────────────────────────────────

    def set_conversation(self, conv_id: str):
        self.conv_id = conv_id
        self._refresh_doc_list()

    def get_selected_collection(self) -> str | None:
        """Retourne le nom de la collection actuellement sélectionnée."""
        return self.selected_collection
