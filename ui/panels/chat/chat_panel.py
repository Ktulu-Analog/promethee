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
chat_panel.py — Panneau de chat refactorisé avec mode agent + outils intégrés
"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QPushButton,
    QLabel,
    QSizePolicy,
    QCheckBox,
    QSlider,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize

from core import rag_engine, tools_engine
from core.long_term_memory import LongTermMemory, is_enabled as ltm_enabled
from core.database import HistoryDB
from ui.widgets import MessageWidget
from ui.workers import StreamWorker, AgentWorker
from ui.widgets.styles import ThemeManager
from ui.widgets.attachment_widget import AttachmentButton, AttachmentBar
from ui.dialogs.cache_dialog import CacheDialog
from ui.widgets.pdf_viewer import PDFViewer
from ui.widgets.profile_selector import ProfileSelector, ProfileManagerDialog
from ui.widgets.profile_manager import get_profile_manager
from ui.widgets.skill_editor import SkillManagerDialog
from ui.widgets.icon_helper import icon_label as _icon_lbl, icon_for_button as _icon_btn

# Imports depuis les modules refactorisés
from .chat_input import KeyCatchTextEdit
from .message_builder import MessageBuilder
from .streaming_handler import StreamingHandler
from .attachment_handler import AttachmentHandler
from .viewport_manager import ViewportManager


class ChatPanel(QWidget):
    """
    Panneau de chat principal refactorisé.

    Signals
    -------
    title_changed : émis quand le titre de la conversation change
    status_message : émis pour afficher un message de statut
    """

    title_changed = pyqtSignal(str, str)  # (conv_id, new_title)
    status_message = pyqtSignal(str)
    profile_tools_changed = pyqtSignal()  # émis quand les familles changent suite à un profil
    token_usage_updated = pyqtSignal(object)  # émet un TokenUsage vers main_window
    compression_stats_updated = pyqtSignal(object)  # émet un dict de stats de compression
    family_routing_changed = pyqtSignal(object)  # émet un dict {family,label,model,backend}
    model_usage_updated    = pyqtSignal(object)  # émet un dict {model,prompt,completion,role}

    def __init__(
        self,
        db: HistoryDB,
        conversation_id: str = None,
        system_prompt: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self.system_prompt = system_prompt
        self._worker = None
        self._rag_enabled = rag_engine.is_available()
        self._rag_collection = None
        self._agent_mode = False
        self._max_iterations = 8  # valeur par défaut
        self._disable_context_management = False
        self._profile_manager = get_profile_manager()
        # Flag LTM : recall déclenché une seule fois par session (par onglet ouvert)
        self._ltm_recalled = False
        self.setObjectName("chat_area")

        # Créer ou récupérer la conversation
        if conversation_id:
            self.conv_id = conversation_id
        else:
            self.conv_id = db.create_conversation(system_prompt=system_prompt)

        # Initialiser l'UI (crée _attachment_bar mais ne connecte pas encore les signaux)
        self._setup_ui()

        # Gestionnaire de virtualisation viewport (attach/detach des WebViews)
        self._viewport_mgr = ViewportManager(self._scroll, self._msgs_layout)

        # Créer les handlers APRÈS avoir créé l'UI
        self._streaming_handler = StreamingHandler(
            self.db,
            self.conv_id,
            self._insert_widget,
            parent=self
        )
        self._streaming_handler.status_message.connect(self.status_message.emit)
        self._streaming_handler.scroll_requested.connect(self._scroll_bottom)

        self._attachment_handler = AttachmentHandler(
            self._attachment_bar,
            lambda msg: self.status_message.emit(msg),
            parent=self
        )

        # Connecter les signaux d'attachements MAINTENANT que le handler existe
        self._connect_attachment_signals()

        # Charger l'historique
        self._load_history()

    # ── Construction UI ───────────────────────────────────────────────────

    def _setup_ui(self):
        """Construit l'interface utilisateur."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Zone de messages scrollable
        self._scroll = QScrollArea()
        self._scroll.setObjectName("scroll_area")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._msgs_container = QWidget()
        self._msgs_layout = QVBoxLayout(self._msgs_container)
        self._msgs_layout.setContentsMargins(32, 24, 32, 24)
        self._msgs_layout.setSpacing(2)
        self._msgs_layout.addStretch()
        self._scroll.setWidget(self._msgs_container)
        layout.addWidget(self._scroll, stretch=1)

        # Zone de saisie
        self._setup_input_area(layout)

    def _setup_input_area(self, parent_layout: QVBoxLayout):
        """Construit la zone de saisie."""
        self._input_area = QWidget()
        self._input_area.setObjectName("input_area")
        self._input_visible = True  # État de visibilité de la barre
        ia = QVBoxLayout(self._input_area)
        ia.setContentsMargins(12, 5, 12, 8)  # Marges réduites de moitié
        ia.setSpacing(4)  # Espacement réduit

        # Toolbar
        self._setup_toolbar(ia)

        # Barre d'attachements
        self._attachment_bar = AttachmentBar()
        self._attachment_bar.preview_requested.connect(self._on_preview_pdf)
        ia.addWidget(self._attachment_bar)

        # Container pour le champ de saisie + bouton attachement
        self._setup_input_field(ia)

        # Boutons d'envoi
        self._setup_buttons(ia)

        # Ajouter un conteneur pour la barre de saisie avec bouton de toggle
        input_wrapper = QWidget()
        wrapper_layout = QVBoxLayout(input_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        # Bouton pour masquer/afficher la barre
        toggle_bar = QWidget()
        toggle_bar.setFixedHeight(20)
        toggle_bar.setObjectName("toggle_bar")
        toggle_layout = QHBoxLayout(toggle_bar)
        toggle_layout.setContentsMargins(8, 0, 8, 0)

        self._toggle_input_btn = QPushButton("▼ Masquer la barre de saisie")
        self._toggle_input_btn.setObjectName("toggle_input_btn")
        self._toggle_input_btn.setFixedHeight(18)
        self._toggle_input_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_input_btn.clicked.connect(self._toggle_input_area)
        toggle_layout.addStretch()
        toggle_layout.addWidget(self._toggle_input_btn)
        toggle_layout.addStretch()

        wrapper_layout.addWidget(toggle_bar)
        wrapper_layout.addWidget(self._input_area)

        parent_layout.addWidget(input_wrapper)

    def _setup_toolbar(self, parent_layout: QVBoxLayout):
        """Construit la toolbar avec checkbox agent, badges, profils."""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        # Mode Agent
        self._agent_check = QCheckBox("Mode Agent")
        self._apply_agent_check_style()
        self._agent_check.toggled.connect(self._on_agent_toggle)
        toolbar.addWidget(self._agent_check)

        # Badge outils
        self._tools_badge = QLabel()
        self._tools_badge.setStyleSheet(ThemeManager.small_label_style('tools_badge_idle'))
        toolbar.addWidget(self._tools_badge)

        # Slider max itérations (visible uniquement en mode agent)
        self._iter_widget = QWidget()
        iter_layout = QHBoxLayout(self._iter_widget)
        iter_layout.setContentsMargins(6, 0, 0, 0)
        iter_layout.setSpacing(4)

        iter_label = QLabel("Itérations :")
        iter_label.setStyleSheet(ThemeManager.small_label_style('char_count_color'))
        iter_layout.addWidget(iter_label)

        self._iter_slider = QSlider(Qt.Orientation.Horizontal)
        self._iter_slider.setMinimum(1)
        self._iter_slider.setMaximum(40)
        self._iter_slider.setValue(12)
        self._iter_slider.setFixedWidth(90)
        self._iter_slider.setFixedHeight(18)
        self._iter_slider.setToolTip("Nombre maximum d'itérations de la boucle agent")
        iter_layout.addWidget(self._iter_slider)

        self._iter_spinbox = QSpinBox()
        self._iter_spinbox.setMinimum(1)
        self._iter_spinbox.setMaximum(40)
        self._iter_spinbox.setValue(12)
        self._iter_spinbox.setFixedWidth(40)
        self._iter_spinbox.setFixedHeight(20)
        self._iter_spinbox.setToolTip("Nombre maximum d'itérations de la boucle agent")
        self._iter_spinbox.setStyleSheet("font-size: 11px;")
        iter_layout.addWidget(self._iter_spinbox)

        # Synchronisation slider ↔ spinbox
        self._iter_slider.valueChanged.connect(self._iter_spinbox.setValue)
        self._iter_spinbox.valueChanged.connect(self._iter_slider.setValue)
        self._iter_slider.valueChanged.connect(self._on_iter_changed)

        # Séparateur visuel
        sep = QLabel("|")
        sep.setStyleSheet(
            f"color: {ThemeManager.inline('chat_sep_color')}; padding: 0 4px;"
        )
        iter_layout.addWidget(sep)

        # Option désactivation gestion du contexte
        self._no_compress_check = QCheckBox("⚠️ Ne pas compresser le contexte")
        self._no_compress_check.setToolTip(
            "Désactive toute gestion du contexte :\n"
            "• Pas de fenêtre glissante (trim)\n"
            "• Pas de compression des résultats d'outils\n"
            "• Pas de troncature\n"
            "• Pas de consolidation mémoire\n\n"
            "Utile pour le débogage ou les sessions critiques.\n"
            "Attention : peut dépasser la fenêtre du modèle sur de longues sessions."
        )
        self._no_compress_check.setStyleSheet(ThemeManager.checkbox_style())
        self._no_compress_check.toggled.connect(self._on_no_compress_toggle)
        iter_layout.addWidget(self._no_compress_check)

        self._iter_widget.setVisible(False)
        toolbar.addWidget(self._iter_widget)

        toolbar.addStretch()

        # Badge RAG
        self._rag_badge = QLabel()
        self._update_rag_badge()
        toolbar.addWidget(self._rag_badge)

        # Sélecteur de profil
        profile_icon = _icon_lbl("user_profile", 16, "Profil système")
        toolbar.addWidget(profile_icon)

        self._profile_selector = ProfileSelector()
        self._profile_selector.setToolTip("Sélectionner un profil système")
        self._profile_selector.load_profiles(
            self._profile_manager.get_profile_names(),
            self._profile_manager.current_profile
        )
        self._profile_selector.profile_changed.connect(self._on_profile_changed)
        toolbar.addWidget(self._profile_selector)

        # Bouton gérer les profils
        manage_profiles_btn = QPushButton()
        manage_profiles_btn.setIcon(_icon_btn("settings_gear", 14))
        manage_profiles_btn.setIconSize(QSize(14, 14))
        manage_profiles_btn.setObjectName("tool_btn")
        manage_profiles_btn.setFixedSize(28, 24)
        manage_profiles_btn.setToolTip("Gérer les profils")
        manage_profiles_btn.clicked.connect(self._manage_profiles)
        toolbar.addWidget(manage_profiles_btn)

        # Bouton gérer les skills
        manage_skills_btn = QPushButton()
        manage_skills_btn.setIcon(_icon_btn("rag_book", 14))
        manage_skills_btn.setIconSize(QSize(14, 14))
        manage_skills_btn.setObjectName("tool_btn")
        manage_skills_btn.setFixedSize(28, 24)
        manage_skills_btn.setToolTip("Gérer les skills")
        manage_skills_btn.clicked.connect(self._manage_skills)
        toolbar.addWidget(manage_skills_btn)

        # Bouton cache
        cache_btn = QPushButton()
        cache_btn.setIcon(_icon_btn("cache_box", 14))
        cache_btn.setIconSize(QSize(14, 14))
        cache_btn.setObjectName("tool_btn")
        cache_btn.setFixedSize(28, 24)
        cache_btn.setToolTip("Gérer le cache d'URLs")
        cache_btn.clicked.connect(self.show_cache_dialog)
        toolbar.addWidget(cache_btn)

        # Compteur de caractères
        self._char_count = QLabel("0")
        self._char_count.setStyleSheet(ThemeManager.small_label_style('char_count_color'))
        toolbar.addWidget(self._char_count)

        parent_layout.addLayout(toolbar)

    def _setup_input_field(self, parent_layout: QVBoxLayout):
        """Construit le champ de saisie avec bouton d'attachement."""
        input_container = QHBoxLayout()
        input_container.setSpacing(8)

        # Bouton d'attachements (les signaux seront connectés plus tard)
        self._attach_btn = AttachmentButton()
        input_container.addWidget(self._attach_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        # Champ de saisie
        self._input = KeyCatchTextEdit()
        self._input.setObjectName("input_box")
        self._input.setPlaceholderText(
            "Écrivez votre message… (Entrée = envoyer, Maj+Entrée = saut de ligne, ↑↓ = historique, Tab = autocomplétion)\n"
            "[ Glissez-déposez des fichiers ou images ici ]"
        )
        self._input.setMaximumHeight(80)  # Réduit de 160 à 80
        self._input.setMinimumHeight(28)  # Réduit de 56 à 28
        self._input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._input.send_requested.connect(self.send_message)
        # files_dropped sera connecté plus tard via _connect_attachment_signals
        self._input.textChanged.connect(self._on_input_text_changed)
        input_container.addWidget(self._input)

        parent_layout.addLayout(input_container)

    def _setup_buttons(self, parent_layout: QVBoxLayout):
        """Construit le bouton d'arrêt (bouton Envoyer supprimé, redondant avec Entrée)."""
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._stop_btn = QPushButton("⏹ Arrêter")
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.clicked.connect(self.stop_stream)
        self._stop_btn.setFixedHeight(26)  # Réduit de 32 à 26
        self._stop_btn.setVisible(False)

        btn_row.addWidget(self._stop_btn)
        parent_layout.addLayout(btn_row)

    def _connect_attachment_signals(self):
        """Connecte les signaux d'attachements une fois que le handler existe."""
        # Connecter les signaux du bouton d'attachement
        self._attach_btn.file_selected.connect(self._attachment_handler.handle_file)
        self._attach_btn.image_selected.connect(self._attachment_handler.handle_image)
        self._attach_btn.url_selected.connect(self._attachment_handler.handle_url)

        # Connecter le drag & drop
        self._input.files_dropped.connect(self._attachment_handler.handle_files_dropped)

    # ── Style helpers ─────────────────────────────────────────────────────

    def _apply_agent_check_style(self):
        """Applique le style à la checkbox agent."""
        self._agent_check.setStyleSheet(ThemeManager.checkbox_style())
        if hasattr(self, '_no_compress_check'):
            self._no_compress_check.setStyleSheet(ThemeManager.checkbox_style())

    def _update_rag_badge(self):
        """Met à jour le badge RAG."""
        if self._rag_enabled:
            self._rag_badge.setText("RAG actif")
            self._rag_badge.setStyleSheet(
                ThemeManager.small_label_style('rag_badge_on', bold=True)
            )
        else:
            self._rag_badge.setText("RAG inactif")
            self._rag_badge.setStyleSheet(
                ThemeManager.small_label_style('rag_badge_off')
            )

    # ── Changement de thème ───────────────────────────────────────────────

    def refresh_theme(self):
        """Propage le changement de thème à tous les sous-widgets."""
        self._apply_agent_check_style()
        self._update_rag_badge()
        self._tools_badge.setStyleSheet(ThemeManager.small_label_style('tools_badge_idle'))
        self._char_count.setStyleSheet(ThemeManager.small_label_style('char_count_color'))

        # Propager aux widgets
        if hasattr(self, '_profile_selector'):
            self._profile_selector.refresh_theme()
        if hasattr(self, '_attachment_bar'):
            self._attachment_bar.refresh_theme()
        if hasattr(self, '_attach_btn'):
            self._attach_btn.refresh_theme()

        # Propager aux messages
        for i in range(self._msgs_layout.count()):
            item = self._msgs_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if hasattr(w, "refresh_theme"):
                    w.refresh_theme()

    # ── Callbacks UI ──────────────────────────────────────────────────────

    def _on_agent_toggle(self, checked: bool):
        """Appelé quand le mode agent est activé/désactivé."""
        self._agent_mode = checked
        self._iter_widget.setVisible(checked)
        if checked:
            tools = [t for t in tools_engine.list_tools() if t.get("enabled", True)]
            tool_count = len(tools)

            # Créer le tooltip avec la liste des outils actifs
            tool_names = [f"{t['icon']} {t['name']}" for t in tools]
            tooltip = "Outils actifs :\n" + "\n".join(tool_names)

            self._tools_badge.setText(f'🛠️ {tool_count} outil{"s" if tool_count > 1 else ""}')
            self._tools_badge.setTextFormat(Qt.TextFormat.PlainText)
            self._tools_badge.setToolTip(tooltip)
            self._tools_badge.setStyleSheet(
                ThemeManager.small_label_style('tools_badge_active', bold=True)
            )
        else:
            self._tools_badge.setText("")
            self._tools_badge.setToolTip("")

    def _on_iter_changed(self, value: int):
        """Appelé quand le slider d'itérations change."""
        self._max_iterations = value

    def _on_no_compress_toggle(self, checked: bool):
        """Appelé quand la case 'Contexte brut' est cochée/décochée."""
        self._disable_context_management = checked

    def _on_preview_pdf(self, path: str):
        """Ouvre le viewer PDF."""
        if not path or not Path(path).exists():
            self.status_message.emit("[!] Fichier PDF introuvable")
            return
        try:
            viewer = PDFViewer(path, self)
            viewer.exec()
        except Exception as e:
            self.status_message.emit(f"[!] Erreur ouverture PDF : {str(e)[:40]}")

    def show_cache_dialog(self):
        """Affiche le dialogue de gestion du cache."""
        dialog = CacheDialog(self)
        dialog.cache_cleared.connect(self._on_cache_cleared)
        dialog.exec()

    def _on_cache_cleared(self):
        """Appelé quand le cache est vidé depuis le dialogue."""
        self.status_message.emit("Cache vidé")

    def _on_input_text_changed(self):
        """Met à jour le compteur de caractères quand le texte de saisie change."""
        self._char_count.setText(str(len(self._input.toPlainText())))

    def _on_profile_changed(self, profile_name: str, system_prompt: str):
        """Appelé quand le profil change."""
        self._profile_manager.set_current_profile(profile_name)
        self.system_prompt = system_prompt

        # Appliquer les familles d'outils définies par le profil
        tools_cfg = self._profile_manager.get_tool_families(profile_name)
        tools_engine.apply_profile_families(
            enabled=tools_cfg.get('enabled', []),
            disabled=tools_cfg.get('disabled', []),
        )
        self.profile_tools_changed.emit()

        self.status_message.emit(f"Profil : {profile_name}")

    def _manage_profiles(self):
        """Ouvre le dialogue de gestion des profils."""
        dialog = ProfileManagerDialog(self)
        dialog.profiles_changed.connect(self._reload_profiles)
        dialog.exec()

    def _reload_profiles(self):
        """Recharge les profils."""
        self._profile_manager.reload()
        self._profile_selector.load_profiles(
            self._profile_manager.get_profile_names(),
            self._profile_manager.current_profile
        )
        self.status_message.emit("Profils rechargés")

    def _manage_skills(self):
        """Ouvre le dialogue de gestion des skills."""
        dialog = SkillManagerDialog(self)
        dialog.skills_changed.connect(self._on_skills_changed)
        dialog.exec()

    def _on_skills_changed(self):
        """Appelé après toute modification dans la bibliothèque de skills."""
        # Rafraîchir le gestionnaire de profils pour que les cases à cocher
        # de skills dans ProfileEditorDialog reflètent l'état à jour.
        self._profile_manager.reload()
        self.status_message.emit("Skills mis à jour")

    # ── Gestion des messages ──────────────────────────────────────────────

    def _load_history(self):
        """Charge l'historique de la conversation."""
        for msg in self.db.get_messages(self.conv_id):
            self._add_msg_widget(msg["role"], msg["content"], save=False)
        # Scroll puis synchronisation viewport : les messages en bas sont
        # attachés, ceux hors écran sont immédiatement détachés.
        QTimer.singleShot(60, self._scroll_bottom)

    def _add_msg_widget(self, role: str, content: str, save: bool = True) -> MessageWidget:
        """Ajoute un widget message."""
        w = MessageWidget(role, content)
        self._msgs_layout.insertWidget(self._msgs_layout.count() - 1, w)
        self._viewport_mgr.add_widget(w)
        if save:
            self.db.add_message(self.conv_id, role, content)
        return w

    def _insert_widget(self, w: QWidget):
        """Insère un widget dans le layout de messages."""
        self._msgs_layout.insertWidget(self._msgs_layout.count() - 1, w)
        self._viewport_mgr.add_widget(w)

    # ── Envoi de message ──────────────────────────────────────────────────

    def send_message(self):
        """Envoie le message avec attachements."""
        text = self._input.toPlainText().strip()
        attachments = self._attachment_bar.get_attachments()

        if not text and not attachments:
            return
        if self._worker is not None:
            return

        # Construire le message pour affichage
        has_images = MessageBuilder.has_images(attachments)
        display_text = MessageBuilder.build_display_text(text, attachments)

        # Ajouter à l'historique des prompts (avant de nettoyer l'input)
        self._input.add_to_history(text)

        # Nettoyer l'input
        self._input.clear()
        self._attachment_bar.clear()

        # Afficher le message utilisateur
        self._add_msg_widget("user", display_text)
        self._scroll_bottom()

        # Auto-titre
        self._update_conversation_title(text)

        # Construire le prompt système avec RAG
        sys_prompt = self._build_system_prompt(text)

        # Construire l'historique
        history = self._build_history_with_attachments(text, attachments)

        # Démarrer le streaming
        self._start_streaming(history, sys_prompt, has_images, attachments)

    def _update_conversation_title(self, text: str):
        """Met à jour le titre de la conversation si nécessaire."""
        conv = self.db.get_conversation(self.conv_id)
        if conv and conv["title"] == "Nouvelle conversation":
            title = text[:50] + ("…" if len(text) > 50 else "")
            self.db.update_conversation_title(self.conv_id, title)
            self.title_changed.emit(self.conv_id, title)

    def _build_system_prompt(self, text: str) -> str:
        """Construit le prompt système avec skills épinglés et contexte RAG."""
        sys_prompt = self.system_prompt

        # ── Injection des skills épinglés du profil actif ──────────────────
        try:
            from core.skill_manager import get_skill_manager
            pinned_slugs = self._profile_manager.get_pinned_skills(
                self._profile_manager.current_profile
            )
            if pinned_slugs:
                skills_block = get_skill_manager().build_pinned_block(pinned_slugs)
                if skills_block:
                    sys_prompt = (sys_prompt + skills_block).strip()
        except Exception as _e:
            import logging
            logging.getLogger("promethee.chat_panel").warning(
                "Injection skills épinglés échouée : %s", _e
            )

        # ── Contexte RAG ───────────────────────────────────────────────────
        if self._rag_enabled:
            ctx = rag_engine.build_rag_context(text, self.conv_id, self._rag_collection)
            if ctx:
                sys_prompt = f"{sys_prompt}\n\n{ctx}".strip()
            elif self._rag_collection:
                # Une collection est sélectionnée mais aucun chunk pertinent
                # n'a été trouvé. On l'indique explicitement au LLM pour éviter
                # qu'il réponde depuis ses connaissances générales sans prévenir.
                notice = (
                    "INSTRUCTION IMPORTANTE : Le mode RAG est actif "
                    f"(collection : {self._rag_collection}), mais aucun document "
                    "pertinent n'a été trouvé pour cette question. "
                    "Tu DOIS indiquer à l'utilisateur que tu ne disposes d'aucun "
                    "élément dans la base documentaire pour répondre à cette demande. "
                    "Ne réponds PAS à partir de tes connaissances générales."
                )
                sys_prompt = f"{sys_prompt}\n\n{notice}".strip()

        # ── Mémoire long terme : souvenirs de conversations passées ────────
        # Le bloc LTM est calculé UNE SEULE FOIS par conversation et persisté
        # dans kv_store. Les réouvertures d'onglet réutilisent le bloc stocké
        # sans relancer le recall, ce qui évite la double-injection.
        if ltm_enabled() and not self._ltm_recalled:
            _ltm_log = __import__("logging").getLogger("promethee.chat_panel")
            _kv_key  = f"ltm:injected:{self.conv_id}"
            try:
                memory_ctx = self.db.kv_get(_kv_key)
                if memory_ctx is None:
                    # Premier message de cette conversation : calcul du recall
                    memory_ctx = LongTermMemory(self.db).recall(
                        text, exclude_conv_id=self.conv_id
                    )
                    if memory_ctx:
                        self.db.kv_set(_kv_key, memory_ctx)
                        _ltm_log.debug("[LTM] Bloc calculé et persisté pour %s", self.conv_id)
                    else:
                        self.db.kv_set(_kv_key, "")
                else:
                    _ltm_log.debug("[LTM] Bloc LTM récupéré depuis kv_store pour %s", self.conv_id)

                if memory_ctx:
                    sys_prompt = f"{memory_ctx}\n\n{sys_prompt}".strip()
                self._ltm_recalled = True
            except Exception as _e:
                _ltm_log.warning("[LTM] Recall échoué : %s", _e)
        # ─────────────────────────────────────────────────────────────────

        return sys_prompt

    def _build_history_with_attachments(self, text: str, attachments: list) -> list:
        """Construit l'historique avec le dernier message en multi-part."""
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in self.db.get_messages(self.conv_id)
        ]

        # Si on a des attachements, remplacer le dernier message par la version multi-part
        if attachments:
            content_parts = MessageBuilder.build_multipart_content(text, attachments)
            MessageBuilder.apply_multipart_to_history(history, content_parts)

        return history

    def _start_streaming(self, history: list, sys_prompt: str, has_images: bool, attachments: list = None):
        """Démarre le streaming de la réponse."""
        # En mode agent, indiquer au LLM que le contenu des pièces jointes est déjà fourni
        if self._agent_mode and attachments:
            notes = []
            for a in attachments:
                if a.get('type') not in ('file', 'image'):
                    continue
                data = a.get('data', {})
                name = data.get('name', '')
                if not name:
                    continue
                file_path = data.get('path', '')
                file_content = data.get('content', '')
                if file_content.startswith('[Fichier binaire') and file_path:
                    notes.append(
                        f"- '{name}' : fichier binaire disponible localement au chemin : {file_path}"
                    )
                else:
                    notes.append(f"- '{name}' : contenu déjà inclus dans le message, ne pas relire avec un outil")
            if notes:
                note = "\n\nPièces jointes du message :\n" + "\n".join(notes)
                sys_prompt = (sys_prompt + note).strip()

        # Indicateur de frappe
        self._streaming_handler.start_typing()
        self._set_streaming(True)

        # Créer le worker approprié
        if self._agent_mode:
            self._worker = AgentWorker(
                history,
                system_prompt=sys_prompt,
                use_tools=True,
                max_iterations=self._max_iterations,
                disable_context_management=self._disable_context_management,
            )
            self._worker.tool_called.connect(self._streaming_handler.on_tool_called)
            self._worker.tool_result.connect(self._streaming_handler.on_tool_result)
            self._worker.tool_image.connect(self._streaming_handler.on_tool_image)
            self._worker.tool_progress.connect(self._streaming_handler.on_tool_progress)
            self._worker.context_event.connect(self.status_message.emit)
            self._worker.memory_event.connect(self._streaming_handler.on_memory_event)
            self._worker.compression_stats.connect(self.compression_stats_updated)
            self._worker.family_routing.connect(self._on_family_routing)
            self._worker.model_usage.connect(self.model_usage_updated)
        else:
            self._worker = StreamWorker(history, system_prompt=sys_prompt)

        # Connecter les signaux
        self._worker.token_received.connect(self._streaming_handler.on_token)
        self._worker.finished_signal.connect(self._on_streaming_finished)
        self._worker.cancelled_signal.connect(self._on_streaming_cancelled)
        self._worker.error_signal.connect(self._streaming_handler.on_error)
        self._worker.token_usage.connect(self.token_usage_updated)
        self._worker.start()

        # Message de statut
        status_msg = "Génération en cours…"
        if has_images:
            status_msg += " (analyse d'images)"
        self.status_message.emit(status_msg)

    def _on_streaming_finished(self, full_text: str):
        """Appelé quand le streaming est terminé."""
        self._streaming_handler.on_finished(full_text)
        self._worker = None
        self._set_streaming(False)

    def _on_streaming_cancelled(self, partial_text: str):
        """Appelé quand l'utilisateur a stoppé le streaming."""
        self._streaming_handler.on_cancelled(partial_text)
        self._worker = None
        self._set_streaming(False)

    def _on_family_routing(self, info: dict):
        """
        Relaie l'événement de routing de famille vers main_window, qui
        le transmettra à la sidebar pour mise à jour du label de modèle.
        """
        self.family_routing_changed.emit(info)

    # ── Contrôle du streaming ─────────────────────────────────────────────

    def stop_stream(self):
        """Arrête le streaming en cours."""
        if self._worker:
            self._worker.cancel()

    def _set_streaming(self, on: bool):
        """Active/désactive l'état de streaming."""
        # Seul le bouton Stop est géré (le bouton Envoyer a été supprimé)
        self._stop_btn.setVisible(on)

    def _scroll_bottom(self):
        """Scroll jusqu'en bas, puis force une passe de synchronisation viewport."""
        sb = self._scroll.verticalScrollBar()

        def _do_scroll():
            sb.setValue(sb.maximum())
            # Synchroniser le viewport après le scroll pour attacher les
            # messages qui viennent d'entrer dans la zone visible.
            self._viewport_mgr.sync_now()

        QTimer.singleShot(30, _do_scroll)

    def _toggle_input_area(self):
        """Masque ou affiche la zone de saisie."""
        self._input_visible = not self._input_visible
        self._input_area.setVisible(self._input_visible)

        if self._input_visible:
            self._toggle_input_btn.setText("▼ Masquer la barre de saisie")
        else:
            self._toggle_input_btn.setText("▲ Afficher la barre de saisie")

    # ── Nettoyage ─────────────────────────────────────────────────────────

    def clear_chat(self):
        """Efface tous les messages."""
        self.db.clear_messages(self.conv_id)
        while self._msgs_layout.count() > 1:
            item = self._msgs_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                if hasattr(widget, 'cleanup'):
                    widget.cleanup()
                widget.deleteLater()

    def cleanup(self):
        """Nettoie tous les widgets et workers."""
        # Arrêter le worker sans bloquer le thread UI.
        # cancel() signale l'arrêt ; on attend 2s max pour une terminaison propre.
        # Si le thread est encore vivant (I/O réseau non interruptible), on le
        # déconnecte de l'UI et on le laisse se terminer seul en arrière-plan.
        if self._worker:
            self._worker.cancel()
            if not self._worker.wait(2000):
                # Thread toujours actif : déconnecter tous ses signaux pour
                # qu'il ne touche plus à l'UI une fois terminé.
                try:
                    self._worker.token_received.disconnect()
                    self._worker.finished_signal.disconnect()
                    self._worker.error_signal.disconnect()
                    self._worker.token_usage.disconnect()
                    # Signaux spécifiques à AgentWorker
                    if hasattr(self._worker, 'tool_called'):
                        self._worker.tool_called.disconnect()
                        self._worker.tool_result.disconnect()
                        self._worker.tool_progress.disconnect()
                        self._worker.context_event.disconnect()
                        self._worker.memory_event.disconnect()
                        self._worker.compression_stats.disconnect()
                        self._worker.family_routing.disconnect()
                        self._worker.model_usage.disconnect()
                except (TypeError, RuntimeError):
                    pass  # Déjà déconnectés ou objet partiellement détruit
            self._worker = None

        # Arrêter le viewport manager en premier (réattache proprement tous
        # les widgets avant leur destruction pour éviter les accès sur des
        # renderers suspendus pendant le cleanup des MessageWidget)
        self._viewport_mgr.cleanup()

        # Nettoyer les handlers
        self._attachment_handler.cleanup()

        # Nettoyer les messages
        for i in range(self._msgs_layout.count()):
            item = self._msgs_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'cleanup'):
                    widget.cleanup()

    # ── Accesseurs ────────────────────────────────────────────────────────

    def get_conv_id(self) -> str:
        """Retourne l'ID de la conversation."""
        return self.conv_id

    def set_rag_collection(self, collection_name: str | None):
        """Définit la collection Qdrant pour le RAG."""
        self._rag_collection = collection_name

    def get_rag_collection(self) -> str | None:
        """Retourne la collection RAG active pour cet onglet."""
        return self._rag_collection
