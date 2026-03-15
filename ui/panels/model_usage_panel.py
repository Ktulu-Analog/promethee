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
model_usage_panel.py — Consommation de tokens par modèle en temps réel
=======================================================================

Affiche pour chaque modèle LLM effectivement utilisé dans la session :
  - Tokens prompt cumulés
  - Tokens completion cumulés
  - Total tokens
  - Nombre d'appels
  - Barre de proportion relative (visuelle)

Principe de collecte :
  Le panneau écoute deux signaux émis par chaque ChatPanel :
    • family_routing_changed — indique quel modèle est actif pour le tour
      en cours (famille → modèle). Quand family=="" le modèle principal
      reprend la main.
    • token_usage_updated    — émis à chaque mise à jour de TokenUsage.
      La delta completion est attribuée au modèle actif au moment de
      l'émission. Le prompt est toujours attribué au modèle principal
      (c'est lui qui lit le contexte).

Intégration dans MainWindow :
    panel = ModelUsagePanel()
    chat_panel.token_usage_updated.connect(panel.on_usage_updated)
    chat_panel.family_routing_changed.connect(panel.on_family_routing)
    # Bouton de toggle identique aux autres panneaux latéraux
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from ui.widgets.styles import ThemeManager


# ── Structure de données ──────────────────────────────────────────────────────

@dataclass
class ModelStats:
    """Statistiques cumulées pour un modèle LLM."""
    model:      str
    label:      str   = ""      # label UI (nom de famille ou "Principal")
    backend:    str   = ""      # "openai" | "ollama" | ""
    prompt:     int   = 0
    completion: int   = 0
    calls:      int   = 0

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    def label_display(self) -> str:
        return self.label or self.model

    def backend_icon(self) -> str:
        if self.backend == "ollama":
            return "💻"
        if self.backend == "openai":
            return "🌐"
        return "🔵"


# ── Widget ligne par modèle ───────────────────────────────────────────────────

class _ModelRow(QWidget):
    """Ligne d'affichage pour un modèle : label + compteurs + barre."""

    def __init__(self, stats: ModelStats, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._stats = stats
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(3)

        t = ThemeManager.inline

        # ── Ligne 1 : icône + label + total tokens ────────────────────────
        top = QHBoxLayout()
        top.setSpacing(4)

        icon_lbl = QLabel(self._stats.backend_icon())
        icon_lbl.setFixedWidth(16)
        icon_lbl.setStyleSheet(f"color: {t('text_primary')}; font-size: 12px;")
        top.addWidget(icon_lbl)

        name_lbl = QLabel(self._stats.label_display())
        name_lbl.setStyleSheet(
            f"color: {t('text_primary')}; font-size: 11px; font-weight: 600;"
        )
        name_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        top.addWidget(name_lbl)

        self._total_lbl = QLabel(self._fmt(self._stats.total))
        self._total_lbl.setStyleSheet(
            f"color: {t('text_primary')}; font-size: 11px; font-weight: 600;"
        )
        top.addWidget(self._total_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        root.addLayout(top)

        # ── Ligne 2 : modèle (nom technique, plus petit) ─────────────────
        model_lbl = QLabel(self._stats.model)
        model_lbl.setStyleSheet(
            f"color: {t('text_muted')}; font-size: 9px; font-style: italic;"
        )
        model_lbl.setWordWrap(True)
        root.addWidget(model_lbl)

        # ── Ligne 3 : prompt / completion / appels ────────────────────────
        detail = QHBoxLayout()
        detail.setSpacing(8)

        self._prompt_lbl = QLabel(f"↑ {self._fmt(self._stats.prompt)}")
        self._prompt_lbl.setStyleSheet(
            f"color: {t('text_secondary')}; font-size: 10px;"
        )
        detail.addWidget(self._prompt_lbl)

        self._compl_lbl = QLabel(f"↓ {self._fmt(self._stats.completion)}")
        self._compl_lbl.setStyleSheet(
            f"color: {t('text_secondary')}; font-size: 10px;"
        )
        detail.addWidget(self._compl_lbl)

        detail.addStretch()

        self._calls_lbl = QLabel(
            f"{self._stats.calls} appel{'s' if self._stats.calls != 1 else ''}"
        )
        self._calls_lbl.setStyleSheet(
            f"color: {t('text_muted')}; font-size: 10px;"
        )
        detail.addWidget(self._calls_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        root.addLayout(detail)

        # ── Ligne 4 : barre de proportion ─────────────────────────────────
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(4)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(self._bar_style())
        root.addWidget(self._bar)

        # ── Séparateur fin ────────────────────────────────────────────────
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(
            f"background-color: {ThemeManager.inline('divider_bg')};"
        )
        root.addWidget(div)

    # ── Mise à jour ───────────────────────────────────────────────────────

    def refresh(self, pct: int = 0) -> None:
        """Met à jour tous les labels depuis self._stats."""
        t = ThemeManager.inline
        self._total_lbl.setText(self._fmt(self._stats.total))
        self._prompt_lbl.setText(f"↑ {self._fmt(self._stats.prompt)}")
        self._compl_lbl.setText(f"↓ {self._fmt(self._stats.completion)}")
        self._calls_lbl.setText(
            f"{self._stats.calls} appel{'s' if self._stats.calls != 1 else ''}"
        )
        self._bar.setValue(pct)
        self._bar.setStyleSheet(self._bar_style())

    def refresh_theme(self) -> None:
        self._bar.setStyleSheet(self._bar_style())

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k"
        return str(n)

    def _bar_style(self) -> str:
        t = ThemeManager.inline
        return (
            f"QProgressBar {{ background: {t('elevated_bg')}; "
            f"border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {t('accent')}; "
            f"border-radius: 2px; }}"
        )


# ── Panneau principal ─────────────────────────────────────────────────────────

class ModelUsagePanel(QWidget):
    """
    Panneau latéral affichant la consommation de tokens par modèle LLM.

    Alimenté par :
      on_usage_updated(TokenUsage)      — signal token_usage_updated de ChatPanel
      on_family_routing(dict)           — signal family_routing_changed de ChatPanel
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(320)

        # Registre : model_name → ModelStats
        self._models: dict[str, ModelStats] = {}
        # Mapping famille → (label, backend) pour enrichir les stats
        self._family_info: dict[str, tuple[str, str]] = {}

        self._build_ui()

    # ── Construction UI ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        t = ThemeManager.inline
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(6)

        # ── En-tête ───────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Consommation par modèle")
        title.setStyleSheet(
            f"color: {t('text_primary')}; font-size: 12px; font-weight: 700;"
        )
        header.addWidget(title)
        header.addStretch()

        self._reset_btn = QPushButton("↺")
        self._reset_btn.setFixedSize(22, 22)
        self._reset_btn.setToolTip("Réinitialiser les compteurs")
        self._reset_btn.setStyleSheet(
            f"QPushButton {{ color: {t('text_muted')}; background: transparent; "
            f"border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {t('text_primary')}; }}"
        )
        self._reset_btn.clicked.connect(self._on_reset)
        header.addWidget(self._reset_btn)
        root.addLayout(header)

        # ── Indicateur modèle actif ────────────────────────────────────────
        self._active_lbl = QLabel("Modèle actif : principal")
        self._active_lbl.setStyleSheet(
            f"color: {t('text_muted')}; font-size: 10px; font-style: italic;"
        )
        self._active_lbl.setWordWrap(True)
        root.addWidget(self._active_lbl)

        # ── Séparateur ────────────────────────────────────────────────────
        self._div_top = QWidget()
        self._div_top.setFixedHeight(1)
        self._div_top.setStyleSheet(f"background-color: {t('divider_bg')};")
        root.addWidget(self._div_top)

        # ── Zone scrollable des lignes par modèle ─────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ background: {t('input_border')}; "
            f"width: 5px; border-radius: 2px; }}"
            f"QScrollBar::handle:vertical {{ background: {t('model_badge_color')}; "
            f"border-radius: 2px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical "
            f"{{ height: 0; }}"
        )

        self._rows_widget = QWidget()
        self._rows_widget.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch()

        scroll.setWidget(self._rows_widget)
        root.addWidget(scroll, stretch=1)

        # ── Total session ─────────────────────────────────────────────────
        self._div_bot = QWidget()
        self._div_bot.setFixedHeight(1)
        self._div_bot.setStyleSheet(f"background-color: {t('divider_bg')};")
        root.addWidget(self._div_bot)

        totals_row = QHBoxLayout()
        totals_lbl = QLabel("Total session")
        totals_lbl.setStyleSheet(
            f"color: {t('text_secondary')}; font-size: 10px;"
        )
        totals_row.addWidget(totals_lbl)
        totals_row.addStretch()

        self._total_session_lbl = QLabel("0")
        self._total_session_lbl.setStyleSheet(
            f"color: {t('text_primary')}; font-size: 11px; font-weight: 600;"
        )
        totals_row.addWidget(
            self._total_session_lbl, alignment=Qt.AlignmentFlag.AlignRight
        )
        root.addLayout(totals_row)

    # ── Slots publics ─────────────────────────────────────────────────────

    def on_family_routing(self, info: dict) -> None:
        """
        Mémorise le label et le backend associés à un modèle de famille.
        Utilisé uniquement pour enrichir l'affichage — l'attribution des
        tokens se fait via on_model_usage.
        """
        family  = info.get("family", "")
        model   = info.get("model",  "")
        label   = info.get("label",  "")
        backend = info.get("backend","")

        if family and model:
            self._family_info[model] = (label or family, backend)

        # Mettre à jour l'indicateur du modèle actif
        if family and model:
            self._active_lbl.setText(f"Actif : {label or family} · {model}")
            self._active_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('logo_color')}; "
                "font-size: 10px; font-style: italic;"
            )
        else:
            self._active_lbl.setText("Modèle actif : principal")
            self._active_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('text_muted')}; "
                "font-size: 10px; font-style: italic;"
            )

    def on_model_usage(self, info: dict) -> None:
        """
        Reçoit un événement de consommation émis directement par agent_loop.

        info = { "model": str,       # nom exact du modèle utilisé
                 "prompt": int,      # tokens prompt de cet appel
                 "completion": int,  # tokens completion de cet appel
                 "role": str }       # "decision" | "final" | "stream"

        Attribution :
          - role "decision" : modèle principal lit le contexte et décide.
            → prompt attribué à ce modèle, completion ignorée (déjà dans "final").
          - role "final" / "stream" : modèle de famille (ou principal) rédige.
            → completion attribuée à ce modèle.
        """
        model      = info.get("model", "") or Config.active_model()
        prompt     = info.get("prompt",     0) or 0
        completion = info.get("completion", 0) or 0
        role       = info.get("role", "decision")

        # Résoudre label et backend depuis les infos de famille mémorisées
        label, backend = self._family_info.get(model, ("", ""))
        if not label:
            if model == Config.active_model():
                label   = "Principal"
                backend = "ollama" if Config.LOCAL else "openai"
            else:
                label   = model
                backend = ""

        # Créer l'entrée si nécessaire
        if model not in self._models:
            self._models[model] = ModelStats(
                model=model, label=label, backend=backend
            )
        else:
            # Mettre à jour label/backend si enrichis depuis family_routing
            if label and not self._models[model].label:
                self._models[model].label   = label
                self._models[model].backend = backend

        stats = self._models[model]

        if role == "decision":
            # Prompt uniquement — c'est le coût de lecture du contexte
            stats.prompt += prompt
            stats.calls  += 1
        elif role in ("final", "stream"):
            # Completion — c'est le coût de rédaction de la réponse
            # Le prompt du stream est aussi attribué (appel LLM distinct)
            stats.prompt     += prompt
            stats.completion += completion
            if role == "stream":
                stats.calls += 1

        self._rebuild_rows()

    def on_usage_updated(self, usage) -> None:
        """
        Conservé pour compatibilité avec main_window (signal token_usage_updated).
        Ignoré — la collecte se fait désormais via on_model_usage.
        """
        pass

    # ── Construction dynamique des lignes ─────────────────────────────────

    def _rebuild_rows(self) -> None:
        """Recrée les lignes depuis self._models, triées par total décroissant."""
        # Vider
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._models:
            self._rows_layout.addStretch()
            self._total_session_lbl.setText("0")
            return

        # Tri : modèle principal en premier, puis par total décroissant
        principal = Config.active_model()
        sorted_models = sorted(
            self._models.values(),
            key=lambda s: (0 if s.model == principal else 1, -s.total),
        )

        grand_total = sum(s.total for s in self._models.values())
        self._total_session_lbl.setText(self._fmt_total(grand_total))

        for stats in sorted_models:
            pct = int(stats.total * 100 / grand_total) if grand_total > 0 else 0
            row = _ModelRow(stats, parent=self._rows_widget)
            row.refresh(pct)
            self._rows_layout.addWidget(row)

        self._rows_layout.addStretch()

    # ── Reset ─────────────────────────────────────────────────────────────

    def _on_reset(self) -> None:
        self._models.clear()
        self._family_info.clear()
        self._active_lbl.setText("Modèle actif : principal")
        self._active_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('text_muted')}; "
            "font-size: 10px; font-style: italic;"
        )
        self._rebuild_rows()

    # ── Thème ─────────────────────────────────────────────────────────────

    def refresh_theme(self) -> None:
        t = ThemeManager.inline
        self._div_top.setStyleSheet(f"background-color: {t('divider_bg')};")
        self._div_bot.setStyleSheet(f"background-color: {t('divider_bg')};")
        # Reconstruire les lignes avec les nouvelles couleurs
        self._rebuild_rows()

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_total(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.2f}M tok"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k tok"
        return f"{n} tok"
