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

from core.tools_engine import report_progress, set_current_family, tool

set_current_family("curriculum_tools", "Programmes (Eduscol)", "🎒")


@tool(
    name="get_curriculum_guidelines",
    description="Récupère les grandes lignes directives, le programme officiel ou les capacités exigibles d'un niveau donné en Physique-Chimie (ex: 'Terminale Spécialité', 'PCSI', 'MPSI', 'Seconde'). "
    "Très utile avant de rédiger un sujet d'examen ou un TP pour s'assurer qu'il respecte le Bulletin Officiel (B.O.).",
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
    Fournit un résumé des attentes du programme.
    Note : Dans une version de production, cet outil devrait scrapper Eduscol ou
    interroger une base de données PDF/RAG interne contenant les B.O. 
    Pour l'instant, on simule une banque de donnée statique (Mock) avec les grands thèmes.
    """
    report_progress(f"Recherche des directives du programme pour le niveau '{level}'...")
    
    # Base de données simulée. Un vrai backend RAG ferait une requête sémantique ici.
    db = {
        "Seconde": {
            "Mouvement et interactions": "Principe d'inertie, modélisation d'une force, chute libre.",
            "L'énergie": "Formes d'énergie, principe de conservation, transfert thermique.",
            "Ondes et signaux": "Émission et perception d'un son, spectres d'émission, réfraction.",
            "Constitution de la matière": "Corps purs, mélanges, entités chimiques, quantité de matière (mole).",
            "Transformations chimiques": "Réactions chimiques, bilan de matière, solutions aqueuses, dilution.",
        },
        "Première Spécialité": {
            "Constitution et transformations": "Mole, concentration, réactions d'oxydoréduction, combustions, dissolution.",
            "Énergie": "Énergie cinétique, énergie potentielle, conservation de l'énergie mécanique, travail d'une force.",
            "Ondes et signaux": "Réfraction, loi de Snell-Descartes, ondes mécaniques, signaux sonores.",
            "Mouvement": "Vecteur vitesse, mouvement rectiligne uniforme/accéléré, lois de Newton (introduction).",
            "Chimie organique": "Formules semi-développées, groupes caractéristiques (alcool, aldéhyde, cétone, acide carboxylique).",
            "Structure de la matière": "Configuration électronique, tableau périodique, liaison covalente, schéma de Lewis.",
        },
        "Terminale Spécialité": {
            "Acide/Base": "pH, Ka, pKa, diagramme de prédominance, titrages pH-métriques.",
            "Cinétique": "Vitesse volumique, temps de demi-réaction, loi de vitesse d'ordre 1, catalyse.",
            "Mécanique": "Lois de Newton, mouvement dans un champ uniforme, équations horaires.",
            "Ondes": "Interférences, diffraction, effet Doppler.",
            "Thermodynamique": "Premier principe de la thermodynamique, bilan enthalpique, enthalpie de réaction.",
            "Chimie organique": "Stratégie de synthèse, rendement, catalyse, polymères.",
            "Électricité": "Condensateur, bobine, circuit RLC, résonance.",
        },
        "PCSI": {
            "Cristallographie": "Modèle du cristal parfait, systèmes cubiques, sites interstitiels.",
            "Thermodynamique": "Premier et Second principe, machines thermiques, changements d'état.",
            "Chimie orga": "Stéréochimie, substitution nucléophile, élimination (SN/E).",
            "Mécanique du point": "Cinématique, dynamique en référentiel non galiléen, oscillateurs.",
            "Optique": "Lois de Snell-Descartes, systèmes optiques centrés, lentilles, miroirs.",
            "Chimie des solutions": "Équilibres acido-basiques, précipitation, complexation, oxydo-réduction.",
        },
        "MPSI": {
            "Mécanique du point": "Cinématique, lois de Newton, théorèmes de l'énergie, oscillateurs harmoniques.",
            "Électrocinétique": "Circuits RC/RL/RLC, régime transitoire, régime sinusoïdal forcé, résonance.",
            "Optique géométrique": "Lois de Snell-Descartes, lentilles, instruments d'optique.",
            "Thermodynamique": "Gaz parfaits, premier principe, second principe, machines thermiques.",
            "Signal": "Analyse de Fourier, filtrage linéaire, fonction de transfert, diagramme de Bode.",
            "Chimie des solutions": "Réactions acido-basiques, de précipitation, d'oxydo-réduction, diagrammes E-pH.",
        },
        "PC": {
            "Thermodynamique chimique": "Potentiel chimique, affinité chimique, variance, loi d'action des masses.",
            "Électromagnétisme": "Équations de Maxwell, ARQS, ondes électromagnétiques dans le vide et dans les plasmas.",
            "Chimie orga": "Composés carbonylés, organomagnésiens, synthèse multi-étapes.",
            "Mécanique des fluides": "Statique des fluides, équation d'Euler, théorème de Bernoulli.",
            "Chimie des matériaux": "Cristallographie, diagrammes binaires, cinétique électrochimique.",
        },
        "MP": {
            "Mécanique des systèmes": "Mécanique du solide, moments d'inertie, théorème du moment cinétique.",
            "Électromagnétisme": "Équations de Maxwell, ondes EM dans le vide et les milieux, guides d'ondes.",
            "Physique quantique": "Fonction d'onde, équation de Schrödinger, puits de potentiel, effet tunnel.",
            "Thermodynamique statistique": "Ensemble microcanonique, distribution de Boltzmann, gaz parfait quantique.",
            "Optique ondulatoire": "Diffraction de Fraunhofer, interférences, réseaux, interféromètre de Michelson.",
        },
    }
    
    # Recherche approximative du niveau
    level_lower = level.lower()
    matched_level = None
    for k in db.keys():
        if k.lower() in level_lower or level_lower in k.lower():
            matched_level = k
            break
            
    if not matched_level:
        return json.dumps({
            "error": "Niveau non trouvé dans la base restreinte actuelle. Essayez Seconde, Terminale Spécialité, PCSI ou PC.",
            "available_levels": list(db.keys())
        }, ensure_ascii=False)
        
    guidelines = db[matched_level]
    
    if domain:
        # Filtrer par domaine si précisé
        domain_lower = domain.lower()
        filtered = {k: v for k, v in guidelines.items() if domain_lower in k.lower()}
        if filtered:
             return json.dumps({
                "level": matched_level,
                "domain_requested": domain,
                "guidelines": filtered,
                "note": "Recommandation : structurez l'exercice en utilisant UNIQUEMENT les notions ci-dessus."
             }, ensure_ascii=False, indent=2)
             
    # Retourner tout le programme du niveau
    return json.dumps({
        "level": matched_level,
        "full_curriculum_summary": guidelines,
        "note": "Recommandation : vérifiez que les concepts de votre réponse ne dépassent pas ce cadre exigible."
    }, ensure_ascii=False, indent=2)
