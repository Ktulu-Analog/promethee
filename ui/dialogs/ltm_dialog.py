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
ltm_dialog.py — Dialogue de gestion de la mémoire long terme (LTM)

Permet à l'utilisateur de :
  • Voir les statistiques de la collection LTM (nb chunks, conversations indexées)
  • Parcourir les conversations indexées et visualiser leur souvenir stocké
  • Oublier un souvenir individuel (suppression du chunk Qdrant + marqueur kv_store)
  • Vider toute la mémoire long terme (reset complet)
  • Ré-indexer toutes les conversations non encore indexées
"""

import logging

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QMessageBox, QListWidget, QListWidgetItem,
    QSplitter, QTextEdit, QProgressBar, QWidget, QSizePolicy,
)

from core.config import Config
from core.long_term_memory import LongTermMemory, is_enabled as ltm_enabled
from ui.widgets.styles import ThemeManager

_log = logging.getLogger("promethee.ltm_dialog")


# ── Worker thread pour les opérations longues ────────────────────────────────

class _IndexAllWorker(QThread):
    """Ré-indexe toutes les conversations non indexées en arrière-plan."""
    progress   = pyqtSignal(int, int)   # (done, total)
    finished_  = pyqtSignal(int, int)   # (indexed, skipped)
    error      = pyqtSignal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db

    def run(self):
        try:
            ltm = LongTermMemory(self._db)
            indexed, skipped = ltm.index_all_unindexed(
                progress_cb=lambda d, t: self.progress.emit(d, t)
            )
            self.finished_.emit(indexed, skipped)
        except Exception as e:
            self.error.emit(str(e))


# ── Dialogue principal ────────────────────────────────────────────────────────

class LtmDialog(QDialog):
    """
    Dialogue de gestion de la mémoire long terme.

    Parameters
    ----------
    db : HistoryDB
        Instance de la base SQLite (déjà ouverte).
    parent : QWidget, optional
    """

    memory_changed = pyqtSignal()   # émis après toute modification

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db  = db
        self._ltm = LongTermMemory(db)
        self._worker: _IndexAllWorker | None = None

        self.setWindowTitle("Mémoire long terme")
        self.setModal(True)
        self.setMinimumSize(680, 520)
        self.resize(760, 580)

        self._setup_ui()
        self._refresh()

    # ── Construction de l'UI ─────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        # En-tête
        hdr = QLabel("🧠 Mémoire long terme")
        hdr.setStyleSheet("font-size: 16px; font-weight: 600; "
                          f"color: {ThemeManager.inline('attachment_name_color')};")
        root.addWidget(hdr)

        if not ltm_enabled():
            warn = QLabel(
                "⚠️  La mémoire long terme est désactivée "
                "(LTM_ENABLED=OFF dans .env).\n"
                "Activez-la pour commencer à mémoriser vos conversations."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"color: {ThemeManager.inline('attachment_size_color')}; "
                "font-style: italic; padding: 8px;"
            )
            root.addWidget(warn)

        # Statistiques
        stats_box = QGroupBox("Statistiques")
        self._style_group(stats_box)
        stats_form = QFormLayout(stats_box)
        stats_form.setSpacing(8)

        self._lbl_chunks   = QLabel("—")
        self._lbl_indexed  = QLabel("—")
        self._lbl_total    = QLabel("—")
        self._lbl_collection = QLabel(Config.LTM_COLLECTION or "—")

        for lbl in (self._lbl_chunks, self._lbl_indexed,
                    self._lbl_total, self._lbl_collection):
            lbl.setStyleSheet(
                f"color: {ThemeManager.inline('attachment_name_color')}; "
                "font-weight: normal;"
            )

        stats_form.addRow("Collection Qdrant :",   self._lbl_collection)
        stats_form.addRow("Chunks en mémoire :",   self._lbl_chunks)
        stats_form.addRow("Conversations indexées :", self._lbl_indexed)
        stats_form.addRow("Conversations totales :",  self._lbl_total)
        root.addWidget(stats_box)

        # Splitter liste / aperçu
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setContentsMargins(0, 0, 0, 0)

        # Liste des conversations indexées
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(6)

        list_hdr = QLabel("Conversations mémorisées")
        list_hdr.setStyleSheet(
            f"color: {ThemeManager.inline('attachment_name_color')}; "
            "font-weight: 600; font-size: 12px;"
        )
        list_layout.addWidget(list_hdr)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {ThemeManager.inline('attachment_item_bg')};
                border: 1px solid {ThemeManager.inline('attachment_item_border')};
                border-radius: 6px;
                color: {ThemeManager.inline('attachment_name_color')};
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {ThemeManager.inline('attachment_item_border')};
            }}
            QListWidget::item:selected {{
                background-color: {ThemeManager.inline('attachment_btn_bg')};
                color: {ThemeManager.inline('attachment_name_color')};
            }}
            QListWidget::item:alternate {{
                background-color: {ThemeManager.inline('attachment_btn_hover_bg')};
            }}
        """)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self._list)

        # Bouton oublier la conversation sélectionnée
        self._forget_btn = QPushButton("🗑  Oublier ce souvenir")
        self._forget_btn.setEnabled(False)
        self._forget_btn.setFixedHeight(32)
        self._style_btn_danger(self._forget_btn)
        self._forget_btn.clicked.connect(self._forget_selected)
        list_layout.addWidget(self._forget_btn)

        splitter.addWidget(list_widget)

        # Aperçu du souvenir
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)

        preview_hdr = QLabel("Aperçu du souvenir")
        preview_hdr.setStyleSheet(
            f"color: {ThemeManager.inline('attachment_name_color')}; "
            "font-weight: 600; font-size: 12px;"
        )
        preview_layout.addWidget(preview_hdr)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText(
            "Sélectionnez une conversation pour voir le souvenir stocké…"
        )
        self._preview.setStyleSheet(f"""
            QTextEdit {{
                background-color: {ThemeManager.inline('attachment_item_bg')};
                border: 1px solid {ThemeManager.inline('attachment_item_border')};
                border-radius: 6px;
                color: {ThemeManager.inline('attachment_name_color')};
                font-size: 12px;
                padding: 8px;
            }}
        """)
        preview_layout.addWidget(self._preview)
        splitter.addWidget(preview_widget)

        splitter.setSizes([280, 420])
        root.addWidget(splitter)

        # Barre de progression (ré-indexation)
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {ThemeManager.inline('attachment_item_border')};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {ThemeManager.inline('attachment_btn_color')};
                border-radius: 3px;
            }}
        """)
        root.addWidget(self._progress_bar)

        self._progress_lbl = QLabel("")
        self._progress_lbl.setVisible(False)
        self._progress_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('attachment_size_color')}; font-size: 11px;"
        )
        root.addWidget(self._progress_lbl)

        # Actions globales + boutons de fermeture
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._reindex_btn = QPushButton("🔄  Ré-indexer tout")
        self._reindex_btn.setFixedHeight(34)
        self._style_btn_normal(self._reindex_btn)
        self._reindex_btn.setToolTip(
            "Indexe dans Qdrant toutes les conversations qui ne sont pas encore mémorisées."
        )
        self._reindex_btn.clicked.connect(self._reindex_all)
        bottom.addWidget(self._reindex_btn)

        self._purge_btn = QPushButton("💣  Vider toute la mémoire")
        self._purge_btn.setFixedHeight(34)
        self._style_btn_danger(self._purge_btn)
        self._purge_btn.setToolTip(
            "Supprime tous les souvenirs de Qdrant ET efface les marqueurs kv_store.\n"
            "Cette action est irréversible."
        )
        self._purge_btn.clicked.connect(self._purge_all)
        bottom.addWidget(self._purge_btn)

        bottom.addStretch()

        refresh_btn = QPushButton("🔃  Actualiser")
        refresh_btn.setFixedHeight(34)
        self._style_btn_normal(refresh_btn)
        refresh_btn.clicked.connect(self._refresh)
        bottom.addWidget(refresh_btn)

        close_btn = QPushButton("Fermer")
        close_btn.setObjectName("send_btn")
        close_btn.setFixedHeight(34)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        root.addLayout(bottom)

    # ── Styles réutilisables ─────────────────────────────────────────────────

    @staticmethod
    def _style_group(box: QGroupBox):
        box.setStyleSheet(f"""
            QGroupBox {{
                color: {ThemeManager.inline('attachment_name_color')};
                border: 1px solid {ThemeManager.inline('attachment_item_border')};
                border-radius: 8px;
                margin-top: 8px;
                padding: 10px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)

    @staticmethod
    def _style_btn_normal(btn: QPushButton):
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeManager.inline('attachment_btn_bg')};
                border: 1px solid {ThemeManager.inline('attachment_btn_border')};
                border-radius: 7px;
                color: {ThemeManager.inline('attachment_name_color')};
                font-size: 12px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.inline('attachment_btn_hover_bg')};
            }}
            QPushButton:disabled {{
                opacity: 0.4;
            }}
        """)

    @staticmethod
    def _style_btn_danger(btn: QPushButton):
        # Réutilise les tokens du bouton Stop (stop_btn_*), cohérents dans les deux thèmes
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeManager.inline('stop_btn_bg')};
                border: 1px solid {ThemeManager.inline('stop_btn_border')};
                border-radius: 7px;
                color: {ThemeManager.inline('stop_btn_color')};
                font-size: 12px;
                padding: 6px 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.inline('attachment_remove_hover_bg')};
            }}
            QPushButton:disabled {{
                opacity: 0.4;
            }}
        """)

    # ── Rafraîchissement des données ─────────────────────────────────────────

    def _refresh(self):
        """Recharge les stats et la liste depuis Qdrant + SQLite."""
        from core import rag_engine

        conversations  = self._db.get_conversations()
        total          = len(conversations)
        indexed_convs  = [c for c in conversations if self._ltm.is_indexed(c["id"])]
        n_indexed      = len(indexed_convs)

        # Nombre de chunks dans la collection LTM
        n_chunks = 0
        if rag_engine.is_available():
            try:
                qc = rag_engine._client()
                if qc:
                    info = qc.get_collection(self._ltm.collection)
                    n_chunks = info.points_count or 0
            except Exception as e:
                _log.debug("[LTM] _refresh : get_collection échoué : %s", e)

        self._lbl_chunks.setText(str(n_chunks))
        self._lbl_indexed.setText(str(n_indexed))
        self._lbl_total.setText(str(total))

        # Remplir la liste
        self._list.clear()
        for conv in indexed_convs:
            title    = conv.get("title", "Conversation sans titre") or "Sans titre"
            date_raw = conv.get("updated_at", "")
            date_str = date_raw[:10] if date_raw else ""
            item     = QListWidgetItem(f"📝  {title[:50]}  ({date_str})")
            item.setData(Qt.ItemDataRole.UserRole, conv["id"])
            item.setToolTip(f"ID : {conv['id']}\nDernière modif : {date_raw}")
            self._list.addItem(item)

        self._preview.clear()
        self._forget_btn.setEnabled(False)

        # Activer/désactiver les boutons globaux
        enabled = ltm_enabled()
        self._reindex_btn.setEnabled(enabled and n_indexed < total)
        self._purge_btn.setEnabled(enabled and n_indexed > 0)

    # ── Sélection d'une conversation ─────────────────────────────────────────

    def _on_selection_changed(self, current: QListWidgetItem, _previous):
        """Affiche le premier chunk Qdrant de la conversation sélectionnée."""
        if current is None:
            self._preview.clear()
            self._forget_btn.setEnabled(False)
            return

        conv_id = current.data(Qt.ItemDataRole.UserRole)
        self._forget_btn.setEnabled(True)
        self._load_preview(conv_id)

    def _load_preview(self, conv_id: str):
        """Charge et affiche le texte du chunk Qdrant pour cette conversation."""
        from core import rag_engine
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        self._preview.setPlainText("Chargement…")

        if not rag_engine.is_available():
            self._preview.setPlainText("Qdrant non disponible.")
            return

        try:
            qc = rag_engine._client()
            if not qc:
                self._preview.setPlainText("Client Qdrant non initialisé.")
                return

            results, _ = qc.scroll(
                collection_name=self._ltm.collection,
                scroll_filter=Filter(
                    must=[FieldCondition(
                        key="source",
                        match=MatchValue(value=f"memory:{conv_id}")
                    )]
                ),
                limit=10,
                with_payload=True,
                with_vectors=False,
            )

            if not results:
                self._preview.setPlainText("Aucun chunk trouvé pour cette conversation.")
                return

            parts = []
            for i, pt in enumerate(results, 1):
                payload = pt.payload or {}
                text    = payload.get("text", "").strip()
                consolidated = payload.get("_consolidated", False)
                prefix = f"[Chunk {i}{'  ·  consolidé' if consolidated else ''}]\n"
                parts.append(prefix + text)

            self._preview.setPlainText("\n\n──────────────────\n\n".join(parts))

        except Exception as e:
            self._preview.setPlainText(f"Erreur lors du chargement :\n{e}")
            _log.warning("[LTM] _load_preview(%s) : %s", conv_id, e)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _forget_selected(self):
        """Supprime le souvenir de la conversation sélectionnée."""
        item = self._list.currentItem()
        if not item:
            return

        conv_id = item.data(Qt.ItemDataRole.UserRole)
        title   = item.text()

        reply = QMessageBox.question(
            self,
            "Confirmation",
            f"Supprimer le souvenir de :\n{title}\n\n"
            "La conversation elle-même n'est pas supprimée, "
            "mais elle ne sera plus mémorisée.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            n = self._ltm.forget_conversation(conv_id)
            # Supprimer aussi le bloc injecté mis en cache
            self._db.kv_delete(f"ltm:injected:{conv_id}")
            _log.info("[LTM] Souvenir supprimé : %s (%d chunk(s))", conv_id, n)
            QMessageBox.information(
                self, "Souvenir oublié",
                f"{n} chunk(s) supprimé(s).\n"
                "Ce souvenir ne sera plus injecté dans les prochaines conversations."
            )
            self.memory_changed.emit()
            self._refresh()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Suppression échouée :\n{e}")

    def _purge_all(self):
        """Vide toute la collection LTM et efface tous les marqueurs kv_store."""
        reply = QMessageBox.question(
            self,
            "Confirmation — action irréversible",
            "⚠️  Toute la mémoire long terme sera effacée :\n\n"
            "  • Tous les chunks Qdrant de la collection LTM\n"
            "  • Tous les marqueurs d'indexation (kv_store)\n"
            "  • Tous les blocs injectés mis en cache\n\n"
            "Cette action est irréversible. Continuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        from core import rag_engine

        deleted_chunks  = 0
        deleted_markers = 0

        # 1. Supprimer tous les chunks de la collection LTM
        if rag_engine.is_available():
            try:
                qc = rag_engine._client()
                if qc:
                    from qdrant_client.models import Filter
                    info   = qc.get_collection(self._ltm.collection)
                    n_pts  = info.points_count or 0
                    if n_pts > 0:
                        qc.delete_collection(self._ltm.collection)
                        deleted_chunks = n_pts
                        _log.info("[LTM] Collection '%s' supprimée (%d chunks)",
                                  self._ltm.collection, n_pts)
            except Exception as e:
                QMessageBox.critical(self, "Erreur Qdrant",
                                     f"Impossible de supprimer la collection :\n{e}")
                return

        # 2. Effacer tous les marqueurs kv_store (ltm:indexed:* et ltm:injected:*)
        try:
            with self._db._conn() as conn:
                row = conn.execute(
                    "DELETE FROM kv_store WHERE key LIKE 'ltm:%'"
                ).rowcount
                deleted_markers = row
        except Exception as e:
            _log.warning("[LTM] Purge kv_store échouée : %s", e)

        QMessageBox.information(
            self, "Mémoire effacée",
            f"Mémoire long terme vidée :\n"
            f"  • {deleted_chunks} chunk(s) Qdrant supprimé(s)\n"
            f"  • {deleted_markers} marqueur(s) kv_store supprimé(s)\n\n"
            "Les conversations peuvent être ré-indexées "
            "via « Ré-indexer tout »."
        )

        self.memory_changed.emit()
        self._refresh()

    def _reindex_all(self):
        """Lance la ré-indexation de toutes les conversations non indexées."""
        if self._worker and self._worker.isRunning():
            return

        self._reindex_btn.setEnabled(False)
        self._purge_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._progress_lbl.setText("Indexation en cours…")
        self._progress_lbl.setVisible(True)

        self._worker = _IndexAllWorker(self._db, parent=self)
        self._worker.progress.connect(self._on_reindex_progress)
        self._worker.finished_.connect(self._on_reindex_finished)
        self._worker.error.connect(self._on_reindex_error)
        self._worker.start()

    def _on_reindex_progress(self, done: int, total: int):
        if total > 0:
            pct = int(done / total * 100)
            self._progress_bar.setValue(pct)
            self._progress_lbl.setText(f"Indexation : {done} / {total} conversations…")

    def _on_reindex_finished(self, indexed: int, skipped: int):
        self._progress_bar.setVisible(False)
        self._progress_lbl.setVisible(False)
        QMessageBox.information(
            self, "Ré-indexation terminée",
            f"Indexation terminée :\n"
            f"  • {indexed} conversation(s) nouvellement indexée(s)\n"
            f"  • {skipped} déjà à jour ou ignorée(s)"
        )
        self.memory_changed.emit()
        self._refresh()

    def _on_reindex_error(self, msg: str):
        self._progress_bar.setVisible(False)
        self._progress_lbl.setVisible(False)
        self._reindex_btn.setEnabled(True)
        self._purge_btn.setEnabled(True)
        QMessageBox.critical(self, "Erreur d'indexation", f"Erreur :\n{msg}")
