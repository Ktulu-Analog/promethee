# ============================================================================
# Prométhée — Assistant IA desktop (Physique-Chimie)
# ============================================================================

"""
curriculum_tools.py — Outils de requête pour les programmes de l'Éducation Nationale
====================================================================

- Récupération des mots-clés du programme.
- Contextualisation des attentes pédagogiques pour le LLM.
"""

import json
import logging
import subprocess
from pathlib import Path

from core.tools_engine import report_progress, set_current_family, tool
from core import rag_engine

_log = logging.getLogger(__name__)

set_current_family("curriculum_tools", "Programmes (Eduscol)", "🎒")

_GDRIVE_ID = "1pQJdpj6J5peR-1FFvHL_1j5EyTQnXKd8"
_LOCAL_DIR = Path("data/programmes_eduscol")

def _sync_and_ingest_programs():
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    
    # Vérifier l'ingestion
    if not rag_engine.is_available():
        return

    # list_sources retourne [{"source": "...", ...}, ...]
    existing_sources = {s["source"] for s in rag_engine.list_sources(conversation_id="global")}
    
    for pdf_path in _LOCAL_DIR.glob("*.pdf"):
        # Ignorer les fichiers vides
        if pdf_path.stat().st_size == 0:
            continue
            
        if pdf_path.name not in existing_sources:
            report_progress(f"Vectorisation du programme local : {pdf_path.name}...")
            rag_engine.ingest_file(str(pdf_path), conversation_id="global")


@tool(
    name="get_curriculum_guidelines",
    description="Récupère les grandes lignes directives, le programme officiel ou les capacités exigibles d'un niveau donné en Physique-Chimie (ex: 'Terminale Spécialité', 'PCSI', 'MPSI', 'Seconde'). "
    "Mots-clés : Eduscol, programme officiel, capacités exigibles. "
    "Très utile avant de rédiger un exercice ou un TP pour s'assurer qu'il respecte le Bulletin Officiel (B.O.) publié sur Eduscol.",
    parameters={
        "type": "object",
        "properties": {
            "level": {
                "type": "string",
                "description": "Niveau visé (ex: 'Seconde', 'Première Spécialité', 'Terminale Spécialité', 'PCSI', 'PC', 'MP', 'MPSI')."
            },
            "domain": {
                "type": "string",
                "description": "Domaine spécifique recherché (ex: 'Thermodynamique', 'Ondes', 'Cinétique', 'Oxydoréduction', 'Mécanique quantique')."
            }
        },
        "required": ["level"],
    },
)
def get_curriculum_guidelines(level: str, domain: str = "") -> str:
    """
    Fournit un résumé des attentes du programme via une base vectorielle RAG
    synchronisée avec un Google Drive d'enseignant.
    """
    report_progress(f"Recherche des directives du programme pour le niveau '{level}'...")
    
    _sync_and_ingest_programs()
    
    if not rag_engine.is_available():
        return json.dumps({
            "error": "Le moteur RAG (Qdrant) n'est pas disponible. Impossible de lire les B.O."
        }, ensure_ascii=False)
        
    query = f"Programme officiel {level}"
    if domain:
        query += f" capacités exigibles limites attendues pour : {domain}"
        
    hits = rag_engine.search(query, top_k=7, conversation_id="global")
    
    if not hits:
        return json.dumps({
            "error": f"Aucun document trouvé pour le niveau {level} dans le domaine {domain}. Le PDF correspondant a-t-il été déposé sur le Google Drive ?",
            "note_stricte": "INTERDICTION ABSOLUE d'aborder des notions de niveau supérieur (pas d'entropie ni de second principe au lycée, etc.). Restreignez-vous aux fondamentaux."
        }, ensure_ascii=False, indent=2)
        
    extracted_texts = []
    for h in hits:
        extracted_texts.append(f"Source: {h['source']} (Score: {h['score']:.2f})\nExtrait:\n{h['text']}\n")
        
    return json.dumps({
        "level_requested": level,
        "domain_requested": domain,
        "official_guidelines_excerpts": extracted_texts,
        "strict_instruction": "N'utilisez QUE les notions évoquées dans ces extraits officiels du B.O. Ne mentionnez AUCUN concept de niveau supérieur ou universitaire non présent explicitement ici."
    }, ensure_ascii=False, indent=2)

