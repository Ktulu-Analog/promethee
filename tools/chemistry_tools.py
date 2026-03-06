# ============================================================================
# Prométhée — Assistant IA desktop (Physique-Chimie)
# ============================================================================

"""
chemistry_tools.py — Outils de requête pour les données de Chimie (PubChem)
====================================================================

- Recherche de molécules, masses molaires, formules brutes.
- Obtention des pictogrammes de sécurité (SMILES/GHS).
"""

import json

import pubchempy as pcp

from core.tools_engine import report_progress, set_current_family, tool

set_current_family("chemistry_tools", "Chimie (PubChem)", "🧪")


@tool(
    name="search_chemical_compound",
    description="Recherche les propriétés de base (formule brute, masse molaire, nom IUPAC, synonymes, numéro CAS) d'une molécule sur PubChem. "
    "Idéal pour préparer les mémorandums de TP de chimie (masses molaires).",
    parameters={
        "type": "object",
        "properties": {
            "name_or_formula": {
                "type": "string",
                "description": "Nom de la molécule (ex: 'benzene', 'aspirin', 'acide chlorhydrique') ou formule brute/SMILES."
            }
        },
        "required": ["name_or_formula"],
    },
)
def search_chemical_compound(name_or_formula: str) -> str:
    """
    Interroge l'API PubChem via pubchempy pour obtenir les propriétés du composé.
    """
    report_progress(f"Recherche de la molécule '{name_or_formula}' sur PubChem...")
    
    try:
        # On tente une recherche par nom. PubChem est meilleur en anglais.
        compounds = pcp.get_compounds(name_or_formula, 'name')
        
        if not compounds:
            return f"Aucune molécule trouvée pour '{name_or_formula}'. Essayez avec son équivalent en anglais (ex: 'water' au lieu de 'eau', 'hydrochloric acid') ou son code SMILES."
        
        # On prend le premier hit le plus pertinent
        c = compounds[0]
        
        res = {
            "iupac_name": c.iupac_name,
            "molecular_formula": c.molecular_formula,
            "molecular_weight": float(c.molecular_weight) if c.molecular_weight else None,
            "isomeric_smiles": c.isomeric_smiles,
            "charge": c.charge,
            "complexity": c.complexity,
            "synonyms": c.synonyms[:5] if c.synonyms else []
        }
        
        return json.dumps(res, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return f"Erreur lors de l'accès à PubChem : {str(e)}"
