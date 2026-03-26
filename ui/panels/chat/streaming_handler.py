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
streaming_handler.py — Gestionnaire des événements de streaming et outils
"""
from typing import Optional, Callable
from PyQt6.QtCore import QObject, pyqtSignal

from ui.widgets import MessageWidget, TypingIndicator
from core.database import HistoryDB


class StreamingHandler(QObject):
    """
    Gère les événements de streaming (tokens, outils, erreurs).

    Signals
    -------
    status_message : Signal pour mettre à jour le statut
    scroll_requested : Signal pour scroller en bas
    """

    status_message = pyqtSignal(str)
    scroll_requested = pyqtSignal()

    def __init__(
        self,
        db: HistoryDB,
        conv_id: str,
        insert_widget_callback: Callable,
        parent=None
    ):
        """
        Parameters
        ----------
        db : HistoryDB
            Base de données
        conv_id : str
            ID de la conversation
        insert_widget_callback : Callable
            Fonction pour insérer un widget dans le layout
        """
        super().__init__(parent)
        self.db = db
        self.conv_id = conv_id
        self._insert_widget = insert_widget_callback

        # État
        self._typing: Optional[TypingIndicator] = None
        self._cur_assistant: Optional[MessageWidget] = None

        # Bulle dédiée aux appels d'outils (créée au premier appel, réutilisée ensuite).
        # _tools_called conserve la liste ordonnée pour reconstruire le contenu.
        self._tool_bubble: Optional[MessageWidget] = None
        self._tools_called: list[str] = []
        # Cache {tool_name: icon} chargé une seule fois par session de streaming.
        self._tool_icons: dict[str, str] = {}

    # ── Gestion des outils ───────────────────────────────────────────────

    def _build_tools_mention(self, suffix: str = "") -> str:
        """Construit la ligne Markdown listant les outils appelés.

        Parameters
        ----------
        suffix : str
            Texte optionnel ajouté après la ligne d'outils (ex: message de
            progression en italique). Doit inclure les sauts de ligne nécessaires.

        Returns
        -------
        str
            Markdown de la forme ``icon *nom*  ·  icon *nom*\\n\\n[suffix]``.
        """
        parts = [
            f"{self._tool_icons.get(n, '🔧')} *{n}*"
            for n in self._tools_called
        ]
        return "  ·  ".join(parts) + "\n\n" + suffix

    def on_tool_called(self, tool_name: str, args_json: str):
        """Callback quand un outil est appelé.

        Tous les appels d'outils s'affichent sur une seule ligne dans le chat :
        chaque nouvel appel met à jour la même bulle plutôt qu'en créer une nouvelle.
        La barre de statut reflète l'outil en cours.
        """
        # Charger le cache d'icônes une seule fois (premier appel de la session)
        if not self._tool_icons:
            from core import tools_engine
            self._tool_icons = {
                t["name"]: t["icon"] for t in tools_engine.list_tools()
            }

        icon = self._tool_icons.get(tool_name, "🔧")
        self._tools_called.append(tool_name)
        mention = self._build_tools_mention()

        if self._tool_bubble is None:
            # Premier appel : retirer l'indicateur de frappe et créer la bulle
            if self._typing:
                self._typing.setParent(None)
                self._typing.deleteLater()
                self._typing = None

            self._tool_bubble = MessageWidget("assistant", mention)
            self._tool_bubble.start_streaming()
            self._cur_assistant = self._tool_bubble
            self._insert_widget(self._tool_bubble)
        else:
            # Appels suivants : mettre à jour la bulle existante
            self._tool_bubble.set_content(mention)

        self.scroll_requested.emit()
        self.status_message.emit(f"{icon} {tool_name}…")

    def on_tool_progress(self, message: str):
        """Callback pour la progression intermédiaire d'un outil (ex: chunks audio).

        Met à jour la bulle d'outil en place et la barre de statut,
        donnant un retour visuel sans bloquer l'UI.
        """
        if self._tool_bubble is not None:
            self._tool_bubble.set_content(self._build_tools_mention(f"_{message}_"))
        self.status_message.emit(message)
        self.scroll_requested.emit()

    def on_memory_event(self, message: str):
        """Callback pour les événements de mémoire de session (consolidation, pinning).

        Affiche une ligne dédiée dans la bulle d'outils (ou la crée si absente)
        et met à jour la barre de statut.
        """
        if self._tool_bubble is not None:
            self._tool_bubble.set_content(
                self._build_tools_mention(f"_🧠 {message}_")
            )
        self.status_message.emit(f"🧠 {message}")
        self.scroll_requested.emit()

    def on_tool_result(self, tool_name: str, result: str):
        """Callback quand un outil retourne un résultat.

        Le résultat brut n'est pas affiché — il est passé au LLM
        qui le synthétise dans sa réponse finale (via on_token).
        On remet la bulle d'outil à son état normal (sans message de progression).
        """
        if self._tool_bubble is not None:
            self._tool_bubble.set_content(self._build_tools_mention())
        self.status_message.emit(f"✓ {tool_name} — génération de la réponse…")
        self.scroll_requested.emit()

    def on_tool_image(self, mime_type: str, base64_data: str):
        """Callback quand un outil génère une image (ex: matplotlib).

        Affiche l'image directement dans le chat sous forme de bulle assistant
        indépendante, avant la réponse textuelle finale.

        On utilise la syntaxe Markdown  ![alt](data:...)  plutôt qu'une balise
        HTML <img> brute : _protect_data_images() dans message_widget.py intercepte
        cette forme et la remplace par un bouton cliquable qui ouvre
        ImageViewerDialog via QPixmap natif.  La balise <img> avec data-URI est
        bloquée par la politique CSP file:// de QWebEngineView.setHtml() et ne
        s'affiche donc jamais dans la WebView.
        """
        data_uri = f"data:{mime_type};base64,{base64_data}"
        # Syntaxe Markdown — interceptée par _protect_data_images()
        img_md = f"![Graphique généré]({data_uri})"
        img_widget = MessageWidget("assistant", img_md)
        self._insert_widget(img_widget)
        self.scroll_requested.emit()

    # ── Gestion du streaming ─────────────────────────────────────────────

    def on_token(self, token: str):
        """Callback pour chaque token reçu.

        Si un MessageWidget existe déjà (créé par on_tool_called),
        on ajoute les tokens à la suite — même bulle, réponse fluide.
        Sinon (streaming sans outil), on crée le widget normalement.
        """
        # Retirer l'indicateur de frappe si présent (streaming sans outil)
        if self._typing:
            self._typing.setParent(None)
            self._typing.deleteLater()
            self._typing = None
            # Pas encore de widget → le créer et démarrer le mode streaming
            if not self._cur_assistant:
                self._cur_assistant = MessageWidget("assistant", "")
                self._cur_assistant.start_streaming()
                self._insert_widget(self._cur_assistant)

        # Ajouter le token au widget existant (avec ou sans mention d'outil)
        if self._cur_assistant:
            self._cur_assistant.append_token(token)
        self.scroll_requested.emit()

    def on_finished(self, full_text: str):
        """Callback quand le streaming est terminé."""
        # Rendu Markdown final (remplace l'affichage texte brut du streaming)
        if self._cur_assistant:
            self._cur_assistant.end_streaming()

        # Sauvegarder en DB si on a du texte
        if full_text.strip():
            self.db.add_message(self.conv_id, "assistant", full_text)

        # Nettoyer l'état
        self.reset()
        self.status_message.emit("Prêt")

    def on_cancelled(self, partial_text: str):
        """Callback quand l'utilisateur a stoppé le streaming."""
        # Finaliser le widget assistant en cours (rendu Markdown du texte partiel)
        if self._cur_assistant:
            self._cur_assistant.end_streaming()

        # Sauvegarder le texte partiel en DB s'il y en a un
        if partial_text.strip():
            self.db.add_message(self.conv_id, "assistant", partial_text)

        # Ajouter une indication visuelle discrète sous la réponse tronquée
        cancelled_widget = MessageWidget("assistant", "*⏹ Réponse interrompue par l'utilisateur.*")
        self._insert_widget(cancelled_widget)

        # Nettoyer l'état
        self.reset()
        self.status_message.emit("Arrêté")

    def on_error(self, error: str):
        """Callback en cas d'erreur."""
        # Retirer l'indicateur si présent
        if self._typing:
            self._typing.setParent(None)
            self._typing = None

        # Stopper le streaming en cours s'il y en a un
        if self._cur_assistant:
            self._cur_assistant.end_streaming()

        # Afficher l'erreur
        error_widget = MessageWidget("assistant", f"[!] **Erreur** : `{error}`")
        self._insert_widget(error_widget)

        # Nettoyer l'état
        self.reset()
        self.status_message.emit(f"Erreur : {error[:80]}")

    # ── Gestion de l'état ────────────────────────────────────────────────

    def start_typing(self):
        """Démarre l'indicateur de frappe."""
        self._typing = TypingIndicator()
        self._insert_widget(self._typing)
        self.scroll_requested.emit()

    def reset(self):
        """Réinitialise l'état du handler."""
        self._cur_assistant = None
        self._typing = None
        self._tool_bubble = None
        self._tools_called = []
        self._tool_icons = {}

    @property
    def typing_indicator(self) -> Optional[TypingIndicator]:
        """Retourne l'indicateur de frappe actuel."""
        return self._typing

    @property
    def current_assistant(self) -> Optional[MessageWidget]:
        """Retourne le widget assistant actuel."""
        return self._cur_assistant
