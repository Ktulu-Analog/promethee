# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
# Année   : 2026
# ============================================================================
"""
tokens.py — Palette de tokens sémantiques (seule source de vérité des couleurs)

Chaque entrée : "nom_token": (valeur_sombre, valeur_claire)

Pour ajouter une couleur :
  1. Ajouter ici dans le groupe sémantique approprié
  2. L'utiliser dans base.qss.tpl via {nom_token}
  C'est tout.

Groupes sémantiques :
  base_*          — fonds principaux
  surface_*       — fonds de surfaces secondaires (sidebar, panels)
  elevated_*      — fonds surélevés (cards, inputs, combobox)
  border_*        — bordures
  text_*          — couleurs de texte
  accent_*        — couleur d'accentuation (orange)
  scroll_*        — scrollbars
  topbar_*        — barre de titre
  sidebar_*       — panneau gauche
  chat_msg_*      — bulles de message
  input_*         — zone de saisie
  send_btn_*      — bouton Envoyer
  stop_btn_*      — bouton Arrêter
  tabs_*          — onglets
  rag_panel_*     — panneau RAG/outils
  tools_card_*    — cartes d'outils
  tools_tooltip_* — tooltip d'outil
  tools_panel_*   — panneau d'outils (divers)
  tool_call_*     — widget d'appel d'outil dans le chat
  attachment_*    — pièces jointes
  menu_*          — menus déroulants
  checkbox_*      — cases à cocher
  badge_*         — badges de statut (RAG, outils)

Palettes :
  Sombre — base #141416, surface #1c1c1f, élevé #242428, accent #d4813d
  Clair  — base #f2f0eb, surface #e6e3dc, élevé #ffffff, accent #8e4e18

Conformité — tous les couples texte/fond ≥ 4.5:1 (WCAG AA)
"""

# ── Police d'interface ────────────────────────────────────────────────────
# Valeur par défaut : stack multi-plateforme sans Segoe UI en tête.
# Surchargée dynamiquement par ThemeManager.set_font_family() depuis les préférences.
_FONT_FAMILY: str = "\"SF Pro Display\", \"Helvetica Neue\", \"Segoe UI\", sans-serif"


def get_font_family() -> str:
    return _FONT_FAMILY


def set_font_family(family: str) -> None:
    global _FONT_FAMILY
    _FONT_FAMILY = family


PALETTE: dict[str, tuple[str, str]] = {
    # ── Fonds principaux ─────────────────────────────────────────────
    "base_bg":              ("#141416", "#f2f0eb"),
    "surface_bg":           ("#1c1c1f", "#e6e3dc"),
    "elevated_bg":          ("#242428", "#ffffff"),
    "status_bg":            ("#0d0d0f", "#e0ddd6"),

    # ── Bordures ─────────────────────────────────────────────────────
    "border":               ("#2e2e34", "#d8d4cc"),
    "border_active":        ("#3a3a40", "#b8b4ac"),

    # ── Texte ────────────────────────────────────────────────────────
    "text_primary":         ("#e4e2ec", "#1e1c18"),
    "text_secondary":       ("#b0adb8", "#5c5850"),
    "text_muted":           ("#8a8a98", "#646058"),
    "text_disabled":        ("#52525c", "#b8b4ac"),

    # ── Accent (orange) ──────────────────────────────────────────────
    "accent":               ("#d4813d", "#8e4e18"),
    "accent_hover":         ("#e08f4a", "#d4813d"),
    "accent_pressed":       ("#bf7030", "#b46428"),
    "accent_user_role":     ("#d4813d", "#8e4e18"),
    "accent_assistant_role":("#7aafd4", "#3a6e9e"),

    # ── Topbar ───────────────────────────────────────────────────────
    "topbar_bg":            ("#0d0d0f", "#e0ddd6"),
    "topbar_border":        ("#2e2e34", "#d8d4cc"),
    "logo_color":           ("#e4e2ec", "#1e1c18"),
    "model_badge_color":    ("#8a8a98", "#5c5850"),
    "model_badge_bg":       ("#242428", "#f2f0eb"),
    "model_badge_border":   ("#2e2e34", "#d8d4cc"),

    # ── Scrollbars ───────────────────────────────────────────────────
    "scroll_handle":        ("#3a3a40", "#c8c4bc"),
    "scroll_handle_hover":  ("#52525c", "#b8b4ac"),

    # ── Inputs ───────────────────────────────────────────────────────
    "input_bg":             ("#242428", "#ffffff"),
    "input_color":          ("#e4e2ec", "#1e1c18"),
    "input_border":         ("#3a3a40", "#b8b4ac"),
    "input_focus_bg":       ("#262630", "#fffdf8"),

    # ── Messages ─────────────────────────────────────────────────────
    "msg_user_bg":          ("#1c1c1f", "#e6e3dc"),
    "msg_user_border":      ("#2e2e34", "#d8d4cc"),

    # ── Rendu HTML des messages (WebView) ────────────────────────────
    "link_color":           ("#6b9fd4", "#4a82b4"),
    "code_inline_color":    ("#cc7c3a", "#b86d2e"),
    "code_bg":              ("#1e1e22", "#e8e4dc"),
    "code_border":          ("#2e2e33", "#d0ccc4"),
    "blockquote_bg":        ("#1a1a1e", "#f0ede6"),
    "table_row_hover":      ("#161618", "#f5f2ec"),
    "code_block_bg":        ("#282C34", "#f0f0f0"),

    # ── Bouton Envoyer ───────────────────────────────────────────────
    "send_btn_disabled_bg":     ("#2e2e34", "#d8d4cc"),
    "send_btn_disabled_color":  ("#8a8a98", "#646058"),

    # ── Bouton Stop ──────────────────────────────────────────────────
    "stop_btn_bg":          ("#2a1a1a", "#fce8e8"),
    "stop_btn_color":       ("#e07878", "#b83030"),
    "stop_btn_border":      ("#4a2828", "#e8b0b0"),
    "stop_btn_hover_bg":    ("#3a2020", "#f8d4d4"),
    "stop_btn_hover_border":("#5a3030", "#d09090"),

    # ── Écologie (CO₂ / kWh) ─────────────────────────────────────────
    "eco_color":            ("#6dbf8a", "#2e7d4f"),
    "eco_warn_color":       ("#c8a84b", "#7a5f10"),

    # ── Onglets ──────────────────────────────────────────────────────
    "tabs_bar_bg":          ("#0d0d0f", "#e6e3dc"),
    "tabs_tab_color":       ("#9c9cac", "#646058"),
    "tabs_tab_hover_bg":    ("#1c1c1f", "#dedad2"),
    "tabs_tab_hover_color": ("#b0adb8", "#5c5850"),
    "tabs_close_hover_bg":  ("#2a1a1a", "#fce8e8"),

    # ── Panneau RAG / outils ─────────────────────────────────────────
    "rag_panel_bg":         ("#1c1c1f", "#e6e3dc"),
    "rag_panel_border":     ("#2e2e34", "#d8d4cc"),
    "rag_title_color":      ("#7aafd4", "#3a6e9e"),
    "rag_info_color":       ("#8a8a98", "#646058"),
    "divider_bg":           ("#2e2e34", "#d8d4cc"),

    # ── Cartes d'outils (panneau droit) ──────────────────────────────
    "tools_card_bg":        ("#1c1c1f", "#f2f0eb"),
    "tools_card_border":    ("#3a3a40", "#d8d4cc"),
    "tools_card_name":      ("#e4e2ec", "#1e1c18"),
    "tools_panel_info":     ("#8a8a98", "#646058"),
    "tools_panel_div":      ("#2e2e34", "#d8d4cc"),
    "tools_tooltip_bg":     ("#2a2a2f", "#ffffff"),
    "tools_tooltip_border": ("#7a7a8a", "#888078"),
    "tools_tooltip_title":  ("#e4e2ec", "#1e1c18"),
    "tools_tooltip_desc":   ("#b0adb8", "#5c5850"),

    # ── Widget appel d'outil dans le chat ────────────────────────────
    "tool_name_color":      ("#d4813d", "#8e4e18"),
    "tool_result_bg":       ("#141416", "#ffffff"),
    "tool_result_color":    ("#b0adb8", "#5c5850"),

    # Alias rétro-compat
    "tool_card_bg":         ("#1c1c1f", "#f2f0eb"),
    "tool_card_border":     ("#2e2e34", "#d8d4cc"),

    # ── Pièces jointes ───────────────────────────────────────────────
    "attachment_btn_bg":            ("#242428", "#ffffff"),
    "attachment_btn_border":        ("#3a3a40", "#b8b4ac"),
    "attachment_btn_color":         ("#d4813d", "#8e4e18"),
    "attachment_btn_hover_bg":      ("#2e2e34", "#f2f0eb"),
    "attachment_item_bg":           ("#1c1c1f", "#ffffff"),
    "attachment_item_border":       ("#2e2e34", "#d8d4cc"),
    "attachment_name_color":        ("#e4e2ec", "#1e1c18"),
    "attachment_size_color":        ("#8a8a98", "#646058"),
    "attachment_remove_color":      ("#8a8a98", "#646058"),
    "attachment_remove_hover_bg":   ("#2a1a1a", "#fce8e8"),
    "attachment_remove_hover_color":("#e07878", "#b83030"),

    # ── Menus ────────────────────────────────────────────────────────
    "menu_bg":                  ("#1c1c1f", "#ffffff"),
    "menu_border":              ("#2e2e34", "#d8d4cc"),
    "menu_item_color":          ("#e4e2ec", "#1e1c18"),
    "menu_item_selected_bg":    ("#2e2e34", "#e6e3dc"),
    "menu_item_selected_color": ("#e4e2ec", "#1e1c18"),
    "menu_separator":           ("#2e2e34", "#d8d4cc"),

    # ── Cases à cocher ───────────────────────────────────────────────
    "checkbox_color":            ("#b0adb8", "#5c5850"),
    "checkbox_checked_color":    ("#d4813d", "#8e4e18"),
    "checkbox_indicator_bg":     ("#242428", "#ffffff"),
    "checkbox_indicator_border": ("#3a3a40", "#b8b4ac"),

    # ── Badges de statut ─────────────────────────────────────────────
    "tools_badge_idle":   ("#8a8a98", "#646058"),
    "tools_badge_active": ("#d4813d", "#8e4e18"),
    "rag_badge_on":       ("#5aaa7a", "#2e7a52"),
    "rag_badge_off":      ("#52525c", "#646058"),
    "char_count_color":   ("#8a8a98", "#646058"),
    "dot_inactive":       ("#3a3a40", "#c8c4bc"),
    "dot_active":         ("#d4813d", "#8e4e18"),

    # ── Statut RAG (Qdrant connecté / non disponible / désactivé) ────
    "rag_status_ok":        ("#5aaa7a", "#2e7a52"),   # vert — connecté
    "rag_status_warn":      ("#8a8a98", "#646058"),   # gris  — non disponible
    "rag_status_off":       ("#52525c", "#888078"),   # gris foncé — désactivé

    # ── Séparateur inline dans le chat ───────────────────────────────
    "chat_sep_color":       ("#8a8a98", "#888078"),   # barre | entre widgets

    # ── Menus contextuels (RAG liste documents) ───────────────────────
    "ctx_menu_bg":          ("#1a1a1e", "#ffffff"),
    "ctx_menu_border":      ("#2e2e33", "#d8d4cc"),
    "ctx_menu_color":       ("#c8c6d0", "#1e1c18"),
    "ctx_menu_sel_bg":      ("#3a2020", "#fce8e8"),
    "ctx_menu_sel_color":   ("#e07070", "#b83030"),

    # ── Boîtes de dialogue de confirmation (RAG suppression) ──────────
    "confirm_dlg_bg":       ("#161618", "#f2f0eb"),
    "confirm_dlg_color":    ("#e8e6e1", "#1e1c18"),
    "confirm_btn_bg":       ("#252528", "#ffffff"),
    "confirm_btn_color":    ("#c8c6d0", "#1e1c18"),
    "confirm_btn_border":   ("#333338", "#c8c4bc"),
    "confirm_btn_hover_bg": ("#2e2e32", "#e6e3dc"),

    # ── Visionneuse PDF ───────────────────────────────────────────────
    "pdf_viewer_bg":        ("#0a0a0c", "#f2f0eb"),   # fond de la zone image
    "pdf_slider_hover":     ("#e08840", "#bf6820"),   # handle slider survol

    # ── Boutons Mermaid (toolbar téléchargement) ──────────────────────
    "mermaid_btn_bg":       ("#2a2a2a", "#f0f0f0"),
    "mermaid_btn_color":    ("#d0d0d0", "#444444"),
    "mermaid_btn_border":   ("#444444", "#cccccc"),
    "mermaid_btn_hover_bg": ("#383838", "#e0e0e0"),
    "mermaid_btn_hover_color": ("#ffffff", "#111111"),
    # Bouton SVG inline (rendu statique fallback, fond clair fixe)
    "mermaid_svg_btn_bg":   ("#f5f5f5", "#f5f5f5"),
    "mermaid_svg_btn_color":("#333333", "#333333"),
    "mermaid_svg_btn_border":("#aaaaaa", "#aaaaaa"),

    # ── Flèches expand/collapse du QTreeWidget sidebar ───────────────
    # Valeurs = URL SVG base64 complètes, substituées directement dans
    # base.qss.tpl via __branch_arrow_closed__ / __branch_arrow_open__.
    # Triangles ▶ (fermé) et ▼ (ouvert), couleur = text_muted du thème.
    "branch_arrow_closed": ("url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxNiAxNic+PHBvbHlnb24gcG9pbnRzPSc1LDMgMTEsOCA1LDEzJyBmaWxsPScjOGE4YTk4Jy8+PC9zdmc+')", "url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxNiAxNic+PHBvbHlnb24gcG9pbnRzPSc1LDMgMTEsOCA1LDEzJyBmaWxsPScjNjQ2MDU4Jy8+PC9zdmc+')"),
    "branch_arrow_open":   ("url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxNiAxNic+PHBvbHlnb24gcG9pbnRzPSczLDUgMTMsNSA4LDExJyBmaWxsPScjOGE4YTk4Jy8+PC9zdmc+')", "url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxNiAxNic+PHBvbHlnb24gcG9pbnRzPSczLDUgMTMsNSA4LDExJyBmaWxsPScjNjQ2MDU4Jy8+PC9zdmc+')"),
}


def get(key: str, dark: bool) -> str:
    """Retourne la valeur du token pour le thème demandé."""
    dark_val, light_val = PALETTE[key]
    return dark_val if dark else light_val


def resolve(dark: bool) -> dict[str, str]:
    """Retourne un dict {token: valeur} pour le thème demandé.
    Utilisé pour substituer les tokens dans les templates QSS."""
    return {k: (v[0] if dark else v[1]) for k, v in PALETTE.items()}
