# ============================================================================
# Prométhée — Assistant IA avancé
# ============================================================================
# Auteur  : Pierre COUGET ktulu.analog@gmail.com
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
tools/writer_tools.py — Outils LLM pour piloter LibreOffice Writer en temps réel
==================================================================================

Outils exposés :
  - writer_new_document    : nouveau document Writer vierge
  - writer_insert_text     : texte (titre, paragraphe, liste)
  - writer_insert_table    : tableau avec en-têtes et lignes
  - writer_insert_chart    : graphique ECharts (rendu PNG par l'extension)
  - writer_save_document   : sauvegarde du document

Protocole : chaque outil pousse un événement JSON dans la queue de la session
Writer active. Le routeur ws_libreoffice.py relaie ces événements à l'extension
Prométhée Bridge dans LibreOffice. Le rendu ECharts est effectué côté client
(Node.js + echarts + canvas).
"""

import json
import logging

from core.tools_engine import tool, set_current_family
from server.routers.ws_libreoffice import push_writer_event, get_writer_session

_log = logging.getLogger(__name__)

set_current_family("writer_tools", "LibreOffice Writer", "📝")


def _get_session_id() -> str | None:
    from core.request_context import get_writer_session_id
    return get_writer_session_id()


def _push(event: dict, session_id: str = "") -> str:
    sid = session_id or _get_session_id()
    if not sid:
        return json.dumps({
            "status": "error",
            "error": (
                "Aucune session LibreOffice Writer active. "
                "L'utilisateur doit ouvrir l'extension Prométhée Bridge dans Writer "
                "et cliquer sur 'Connecter', puis fournir son Session ID."
            )
        }, ensure_ascii=False)

    if get_writer_session(sid) is None:
        return json.dumps({
            "status": "error",
            "error": f"Session Writer '{sid}' introuvable ou déconnectée."
        }, ensure_ascii=False)

    push_writer_event(sid, event)
    return json.dumps({"status": "ok", "session_id": sid, "event": event["type"]},
                      ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# OUTILS
# ═══════════════════════════════════════════════════════════════════════════════

@tool(
    name="writer_new_document",
    description=(
        "Ouvre un nouveau document vierge dans LibreOffice Writer. "
        "À appeler en début de génération. "
        "Nécessite que l'extension Prométhée Bridge soit connectée dans Writer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Titre principal du document, inséré en premier."
            },
            "session_id": {
                "type": "string",
                "description": "Session Writer (optionnel, résolu automatiquement depuis le contexte)."
            }
        },
        "required": []
    }
)
def writer_new_document(title: str = "", session_id: str = "") -> str:
    return _push({"type": "new_document", "title": title}, session_id)


@tool(
    name="writer_insert_text",
    description=(
        "Insère du texte dans le document LibreOffice Writer en temps réel. "
        "Utiliser style='heading1'/'heading2'/'heading3' pour les titres, "
        "'paragraph' pour le corps de texte, 'list_item' pour les listes à puces. "
        "Appeler section par section au fil de la rédaction."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Texte à insérer."
            },
            "style": {
                "type": "string",
                "enum": ["heading1", "heading2", "heading3", "paragraph", "list_item"],
                "description": "Style typographique. Défaut : 'paragraph'."
            },
            "session_id": {
                "type": "string",
                "description": "Session Writer (optionnel)."
            }
        },
        "required": ["text"]
    }
)
def writer_insert_text(text: str, style: str = "paragraph", session_id: str = "") -> str:
    return _push({"type": "insert_text", "text": text, "style": style}, session_id)


@tool(
    name="writer_insert_table",
    description=(
        "Insère un tableau dans le document LibreOffice Writer. "
        "Toutes les valeurs des cellules doivent être des chaînes de caractères."
    ),
    parameters={
        "type": "object",
        "properties": {
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "En-têtes de colonnes."
            },
            "rows": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string"}},
                "description": "Lignes de données (listes de chaînes)."
            },
            "caption": {
                "type": "string",
                "description": "Légende du tableau (optionnel)."
            },
            "session_id": {
                "type": "string",
                "description": "Session Writer (optionnel)."
            }
        },
        "required": ["headers", "rows"]
    }
)
def writer_insert_table(
    headers: list[str],
    rows: list[list[str]],
    caption: str = "",
    session_id: str = ""
) -> str:
    return _push({
        "type": "insert_table",
        "caption": caption,
        "headers": headers,
        "rows": rows,
    }, session_id)


@tool(
    name="writer_insert_chart",
    description=(
        "Insère un graphique dans le document LibreOffice Writer. "
        "Fournir la configuration ECharts complète — même format que pour les graphiques du chat. "
        "Le rendu PNG est effectué côté client par l'extension (Node.js + ECharts). "
        "Types supportés : bar, line, pie, scatter."
    ),
    parameters={
        "type": "object",
        "properties": {
            "echarts_option": {
                "type": "object",
                "description": "Configuration ECharts complète (title, xAxis, yAxis, series…)."
            },
            "caption": {
                "type": "string",
                "description": "Légende du graphique (optionnel)."
            },
            "width": {
                "type": "integer",
                "description": "Largeur PNG en pixels. Défaut : 800."
            },
            "height": {
                "type": "integer",
                "description": "Hauteur PNG en pixels. Défaut : 400."
            },
            "session_id": {
                "type": "string",
                "description": "Session Writer (optionnel)."
            }
        },
        "required": ["echarts_option"]
    }
)
def writer_insert_chart(
    echarts_option: dict,
    caption: str = "",
    width: int = 800,
    height: int = 400,
    session_id: str = ""
) -> str:
    return _push({
        "type": "insert_chart",
        "caption": caption,
        "echarts_option": echarts_option,
        "width": width,
        "height": height,
    }, session_id)


@tool(
    name="writer_save_document",
    description=(
        "Sauvegarde le document LibreOffice Writer courant. "
        "Si filename est fourni (ex: rapport.odt), sauvegarde sous ce nom dans ~/Documents/. "
        "À appeler en fin de génération."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Nom du fichier (ex: rapport.odt). Si omis, sauvegarde sur place."
            },
            "session_id": {
                "type": "string",
                "description": "Session Writer (optionnel)."
            }
        },
        "required": []
    }
)
def writer_save_document(filename: str = "", session_id: str = "") -> str:
    return _push({"type": "save_document", "filename": filename}, session_id)
