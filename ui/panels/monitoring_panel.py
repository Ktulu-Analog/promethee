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
monitoring_panel.py — Tableau de bord de consommation (tokens, coût, carbone)

Affiche en temps réel et par conversation :
  - Tokens prompt / completion / total
  - Coût cumulé en euros (API Albert / OpenAI)
  - Empreinte carbone : kgCO₂eq et kWh (données API Albert)
  - Nombre d'appels LLM
  - Jauge de remplissage de la fenêtre de contexte
  - Historique graphique de la session (sparkline)

Intégration dans MainWindow :
  - Alimenté par le signal token_usage_updated émis par chaque ChatPanel
  - Méthode set_conversation(conv_id, title) pour lier l'onglet actif
  - refresh_theme() pour la propagation du thème

Usage :
    panel = MonitoringPanel()
    chat_panel.token_usage_updated.connect(panel.on_usage_updated)
    panel.set_conversation(conv_id, title)
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
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
from ui.widgets import SectionLabel
from ui.widgets.scroll_helper import make_transparent_scroll, make_divider
from ui.widgets.styles import ThemeManager


# ── Structures de données ─────────────────────────────────────────────────────

@dataclass
class ConvStats:
    """Statistiques cumulées pour une conversation."""
    conv_id:    str
    title:      str            = "Nouvelle conversation"
    prompt:     int            = 0
    completion: int            = 0
    calls:      int            = 0
    cost:       float          = 0.0
    co2_min:    float          = 0.0   # kg
    co2_max:    float          = 0.0   # kg
    kwh_min:    float          = 0.0
    kwh_max:    float          = 0.0
    # Historique de prompt_tokens pour la sparkline (max 60 points)
    history:    list[int]      = field(default_factory=list)
    last_ts:    float          = field(default_factory=time.time)

    # ── Statistiques de compression ───────────────────────────────────
    # Nombre d'opérations par type
    compress_ops:      dict    = field(default_factory=dict)   # {type: count}
    # Économie cumulée en caractères (avant - après) par type
    compress_saved:    dict    = field(default_factory=dict)   # {type: saved_chars}
    # Total caractères traités avant compression (toutes opérations)
    compress_total_in: int     = 0
    # Total caractères après compression (toutes opérations)
    compress_total_out: int    = 0
    # Journal des 8 dernières opérations (pour affichage)
    compress_log:      list    = field(default_factory=list)   # list[dict]

    def update(self, usage) -> None:
        """Intègre un objet TokenUsage dans les statistiques."""
        if usage is None:
            return
        p  = getattr(usage, "prompt",     0) or 0
        c  = getattr(usage, "completion", 0) or 0
        ca = getattr(usage, "calls",      0) or 0

        # On accumule calls (chaque objet usage représente le cumulé depuis le début
        # de la session agent ; on ne prend que le delta si calls > last_calls).
        # Ici on stocke simplement le maximum vu (calls est déjà cumulatif côté llm_service).
        self.calls  = max(self.calls,  ca)
        self.prompt = max(self.prompt, p)   # prompt = fenêtre actuelle (pas cumulée)
        self.completion += max(0, c - (self.completion))   # delta completion

        cost   = getattr(usage, "cost",   0.0) or 0.0
        self.cost = max(self.cost, cost)   # cost déjà cumulatif

        carbon = getattr(usage, "carbon", {}) or {}
        co2    = carbon.get("kgCO2eq", {})
        kwh    = carbon.get("kWh",     {})
        if co2:
            self.co2_min = max(self.co2_min, co2.get("min", 0.0))
            self.co2_max = max(self.co2_max, co2.get("max", 0.0))
        if kwh:
            self.kwh_min = max(self.kwh_min, kwh.get("min", 0.0))
            self.kwh_max = max(self.kwh_max, kwh.get("max", 0.0))

        # Sparkline : on enregistre le prompt courant (fenêtre contexte)
        self.history.append(p)
        if len(self.history) > 60:
            self.history = self.history[-60:]
        self.last_ts = time.time()

    def update_compression(self, stats: dict) -> None:
        """Intègre un dict de stats de compression {type, before, after, saved, pct}."""
        op_type = stats.get("type", "unknown")
        before  = stats.get("before", 0)
        after   = stats.get("after",  0)
        saved   = stats.get("saved",  0)
        pct     = stats.get("pct",    0.0)

        self.compress_ops[op_type]   = self.compress_ops.get(op_type, 0) + 1
        self.compress_saved[op_type] = self.compress_saved.get(op_type, 0) + saved
        self.compress_total_in  += before
        self.compress_total_out += after

        # Journal des 8 dernières opérations
        self.compress_log.append({
            "type":   op_type,
            "before": before,
            "after":  after,
            "saved":  saved,
            "pct":    pct,
            "ts":     time.time(),
        })
        if len(self.compress_log) > 8:
            self.compress_log = self.compress_log[-8:]
        self.last_ts = time.time()

    @property
    def compress_total_saved(self) -> int:
        return self.compress_total_in - self.compress_total_out

    @property
    def compress_total_pct(self) -> float:
        if self.compress_total_in <= 0:
            return 0.0
        return self.compress_total_saved / self.compress_total_in * 100

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    def pct(self) -> int:
        m = Config.CONTEXT_MODEL_MAX_TOKENS
        if m <= 0:
            return 0
        return min(100, self.prompt * 100 // m)


# ── Sparkline ─────────────────────────────────────────────────────────────────

class SparklineWidget(QWidget):
    """
    Mini graphique linéaire de l'historique de tokens (prompt_tokens par appel).
    Dessiné via QPainter, sans dépendance à matplotlib ou autre bibliothèque.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[int] = []
        self._model_max: int  = Config.CONTEXT_MODEL_MAX_TOKENS
        self.setMinimumHeight(44)
        self.setMaximumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, values: list[int], model_max: int = 0) -> None:
        self._data      = values[-60:]
        self._model_max = model_max or Config.CONTEXT_MODEL_MAX_TOKENS
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._data:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h   = self.width(), self.height()
        pad_x, pad_y = 4, 6

        # Fond
        bg = QColor(ThemeManager.inline("elevated_bg"))
        p.fillRect(0, 0, w, h, bg)

        # Ligne de seuil 80 %
        if self._model_max > 0:
            y_thresh = pad_y + (h - 2 * pad_y) * (1 - 0.80)
            pen = QPen(QColor(ThemeManager.inline("eco_warn_color")))
            pen.setWidth(1)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(pad_x, int(y_thresh), w - pad_x, int(y_thresh))

        # Courbe
        vals = self._data
        n    = len(vals)
        vmax = max(self._model_max, max(vals) or 1)

        xs = [pad_x + i * (w - 2 * pad_x) / max(n - 1, 1) for i in range(n)]
        ys = [pad_y + (h - 2 * pad_y) * (1 - v / vmax)    for v in vals]

        # Aire de remplissage (dégradé simulé par opacité)
        fill_path = QPainterPath()
        fill_path.moveTo(xs[0], h - pad_y)
        for x, y in zip(xs, ys):
            fill_path.lineTo(x, y)
        fill_path.lineTo(xs[-1], h - pad_y)
        fill_path.closeSubpath()

        last_pct = vals[-1] / vmax if vmax > 0 else 0
        if last_pct >= 0.80:
            fill_color = QColor(ThemeManager.inline("eco_warn_color"))
        else:
            fill_color = QColor(ThemeManager.inline("accent"))
        fill_color.setAlpha(38)
        p.fillPath(fill_path, fill_color)

        # Trait principal
        line_color = QColor(
            ThemeManager.inline("eco_warn_color") if last_pct >= 0.80
            else ThemeManager.inline("accent")
        )
        pen = QPen(line_color, 1.6)
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:]):
            path.lineTo(x, y)
        p.drawPath(path)

        # Point terminal
        p.setBrush(line_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(xs[-1]) - 3, int(ys[-1]) - 3, 6, 6)

        p.end()


# ── Carte de stat ─────────────────────────────────────────────────────────────

class StatCard(QWidget):
    """
    Petite carte affichant une valeur métrique avec icône et libellé.
    Utilisée pour tokens, coût, CO₂, etc.
    """

    def __init__(self, icon: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui(icon, label)

    def _build_ui(self, icon: str, label: str) -> None:
        self.setObjectName("stat_card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)
        ico = QLabel(icon)
        ico.setStyleSheet("font-size: 15px; border: none;")
        ico.setFixedWidth(22)
        top.addWidget(ico)
        lbl = QLabel(label)
        lbl.setObjectName("stat_card_label")
        lbl.setStyleSheet(
            f"color: {ThemeManager.inline('text_muted')}; font-size: 10px; border: none;"
        )
        top.addWidget(lbl, stretch=1)
        layout.addLayout(top)

        self._value_lbl = QLabel("—")
        self._value_lbl.setObjectName("stat_card_value")
        self._value_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('text_primary')}; "
            "font-size: 13px; font-weight: 700; border: none;"
        )
        layout.addWidget(self._value_lbl)

        self._apply_card_style()

    def _apply_card_style(self) -> None:
        bg     = ThemeManager.inline("elevated_bg")
        border = ThemeManager.inline("border")
        self.setStyleSheet(
            f"QWidget#stat_card {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 8px; }}"
            f"QWidget#stat_card * {{ background: transparent; border: none; }}"
        )

    def set_value(self, text: str, color: str | None = None) -> None:
        self._value_lbl.setText(text)
        c = color or ThemeManager.inline("text_primary")
        self._value_lbl.setStyleSheet(
            f"color: {c}; font-size: 13px; font-weight: 700; border: none;"
        )

    def refresh_theme(self) -> None:
        self._apply_card_style()
        self._value_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('text_primary')}; "
            "font-size: 13px; font-weight: 700; border: none;"
        )
        for lbl in self.findChildren(QLabel, "stat_card_label"):
            lbl.setStyleSheet(
                f"color: {ThemeManager.inline('text_muted')}; font-size: 10px; border: none;"
            )


# ── Panneau principal ─────────────────────────────────────────────────────────

class MonitoringPanel(QWidget):
    """
    Panneau latéral de monitoring : tokens, coût, carbone, sparkline.

    Signaux
    -------
    reset_requested(conv_id) : demande de remise à zéro des stats d'une conversation.
    """

    reset_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rag_panel")   # hérite du style panneau existant
        self.setMinimumWidth(240)
        self.setMaximumWidth(340)

        # Données : conv_id → ConvStats
        self._stats:    dict[str, ConvStats] = {}
        self._conv_id:  str | None           = None
        self._conv_title: str                = "—"

        # Totaux session (toutes conversations confondues)
        self._session_cost:   float = 0.0
        self._session_co2:    float = 0.0   # kg max
        self._session_kwh:    float = 0.0   # kWh max
        self._session_calls:  int   = 0

        self._setup_ui()

        # Timer de rafraîchissement de l'horodatage "dernier appel"
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)   # 30 s
        self._timer.timeout.connect(self._refresh_last_seen)
        self._timer.start()

    # ── Construction UI ───────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(10)

        # ── En-tête ──────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("📊"))
        title = QLabel("Monitoring")
        title.setObjectName("rag_title")
        hdr.addWidget(title)
        hdr.addStretch()
        self._reset_btn = QPushButton("↺")
        self._reset_btn.setObjectName("tool_btn")
        self._reset_btn.setFixedSize(28, 28)
        self._reset_btn.setToolTip("Remettre à zéro les stats de cette conversation")
        self._reset_btn.setStyleSheet("font-size: 15px;")
        self._reset_btn.clicked.connect(self._on_reset)
        hdr.addWidget(self._reset_btn)
        layout.addLayout(hdr)

        # ── Conversation active ───────────────────────────────────────
        self._conv_lbl = QLabel("Aucune conversation")
        self._conv_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('rag_info_color')}; font-size: 11px;"
        )
        self._conv_lbl.setWordWrap(True)
        layout.addWidget(self._conv_lbl)

        self._div0 = make_divider()
        layout.addWidget(self._div0)

        # ── Section : conversation courante ───────────────────────────
        layout.addWidget(SectionLabel("💬 Cette conversation"))

        # Grille 2×2 de stat cards
        grid1 = QHBoxLayout()
        grid1.setSpacing(6)
        self._card_prompt     = StatCard("⬆️", "Prompt tokens")
        self._card_completion = StatCard("⬇️", "Completion tokens")
        grid1.addWidget(self._card_prompt)
        grid1.addWidget(self._card_completion)
        layout.addLayout(grid1)

        grid2 = QHBoxLayout()
        grid2.setSpacing(6)
        self._card_calls  = StatCard("🔁", "Appels LLM")
        self._card_cost   = StatCard("💶", "Coût")
        grid2.addWidget(self._card_calls)
        grid2.addWidget(self._card_cost)
        layout.addLayout(grid2)

        # ── Jauge contexte ───────────────────────────────────────────
        ctx_row = QHBoxLayout()
        ctx_lbl = QLabel("Fenêtre de contexte")
        ctx_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('text_secondary')}; font-size: 11px;"
        )
        ctx_row.addWidget(ctx_lbl)
        self._ctx_pct_lbl = QLabel("0 %")
        self._ctx_pct_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('text_muted')}; font-size: 11px;"
        )
        ctx_row.addWidget(self._ctx_pct_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(ctx_row)

        self._ctx_bar = QProgressBar()
        self._ctx_bar.setRange(0, 100)
        self._ctx_bar.setValue(0)
        self._ctx_bar.setFixedHeight(7)
        self._ctx_bar.setTextVisible(False)
        self._ctx_bar.setStyleSheet(self._ctx_bar_style(0))
        layout.addWidget(self._ctx_bar)

        # ── Empreinte carbone ────────────────────────────────────────
        self._div1 = make_divider()
        layout.addWidget(self._div1)
        layout.addWidget(SectionLabel("🌿 Empreinte carbone"))

        grid3 = QHBoxLayout()
        grid3.setSpacing(6)
        self._card_co2 = StatCard("☁️", "CO₂ (kgCO₂eq)")
        self._card_kwh = StatCard("⚡", "Énergie (kWh)")
        grid3.addWidget(self._card_co2)
        grid3.addWidget(self._card_kwh)
        layout.addLayout(grid3)

        self._eco_hint = QLabel("Données disponibles uniquement\navec l'API Albert.")
        self._eco_hint.setStyleSheet(
            f"color: {ThemeManager.inline('text_disabled')}; font-size: 10px;"
        )
        self._eco_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._eco_hint)

        # ── Sparkline ────────────────────────────────────────────────
        self._div2 = make_divider()
        layout.addWidget(self._div2)
        layout.addWidget(SectionLabel("📈 Historique (prompt tokens)"))

        self._sparkline = SparklineWidget()
        layout.addWidget(self._sparkline)

        spark_legend = QHBoxLayout()
        spark_legend.setSpacing(4)
        dash_lbl = QLabel("— — seuil 80 %")
        dash_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('eco_warn_color')}; font-size: 10px;"
        )
        spark_legend.addStretch()
        spark_legend.addWidget(dash_lbl)
        layout.addLayout(spark_legend)

        # ── Section : optimisation contexte ──────────────────────────
        self._div_comp = make_divider()
        layout.addWidget(self._div_comp)
        layout.addWidget(SectionLabel("⚙️ Optimisation contexte"))

        grid_comp = QHBoxLayout()
        grid_comp.setSpacing(6)
        self._card_comp_ops   = StatCard("🗜️", "Opérations")
        self._card_comp_saved = StatCard("💾", "Car. économisés")
        grid_comp.addWidget(self._card_comp_ops)
        grid_comp.addWidget(self._card_comp_saved)
        layout.addLayout(grid_comp)

        # Barre de taux de compression global
        comp_row = QHBoxLayout()
        comp_lbl = QLabel("Taux de compression")
        comp_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('text_secondary')}; font-size: 11px;"
        )
        comp_row.addWidget(comp_lbl)
        self._comp_pct_lbl = QLabel("0 %")
        self._comp_pct_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('text_muted')}; font-size: 11px;"
        )
        comp_row.addWidget(self._comp_pct_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(comp_row)

        self._comp_bar = QProgressBar()
        self._comp_bar.setRange(0, 100)
        self._comp_bar.setValue(0)
        self._comp_bar.setFixedHeight(7)
        self._comp_bar.setTextVisible(False)
        self._comp_bar.setStyleSheet(self._comp_bar_style(0))
        layout.addWidget(self._comp_bar)

        # Journal des dernières opérations
        self._comp_log_widget = QWidget()
        self._comp_log_widget.setStyleSheet("background: transparent;")
        self._comp_log_layout = QVBoxLayout(self._comp_log_widget)
        self._comp_log_layout.setContentsMargins(0, 2, 0, 0)
        self._comp_log_layout.setSpacing(1)
        layout.addWidget(self._comp_log_widget)

        self._comp_hint = QLabel("Aucune compression effectuée.")
        self._comp_hint.setStyleSheet(
            f"color: {ThemeManager.inline('text_disabled')}; font-size: 10px;"
        )
        self._comp_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._comp_hint)

        # ── Section : session globale ─────────────────────────────────
        self._div3 = make_divider()
        layout.addWidget(self._div3)
        layout.addWidget(SectionLabel("🗂️ Totaux de la session"))

        scroll = make_transparent_scroll()

        self._session_widget = QWidget()
        self._session_widget.setStyleSheet("background: transparent;")
        self._session_layout = QVBoxLayout(self._session_widget)
        self._session_layout.setContentsMargins(0, 0, 4, 0)
        self._session_layout.setSpacing(4)

        grid4 = QHBoxLayout()
        grid4.setSpacing(6)
        self._card_sess_cost  = StatCard("💶", "Coût session")
        self._card_sess_co2   = StatCard("☁️", "CO₂ session")
        grid4.addWidget(self._card_sess_cost)
        grid4.addWidget(self._card_sess_co2)
        self._session_layout.addLayout(grid4)

        grid5 = QHBoxLayout()
        grid5.setSpacing(6)
        self._card_sess_calls = StatCard("🔁", "Appels session")
        self._card_sess_kwh   = StatCard("⚡", "Énergie session")
        grid5.addWidget(self._card_sess_calls)
        grid5.addWidget(self._card_sess_kwh)
        self._session_layout.addLayout(grid5)

        # Liste des conversations de la session
        self._conv_list_widget = QWidget()
        self._conv_list_widget.setStyleSheet("background: transparent;")
        self._conv_list_layout = QVBoxLayout(self._conv_list_widget)
        self._conv_list_layout.setContentsMargins(0, 4, 0, 0)
        self._conv_list_layout.setSpacing(2)
        self._session_layout.addWidget(self._conv_list_widget)
        self._session_layout.addStretch()

        scroll.setWidget(self._session_widget)
        layout.addWidget(scroll, stretch=1)

        # ── Pied de page ─────────────────────────────────────────────
        self._div4 = make_divider()
        layout.addWidget(self._div4)

        self._footer_lbl = QLabel("Données de la session courante uniquement.")
        self._footer_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('tools_panel_info')}; font-size: 10px;"
        )
        self._footer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer_lbl.setWordWrap(True)
        layout.addWidget(self._footer_lbl)

    # ── Alimentation en données ───────────────────────────────────────

    def set_conversation(self, conv_id: str, title: str = "") -> None:
        """Lie le panneau à la conversation active."""
        self._conv_id    = conv_id
        self._conv_title = title or conv_id[:8]
        self._conv_lbl.setText(f"Conversation : {self._conv_title}")

        # Crée les stats si inexistantes
        if conv_id not in self._stats:
            self._stats[conv_id] = ConvStats(conv_id=conv_id, title=self._conv_title)
        else:
            self._stats[conv_id].title = self._conv_title

        self._refresh_current()

    def on_usage_updated(self, usage) -> None:
        """
        Reçoit un objet TokenUsage depuis ChatPanel.token_usage_updated.
        Met à jour les stats de la conversation active puis rafraîchit l'UI.
        """
        if self._conv_id is None or usage is None:
            return

        # Initialiser les stats si nécessaire
        if self._conv_id not in self._stats:
            self._stats[self._conv_id] = ConvStats(
                conv_id=self._conv_id, title=self._conv_title
            )

        self._stats[self._conv_id].update(usage)
        self._recalculate_session()
        self._refresh_current()
        self._refresh_session()

    def on_compression_stats(self, stats: dict) -> None:
        """
        Reçoit un dict de stats de compression depuis AgentWorker.compression_stats.
        Met à jour les stats de la conversation active puis rafraîchit la section.
        """
        if self._conv_id is None or stats is None:
            return
        if self._conv_id not in self._stats:
            self._stats[self._conv_id] = ConvStats(
                conv_id=self._conv_id, title=self._conv_title
            )
        self._stats[self._conv_id].update_compression(stats)
        self._refresh_compression()

    def reset_conversation(self, conv_id: str | None = None) -> None:
        """Remet à zéro les stats d'une conversation (par défaut : la courante)."""
        cid = conv_id or self._conv_id
        if cid and cid in self._stats:
            title = self._stats[cid].title
            self._stats[cid] = ConvStats(conv_id=cid, title=title)
        self._recalculate_session()
        self._refresh_current()
        self._refresh_session()

    # ── Rafraîchissement UI ──────────────────────────────────────────

    def _refresh_current(self) -> None:
        """Met à jour les widgets de la section 'conversation courante'."""
        if self._conv_id is None or self._conv_id not in self._stats:
            self._clear_current()
            return

        s   = self._stats[self._conv_id]
        pct = s.pct()
        muted   = ThemeManager.inline("text_muted")
        accent  = ThemeManager.inline("accent")
        red     = ThemeManager.inline("stop_btn_color")
        eco     = ThemeManager.inline("eco_color")
        eco_w   = ThemeManager.inline("eco_warn_color")

        # Tokens
        self._card_prompt.set_value(
            f"{s.prompt:,}",
            red if pct >= 80 else (accent if pct >= 60 else None)
        )
        self._card_completion.set_value(f"{s.completion:,}")
        self._card_calls.set_value(str(s.calls) if s.calls else "—")

        # Coût
        if s.cost > 0:
            if s.cost < 0.001:
                cost_str = "< 0,001 €"
            else:
                cost_str = f"{s.cost:.4f} €"
            self._card_cost.set_value(cost_str)
        else:
            self._card_cost.set_value("—", muted)

        # Contexte
        self._ctx_bar.setValue(pct)
        self._ctx_bar.setStyleSheet(self._ctx_bar_style(pct))
        color = red if pct >= 80 else (accent if pct >= 60 else muted)
        self._ctx_pct_lbl.setText(f"{pct} %")
        self._ctx_pct_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")

        # Carbone
        has_carbon = s.co2_max > 0 or s.kwh_max > 0
        self._eco_hint.setVisible(not has_carbon)

        if s.co2_max > 0:
            co2_kg_min = s.co2_min
            co2_kg_max = s.co2_max
            if co2_kg_max < 0.000001:
                co2_str = "< 0,000001 kg"
            elif abs(co2_kg_max - co2_kg_min) < 0.0000001:
                co2_str = f"{co2_kg_max:.3f} kg"
            else:
                co2_str = f"{co2_kg_min:.3f}–{co2_kg_max:.3f} kg"
            self._card_co2.set_value(co2_str, eco_w if co2_kg_max > 0.0005 else eco)
        else:
            self._card_co2.set_value("—", muted)

        if s.kwh_max > 0:
            kwh_min = s.kwh_min
            kwh_max = s.kwh_max
            if kwh_max < 0.000001:
                kwh_str = "< 0,000001 kWh"
            elif abs(kwh_max - kwh_min) < 0.0000001:
                kwh_str = f"{kwh_max:.3f} kWh"
            else:
                kwh_str = f"{kwh_min:.3f}–{kwh_max:.3f} kWh"
            self._card_kwh.set_value(kwh_str, eco)
        else:
            self._card_kwh.set_value("—", muted)

        # Sparkline
        self._sparkline.set_data(s.history)

        # Section compression
        self._refresh_compression()

    def _clear_current(self) -> None:
        """Vide tous les widgets de la section courante."""
        muted = ThemeManager.inline("text_muted")
        for card in (
            self._card_prompt, self._card_completion,
            self._card_calls, self._card_cost,
            self._card_co2, self._card_kwh,
        ):
            card.set_value("—", muted)
        self._ctx_bar.setValue(0)
        self._ctx_pct_lbl.setText("0 %")
        self._sparkline.set_data([])
        self._eco_hint.setVisible(True)
        self._clear_compression()

    # Libellés courts pour chaque type d'opération
    _OP_LABELS = {
        "compress_tool":  "Compression outil",
        "truncate_code":  "Troncature code",
        "truncate_text":  "Troncature texte",
        "trim_msgs":      "Trim historique",
    }

    def _refresh_compression(self) -> None:
        """Met à jour la section 'Optimisation contexte'."""
        if self._conv_id is None or self._conv_id not in self._stats:
            self._clear_compression()
            return

        s    = self._stats[self._conv_id]
        muted  = ThemeManager.inline("text_muted")
        accent = ThemeManager.inline("accent")
        eco    = ThemeManager.inline("eco_color")

        total_ops = sum(s.compress_ops.values())
        if total_ops == 0:
            self._clear_compression()
            return

        self._comp_hint.setVisible(False)

        # Carte opérations
        self._card_comp_ops.set_value(str(total_ops))

        # Carte économie
        saved = s.compress_total_saved
        if saved >= 1_000_000:
            saved_str = f"{saved / 1_000_000:.1f} M"
        elif saved >= 1_000:
            saved_str = f"{saved / 1_000:.1f} k"
        else:
            saved_str = str(saved)
        self._card_comp_saved.set_value(saved_str, eco)

        # Barre taux global
        pct = int(s.compress_total_pct)
        self._comp_bar.setValue(pct)
        self._comp_bar.setStyleSheet(self._comp_bar_style(pct))
        self._comp_pct_lbl.setText(f"{pct} %")
        color = accent if pct >= 30 else muted
        self._comp_pct_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")

        # Dernière opération uniquement
        while self._comp_log_layout.count():
            item = self._comp_log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if s.compress_log:
            entry  = s.compress_log[-1]
            op_lbl = self._OP_LABELS.get(entry["type"], entry["type"])
            before = entry["before"]
            after  = entry["after"]
            ep     = int(entry["pct"])
            def _fmt(n):
                return f"{n/1000:.1f}k" if n >= 1000 else str(n)
            row = QHBoxLayout()
            row.setSpacing(4)
            type_lbl = QLabel(f"• {op_lbl}")
            type_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('text_secondary')}; font-size: 10px;"
            )
            type_lbl.setFixedWidth(115)
            row.addWidget(type_lbl)
            val_lbl = QLabel(f"{_fmt(before)} → {_fmt(after)} (-{ep}%)")
            val_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('text_muted')}; font-size: 10px;"
            )
            row.addWidget(val_lbl, stretch=1, alignment=Qt.AlignmentFlag.AlignRight)
            container = QWidget()
            container.setLayout(row)
            container.setStyleSheet("background: transparent;")
            self._comp_log_layout.addWidget(container)

    def _clear_compression(self) -> None:
        """Vide la section compression."""
        muted = ThemeManager.inline("text_muted")
        self._card_comp_ops.set_value("—", muted)
        self._card_comp_saved.set_value("—", muted)
        self._comp_bar.setValue(0)
        self._comp_pct_lbl.setText("0 %")
        self._comp_hint.setVisible(True)
        while self._comp_log_layout.count():
            item = self._comp_log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _refresh_session(self) -> None:
        """Met à jour les totaux de session et la liste des conversations."""
        muted = ThemeManager.inline("text_muted")
        eco   = ThemeManager.inline("eco_color")

        # Cartes totaux
        if self._session_cost > 0:
            self._card_sess_cost.set_value(
                f"< 0,001 €" if self._session_cost < 0.001 else f"{self._session_cost:.4f} €"
            )
        else:
            self._card_sess_cost.set_value("—", muted)

        self._card_sess_calls.set_value(
            str(self._session_calls) if self._session_calls else "—", muted
        )

        if self._session_co2 > 0:
            co2_kg = self._session_co2
            self._card_sess_co2.set_value(
                f"{co2_kg:.3f} kg" if co2_kg >= 0.000001 else "< 0,000001 kg", eco
            )
        else:
            self._card_sess_co2.set_value("—", muted)

        if self._session_kwh > 0:
            kwh = self._session_kwh
            self._card_sess_kwh.set_value(
                f"{kwh:.3f} kWh" if kwh >= 0.000001 else "< 0,000001 kWh", eco
            )
        else:
            self._card_sess_kwh.set_value("—", muted)

        # Liste des conversations
        # Vider et reconstruire
        while self._conv_list_layout.count():
            item = self._conv_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._stats:
            return

        header = QLabel("Conversations :")
        header.setStyleSheet(
            f"color: {ThemeManager.inline('text_secondary')}; font-size: 10px;"
        )
        self._conv_list_layout.addWidget(header)

        for cid, s in sorted(
            self._stats.items(), key=lambda kv: kv[1].last_ts, reverse=True
        ):
            row = QHBoxLayout()
            row.setSpacing(4)
            is_active = (cid == self._conv_id)

            title_lbl = QLabel(
                ("▶ " if is_active else "  ") + (s.title[:20] + "…" if len(s.title) > 20 else s.title)
            )
            title_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('text_primary' if is_active else 'text_secondary')};"
                f"font-size: 10px; {'font-weight: 700;' if is_active else ''}"
            )
            title_lbl.setFixedWidth(120)
            row.addWidget(title_lbl)

            tok_lbl = QLabel(f"{(s.prompt + s.completion):,} tok")
            tok_lbl.setStyleSheet(
                f"color: {ThemeManager.inline('text_muted')}; font-size: 10px;"
            )
            row.addWidget(tok_lbl, stretch=1, alignment=Qt.AlignmentFlag.AlignRight)

            container = QWidget()
            container.setLayout(row)
            container.setStyleSheet("background: transparent;")
            self._conv_list_layout.addWidget(container)

    def _refresh_last_seen(self) -> None:
        """Appelé par le timer périodique (30 s) — rien à rafraîchir pour l'instant."""
        pass

    # ── Calculs session ───────────────────────────────────────────────

    def _recalculate_session(self) -> None:
        """Recalcule les totaux de session depuis toutes les ConvStats."""
        self._session_cost  = sum(s.cost    for s in self._stats.values())
        self._session_co2   = sum(s.co2_max for s in self._stats.values())
        self._session_kwh   = sum(s.kwh_max for s in self._stats.values())
        self._session_calls = sum(s.calls   for s in self._stats.values())

    # ── Actions ──────────────────────────────────────────────────────

    def _on_reset(self) -> None:
        if self._conv_id:
            self.reset_conversation(self._conv_id)
            self.reset_requested.emit(self._conv_id)

    # ── Helpers UI ────────────────────────────────────────────────────

    @staticmethod
    def _ctx_bar_style(pct: int) -> str:
        if pct >= 80:
            color = ThemeManager.inline("stop_btn_color")
        elif pct >= 60:
            color = ThemeManager.inline("accent")
        else:
            color = ThemeManager.inline("eco_color")
        bg     = ThemeManager.inline("elevated_bg")
        border = ThemeManager.inline("border")
        return (
            f"QProgressBar {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )

    @staticmethod
    def _comp_bar_style(pct: int) -> str:
        """Style de la barre de taux de compression (vert dès ~10%)."""
        if pct >= 50:
            color = ThemeManager.inline("eco_color")
        elif pct >= 20:
            color = ThemeManager.inline("accent")
        else:
            color = ThemeManager.inline("text_muted")
        bg     = ThemeManager.inline("elevated_bg")
        border = ThemeManager.inline("border")
        return (
            f"QProgressBar {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )

    # ── Thème ─────────────────────────────────────────────────────────

    def refresh_theme(self) -> None:
        """Propage le thème à tous les sous-widgets."""
        for div in (self._div0, self._div1, self._div2, self._div3, self._div4,
                    self._div_comp):
            div.setStyleSheet(f"background-color: {ThemeManager.inline('divider_bg')};")

        self._conv_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('rag_info_color')}; font-size: 11px;"
        )
        self._eco_hint.setStyleSheet(
            f"color: {ThemeManager.inline('text_disabled')}; font-size: 10px;"
        )
        self._comp_hint.setStyleSheet(
            f"color: {ThemeManager.inline('text_disabled')}; font-size: 10px;"
        )
        self._footer_lbl.setStyleSheet(
            f"color: {ThemeManager.inline('tools_panel_info')}; font-size: 10px;"
        )
        self._ctx_bar.setStyleSheet(self._ctx_bar_style(self._ctx_bar.value()))
        self._comp_bar.setStyleSheet(self._comp_bar_style(self._comp_bar.value()))
        self._sparkline.update()

        for card in (
            self._card_prompt, self._card_completion,
            self._card_calls, self._card_cost,
            self._card_co2, self._card_kwh,
            self._card_comp_ops, self._card_comp_saved,
            self._card_sess_cost, self._card_sess_calls,
            self._card_sess_co2, self._card_sess_kwh,
        ):
            card.refresh_theme()

        # Forcer le rafraîchissement visuel complet
        self._refresh_current()
        self._refresh_session()
