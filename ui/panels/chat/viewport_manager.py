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
viewport_manager.py — Virtualisation des MessageWidget dans un QScrollArea
"""
from PyQt6.QtCore import QTimer


class ViewportManager:
    """
    Gère la virtualisation des MessageWidget dans un QScrollArea.

    Principe
    ────────
    Seuls les widgets dans la zone visible + un buffer vertical sont maintenus
    ATTACHÉS (renderer WebEngine actif). Les widgets hors de cette zone sont
    DÉTACHÉS (renderer suspendu via LifecycleState.Discarded).

    Avec une fenêtre de 800px, des messages de ~150px et un buffer de 1×
    la hauteur du viewport, environ 16 WebViews sont actifs simultanément
    quel que soit le nombre total de messages.

    Stabilité du scroll (scroll anchor)
    ─────────────────────────────────────
    Quand un widget est attaché, le renderer WebEngine recharge le HTML et
    met à jour sa hauteur en trois passes asynchrones (0 ms, 350 ms, 700 ms).
    Chaque mise à jour de hauteur déclenche un recalcul du layout Qt, qui
    déplace la scrollbar — ce qui provoque des sauts visibles lors du scroll
    vers le haut.

    Pour éviter cela, le manager identifie un widget d'ancrage avant chaque
    passe de synchronisation : le premier widget partiellement ou totalement
    visible en haut du viewport. La position de scroll est ensuite maintenue
    relativement à ce widget (distance entre le haut du viewport et le haut
    du widget d'ancrage) pendant toute la durée de vie des timers de hauteur.

    L'ancre est libérée dès que plus aucun widget n'est en cours d'attachement,
    ou après une fenêtre de 900 ms (durée des trois passes de hauteur).

    Intégration
    ───────────
    ViewportManager s'abonne au signal valueChanged de la scrollbar verticale
    et planifie une passe de synchronisation via un QTimer debounce (200 ms).
    Cela évite de déclencher des attach/detach à chaque pixel de scroll.

    La passe est également déclenchée manuellement après l'ajout d'un widget
    (add_widget) pour s'assurer que les nouveaux messages sont correctement
    attachés s'ils sont dans la zone visible.

    Parameters
    ----------
    scroll_area : QScrollArea
        La zone de scroll contenant les messages.
    msgs_layout : QVBoxLayout
        Le layout vertical dans lequel les MessageWidget sont insérés.
    buffer_factor : float
        Multiplicateur de la hauteur du viewport pour définir le buffer.
        1.0 = buffer de 1× la hauteur du viewport au-dessus et en-dessous.
        Défaut : 1.0 (bon compromis mémoire/fluidité).
    """

    def __init__(self, scroll_area, msgs_layout, buffer_factor: float = 1.0):
        self._scroll      = scroll_area
        self._layout      = msgs_layout
        self._buffer      = buffer_factor

        # Timer debounce : regroupe les événements scroll rapprochés
        self._sync_timer  = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(200)  # ms
        self._sync_timer.timeout.connect(self._sync)

        # ── Scroll anchor ──────────────────────────────────────────────
        # Widget d'ancrage : premier widget visible en haut du viewport.
        # _anchor_offset : distance (pixels) entre le haut du viewport
        # et le haut du widget d'ancrage au moment où l'ancre est posée.
        self._anchor_widget = None
        self._anchor_offset = 0          # viewport_top - widget_top

        # Timer de relâchement de l'ancre : libère l'ancre 900 ms après
        # le dernier attach(), soit après la 3e passe de hauteur (700 ms)
        # plus une marge de sécurité (200 ms).
        self._anchor_release_timer = QTimer()
        self._anchor_release_timer.setSingleShot(True)
        self._anchor_release_timer.setInterval(900)
        self._anchor_release_timer.timeout.connect(self._release_anchor)

        # Connecter la scrollbar pour mettre à jour l'ancre pendant le scroll
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Connecter le recalcul de layout pour restaurer la position d'ancrage
        # quand Qt redimensionne les widgets après les mises à jour de hauteur.
        # resized() n'existe pas sur QScrollArea — on passe par un QTimer court
        # déclenché depuis _on_height_changed (abonnement aux widgets attachés).
        self._restore_timer = QTimer()
        self._restore_timer.setSingleShot(True)
        self._restore_timer.setInterval(0)    # cycle suivant
        self._restore_timer.timeout.connect(self._restore_anchor)

    # ── API publique ──────────────────────────────────────────────────

    def add_widget(self, widget):
        """
        Notifie le manager qu'un nouveau widget vient d'être ajouté.

        Déclenche une passe de synchronisation immédiate (sans debounce)
        car le widget est probablement dans la zone visible — notamment
        lors du streaming où les messages arrivent en bas de la liste.
        """
        QTimer.singleShot(0, self._sync)

    def sync_now(self):
        """Force une passe de synchronisation immédiate (sans debounce)."""
        self._sync_timer.stop()
        self._sync()

    def cleanup(self):
        """Arrête les timers et détache tous les widgets."""
        self._sync_timer.stop()
        self._anchor_release_timer.stop()
        self._restore_timer.stop()
        self._scroll.verticalScrollBar().valueChanged.disconnect(self._on_scroll)
        for w in self._iter_message_widgets():
            if not w.is_attached:
                w.attach()

    # ── Scroll handler ────────────────────────────────────────────────

    def _on_scroll(self, value: int):
        """
        Réponse au scroll : démarre/redémarre le debounce timer.
        Met aussi à jour l'offset d'ancrage si une ancre est active,
        pour que l'ancre suive le scroll manuel de l'utilisateur.
        """
        # Si l'ancre est active et que le scroll vient de l'utilisateur
        # (et non de _restore_anchor), recalculer l'offset.
        if self._anchor_widget is not None and not self._restore_timer.isActive():
            self._update_anchor_offset()

        self._sync_timer.start()   # restart si déjà actif

    # ── Scroll anchor ─────────────────────────────────────────────────

    def _find_anchor(self):
        """
        Identifie le widget d'ancrage : le premier MessageWidget dont
        le bas est visible dans le viewport (partiellement ou totalement).

        Retourne (widget, offset) où offset = viewport_top - widget_top,
        ou (None, 0) si aucun widget n'est trouvé.
        """
        sb           = self._scroll.verticalScrollBar()
        viewport_top = sb.value()
        container    = self._scroll.widget()

        for w in self._iter_message_widgets():
            pos = w.mapTo(container, w.rect().topLeft())
            w_top    = pos.y()
            w_bottom = w_top + w.height()
            if w_bottom > viewport_top:
                # Ce widget est le premier partiellement visible
                return w, viewport_top - w_top

        return None, 0

    def _set_anchor(self):
        """Pose l'ancre sur le widget actuellement visible en haut."""
        widget, offset = self._find_anchor()
        if widget is not None:
            self._anchor_widget = widget
            self._anchor_offset = offset

    def _update_anchor_offset(self):
        """Recalcule l'offset de l'ancre sans changer le widget d'ancrage."""
        if self._anchor_widget is None:
            return
        sb           = self._scroll.verticalScrollBar()
        viewport_top = sb.value()
        container    = self._scroll.widget()
        try:
            pos   = self._anchor_widget.mapTo(container, self._anchor_widget.rect().topLeft())
            self._anchor_offset = viewport_top - pos.y()
        except RuntimeError:
            self._anchor_widget = None

    def _restore_anchor(self):
        """
        Restaure la position de scroll pour maintenir le widget d'ancrage
        à la même position relative dans le viewport.

        Appelé après chaque recalcul de layout (via _restore_timer) pendant
        que des widgets sont en cours d'attachement.
        """
        if self._anchor_widget is None:
            return

        container = self._scroll.widget()
        sb        = self._scroll.verticalScrollBar()

        try:
            pos = self._anchor_widget.mapTo(container, self._anchor_widget.rect().topLeft())
            target = pos.y() + self._anchor_offset
            target = max(0, min(target, sb.maximum()))
            if abs(sb.value() - target) > 2:   # seuil : ne corriger que si décalage > 2 px
                sb.setValue(target)
        except RuntimeError:
            # Widget détruit entre-temps
            self._anchor_widget = None

    def _release_anchor(self):
        """Libère l'ancre de scroll."""
        self._anchor_widget = None
        self._anchor_offset = 0

    def _schedule_restore(self):
        """Planifie une restauration d'ancrage au prochain cycle d'événements."""
        if self._anchor_widget is not None:
            self._restore_timer.start()

    # ── Passe de synchronisation ──────────────────────────────────────

    def _sync(self):
        """
        Parcourt tous les MessageWidget et ajuste leur état attaché/détaché.

        Avant d'attacher des widgets, pose une ancre de scroll pour
        stabiliser la position après les mises à jour de hauteur asynchrones.

        Calcul de la zone active
        ────────────────────────
        viewport_top    = position actuelle de la scrollbar
        viewport_bottom = viewport_top + hauteur visible
        buffer          = viewport_height × buffer_factor

        zone_active = [viewport_top - buffer, viewport_bottom + buffer]

        Un widget dont le rectangle intersecte zone_active est attaché ;
        les autres sont détachés.
        """
        sb              = self._scroll.verticalScrollBar()
        viewport_top    = sb.value()
        viewport_height = self._scroll.viewport().height()
        viewport_bottom = viewport_top + viewport_height
        buffer          = int(viewport_height * self._buffer)

        zone_top    = viewport_top    - buffer
        zone_bottom = viewport_bottom + buffer

        container = self._scroll.widget()

        # Identifier si des attachements vont se produire
        # pour poser l'ancre avant de modifier le layout.
        will_attach = False
        for w in self._iter_message_widgets():
            pos_in_container = w.mapTo(container, w.rect().topLeft())
            w_top    = pos_in_container.y()
            w_bottom = w_top + w.height()
            in_zone  = w_bottom > zone_top and w_top < zone_bottom
            if in_zone and not w.is_attached:
                will_attach = True
                break

        # Poser l'ancre avant tout attachement, uniquement si on remonte
        # dans la conversation (viewport_top > 0 : pas en bas de liste).
        # En bas (scroll_to_bottom), on ne veut pas d'ancre — le comportement
        # normal est de rester collé au bas.
        at_bottom = sb.value() >= sb.maximum() - 4
        if will_attach and not at_bottom:
            if self._anchor_widget is None:
                self._set_anchor()
            # Prolonger la fenêtre de protection
            self._anchor_release_timer.start()

        # Passe d'attach/detach
        for w in self._iter_message_widgets():
            pos_in_container = w.mapTo(container, w.rect().topLeft())
            w_top    = pos_in_container.y()
            w_bottom = w_top + w.height()
            in_zone  = w_bottom > zone_top and w_top < zone_bottom

            if in_zone and not w.is_attached:
                w.attach()
                # Abonner aux mises à jour de hauteur de ce widget
                # pour déclencher la restauration d'ancrage.
                self._connect_height_signal(w)
            elif not in_zone and w.is_attached:
                w.detach()

    # ── Connexion aux signaux de hauteur des widgets ──────────────────

    def _connect_height_signal(self, widget):
        """
        Abonne le manager aux mises à jour de géométrie du widget
        pour déclencher _schedule_restore() après chaque changement de hauteur.

        Utilise resizeEvent via un filtre d'événement léger plutôt qu'un
        signal custom pour éviter de modifier MessageWidget.
        """
        # Éviter les connexions multiples sur le même widget
        if getattr(widget, '_viewport_mgr_connected', False):
            return
        widget._viewport_mgr_connected = True

        # QWidget.geometryChanged n'existe pas en PyQt6.
        # On installe un event filter minimal qui détecte QEvent::Resize.
        from PyQt6.QtCore import QObject, QEvent

        class _HeightWatcher(QObject):
            def __init__(self_, parent_widget, schedule_fn):
                super().__init__(parent_widget)
                self_._schedule = schedule_fn

            def eventFilter(self_, obj, event):
                if event.type() == QEvent.Type.Resize:
                    self_._schedule()
                return False

        watcher = _HeightWatcher(widget, self._schedule_restore)
        widget.installEventFilter(watcher)
        # Stocker le watcher pour éviter le GC
        widget._viewport_height_watcher = watcher

    # ── Itérateur interne ─────────────────────────────────────────────

    def _iter_message_widgets(self):
        """
        Itère sur les MessageWidget présents dans le layout.
        """
        from ui.widgets.message_widget import MessageWidget
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item:
                w = item.widget()
                if isinstance(w, MessageWidget):
                    yield w
