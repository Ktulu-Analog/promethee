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
tools/ — Modules d'outils pour Prométhée
=================================================

Chaque sous-module expose un ensemble d'outils thématiques et s'enregistre
automatiquement dans core.tools_engine lors de son import.

Modules disponibles :

  system_tools        — read_file, list_files, ...
  python_tools        — python_eval, python_exec, python_install,
                        python_run_script, python_list_packages,
                        python_reset_env
  data_tools          — datetime_now, json_formatter
  data_file_tools     — df_read, df_list, df_head, df_info,
                        df_value_counts, df_query, df_pivot,
                        df_merge, df_write, df_drop
  sql_tools           — sql_connect, sql_disconnect,
                        sql_list_connections, sql_list_tables,
                        sql_describe, sql_query, sql_execute,
                        sql_explain, sql_export_csv
  web_tools           — web_fetch, web_screenshot, web_extract,
                        web_links, web_tables, web_rss,
                        web_download_file,web_search,
                        web_search_news, web_search_engine
  legifrance_tools    — outils API PISTE/Légifrance
  judilibre_tools     — outils API PISTE/Judilibre
  thunderbird_tools   — tb_list_mails, tb_search_mails,
                        tb_read_mail, tb_mark_mail, tb_move_mail,
                        tb_create_draft, tb_agenda_upcoming,
                        tb_agenda_search, tb_todo_list,
                        tb_agenda_create, tb_agenda_update,
                        tb_agenda_delete
  export_tools        — export_md, export_docx, export_xlsx_json,
                        export_xlsx_csv, export_pptx_json,
                        export_pptx_outline, export_pdf,
                        export_libreoffice, export_libreoffice_native
  skill_tools         — skill_list, skill_read
  web_search_tools    — web_search, web_search_news, web_search_engine
  ocr_tools           — ocr_image, ocr_pdf, ocr_pdf_detect,
                        ocr_languages

Pour activer tous les outils en une seule ligne :
    from tools import register_all
    register_all()

Pour activer uniquement certains modules :
    import tools.python_tools
    import tools.web_tools

Prérequis pour web_tools :
    pip install requests beautifulsoup4 lxml markdownify

Prérequis pour legifrance_tools (.env) :
    LEGIFRANCE_CLIENT_ID=votre_client_id
    LEGIFRANCE_CLIENT_SECRET=votre_client_secret

Prérequis pour thunderbird_tools :
    Thunderbird doit avoir été lancé au moins une fois (création du profil).
    Variable optionnelle : TB_PROFILE_PATH=/chemin/vers/profil

Note sur python_tools :
    Crée automatiquement un environnement virtuel dans ~/.promethee_python_env/
    où les packages peuvent être installés et le code exécuté en toute sécurité.
"""


def register_all() -> None:
    """Importe tous les modules d'outils pour les enregistrer dans tools_engine."""
    from tools import system_tools
    from tools import export_tools
    from tools import python_tools
    from tools import data_tools
    from tools import data_file_tools
    from tools import sql_tools
    from tools import ocr_tools
    from tools import web_tools
    from tools import legifrance_tools
    from tools import judilibre_tools
    from tools import datagouv_tools
    from tools import thunderbird_tools
    from tools import skill_tools


