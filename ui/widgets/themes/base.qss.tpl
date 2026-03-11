/* ============================================================================
   Prométhée — base.qss.tpl
   Template QSS principal. Variables : {token_name} → remplacées par ThemeManager.
   Pour ajouter un style : éditer ce fichier uniquement.
   ============================================================================ */

/* ── Fenêtre principale ── */
QMainWindow, QWidget#central {
    background-color: __base_bg__;
    color: __text_primary__;
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 14px;
}

/* ── Sidebar ── */
QWidget#sidebar {
    background-color: __surface_bg__;
    border-right: 1px solid __border__;
    min-width: 260px; max-width: 300px;
}
QLabel#app_title {
    color: __text_primary__; font-size: 16px; font-weight: 700;
    letter-spacing: 0.2px; padding: 6px 0px;
}
QLabel#mode_label { color: __text_muted__; font-size: 11px; padding: 0px; }

QWidget#sidebar_strip {
    background-color: __surface_bg__;
    border-right: 1px solid __border__;
}
QPushButton#sidebar_toggle_btn, QPushButton#sidebar_action_btn {
    background-color: transparent; border: none; border-radius: 6px; padding: 0px;
}
QPushButton#sidebar_toggle_btn:hover,
QPushButton#sidebar_action_btn:hover   { background-color: __elevated_bg__; }
QPushButton#sidebar_toggle_btn:pressed,
QPushButton#sidebar_action_btn:pressed { background-color: __border__; }

QPushButton#new_chat_btn {
    background-color: __accent__; color: #ffffff; border: none;
    border-radius: 8px; padding: 9px 16px; font-weight: 700;
    font-size: 13px; text-align: left;
}
QPushButton#new_chat_btn:hover   { background-color: __accent_hover__; }
QPushButton#new_chat_btn:pressed { background-color: __accent_pressed__; }

/* ── Liste de conversations (QListWidget — legacy) ── */
QListWidget#conv_list {
    background-color: transparent; border: none; outline: none; padding: 4px 8px;
}
QListWidget#conv_list::item {
    background-color: transparent; color: __text_secondary__; border-radius: 7px;
    padding: 9px 10px; margin: 1px 0px; font-size: 13px;
}
QListWidget#conv_list::item:hover    { background-color: __elevated_bg__; color: __text_primary__; }
QListWidget#conv_list::item:selected { background-color: __border__; color: __text_primary__; font-weight: 600; }

/* ── Arbre de conversations (QTreeWidget) ── */
QTreeWidget#conv_tree {
    background-color: __surface_bg__; border: none; outline: none;
    padding: 4px 8px; color: __text_secondary__;
}
QTreeWidget#conv_tree::item {
    background-color: transparent; color: __text_secondary__; border-radius: 7px;
    padding: 5px 6px; margin: 1px 0px; font-size: 13px;
}
QTreeWidget#conv_tree::item:hover    { background-color: __elevated_bg__; color: __text_primary__; }
QTreeWidget#conv_tree::item:selected { background-color: __border__; color: __text_primary__; font-weight: 600; }
QTreeWidget#conv_tree::branch,
QTreeWidget#conv_tree::branch:hover,
QTreeWidget#conv_tree::branch:selected,
QTreeWidget#conv_tree::branch:active {
    background-color: transparent; image: none; border: none;
}

/* ── Barre de recherche ── */
QLineEdit#search_bar {
    background-color: __elevated_bg__; border: 1px solid __border__;
    border-radius: 8px; color: __text_primary__; padding: 7px 12px; font-size: 13px;
}
QLineEdit#search_bar:focus { border-color: __accent__; }

/* ── Zone chat ── */
QWidget#chat_area { background-color: __base_bg__; }
QScrollArea#scroll_area { background-color: transparent; border: none; }
QScrollArea#scroll_area > QWidget > QWidget { background-color: transparent; }

QWidget#msg_user      { background-color: __msg_user_bg__; border-radius: 12px; border: 1px solid __msg_user_border__; }
QWidget#msg_assistant { background-color: transparent; }
QLabel#msg_role_user      { color: __accent_user_role__; font-weight: 700; font-size: 11px; letter-spacing: 1px; }
QLabel#msg_role_assistant { color: __accent_assistant_role__; font-weight: 700; font-size: 11px; letter-spacing: 1px; }
QTextBrowser#msg_content  {
    background-color: transparent; border: none; color: __text_primary__;
    font-size: 14px; selection-background-color: __accent__55;
}

/* ── Zone saisie ── */
QWidget#input_area { background-color: __surface_bg__; border-top: 1px solid __border__; padding: 12px 16px; }
QTextEdit#input_box {
    background-color: __elevated_bg__; border: 1px solid __border_active__;
    border-radius: 12px; color: __text_primary__; padding: 8px 12px; font-size: 14px;
}
QTextEdit#input_box:focus { border-color: __accent__; background-color: __input_focus_bg__; }

QWidget#toggle_bar { background-color: __surface_bg__; border-top: 1px solid __border__; }
QPushButton#toggle_input_btn {
    background-color: transparent; color: __text_muted__; border: none;
    font-size: 11px; font-weight: 600; padding: 2px 12px;
}
QPushButton#toggle_input_btn:hover { color: __text_secondary__; }

/* ── Bouton Envoyer ── */
QPushButton#send_btn {
    background-color: __accent__; color: #ffffff; border: none;
    border-radius: 10px; padding: 6px 16px; font-weight: 700;
    font-size: 14px; min-width: 80px;
}
QPushButton#send_btn:hover    { background-color: __accent_hover__; }
QPushButton#send_btn:pressed  { background-color: __accent_pressed__; }
QPushButton#send_btn:disabled {
    background-color: __send_btn_disabled_bg__;
    color: __send_btn_disabled_color__;
}

/* ── Bouton Stop ── */
QPushButton#stop_btn {
    background-color: __stop_btn_bg__; color: __stop_btn_color__;
    border: 1px solid __stop_btn_border__;
    border-radius: 10px; padding: 4px 16px; font-weight: 700; font-size: 14px;
}
QPushButton#stop_btn:hover {
    background-color: __stop_btn_hover_bg__;
    border-color: __stop_btn_hover_border__;
}

/* ── Boutons d'outil ── */
QPushButton#tool_btn {
    background-color: transparent; color: __text_secondary__;
    border: 1px solid __border__; border-radius: 7px; padding: 5px 10px; font-size: 12px;
}
QPushButton#tool_btn:hover {
    background-color: __elevated_bg__; color: __text_primary__; border-color: __border_active__;
}

/* ── Panneau RAG / outils ── */
QWidget#rag_panel {
    background-color: __surface_bg__; border-left: 1px solid __border__;
    min-width: 280px; max-width: 320px;
}
QLabel#rag_title {
    color: __rag_title_color__; font-size: 13px; font-weight: 700;
    letter-spacing: 0.5px; padding: 4px 0;
}
QListWidget#doc_list {
    background-color: transparent; border: 1px solid __border__;
    border-radius: 8px; color: __text_secondary__; font-size: 12px; padding: 4px;
}
QListWidget#doc_list::item       { padding: 6px 8px; border-radius: 5px; }
QListWidget#doc_list::item:hover { background-color: __elevated_bg__; color: __text_primary__; }

/* ── Barre de statut ── */
QStatusBar {
    background-color: __status_bg__; color: __text_muted__;
    border-top: 1px solid __border__; font-size: 11px;
}

/* ── Scrollbars ── */
QScrollBar:vertical   { background: transparent; width: 6px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 6px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: __scroll_handle__; border-radius: 3px;
}
QScrollBar::handle:vertical   { min-height: 30px; }
QScrollBar::handle:horizontal { min-width: 30px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: __scroll_handle_hover__;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical   { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Splitter ── */
QSplitter::handle { background-color: __border__; width: 1px; }

/* ── Tooltip global ── */
QToolTip {
    background-color: __elevated_bg__; color: __text_primary__;
    border: 1px solid __border_active__; border-radius: 6px;
    padding: 5px 10px; font-size: 12px;
}

/* ── ComboBox ── */
QComboBox {
    background-color: __elevated_bg__; border: 1px solid __border_active__;
    border-radius: 7px; color: __text_primary__; padding: 5px 10px;
    font-size: 13px; min-width: 120px;
}
QComboBox:hover { border-color: __text_muted__; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { width: 10px; height: 10px; }
QComboBox QAbstractItemView {
    background-color: __elevated_bg__; border: 1px solid __border_active__;
    color: __text_primary__; selection-background-color: __accent__;
    selection-color: #fff; padding: 4px;
}

/* ── Dialogs et widgets génériques ── */
QDialog  { background-color: __surface_bg__; color: __text_primary__; }
QLineEdit {
    background-color: __elevated_bg__; border: 1px solid __border_active__;
    border-radius: 7px; color: __text_primary__; padding: 7px 12px; font-size: 13px;
}
QLineEdit:focus { border-color: __accent__; }
QPushButton {
    background-color: __elevated_bg__; color: __text_primary__;
    border: 1px solid __border_active__; border-radius: 7px;
    padding: 7px 14px; font-size: 13px;
}
QPushButton:hover { background-color: __border__; border-color: __text_muted__; }

/* ── Barre de progression ── */
QProgressBar {
    background-color: __elevated_bg__; border: none;
    border-radius: 4px; height: 6px; color: transparent;
}
QProgressBar::chunk { background-color: __accent__; border-radius: 4px; }

/* ── Labels ── */
QLabel { color: __text_primary__; }
QLabel#section_label {
    color: __text_muted__; font-size: 11px; letter-spacing: 0.8px;
    font-weight: 700; padding: 8px 0 4px 0;
}

/* ── GroupBox ── */
QGroupBox {
    color: __text_secondary__; border: 1px solid __border__; border-radius: 8px;
    margin-top: 8px; padding: 12px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
