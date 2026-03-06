# ============================================================================
# Prométhée — Assistant IA desktop (Physique-Chimie)
# ============================================================================

"""
lms_tools.py — Outil d'export vers les plateformes d'apprentissage (LMS)
====================================================================

- Export de QCM au format Moodle XML pour import direct dans un ENT ou Pronote.
"""

import json
from pathlib import Path

from core.tools_engine import report_progress, set_current_family, tool

set_current_family("lms_tools", "Export LMS (Moodle)", "🎓")

def _resolve_output(output_path: str, default_name: str) -> Path:
    from tools.export_tools import _resolve_output as resolve
    return resolve(output_path, default_name)

def _ok(path: Path, extra: dict | None = None) -> str:
    r = {"status": "ok", "path": str(path), "size_bytes": path.stat().st_size}
    if extra:
        r.update(extra)
    return json.dumps(r, ensure_ascii=False)

def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)


@tool(
    name="export_moodle_xml",
    description=(
        "Génère un fichier Moodle XML (.xml) contenant une banque de questions (QCM). "
        "Ce format est standard et peut être importé directement dans Pronote, Moodle ou tout ENT de lycée. "
        "Très utile pour créer des quiz Rapides d'évaluation en Physique-Chimie."
    ),
    parameters={
        "type": "object",
        "properties": {
            "category_name": {
                "type": "string",
                "description": "Nom de la catégorie pour ranger ces questions dans la banque (ex: 'Séquence 1 - Cinétique')."
            },
            "questions": {
                "type": "array",
                "description": "Liste des questions QCM.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Titre court de la question"},
                        "text": {"type": "string", "description": "L'énoncé de la question"},
                        "answers": {
                            "type": "array",
                            "description": "Liste des choix de réponse",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string", "description": "Le texte du choix"},
                                    "fraction": {"type": "integer", "description": "100 si bonne réponse, 0 si mauvaise réponse. (Pénalité possible: -33, -50)"},
                                    "feedback": {"type": "string", "description": "Feedback optionnel spécifique à cette réponse"}
                                },
                                "required": ["text", "fraction"]
                            }
                        }
                    },
                    "required": ["name", "text", "answers"]
                }
            },
            "output_path": {
                "type": "string",
                "description": "Chemin de destination (ex: ~/Documents/qcm_cinetique.xml). Optionnel."
            },
            "filename": {
                "type": "string",
                "description": "Nom du fichier si output_path est omis (ex: qcm_cinetique.xml)."
            }
        },
        "required": ["category_name", "questions"]
    }
)
def export_moodle_xml(category_name: str, questions: list[dict], output_path: str = "", filename: str = "") -> str:
    """Génère un fichier lisible par Moodle XML Import."""
    report_progress(f"Création d'un export Moodle XML de {len(questions)} questions...")
    
    try:
        name = filename or "export_moodle.xml"
        if not name.endswith(".xml"):
            name += ".xml"
        p = _resolve_output(output_path, name)
        
        # En-tête Moodle XML
        xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<quiz>']
        
        # Catégorie
        xml.append('  <question type="category">')
        xml.append('    <category>')
        xml.append(f'      <text><![CDATA[$course$ / {category_name}]]></text>')
        xml.append('    </category>')
        xml.append('  </question>')
        
        # Questions
        for q in questions:
            xml.append('  <question type="multichoice">')
            xml.append(f'    <name><text><![CDATA[{q.get("name", "Question")}]]></text></name>')
            xml.append(f'    <questiontext format="html"><text><![CDATA[{q.get("text", "")}]]></text></questiontext>')
            xml.append('    <single>true</single>')  # Support QCU par défaut
            xml.append('    <shuffleanswers>true</shuffleanswers>')
            xml.append('    <answernumbering>abc</answernumbering>')
            
            for a in q.get("answers", []):
                fraction = a.get("fraction", 0)
                xml.append(f'    <answer fraction="{fraction}">')
                xml.append(f'      <text><![CDATA[{a.get("text", "")}]]></text>')
                if a.get("feedback"):
                    xml.append(f'      <feedback><text><![CDATA[{a.get("feedback")}]]></text></feedback>')
                xml.append('    </answer>')
                
            xml.append('  </question>')
            
        xml.append('</quiz>')
        
        p.write_text("\n".join(xml), encoding="utf-8")
        return _ok(p, {"questions_exported": len(questions)})
        
    except Exception as e:
        return _err(f"export_moodle_xml : {e}")
