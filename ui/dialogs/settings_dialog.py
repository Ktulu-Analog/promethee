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
settings_dialog.py — Dialogue de configuration du modèle et des préférences
"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTabWidget, QWidget,
    QTextEdit, QFormLayout, QGroupBox, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, QThread
from PyQt6.QtGui import QPainter, QColor
from dotenv import set_key
from core.config import Config
from ui.widgets.styles import ThemeManager
from ui.widgets.scroll_helper import make_transparent_scroll


# ── Helpers module-level ───────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent
_ENV_PATH = _ROOT / ".env"


def _save_env(key: str, value: str):
    """Crée le .env si nécessaire, puis écrit la clé."""
    if not _ENV_PATH.exists():
        src = _ROOT / ".env.example"
        if src.exists():
            import shutil
            shutil.copy(src, _ENV_PATH)
        else:
            _ENV_PATH.touch()
    set_key(str(_ENV_PATH), key, value)
    print(f"[Settings] {key}={value}")


def _fetch_openai_models(api_base: str, api_key: str) -> list[str]:
    """Récupère les modèles depuis un serveur OpenAI-compatible."""
    try:
        from openai import OpenAI
        client = OpenAI(base_url=api_base, api_key=api_key or "dummy", timeout=10.0)
        return sorted(m.id for m in client.models.list().data)
    except Exception as e:
        print(f"[Settings] OpenAI fetch error: {e}")
        return []


def _fetch_ollama_models(ollama_url: str) -> list[str]:
    """Récupère les modèles depuis Ollama."""
    try:
        import requests
        r = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=10)
        return sorted(m["name"] for m in r.json().get("models", [])) if r.ok else []
    except Exception as e:
        print(f"[Settings] Ollama fetch error: {e}")
        return []


# ── Worker thread ──────────────────────────────────────────────────────────

class _ModelFetchWorker(QThread):
    """Récupère la liste des modèles sans bloquer l'UI."""
    finished = pyqtSignal(list)

    def __init__(self, mode: str, api_base="", api_key="", ollama_url="", parent=None):
        super().__init__(parent)
        self._mode, self._api_base = mode, api_base
        self._api_key, self._ollama_url = api_key, ollama_url

    def run(self):
        models = (_fetch_openai_models(self._api_base, self._api_key)
                  if self._mode == "openai"
                  else _fetch_ollama_models(self._ollama_url))
        self.finished.emit(models)


# ── ComboBox avec flèche ───────────────────────────────────────────────────

class ComboBoxWithArrow(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setPen(QColor(ThemeManager.inline('input_color')))
        p.setFont(self.font())
        p.drawText(self.rect().width() - 20, self.rect().height() // 2 + 5, "▼")
        p.end()


# ── Dialogue principal ─────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres")
        self.setModal(True)
        self.setMinimumSize(520, 440)
        self._workers: dict[str, _ModelFetchWorker | None] = {"openai": None, "ollama": None}
        self._setup_ui()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_models("ollama" if Config.LOCAL else "openai", silent=True)

    # ── Construction de l'UI ───────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Paramètres")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {ThemeManager.inline('logo_color')};"
        )
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {ThemeManager.inline('input_border')};
                border-radius: 8px;
                background-color: {ThemeManager.inline('tool_card_bg')};
                padding: 12px;
            }}
            QTabBar::tab {{
                background-color: {ThemeManager.inline('model_badge_bg')};
                color: {ThemeManager.inline('tools_badge_idle')};
                border: 1px solid {ThemeManager.inline('input_border')};
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 6px 16px; margin-right: 2px; font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background-color: {ThemeManager.inline('tool_card_bg')};
                color: {ThemeManager.inline('logo_color')}; font-weight: 600;
            }}
            QTabBar::tab:hover {{ color: {ThemeManager.inline('model_badge_color')}; }}
        """)
        tabs.addTab(self._make_model_tab(), "Modèle")
        tabs.addTab(self._make_tools_tab(), "Outils")
        tabs.addTab(self._make_system_tab(), "Système")
        tabs.addTab(self._make_rag_tab(), "RAG")
        tabs.addTab(self._make_interface_tab(), "Interface")
        layout.addWidget(tabs, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Enregistrer")
        save_btn.setObjectName("send_btn")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _group_style(self) -> str:
        t = ThemeManager.inline
        return f"""
            QGroupBox {{
                color: {t('model_badge_color')};
                border: 1px solid {t('input_border')};
                border-radius: 7px; margin-top: 8px; padding: 8px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
        """

    def _combo_style(self, extra: str = "") -> str:
        t = ThemeManager.inline
        return f"""
            QComboBox {{
                background: {t('input_bg')}; color: {t('input_color')};
                border: 1px solid {t('input_border')}; border-radius: 6px;
                padding: 4px 8px; {extra}
            }}
            QComboBox:hover {{ border-color: {t('logo_color')}; }}
            QComboBox QAbstractItemView {{
                background: {t('menu_bg')}; color: {t('menu_item_color')};
                border: 1px solid {t('menu_border')};
                selection-background-color: {t('menu_item_selected_bg')};
                selection-color: {t('menu_item_selected_color')};
            }}
        """

    def _make_model_combo_row(self, mode: str) -> tuple[ComboBoxWithArrow, QPushButton]:
        """Crée une ligne (ComboBox + bouton 🔄) pour un mode donné."""
        combo = ComboBoxWithArrow()
        combo.setEditable(True)
        combo.setMinimumWidth(250)
        combo.setMaxVisibleItems(15)
        combo.setStyleSheet(self._combo_style("padding-right: 28px;"))
        btn = QPushButton("🔄")
        btn.setFixedSize(36, 32)
        btn.setStyleSheet("font-size: 16px;")
        btn.setToolTip("Actualiser la liste des modèles")
        btn.clicked.connect(lambda _: self._refresh_models(mode, silent=False))
        return combo, btn

    # ── Onglet Modèle ──────────────────────────────────────────────

    def _make_model_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        # Sélecteur de mode
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("🌐  Distant  (OpenAI-compatible)", userData=False)
        self._mode_combo.addItem("💻  Local  (Ollama)", userData=True)
        self._mode_combo.setCurrentIndex(1 if Config.LOCAL else 0)
        self._mode_combo.setStyleSheet(self._combo_style("padding: 4px 10px; font-size: 13px;"))
        self._mode_combo.currentIndexChanged.connect(
            lambda _: self._on_local_toggle(self._mode_combo.currentData())
        )
        mode_form = QFormLayout()
        mode_form.addRow("Mode de fonctionnement :", self._mode_combo)
        layout.addLayout(mode_form)

        # ── Groupe OpenAI ──
        self._openai_group = QGroupBox("Serveur OpenAI-compatible")
        self._openai_group.setStyleSheet(self._group_style())
        og = QFormLayout(self._openai_group)
        self._api_base = QLineEdit(Config.OPENAI_API_BASE)
        self._api_key = QLineEdit(Config.OPENAI_API_KEY)
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_model_combo, self._openai_refresh_btn = self._make_model_combo_row("openai")
        openai_row = QHBoxLayout()
        openai_row.addWidget(self._openai_model_combo)
        openai_row.addWidget(self._openai_refresh_btn)
        og.addRow("API Base URL :", self._api_base)
        og.addRow("API Key :", self._api_key)
        og.addRow("Modèle :", openai_row)
        layout.addWidget(self._openai_group)

        # ── Groupe Ollama ──
        self._ollama_group = QGroupBox("Ollama local")
        self._ollama_group.setStyleSheet(self._group_style())
        ol = QFormLayout(self._ollama_group)
        self._ollama_url = QLineEdit(Config.OLLAMA_BASE_URL)
        self._ollama_model_combo, self._ollama_refresh_btn = self._make_model_combo_row("ollama")
        ollama_row = QHBoxLayout()
        ollama_row.addWidget(self._ollama_model_combo)
        ollama_row.addWidget(self._ollama_refresh_btn)
        ol.addRow("URL :", self._ollama_url)
        ol.addRow("Modèle :", ollama_row)
        layout.addWidget(self._ollama_group)

        layout.addStretch()
        self._openai_model_combo.setCurrentText(Config.OPENAI_MODEL)
        self._ollama_model_combo.setCurrentText(Config.OLLAMA_MODEL)
        self._on_local_toggle(Config.LOCAL)
        return widget

    # ── Onglet Outils ──────────────────────────────────────────────

    def _make_tools_tab(self) -> QWidget:
        """
        Onglet "Outils" : liste dynamique de toutes les familles d'outils
        enregistrées au runtime.

        Pour chaque famille, deux contrôles :
          • Activée / désactivée  (toggle existant, persisté dans _PREFS_FILE)
          • Modèle assigné        (combo + backend + base URL, persisté dans
                                   ~/.promethee_family_models.json)

        La liste est construite depuis tools_engine.list_families() : aucune
        modification de code n'est nécessaire quand une nouvelle famille est
        ajoutée au projet.
        """
        from PyQt6.QtWidgets import QScrollArea
        from core import tools_engine

        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ── En-tête ────────────────────────────────────────────────────────
        hint = QLabel(
            "Assignez optionnellement un modèle LLM dédié à chaque famille d'outils.\n"
            "Laisser le champ Modèle vide = le modèle principal est utilisé.\n"
            "L'activation / désactivation des familles se gère depuis les profils ou la liste des outils."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {ThemeManager.inline('text_secondary')}; font-size: 11px;"
        )
        outer.addWidget(hint)

        # ── Zone scrollable ────────────────────────────────────────────────
        scroll = make_transparent_scroll(
            extra_style=(
                f"QScrollBar:vertical {{ background: {ThemeManager.inline('input_border')};"
                f" width: 6px; border-radius: 3px; }}"
                f"QScrollBar::handle:vertical {{ background: {ThemeManager.inline('model_badge_color')};"
                f" border-radius: 3px; }}"
                f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            ),
        )

        inner_widget = QWidget()
        inner_widget.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner_widget)
        inner_layout.setContentsMargins(0, 0, 4, 0)
        inner_layout.setSpacing(8)

        self._tools_family_widgets: dict[str, dict] = {}

        families = sorted(tools_engine.list_families(), key=lambda f: f["label"])

        for fam in families:
            family_key   = fam["family"]
            family_label = fam["label"]
            family_icon  = fam["icon"]
            tool_count   = fam["tool_count"]
            cur_model    = fam["model_name"]
            cur_backend  = fam["model_backend"]
            cur_base_url = fam["model_base_url"]

            # ── GroupBox par famille ───────────────────────────────────────
            grp = QGroupBox(f"{family_icon}  {family_label}  ({tool_count} outil{'s' if tool_count > 1 else ''})")
            grp.setStyleSheet(self._group_style())
            grp_layout = QVBoxLayout(grp)
            grp_layout.setSpacing(6)
            grp_layout.setContentsMargins(10, 8, 10, 8)

            # ── Ligne 1 : backend ─────────────────────────────────────────
            backend_row = QHBoxLayout()
            backend_lbl = QLabel("Backend :")
            backend_lbl.setFixedWidth(72)
            backend_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('model_badge_color')}; font-size: 12px;"
            )
            backend_combo = QComboBox()
            backend_combo.setStyleSheet(self._combo_style())
            backend_combo.addItem("(modèle principal)", userData="")
            backend_combo.addItem("🌐 OpenAI-compatible", userData="openai")
            backend_combo.addItem("💻 Ollama local",      userData="ollama")
            for i in range(backend_combo.count()):
                if backend_combo.itemData(i) == cur_backend:
                    backend_combo.setCurrentIndex(i)
                    break
            backend_row.addWidget(backend_lbl)
            backend_row.addWidget(backend_combo)
            backend_row.addStretch()
            grp_layout.addLayout(backend_row)

            # ── Ligne 3 : modèle (combo éditable + bouton refresh) ─────────
            model_row = QHBoxLayout()
            model_lbl = QLabel("Modèle :")
            model_lbl.setFixedWidth(72)
            model_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('model_badge_color')}; font-size: 12px;"
            )
            model_combo = ComboBoxWithArrow()
            model_combo.setEditable(True)
            model_combo.setMinimumWidth(220)
            model_combo.setStyleSheet(self._combo_style("padding-right: 28px;"))
            model_combo.setCurrentText(cur_model)
            model_combo.lineEdit().setPlaceholderText("(vide = modèle principal)")

            refresh_btn = QPushButton("🔄")
            refresh_btn.setFixedSize(32, 28)
            refresh_btn.setStyleSheet("font-size: 14px;")
            refresh_btn.setToolTip("Récupérer la liste des modèles disponibles")

            def _make_refresh(bk_cb, m_cb, base_edit):
                def _do():
                    backend = bk_cb.currentData() or (
                        "ollama" if Config.LOCAL else "openai"
                    )
                    # Résolution de l'URL : base_url si renseigné, sinon config principale
                    custom_url = base_edit.text().strip()
                    if backend == "ollama":
                        url = custom_url or Config.OLLAMA_BASE_URL
                        worker = _ModelFetchWorker("ollama", ollama_url=url, parent=self)
                    else:
                        url = custom_url or Config.OPENAI_API_BASE
                        worker = _ModelFetchWorker(
                            "openai",
                            api_base=url,
                            api_key=Config.OPENAI_API_KEY,
                            parent=self,
                        )
                    m_cb.clear()
                    m_cb.addItem("Chargement…")
                    def _on_done(models):
                        m_cb.clear()
                        m_cb.addItems(models)
                    worker.finished.connect(_on_done)
                    worker.start()
                return _do

            # ── Ligne 4 : base URL optionnelle ────────────────────────────
            url_row = QHBoxLayout()
            url_lbl = QLabel("Base URL :")
            url_lbl.setFixedWidth(72)
            url_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('model_badge_color')}; font-size: 12px;"
            )
            base_url_edit = QLineEdit(cur_base_url)
            base_url_edit.setPlaceholderText("(vide = hérite de l'endpoint principal)")

            # Brancher le refresh maintenant que base_url_edit existe
            refresh_btn.clicked.connect(
                _make_refresh(backend_combo, model_combo, base_url_edit)
            )

            model_row.addWidget(model_lbl)
            model_row.addWidget(model_combo)
            model_row.addWidget(refresh_btn)
            grp_layout.addLayout(model_row)

            url_row.addWidget(url_lbl)
            url_row.addWidget(base_url_edit)
            grp_layout.addLayout(url_row)

            # ── Stockage des références ────────────────────────────────────
            self._tools_family_widgets[family_key] = {
                "backend":   backend_combo,
                "model":     model_combo,
                "base_url":  base_url_edit,
            }

            inner_layout.addWidget(grp)

        inner_layout.addStretch()
        inner_widget.setLayout(inner_layout)
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll, stretch=1)
        return widget

    # ── Onglet Système ─────────────────────────────────────────────

    def _make_system_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        lbl = QLabel("Prompt système par défaut :")
        lbl.setStyleSheet(f"color: {ThemeManager.inline('model_badge_color')}; font-size: 12px;")
        layout.addWidget(lbl)
        self._system_prompt = QTextEdit()
        self._system_prompt.setObjectName("input_box")
        self._system_prompt.setPlaceholderText("Ex: Tu es un assistant expert en développement Python…")
        layout.addWidget(self._system_prompt, stretch=1)
        return widget

    # ── Onglet RAG ─────────────────────────────────────────────────


    def _make_rag_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        qdrant_group = QGroupBox("Qdrant")
        qdrant_group.setStyleSheet(self._group_style())
        qf = QFormLayout(qdrant_group)
        self._qdrant_url = QLineEdit(Config.QDRANT_URL)
        self._qdrant_collection = QLineEdit(Config.QDRANT_COLLECTION)
        qf.addRow("URL :", self._qdrant_url)
        qf.addRow("Collection :", self._qdrant_collection)
        layout.addWidget(qdrant_group)

        embed_group = QGroupBox("Embeddings")
        embed_group.setStyleSheet(self._group_style())
        ef = QFormLayout(embed_group)
        self._embedding_mode = QComboBox()
        self._embedding_mode.addItems(["local", "api"])
        self._embedding_mode.setCurrentText(getattr(Config, 'EMBEDDING_MODE', "local"))
        self._embedding_model = QLineEdit(getattr(Config, 'EMBEDDING_MODEL', "all-MiniLM-L6-v2"))
        self._embedding_api_base = QLineEdit(getattr(Config, 'EMBEDDING_API_BASE', "https://api.openai.com/v1"))
        self._embedding_dimension = QLineEdit(str(getattr(Config, 'EMBEDDING_DIMENSION', "384")))
        ef.addRow("Mode :", self._embedding_mode)
        ef.addRow("Modèle :", self._embedding_model)
        ef.addRow("API Base :", self._embedding_api_base)
        ef.addRow("Dimension :", self._embedding_dimension)
        layout.addWidget(embed_group)

        from core import rag_engine
        ok = rag_engine.is_available()
        color = ThemeManager.inline('rag_badge_on' if ok else 'attachment_remove_hover_color')
        status_lbl = QLabel("Disponible" if ok else "Dépendances manquantes")
        status_lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
        layout.addWidget(status_lbl)
        layout.addStretch()
        return widget

    # ── Logique fetch modèles (unifiée) ────────────────────────────

    def _refresh_models(self, mode: str, silent: bool = False):
        """Lance le fetch des modèles pour 'openai' ou 'ollama'."""
        if mode == "openai":
            url = self._api_base.text().strip()
            err_msg = "Veuillez d'abord saisir l'API Base URL"
            worker_kwargs = dict(mode="openai", api_base=url, api_key=self._api_key.text().strip())
        else:
            url = self._ollama_url.text().strip()
            err_msg = "Veuillez d'abord saisir l'URL Ollama"
            worker_kwargs = dict(mode="ollama", ollama_url=url)

        if not url:
            if not silent:
                QMessageBox.warning(self, "Erreur", err_msg)
            return

        btn = self._openai_refresh_btn if mode == "openai" else self._ollama_refresh_btn
        prev = self._workers[mode]
        if prev and prev.isRunning():
            prev.quit()

        btn.setEnabled(False)
        btn.setText("⏳")
        worker = _ModelFetchWorker(**worker_kwargs)
        worker.setParent(None)
        worker.finished.connect(lambda models: self._on_models_fetched(mode, models, silent))
        worker.start()
        self._workers[mode] = worker

    def _on_models_fetched(self, mode: str, models: list[str], silent: bool):
        """Callback unifié après fetch."""
        if mode == "openai":
            combo, btn = self._openai_model_combo, self._openai_refresh_btn
            fallback = Config.OPENAI_MODEL
            err_hint = "• L'URL de l'API est correcte\n• Le serveur est accessible\n• La clé API est valide"
        else:
            combo, btn = self._ollama_model_combo, self._ollama_refresh_btn
            fallback = Config.OLLAMA_MODEL
            err_hint = "• Ollama est démarré (ollama serve)\n• L'URL est correcte\n• Le port est accessible"

        current = combo.currentText() or fallback
        combo.clear()
        if models:
            combo.addItems(models)
            idx = combo.findText(current)
            if idx < 0:
                combo.insertItem(0, current)
                idx = 0
            combo.setCurrentIndex(idx)
            if not silent:
                QMessageBox.information(self, "Succès",
                    f"{len(models)} modèle(s) récupéré(s) !\n\nCliquez sur ▼ pour voir la liste.")
        else:
            combo.setCurrentText(current)
            if not silent:
                QMessageBox.warning(self, "Erreur",
                    f"Impossible de récupérer la liste des modèles.\n\nVérifiez :\n{err_hint}\n\n"
                    "Consultez la console pour plus de détails.")

        btn.setEnabled(True)
        btn.setText("🔄")

    def _on_local_toggle(self, is_local: bool):
        self._openai_group.setVisible(not is_local)
        self._ollama_group.setVisible(is_local)
        mode = "ollama" if is_local else "openai"
        combo = self._ollama_model_combo if is_local else self._openai_model_combo
        if combo.count() <= 1:
            self._refresh_models(mode, silent=True)

    # ── Onglet Interface ───────────────────────────────────────────

    def _make_interface_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QSpacerItem, QSizePolicy
        from ui.widgets.styles import ThemeManager as TM

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        font_group = QGroupBox("Police de l'interface")
        font_group.setStyleSheet(self._group_style())
        fg = QFormLayout(font_group)

        self._font_combo = QComboBox()
        self._font_combo.setStyleSheet(self._combo_style())
        for label in TM.FONT_OPTIONS:
            self._font_combo.addItem(label)
        current_label = TM.get_font_family_label()
        idx = self._font_combo.findText(current_label)
        self._font_combo.setCurrentIndex(max(idx, 0))

        from PyQt6.QtGui import QFont, QPalette, QColor

        preview_lbl = QLabel("Aperçu : La vieille forêt aux branches tordues — 0123456789")
        preview_lbl.setWordWrap(True)

        def _update_preview(label: str):
            stack = TM.FONT_OPTIONS.get(label, label)
            first = stack.split(",")[0].strip().strip('"')
            f = QFont(first, 13)
            f.setStyleHint(QFont.StyleHint.SansSerif)
            preview_lbl.setFont(f)
            # couleur via palette pour ne pas interférer avec la font
            pal = preview_lbl.palette()
            pal.setColor(QPalette.ColorRole.WindowText,
                         QColor(ThemeManager.inline('text_primary')))
            preview_lbl.setPalette(pal)
            preview_lbl.update()

        self._font_combo.currentTextChanged.connect(_update_preview)
        _update_preview(current_label)

        hint = QLabel(
            "⚠ Le changement de police prend effet immédiatement.\n"
            "Un redémarrage peut être nécessaire pour certains éléments."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {ThemeManager.inline('text_secondary')}; font-size: 11px;"
        )

        fg.addRow("Police :", self._font_combo)
        fg.addRow("", preview_lbl)
        fg.addRow("", hint)
        layout.addWidget(font_group)
        layout.addStretch()
        return widget

    # ── Sauvegarde ─────────────────────────────────────────────────

    def _save(self):
        is_local = self._mode_combo.currentData()

        # Paires (clé_env, valeur, attribut_Config_ou_None)
        entries = [
            ("LOCAL",              "ON" if is_local else "OFF",           None),
            ("OPENAI_API_BASE",    self._api_base.text(),                  "OPENAI_API_BASE"),
            ("OPENAI_API_KEY",     self._api_key.text(),                   "OPENAI_API_KEY"),
            ("OPENAI_MODEL",       self._openai_model_combo.currentText(), "OPENAI_MODEL"),
            ("OLLAMA_BASE_URL",    self._ollama_url.text(),                "OLLAMA_BASE_URL"),
            ("OLLAMA_MODEL",       self._ollama_model_combo.currentText(), "OLLAMA_MODEL"),
            ("QDRANT_URL",         self._qdrant_url.text(),                "QDRANT_URL"),
            ("QDRANT_COLLECTION",  self._qdrant_collection.text(),         "QDRANT_COLLECTION"),
            ("EMBEDDING_MODE",     self._embedding_mode.currentText(),     "EMBEDDING_MODE"),
            ("EMBEDDING_MODEL",    self._embedding_model.text(),           "EMBEDDING_MODEL"),
            ("EMBEDDING_API_BASE", self._embedding_api_base.text(),        "EMBEDDING_API_BASE"),
            ("EMBEDDING_DIMENSION",self._embedding_dimension.text(),       None),
        ]
        for key, value, attr in entries:
            _save_env(key, value)
            if attr:
                setattr(Config, attr, value)

        Config.LOCAL = is_local
        Config.EMBEDDING_DIMENSION = int(self._embedding_dimension.text())
        print(f"[Settings] Modèle actif: {Config.active_model()}")

        # ── Préférences interface ──
        from PyQt6.QtCore import QSettings
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QApplication
        from ui.widgets.styles import ThemeManager as TM

        font_label = self._font_combo.currentText()
        TM.set_font_family(font_label)
        prefs = QSettings("Promethee", "App")
        prefs.setValue("ui/font_family", font_label)
        # Mettre à jour la QFont de l'application
        stack = TM.get_font_family_stack()
        first_font = stack.split(",")[0].strip().strip('"')
        app_font = QFont(first_font, 10)
        app_font.setStyleHint(QFont.StyleHint.SansSerif)
        QApplication.instance().setFont(app_font)
        # Ré-appliquer le style global à la fenêtre principale
        if self.parent():
            TM.apply(self.parent())
        print(f"[Settings] Police: {font_label}")

        from core import rag_engine
        rag_engine._init_embedder()

        # ── Familles d'outils : modèles assignés ──
        from core import tools_engine
        for family_key, widgets in self._tools_family_widgets.items():
            # Modèle assigné (persisté dans ~/.promethee_family_models.json)
            backend  = widgets["backend"].currentData() or ""
            model    = widgets["model"].currentText().strip()
            base_url = widgets["base_url"].text().strip()
            tools_engine.set_family_model(family_key, backend, model, base_url)

        self.settings_changed.emit()
        self.accept()

    def get_system_prompt(self) -> str:
        return self._system_prompt.toPlainText().strip()
