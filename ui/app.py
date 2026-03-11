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
app.py — Application Qt

Initialisation du chiffrement de la base de donnees
----------------------------------------------------
Si DB_ENCRYPTION=ON dans .env, un dialogue de passphrase est présenté avant
l'ouverture de la fenêtre principale. La passphrase est injectée dans
HistoryDB via une instance partagée passée à MainWindow.

Flux :
  1. Créer QApplication
  2. Si DB_ENCRYPTION=ON :
       a. Détecter si la base existe déjà (base existante ou nouvelle)
       b. Afficher PassphraseDialog (MODE_OPEN ou MODE_CREATE)
       c. Valider la passphrase contre le sentinel (WrongPassphraseError)
          -> En cas d'échec : re-afficher le dialogue avec message d'erreur
       d. Passer l'instance HistoryDB configurée à MainWindow
  3. Sinon (Si DB_ENCRYPTION=OFF) : fonctionnement en clair
"""
import sys
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtGui import QFont

from core import Config, HistoryDB
from core.database import WrongPassphraseError
from core import crypto
from .main_window import MainWindow
from .widgets.styles import ThemeManager
from .splash_screen import SplashScreen


def _request_passphrase(db: HistoryDB, db_exists: bool) -> bool:
    """
    Affiche le dialogue de passphrase et configure db en conséquence.

    Retourne True si la passphrase a été validée, False si l'utilisateur
    a annulé (dans ce cas l'application doit quitter).
    """
    from .dialogs.passphrase_dialog import PassphraseDialog

    mode = PassphraseDialog.MODE_OPEN if db_exists else PassphraseDialog.MODE_CREATE

    while True:
        dlg = PassphraseDialog(mode=mode)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False   # annulation -> quitter

        try:
            db.set_passphrase(dlg.passphrase())
            return True    # succès
        except WrongPassphraseError:
            # Recréer le dialogue avec message d'erreur (la passphrase est effacée)
            err_dlg = PassphraseDialog(mode=mode)
            err_dlg.show_error(
                "Passphrase incorrecte. Veuillez reessayer."
            )
            if err_dlg.exec() != QDialog.DialogCode.Accepted:
                return False
            try:
                db.set_passphrase(err_dlg.passphrase())
                return True
            except WrongPassphraseError:
                # Apres deux échecs consécutifs, afficher un message et quitter
                msg = QMessageBox()
                msg.setWindowTitle("Acces refuse")
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setText(
                    "<b>Passphrase incorrecte.</b><br><br>"
                    "Impossible d'ouvrir la base de données chiffrée.<br>"
                    "Verifiez votre passphrase et relancez l'application."
                )
                msg.setStyleSheet(ThemeManager.dialog_style())
                msg.exec()
                return False


def run():
    """Lance l'application PyQt6."""
    app = QApplication(sys.argv)
    app.setApplicationName(Config.APP_TITLE)
    app.setApplicationVersion(Config.APP_VERSION)

    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    # -- Splash screen -------------------------------------------------------
    # Pour utiliser une image : SplashScreen.IMAGE_PATH = Path("assets/splash.png")
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    # -- Initialisation de la base de donnees --------------------------------
    import os
    from pathlib import Path
    db_path  = Config.HISTORY_DB
    db_exists = Path(db_path).exists() and Path(db_path).stat().st_size > 0

    splash.set_message("Ouverture de la base de données…")
    app.processEvents()
    db = HistoryDB(db_path=db_path)

    if Config.DB_ENCRYPTION:
        if not crypto._CRYPTO_OK:
            msg = QMessageBox()
            msg.setWindowTitle("Dependance manquante")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText(
                "<b>Le module 'cryptography' est requis pour le chiffrement.</b><br><br>"
                "Installez-le avec :<br><code>pip install cryptography</code><br><br>"
                "Ou désactivez le chiffrement dans .env : <code>DB_ENCRYPTION=OFF</code>"
            )
            msg.exec()
            sys.exit(1)

        ok = _request_passphrase(db, db_exists)
        if not ok:
            sys.exit(0)

    # -- Fenêtre principale --------------------------------------------------
    splash.set_message("Démarrage…")
    app.processEvents()
    win = MainWindow(db=db)
    splash.finish(win)
    win.show()

    # Nettoyer le cache de clés à la fermeture
    app.aboutToQuit.connect(crypto.clear_key_cache)

    sys.exit(app.exec())
