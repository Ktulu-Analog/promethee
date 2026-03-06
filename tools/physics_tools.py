# ============================================================================
# Prométhée — Assistant IA desktop (Physique-Chimie)
# ============================================================================

"""
physics_tools.py — Outils de requête pour les données de Physique
====================================================================

- Accès aux constantes fondamentales via l'API CODATA ou des bibliothèques scientifiques (scipy.constants).
- Accès aux données du NIST (si nécessaire via requêtes HTTP).
"""

import json
from typing import Dict, Any

import scipy.constants as const

from core.tools_engine import report_progress, set_current_family, tool

set_current_family("physics_tools", "Physique (CODATA/NIST)", "🧲")


@tool(
    name="get_physical_constant",
    description="Récupère la valeur, l'unité et l'incertitude d'une constante physique fondamentale (CODATA / NIST). "
    "Recherche les constantes par mot-clé (ex: 'Planck', 'Avogadro', 'faraday', 'electron mass'). "
    "Privilégiez des mots-clés en anglais pour avoir plus de résultats (ex: 'speed of light', 'Boltzmann').",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "Mot-clé ou nom partiel de la constante recherchée (ex: 'Planck', 'gravitation', 'Avogadro')."
            }
        },
        "required": ["keyword"],
    },
)
def get_physical_constant(keyword: str) -> str:
    """
    Recherche une constante physique dans la base de données de scipy.constants
    (qui encapsule les valeurs recommandées par CODATA).
    """
    report_progress(f"Recherche de la constante pour le mot-clé: '{keyword}'...")
    
    keyword_lower = keyword.lower()
    results = []
    
    # physical_constants est un dictionnaire : clé -> (valeur, unité, incertitude)
    for key, (value, unit, uncertainty) in const.physical_constants.items():
        if keyword_lower in key.lower():
            results.append({
                "name": key,
                "value": value,
                "unit": unit,
                "uncertainty": uncertainty
            })
            
    if not results:
        return f"Aucune constante trouvée pour le mot-clé '{keyword}'. Essayez avec un terme anglais plus générique (ex: 'mass', 'charge', 'constant')."
        
    # Limiter le nombre de résultats pour ne pas inonder le LLM
    if len(results) > 10:
        return json.dumps({
            "message": f"Trop de résultats ({len(results)}). Voici les 10 premiers. Soyez plus précis.",
            "results": results[:10]
        }, ensure_ascii=False, indent=2)
        
    return json.dumps(results, ensure_ascii=False, indent=2)


@tool(
    name="convert_units",
    description="Convertit une valeur d'une unité à une autre (si elles sont homogènes) ou fournit un facteur de conversion. Utile pour vérifier un changement d'unité dans un exercice ou vérifier la cohérence.",
    parameters={
        "type": "object",
        "properties": {
            "value": {
                "type": "number",
                "description": "Chiffre à convertir (ex: 10.5)."
            },
            "from_unit": {
                "type": "string",
                "description": "Unité de départ (ex: 'eV', 'atm', 'calorie', 'angstrom')."
            },
            "to_unit": {
                "type": "string",
                "description": "Unité d'arrivée (ex: 'J', 'Pa', 'joule', 'm')."
            }
        },
        "required": ["value", "from_unit", "to_unit"],
    },
)
def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """
    Effectue une conversion basique d'unités via scipy.constants si l'unité de départ
    correspond à un facteur connu (qui convertit souvent vers l'unité SI).
    """
    report_progress(f"Conversion de {value} {from_unit} vers {to_unit}...")
    
    # Nettoyage
    from_u = from_unit.strip()
    to_u = to_unit.strip()
    
    # scipy.constants possède des facteurs de conversion directs, par ex scipy.constants.eV est la valeur d'1 eV en Joules
    known_factors = {
        "eV": const.eV,
        "electron_volt": const.eV,
        "atm": const.atm,
        "calorie": const.calorie,
        "cal": const.calorie,
        "angstrom": const.angstrom,
        "light_year": const.light_year,
        "parsec": const.parsec,
        "au": const.au, # Astronomical unit
        "c": const.c, # Vitesse de la lumière
        "g": const.g, # Gravité terrestre (pour de la force en kgf)
        "hp": const.hp, # Horsepower
        "bar": const.bar,
        "mmHg": const.mmHg,
        "knot": const.knot,
        "nautical_mile": const.nautical_mile
    }
    
    # C'est une fonction utilitaire très basique. Une approche plus robuste utiliserait `pint` ou `astropy.units`.
    # Pour ne pas imposer de dépendance énorme, on fait le minimum vital ici.
    
    res = {
        "status": "not_implemented",
        "message": f"Conversion de complexe/composée non prise en charge nativement par cet outil léger. Utilisez python_tools pour un calcul d'unités robuste, ou les valeurs CODATA.",
        "known_direct_factors_to_SI": list(known_factors.keys())
    }
    
    # Si c'est une conversion de/vers le SI
    if from_u in known_factors and to_u in ["J", "Pa", "m", "kg", "s", "m/s", "W"]:
        # Suppose from_u is non-SI, to_u is SI
        result_value = value * known_factors[from_u]
        return json.dumps({"value": result_value, "unit": to_u, "note": f"Conversion basée sur {from_u} dans le système SI"}, indent=2)
        
    if to_u in known_factors and from_u in ["J", "Pa", "m", "kg", "s", "m/s", "W"]:
        # Suppose from_u is SI, to_u is non-SI
        result_value = value / known_factors[to_u]
        return json.dumps({"value": result_value, "unit": to_u, "note": f"Conversion calculée depuis le SI"}, indent=2)
        
    return json.dumps(res, ensure_ascii=False, indent=2)
