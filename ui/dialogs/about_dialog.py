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
about_dialog.py — Dialogue À propos de l'application
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from core.config import Config
from ui.widgets.styles import ThemeManager


class AboutDialog(QDialog):
    """Dialogue affichant les informations sur l'application."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("À propos")
        self.setModal(True)
        self.setFixedSize(520, 420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 20)
        layout.setSpacing(15)

        # Logo image (si disponible) ou titre texte en fallback
        _logo_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
        if _logo_path.exists():
            logo_lbl = QLabel()
            px = QPixmap(str(_logo_path))
            px = px.scaled(180, 100,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(px)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_lbl.setStyleSheet("background: transparent;")
            layout.addWidget(logo_lbl)
        else:
            title = QLabel(Config.APP_TITLE)
            title_font = QFont()
            title_font.setPointSize(24)
            title_font.setBold(True)
            title.setFont(title_font)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet(f"color: {ThemeManager.inline('logo_color')};")
            layout.addWidget(title)

        # Version
        version_label = QLabel(f"{Config.APP_TITLE} v{Config.APP_VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet(
            f"font-size: 14px; color: {ThemeManager.inline('model_badge_color')};"
        )
        layout.addWidget(version_label)

        # Espaceur
        layout.addSpacing(10)


        # Description
        desc = QLabel(
            "Compréhension contextuelle : l’IA suit le fil de vos échanges.\n"
            "Sécurité : vos conversations restent privées et chiffrées.\n"
            "Personnalisation : adaptez le ton, le style et les domaines d’expertise."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size: 13px; color: {ThemeManager.inline('input_color')}; "
            "line-height: 1.5;"
        )
        layout.addWidget(desc)

        layout.addSpacing(15)

        # Informations détaillées
        info_layout = QVBoxLayout()
        info_layout.setSpacing(0)

        info_data = [
            ("Date", "Février 2026"),
            ("Auteur", "Pierre COUGET"),
            ("Licence", "AGPL 3.0"),
            ("Python", "3.11+"),
            ("Framework", "PyQt6"),
        ]

        for label, value in info_data:
            row = QHBoxLayout()
            row.setSpacing(10)

            lbl = QLabel(f"{label} :")
            lbl.setStyleSheet(
                f"font-weight: 600; color: {ThemeManager.inline('model_badge_color')}; "
                "min-width: 80px;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(lbl)

            val = QLabel(value)
            val.setStyleSheet(f"color: {ThemeManager.inline('input_color')};")
            row.addWidget(val)
            row.addStretch()

            info_layout.addLayout(row)

        layout.addLayout(info_layout)

        layout.addStretch()

        # Bouton fermer
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Fermer")
        close_btn.setFixedSize(100, 32)
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ThemeManager.inline('input_bg')};
                color: {ThemeManager.inline('input_color')};
                border: 1px solid {ThemeManager.inline('input_border')};
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {ThemeManager.inline('tool_card_bg')};
            }}
            QPushButton:pressed {{
                background: {ThemeManager.inline('tool_card_border')};
            }}
        """)

        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Style du dialogue
        self.setStyleSheet(f"""
            QDialog {{
                background: {ThemeManager.inline('tool_result_bg')};
            }}
        """)
