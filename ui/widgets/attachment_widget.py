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
attachment_widget.py — Widget de gestion des attachements (fichiers, images, URLs)
"""
import base64
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QToolButton, QMenu, QFileDialog, QInputDialog, QFrame,
    QScrollArea, QSizePolicy, QProgressBar,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QImage, QIcon, QAction
from .styles import ThemeManager
from .icon_helper import icon_label, icon_pixmap, icon_for_button, icon_for_file


class LoadingItem(QWidget):
    """Widget temporaire affichant le chargement d'une URL."""

    cancel_requested = pyqtSignal()

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)

        header.addWidget(icon_label("url", 16))  # icône SVG lien

        url_label = QLabel(self.url[:50] + ("..." if len(self.url) > 50 else ""))
        url_label.setStyleSheet(
            f"color: {ThemeManager.inline('attachment_name_color')}; "
            "font-size: 12px; font-weight: 500;"
        )
        header.addWidget(url_label)
        header.addStretch()

        # Bouton annuler — icône SVG
        cancel_btn = QPushButton()
        cancel_btn.setIcon(icon_for_button("close_x", 14))
        cancel_btn.setIconSize(QSize(14, 14))
        cancel_btn.setFixedSize(20, 20)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {ThemeManager.inline('attachment_remove_color')};
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.inline('attachment_remove_hover_bg')};
                color: {ThemeManager.inline('attachment_remove_hover_color')};
            }}
        """)
        cancel_btn.clicked.connect(self.cancel_requested.emit)
        header.addWidget(cancel_btn)

        layout.addLayout(header)

        # Barre de progression
        self.progress = QProgressBar()
        self.progress.setMaximum(0)  # Mode indéterminé
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {ThemeManager.inline('attachment_item_border')};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {ThemeManager.inline('attachment_btn_color')};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.progress)

        # Style du container
        bg = ThemeManager.inline("attachment_item_bg")
        border = ThemeManager.inline("attachment_item_border")
        self.setStyleSheet(f"""
            LoadingItem {{
                background-color: {bg};
                border: 1px solid {border};
                border-left: 3px solid {ThemeManager.inline('attachment_btn_color')};
                border-radius: 6px;
            }}
        """)

    def set_status(self, status: str):
        """Met à jour le statut affiché."""
        # On pourrait ajouter un label de statut si nécessaire
        pass


class AttachmentItem(QWidget):
    """Widget représentant un seul attachement."""

    remove_requested = pyqtSignal()
    preview_requested = pyqtSignal(str)  # Chemin du fichier

    def __init__(self, attachment_type: str, data: dict, parent=None):
        super().__init__(parent)
        self.attachment_type = attachment_type  # 'file', 'image', 'url'
        self.data = data
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Thumbnail pour les images
        if self.attachment_type == "image" and "base64" in self.data:
            try:
                from PyQt6.QtCore import QByteArray
                # Décoder le base64 et créer un QPixmap
                img_data = QByteArray.fromBase64(self.data["base64"].encode())
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)

                # Créer le label avec thumbnail
                thumb_label = QLabel()
                thumb_label.setPixmap(pixmap.scaled(
                    40, 40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
                thumb_label.setFixedSize(40, 40)
                thumb_label.setStyleSheet("border-radius: 4px; background: transparent;")
                layout.addWidget(thumb_label)
            except Exception:
                # Fallback vers l'icône si erreur
                layout.addWidget(icon_label("image", 20))

        # Preview pour les PDFs
        elif self.attachment_type == "file" and "preview" in self.data and self.data["preview"]:
            try:
                from PyQt6.QtCore import QByteArray
                # Décoder le base64 du preview
                img_data = QByteArray.fromBase64(self.data["preview"].encode())
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)

                # Créer le label avec thumbnail
                thumb_label = QLabel()
                thumb_label.setPixmap(pixmap.scaled(
                    40, 40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
                thumb_label.setFixedSize(40, 40)
                thumb_label.setStyleSheet("border-radius: 4px; background: transparent; border: 1px solid #444;")
                thumb_label.setToolTip("Aperçu de la première page")
                layout.addWidget(thumb_label)
            except Exception:
                # Fallback vers l'icône si erreur
                layout.addWidget(icon_label("pdf", 20))

        else:
            # Icône SVG selon le type
            if self.attachment_type == "image":
                layout.addWidget(icon_label("image", 20))
            elif self.attachment_type == "url":
                layout.addWidget(icon_label("url", 20))
            else:
                # Choisir pdf ou file selon l'extension
                file_path = self.data.get("path", self.data.get("name", ""))
                suffix = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
                if suffix == "pdf":
                    layout.addWidget(icon_label("pdf", 20))
                else:
                    layout.addWidget(icon_label("file", 20))

        # Nom/description
        name = self.data.get("name", "")
        if self.attachment_type == "url":
            name = self.data.get("url", "")[:50]

        # Ajouter le nombre de pages pour les PDFs
        if self.attachment_type == "file" and "pages" in self.data:
            name += f" ({self.data['pages']} pages"
            # Indicateur OCR
            if self.data.get("ocr_used"):
                name += ", OCR"
            name += ")"

        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: {ThemeManager.inline('attachment_name_color')}; "
            "font-size: 12px; font-weight: 500;"
        )
        name_label.setWordWrap(False)
        name_label.setMaximumWidth(200)
        layout.addWidget(name_label)

        # Taille (pour fichiers)
        if self.attachment_type in ("file", "image", "url") and "size" in self.data:
            size_kb = self.data["size"] / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            size_label = QLabel(size_str)
            size_label.setStyleSheet(
                f"color: {ThemeManager.inline('attachment_size_color')}; font-size: 10px;"
            )
            layout.addWidget(size_label)

        layout.addStretch()

        # Bouton preview pour PDFs
        if self.attachment_type == "file" and "preview" in self.data and self.data["preview"]:
            preview_btn = QPushButton()
            preview_btn.setIcon(icon_for_button("preview_eye", 14))
            preview_btn.setIconSize(QSize(14, 14))
            preview_btn.setObjectName("preview_btn")
            preview_btn.setFixedSize(24, 24)
            preview_btn.setToolTip("Prévisualiser le PDF")
            preview_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {ThemeManager.inline('attachment_btn_bg')};
                    color: {ThemeManager.inline('attachment_btn_color')};
                    border: 1px solid {ThemeManager.inline('attachment_btn_border')};
                    border-radius: 12px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {ThemeManager.inline('attachment_btn_hover_bg')};
                }}
            """)
            preview_btn.clicked.connect(self._on_preview_clicked)
            layout.addWidget(preview_btn)

        # Bouton supprimer — icône SVG
        remove_btn = QPushButton()
        remove_btn.setIcon(icon_for_button("close_x", 12))
        remove_btn.setIconSize(QSize(12, 12))
        remove_btn.setObjectName("attachment_remove_btn")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {ThemeManager.inline('attachment_remove_color')};
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {ThemeManager.inline('attachment_remove_hover_bg')};
                color: {ThemeManager.inline('attachment_remove_hover_color')};
            }}
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        layout.addWidget(remove_btn)

        # Style du container
        self._apply_style()

    def _on_preview_clicked(self):
        """Émet le signal de prévisualisation avec le chemin du fichier."""
        self.preview_requested.emit(self.data.get("path", ""))

    def _apply_style(self):
        bg = ThemeManager.inline("attachment_item_bg")
        border = ThemeManager.inline("attachment_item_border")
        self.setStyleSheet(f"""
            AttachmentItem {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
        """)

    def refresh_theme(self):
        self._apply_style()


class AttachmentBar(QWidget):
    """Barre d'attachements affichée sous le champ de saisie."""

    preview_requested = pyqtSignal(str)  # Chemin du fichier

    def __init__(self, parent=None):
        super().__init__(parent)
        self.attachments = []
        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(6)

        # Scroll area pour les attachements
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(50)

        self._container = QWidget()
        self._container_layout = QHBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(6)
        self._container_layout.addStretch()

        scroll.setWidget(self._container)
        layout.addWidget(scroll)

    def add_loading_item(self, loading_item: "LoadingItem"):
        """Insère un indicateur de chargement (URL en cours de fetch)."""
        self._container_layout.insertWidget(
            self._container_layout.count() - 1,
            loading_item
        )
        self.setVisible(True)

    def remove_loading_item(self, loading_item: "LoadingItem"):
        """Retire un indicateur de chargement."""
        loading_item.setParent(None)
        loading_item.deleteLater()

    def add_attachment(self, attachment_type: str, data: dict):
        """Ajoute un attachement."""
        item = AttachmentItem(attachment_type, data)
        item.remove_requested.connect(lambda: self._remove_attachment(item))
        item.preview_requested.connect(self.preview_requested.emit)

        # Insérer avant le stretch
        self._container_layout.insertWidget(
            self._container_layout.count() - 1, item
        )

        self.attachments.append({
            "type": attachment_type,
            "data": data,
            "widget": item
        })

        self.setVisible(True)

    def _remove_attachment(self, item: AttachmentItem):
        """Supprime un attachement."""
        # Trouver et supprimer de la liste
        self.attachments = [
            a for a in self.attachments if a["widget"] != item
        ]

        # Supprimer le widget
        item.setParent(None)
        item.deleteLater()

        # Cacher si vide
        if not self.attachments:
            self.setVisible(False)

    def clear(self):
        """Supprime tous les attachements."""
        for att in self.attachments:
            att["widget"].setParent(None)
            att["widget"].deleteLater()
        self.attachments.clear()
        self.setVisible(False)

    def get_attachments(self) -> list:
        """Retourne la liste des attachements."""
        return [
            {"type": a["type"], "data": a["data"]}
            for a in self.attachments
        ]

    def refresh_theme(self):
        """Propage le changement de thème."""
        for att in self.attachments:
            if hasattr(att["widget"], "refresh_theme"):
                att["widget"].refresh_theme()


class AttachmentButton(QToolButton):
    """Bouton "+" pour ajouter des attachements."""

    file_selected = pyqtSignal(str)      # path
    image_selected = pyqtSignal(str)     # path
    url_selected = pyqtSignal(str)       # url

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setText("+")
        self.setToolTip("Ajouter un fichier, une image ou une URL")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        # Style
        self._apply_style()

        # Menu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {ThemeManager.inline('menu_bg')};
                border: 1px solid {ThemeManager.inline('menu_border')};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px 8px 12px;
                border-radius: 4px;
                color: {ThemeManager.inline('menu_item_color')};
            }}
            QMenu::item:selected {{
                background: {ThemeManager.inline('menu_item_selected_bg')};
                color: {ThemeManager.inline('menu_item_selected_color')};
            }}
            QMenu::separator {{
                height: 1px;
                background: {ThemeManager.inline('menu_separator')};
                margin: 4px 8px;
            }}
        """)

        # Actions avec icônes SVG
        file_action = QAction("  Joindre un fichier", self)
        file_action.setIcon(QIcon(icon_pixmap("file", 16)))
        file_action.triggered.connect(self._select_file)
        menu.addAction(file_action)

        image_action = QAction("  Joindre une image", self)
        image_action.setIcon(QIcon(icon_pixmap("image", 16)))
        image_action.triggered.connect(self._select_image)
        menu.addAction(image_action)

        menu.addSeparator()

        url_action = QAction("  Ajouter une URL", self)
        url_action.setIcon(QIcon(icon_pixmap("url", 16)))
        url_action.triggered.connect(self._add_url)
        menu.addAction(url_action)

        self.setMenu(menu)

    def _apply_style(self):
        bg = ThemeManager.inline("attachment_btn_bg")
        border = ThemeManager.inline("attachment_btn_border")
        color = ThemeManager.inline("attachment_btn_color")
        hover_bg = ThemeManager.inline("attachment_btn_hover_bg")

        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 18px;
                color: {color};
                font-size: 18px;
                font-weight: bold;
                padding: 0;
                width: 36px;
                height: 36px;
            }}
            QToolButton:hover {{
                background-color: {hover_bg};
            }}
            QToolButton::menu-indicator {{
                image: none;
            }}
        """)

    def _select_file(self):
        """Ouvre un dialogue pour sélectionner un ou plusieurs fichiers."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Sélectionner des fichiers",
            "",
            "Tous les fichiers (*.*);;"
            "Texte (*.txt *.md *.py *.js *.json *.xml *.yaml *.csv);;"
            "PDF (*.pdf);;"
            "Office (*.docx *.xlsx *.pptx)"
        )
        for path in paths:
            self.file_selected.emit(path)

    def _select_image(self):
        """Ouvre un dialogue pour sélectionner une ou plusieurs images."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Sélectionner des images",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )
        for path in paths:
            self.image_selected.emit(path)

    def _add_url(self):
        """Demande une URL à l'utilisateur."""
        url, ok = QInputDialog.getText(
            self,
            "Ajouter une URL",
            "URL à analyser :",
            text="https://"
        )
        if ok and url.strip():
            self.url_selected.emit(url.strip())

    def refresh_theme(self):
        """Propage le changement de thème."""
        self._apply_style()
