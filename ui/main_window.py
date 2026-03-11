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
main_window.py — Fenêtre principale de l'application

Les classes ThemeSwitch, ConvSidePanel et ToolsPanel ont été extraites
dans leurs propres fichiers pour une meilleure organisation.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QSplitter, QStatusBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction

from core import Config, HistoryDB
from core.long_term_memory import LongTermMemory, is_enabled as ltm_enabled
from .panels import ChatPanel, RagPanel, ToolsPanel, MonitoringPanel
from .dialogs import SettingsDialog, AboutDialog
from .widgets import ConvSidePanel
from .widgets.styles import ThemeManager


# ══════════════════════════════════════════════════════════════════════
#  MainWindow
# ══════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Fenêtre principale de l'application."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db if db is not None else HistoryDB()
        self._rag_visible        = True
        self._tools_visible      = False
        self._monitoring_visible = False

        self.setWindowTitle(Config.APP_TITLE)
        self.resize(1380, 860)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(ThemeManager.get_main_style())

        self._setup_menu()
        self._setup_ui()
        self._setup_status_bar()

        # ── Chargement de l'arbre dossiers/conversations ──────────────────
        # 1. Construire la structure dans la sidebar depuis la BDD
        self._tabs.load_folder_tree(self.db)

        # 2. Ouvrir les ChatPanels et les enregistrer dans l'arbre
        convs = self.db.get_conversations()
        if convs:
            for c in convs[:Config.SIDEBAR_MAX_CONVERSATIONS]:
                self._open_tab(c["id"])
            self._tabs.setCurrentIndex(0)
            # Initialiser le monitoring sur la première conversation
            first_conv = convs[0]
            self._monitoring_panel.set_conversation(first_conv["id"], first_conv["title"])
        else:
            self._new_tab()

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _short_title(title: str, max_len: int = 28) -> str:
        """Tronque un titre pour l'affichage dans un onglet."""
        return (title[:max_len] + "…") if len(title) > max_len else title

    def _chat_panels(self):
        """Itère sur tous les ChatPanel ouverts."""
        for i in range(self._tabs.count()):
            panel = self._tabs.widget(i)
            if isinstance(panel, ChatPanel):
                yield i, panel

    # ── Menu ──────────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = self.menuBar()
        self._menubar = mb
        self._apply_menubar_style()

        fm = mb.addMenu("Fichier")
        a = QAction("Nouveau chat", self); a.setShortcut("Ctrl+N"); a.triggered.connect(self._new_tab); fm.addAction(a)
        fm.addSeparator()
        a2 = QAction("Quitter", self); a2.setShortcut("Ctrl+Q"); a2.triggered.connect(self.close); fm.addAction(a2)

        vm = mb.addMenu("Affichage")
        a3 = QAction("Panneau RAG",        self); a3.setShortcut("Ctrl+R"); a3.triggered.connect(self._toggle_rag);        vm.addAction(a3)
        a4 = QAction("Panneau Outils",     self); a4.setShortcut("Ctrl+T"); a4.triggered.connect(self._toggle_tools);      vm.addAction(a4)
        a_mon = QAction("Panneau Monitoring", self); a_mon.setShortcut("Ctrl+M"); a_mon.triggered.connect(self._toggle_monitoring); vm.addAction(a_mon)
        vm.addSeparator()
        a_theme = QAction("Basculer thème clair / sombre", self)
        a_theme.setShortcut("Ctrl+Shift+T")
        a_theme.triggered.connect(self._toggle_theme_from_menu)
        vm.addAction(a_theme)

        sm = mb.addMenu("Paramètres")
        a5 = QAction("Paramètres…", self); a5.setShortcut("Ctrl+,"); a5.triggered.connect(self._open_settings); sm.addAction(a5)

        hm = mb.addMenu("Aide")
        a6 = QAction("À propos…", self); a6.triggered.connect(self._open_about); hm.addAction(a6)

    def _apply_menubar_style(self):
        """Applique le style de la barre de menu selon le thème actif."""
        self._menubar.setStyleSheet(ThemeManager.menubar_style())

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QWidget()
        root.setObjectName("central")
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setChildrenCollapsible(False)

        self._tabs = ConvSidePanel()
        self._tabs.new_tab_requested.connect(self._new_tab)
        self._tabs.tabCloseRequested.connect(self._on_tab_close)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.convDeleteRequested.connect(self._on_conv_delete)
        # Signaux ex-TopBar maintenant émis par la sidebar
        self._tabs.clear_requested.connect(self._clear_current)
        self._tabs.rag_toggle.connect(self._toggle_rag)
        self._tabs.tools_toggle.connect(self._toggle_tools)
        self._tabs.monitoring_toggle.connect(self._toggle_monitoring)
        self._tabs.settings_requested.connect(self._open_settings)
        self._tabs.theme_changed.connect(self._propagate_theme)
        self._splitter.addWidget(self._tabs)

        self._rag_panel = RagPanel()
        self._rag_panel.status_message.connect(self._set_status)
        self._rag_panel.collection_changed.connect(self._on_rag_collection_changed)
        self._rag_panel.setMinimumWidth(260)
        self._rag_panel.setMaximumWidth(360)
        self._splitter.addWidget(self._rag_panel)

        self._tools_panel = ToolsPanel()
        self._tools_panel.setMinimumWidth(240)
        self._tools_panel.setMaximumWidth(320)
        self._tools_panel.setVisible(False)
        self._splitter.addWidget(self._tools_panel)

        self._monitoring_panel = MonitoringPanel()
        self._monitoring_panel.setVisible(False)
        self._splitter.addWidget(self._monitoring_panel)

        self._splitter.setSizes([1000, 300, 0, 0])
        vbox.addWidget(self._splitter, stretch=1)

    def _setup_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_lbl = QLabel("Prêt")
        sb.addWidget(self._status_lbl)

        # ── Widgets permanents (droite → gauche dans l'ordre d'ajout) ──
        self._token_lbl  = QLabel()   # consommation tokens + %
        self._cost_lbl   = QLabel()   # coût en euros
        self._carbon_lbl = QLabel()   # empreinte carbone CO₂ / kWh

        sb.addPermanentWidget(self._carbon_lbl)
        sb.addPermanentWidget(self._cost_lbl)
        sb.addPermanentWidget(self._token_lbl)
        sb.addPermanentWidget(QLabel(f"{Config.APP_TITLE} · v{Config.APP_VERSION}"))

        self._update_token_display(None)

    # ── Thème ─────────────────────────────────────────────────────────

    def _toggle_theme_from_menu(self):
        """Appelé depuis le menu Affichage."""
        ThemeManager.toggle()
        self._propagate_theme()

    def _propagate_theme(self):
        """Propage le thème courant à toute la hiérarchie de widgets."""
        self.setStyleSheet(ThemeManager.get_main_style())
        self._apply_menubar_style()
        self._tabs.refresh_theme()   # inclut ThemeSwitch.sync() via sidebar
        self._rag_panel.refresh_theme()
        self._tools_panel.refresh_theme()
        self._monitoring_panel.refresh_theme()
        for _, panel in self._chat_panels():
            panel.refresh_theme()
        label = "sombre" if ThemeManager.is_dark() else "clair"
        self._set_status(f"Thème {label} activé")

    # ── Onglets ───────────────────────────────────────────────────────

    def _new_tab(self, conv_id: str = None):
        """Ouvre ou cree une conversation et l'associe a un ChatPanel.

        Si conv_id est fourni (conversation existante chargee depuis la BDD),
        le panel est enregistre dans l'item de l'arbre existant via
        register_widget() -- le dossier d'appartenance est ainsi preserve.

        Si conv_id est None (nouveau chat), la conversation est creee en BDD,
        puis ajoutee dans la section << Sans dossier >> via addTab().
        """
        is_new = conv_id is None
        if is_new:
            conv_id = self.db.create_conversation()

        panel = ChatPanel(self.db, conversation_id=conv_id)
        panel.title_changed.connect(self._on_title_changed)
        panel.status_message.connect(self._set_status)
        panel.profile_tools_changed.connect(self._tools_panel.refresh_families)
        panel.token_usage_updated.connect(self._update_token_display)
        panel.token_usage_updated.connect(self._monitoring_panel.on_usage_updated)
        panel.compression_stats_updated.connect(self._monitoring_panel.on_compression_stats)

        selected_collection = self._rag_panel.get_selected_collection()
        if selected_collection:
            panel.set_rag_collection(selected_collection)

        conv  = self.db.get_conversation(conv_id)
        title = conv["title"] if conv else "Nouveau chat"

        if is_new:
            # Nouveau chat : ajout dans << Sans dossier >>
            idx = self._tabs.addTab(panel, self._short_title(title))
        else:
            # Conversation existante : brancher le panel sur l'item de l'arbre
            stack_idx = self._tabs._stack.addWidget(panel)
            self._tabs.register_widget(conv_id, panel, stack_idx)
            idx = stack_idx

        self._tabs.setCurrentIndex(idx)
        self._rag_panel.set_conversation(conv_id)
        self._monitoring_panel.set_conversation(conv_id, title)
        return idx

    def _open_tab(self, conv_id: str):
        for i, panel in self._chat_panels():
            if panel.get_conv_id() == conv_id:
                self._tabs.setCurrentIndex(i)
                return
        self._new_tab(conv_id)

    def closeEvent(self, event):
        """Indexe toutes les conversations ouvertes dans la LTM avant de quitter."""
        if ltm_enabled():
            panels = list(self._chat_panels())
            if panels:
                self._set_status(f"Sauvegarde mémoire long terme ({len(panels)} conversation(s))…")
                for _, panel in panels:
                    try:
                        LongTermMemory(self.db).index_conversation(panel.get_conv_id())
                    except Exception as _e:
                        import logging
                        logging.getLogger(__name__).warning(
                            "[LTM] Indexation à la fermeture échouée : %s", _e
                        )
        event.accept()

    def _on_tab_close(self, index: int):
        widget = self._tabs.widget(index)
        if widget:
            if hasattr(widget, 'cleanup'):
                widget.cleanup()

            # ── Mémoire long terme : indexer la conversation fermée ───────
            if ltm_enabled() and hasattr(widget, 'get_conv_id'):
                try:
                    LongTermMemory(self.db).index_conversation(widget.get_conv_id())
                except Exception as _e:
                    import logging
                    logging.getLogger(__name__).warning("[LTM] Indexation échouée : %s", _e)
            # ─────────────────────────────────────────────────────────────

            self._tabs.removeTab(index)
            widget.deleteLater()
        if self._tabs.count() == 0:
            self._new_tab()

    def _on_conv_delete(self, conv_id: str):
        """Supprime définitivement une conversation de la DB et de la sidebar."""
        # Cherche le widget ouvert correspondant à ce conv_id (peut être None)
        target_widget = None
        target_index  = -1
        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            if w and hasattr(w, "get_conv_id") and w.get_conv_id() == conv_id:
                target_widget = w
                target_index  = i
                break

        if target_widget is not None:
            if hasattr(target_widget, "cleanup"):
                target_widget.cleanup()
            self._tabs.removeTab(target_index)
            target_widget.deleteLater()

        try:
            self.db.delete_conversation(conv_id)
        except AttributeError:
            self.db.clear_messages(conv_id)

        # ── Mémoire long terme : oublier cette conversation ───────────────
        if ltm_enabled():
            try:
                LongTermMemory(self.db).forget_conversation(conv_id)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning("[LTM] Oubli échoué : %s", _e)
        # ─────────────────────────────────────────────────────────────────

        self._set_status("Conversation supprimée")
        if self._tabs.count() == 0:
            self._new_tab()

    def _on_tab_changed(self, index: int):
        widget = self._tabs.widget(index)
        if isinstance(widget, ChatPanel):
            conv_id = widget.get_conv_id()
            self._rag_panel.set_conversation(conv_id)
            # Récupérer le titre depuis la base pour le panneau de monitoring
            conv = self.db.get_conversation(conv_id)
            title = conv["title"] if conv else ""
            self._monitoring_panel.set_conversation(conv_id, title)

    def _on_title_changed(self, conv_id: str, title: str):
        short = self._short_title(title)
        for i, panel in self._chat_panels():
            if panel.get_conv_id() == conv_id:
                self._tabs.setTabText(i, short)
                self._tabs.setTabToolTip(i, title)
                break
        # Mettre à jour le titre dans le panneau monitoring
        self._monitoring_panel.set_conversation(conv_id, title)

    # ── Actions ───────────────────────────────────────────────────────

    def _clear_current(self):
        panel = self._tabs.currentWidget()
        if isinstance(panel, ChatPanel):
            panel.clear_chat()
            self._set_status("Conversation effacée")

    def _toggle_panel(self, panel, visible_attr: str, splitter_index: int, default_width: int):
        """
        Affiche ou masque un panneau latéral en redistribuant l'espace du splitter.

        Parameters
        ----------
        panel : QWidget
            Le panneau à afficher/masquer.
        visible_attr : str
            Nom de l'attribut booléen d'état (ex. '_rag_visible').
        splitter_index : int
            Index du panneau dans le splitter (1 = RAG, 2 = Outils).
        default_width : int
            Largeur à restaurer lors de l'affichage.
        """
        visible = not getattr(self, visible_attr)
        setattr(self, visible_attr, visible)
        panel.setVisible(visible)
        sizes = self._splitter.sizes()
        if not visible:
            # Redistribuer la largeur au panneau central (index 0)
            sizes[0] += sizes[splitter_index]
            sizes[splitter_index] = 0
        else:
            sizes[0] = max(0, sizes[0] - default_width)
            sizes[splitter_index] = default_width
        self._splitter.setSizes(sizes)

    def _toggle_rag(self):
        self._toggle_panel(self._rag_panel, "_rag_visible", 1, 300)

    def _toggle_tools(self):
        self._toggle_panel(self._tools_panel, "_tools_visible", 2, 280)

    def _toggle_monitoring(self):
        self._toggle_panel(self._monitoring_panel, "_monitoring_visible", 3, 280)

    def _open_settings(self):
        """Ouvre le dialogue de paramètres."""
        dlg = SettingsDialog(self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _open_about(self):
        """Ouvre le dialogue À propos de l'application."""
        dlg = AboutDialog(self)
        dlg.exec()

    def _on_settings_changed(self):
        """Appelé quand les paramètres sont modifiés."""
        self._tabs.update_model()

        msg = QMessageBox(self)
        msg.setWindowTitle("Paramètres mis à jour")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            f"<b>Paramètres enregistrés !</b><br><br>"
            f"Modèle actif : <b>{Config.active_model()}</b><br><br>"
            f"Le nouveau modèle sera utilisé pour :<br>"
            f"• Les nouveaux chats (Ctrl+N)<br>"
            f"• Les chats rechargés après redémarrage<br><br>"
            f"Les conversations en cours continuent avec leur modèle initial."
        )
        msg.setStyleSheet(ThemeManager.dialog_style())
        msg.exec()
        self._set_status("Paramètres mis à jour")

    def _on_rag_collection_changed(self, collection_name: str):
        """Appelé quand la collection RAG change."""
        for _, panel in self._chat_panels():
            panel.set_rag_collection(collection_name)
        self._set_status(f"Collection RAG : {collection_name}")

    # ── Barre de statut ───────────────────────────────────────────────

    def _update_token_display(self, usage) -> None:
        """
        Met à jour les trois indicateurs de la barre de statut :
          - _token_lbl  : tokens prompt / max (%)
          - _cost_lbl   : coût en euros (masqué si nul)
          - _carbon_lbl : CO₂ et kWh (masqués si absents)
        """
        muted  = ThemeManager.inline("text_muted")
        accent = ThemeManager.inline("accent")
        red    = ThemeManager.inline("stop_btn_color")
        eco    = ThemeManager.inline("eco_color")
        eco_w  = ThemeManager.inline("eco_warn_color")
        base_style = "font-size: 11px; padding: 0 10px;"

        # ── Pas encore de données ─────────────────────────────────────
        if usage is None or usage.prompt == 0:
            self._token_lbl.setText("— tokens")
            self._token_lbl.setStyleSheet(f"{base_style} color: {muted};")
            self._cost_lbl.hide()
            self._carbon_lbl.hide()
            return

        # ── Tokens ───────────────────────────────────────────────────
        model_max = Config.CONTEXT_MODEL_MAX_TOKENS
        prompt    = usage.prompt
        total     = usage.total
        pct       = min(100, prompt * 100 // model_max) if model_max > 0 else 0

        if pct >= 80:
            tok_color = red
        elif pct >= 60:
            tok_color = accent
        else:
            tok_color = muted

        # Afficher prompt (contexte fenêtre) et completion séparément si disponibles
        if usage.completion > 0:
            tok_text = (
                f"↑ {prompt:,}  ↓ {usage.completion:,} tok"
                f"  ({pct}% ctx)"
            )
        else:
            tok_text = f"{prompt:,} / {model_max:,} tok  ({pct}%)"

        self._token_lbl.setText(tok_text)
        self._token_lbl.setStyleSheet(f"{base_style} color: {tok_color};")
        self._token_lbl.show()

        # ── Coût ─────────────────────────────────────────────────────
        cost = getattr(usage, "cost", 0.0) or 0.0
        if cost > 0:
            if cost < 0.001:
                cost_text = f"< 0,001 €"
            else:
                cost_text = f"{cost:.4f} €"
            self._cost_lbl.setText(f"💶 {cost_text}")
            self._cost_lbl.setStyleSheet(f"{base_style} color: {muted};")
            self._cost_lbl.show()
        else:
            self._cost_lbl.hide()

        # ── Carbone ──────────────────────────────────────────────────
        carbon = getattr(usage, "carbon", {}) or {}
        kwh    = carbon.get("kWh", {})
        co2    = carbon.get("kgCO2eq", {})

        carbon_parts = []

        if co2:
            lo_g = co2.get("min", 0.0)
            hi_g = co2.get("max", 0.0)
            if hi_g < 0.001:
                co2_str = "< 0,001 gCO₂"
            elif lo_g == hi_g or abs(hi_g - lo_g) < 0.0001:
                co2_str = f"{hi_g:.3f} KgCO₂"
            else:
                co2_str = f"{lo_g:.3f}–{hi_g:.3f} KgCO₂"
            carbon_parts.append(co2_str)

        if kwh:
            lo_wh = kwh.get("min", 0.0)
            hi_wh = kwh.get("max", 0.0)
            if hi_wh < 0.001:
                kwh_str = "< 0,001 Wh"
            elif lo_wh == hi_wh or abs(hi_wh - lo_wh) < 0.0001:
                kwh_str = f"{hi_wh:.3f} KWh"
            else:
                kwh_str = f"{lo_wh:.3f}–{hi_wh:.3f} KWh"
            carbon_parts.append(kwh_str)

        if carbon_parts:
            # Couleur selon l'intensité CO₂ (seuils indicatifs)
            hi_g = co2.get("max", 0.0) if co2 else 0.0
            carbon_color = eco_w if hi_g > 0.5 else eco
            self._carbon_lbl.setText("🌿 " + "  ·  ".join(carbon_parts))
            self._carbon_lbl.setStyleSheet(f"{base_style} color: {carbon_color};")
            self._carbon_lbl.show()
        else:
            self._carbon_lbl.hide()

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)
        QTimer.singleShot(6000, lambda: self._status_lbl.setText("Prêt"))
