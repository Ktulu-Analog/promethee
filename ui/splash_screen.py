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
splash_screen.py — Écran de démarrage

Utilisation dans app.py :
    from .splash_screen import SplashScreen

    splash = SplashScreen()          # image optionnelle via IMAGE_PATH
    splash.show()
    app.processEvents()

    # ... initialisation ...
    splash.set_message("Chargement de la base de données…")
    app.processEvents()

    # ... suite ...
    splash.finish(win)               # ferme proprement au moment de win.show()

Configuration :
    SplashScreen.IMAGE_PATH = Path("assets/splash.png")   # None = pas d'image
    SplashScreen.DURATION_MS = 0      # 0 = fermeture manuelle via finish()
"""

from __future__ import annotations
from pathlib import Path

from PyQt6.QtWidgets import QSplashScreen, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore    import Qt, QTimer
from PyQt6.QtGui     import QPixmap, QPainter, QColor, QFont, QPen
from core.config import Config


# ── Configuration (modifier ici ou depuis l'extérieur avant instanciation) ───

class SplashScreen(QSplashScreen):
    """
    Écran de démarrage minimaliste.

    Si IMAGE_PATH pointe vers une image existante, elle est affichée centrée.
    Sinon un fond dégradé avec le nom de l'application est affiché.
    """

    # -- Paramètres à personnaliser ------------------------------------------
    IMAGE_PATH: Path | None = Path(__file__).parent.parent / "assets" / "logo.png"
    WIDTH:     int = 512
    BANNER_H:  int = 48              # hauteur du bandeau sous le logo
    HEIGHT:    int = WIDTH + BANNER_H  # hauteur totale calculée automatiquement
    BG_TOP:    str = "#141416"       # couleur haut du dégradé (thème sombre)
    BG_BOTTOM: str = "#1c1c1f"       # couleur bas du dégradé
    ACCENT:    str = "#d4813d"       # couleur d'accentuation
    APP_NAME:  str = "Prométhée"
    VERSION:   str = f"v{Config.APP_VERSION}"  # défini via APP_VERSION dans .env
    DURATION_MS: int = 0             # 0 = fermeture via finish() uniquement

    def __init__(self):
        pixmap = self._make_pixmap()
        super().__init__(pixmap)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        # Centrer sur l'écran
        screen = self.screen().geometry()
        self.move(
            screen.center().x() - self.WIDTH  // 2,
            screen.center().y() - self.HEIGHT // 2,
        )
        if self.DURATION_MS > 0:
            QTimer.singleShot(self.DURATION_MS, self.close)

    # ── Pixmap ───────────────────────────────────────────────────────────────

    def _make_pixmap(self) -> QPixmap:
        """Compose le pixmap du splash : image ou fond dégradé + texte."""
        px = QPixmap(self.WIDTH, self.HEIGHT)
        px.fill(Qt.GlobalColor.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fond
        from PyQt6.QtGui import QLinearGradient
        grad = QLinearGradient(0, 0, 0, self.HEIGHT)
        grad.setColorAt(0.0, QColor(self.BG_TOP))
        grad.setColorAt(1.0, QColor(self.BG_BOTTOM))
        painter.fillRect(0, 0, self.WIDTH, self.HEIGHT, grad)

        # Image (si configurée et existante)
        if self.IMAGE_PATH and Path(self.IMAGE_PATH).exists():
            img = QPixmap(str(self.IMAGE_PATH))
            # Mise à l'échelle pour couvrir exactement le carré du logo
            img = img.scaled(self.WIDTH, self.WIDTH,
                             Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(0, 0, img)
        else:
            # Nom de l'application centré
            font = QFont("Segoe UI", 28, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor("#e4e2ec"))
            painter.drawText(
                0, 0, self.WIDTH, int(self.HEIGHT * 0.70),
                Qt.AlignmentFlag.AlignCenter,
                self.APP_NAME,
            )

        # Fond du bandeau (sous le logo)
        from PyQt6.QtGui import QLinearGradient as _LG
        band_grad = _LG(0, self.WIDTH, 0, self.HEIGHT)
        band_grad.setColorAt(0.0, QColor(self.BG_TOP))
        band_grad.setColorAt(1.0, QColor(self.BG_BOTTOM))
        painter.fillRect(0, self.WIDTH, self.WIDTH, self.BANNER_H, band_grad)

        # Version (dans le bandeau bas, au-dessus de la barre accent)
        if self.VERSION:
            font_v = QFont("Segoe UI", 10)
            painter.setFont(font_v)
            painter.setPen(QColor(self.ACCENT))
            painter.drawText(
                0, self.WIDTH,
                self.WIDTH, self.BANNER_H - 3,  # -3 pour laisser place à la barre
                Qt.AlignmentFlag.AlignCenter,
                self.VERSION,
            )

        # Barre de couleur accent en bas
        bar_h = 3
        painter.fillRect(0, self.HEIGHT - bar_h, self.WIDTH, bar_h, QColor(self.ACCENT))

        painter.end()
        return px

    # ── Message de statut ────────────────────────────────────────────────────

    def set_message(self, text: str) -> None:
        """Affiche un message de statut en bas du splash."""
        self.showMessage(
            text,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            QColor("#8a8a98"),
        )
