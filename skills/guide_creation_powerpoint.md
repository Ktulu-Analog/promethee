---
name: Guide création PowerPoint
description: >
  PROTOCOLE OBLIGATOIRE avant tout export PowerPoint.
  Étape 1 obligatoire : chercher un gabarit .pptx dans ~/Modèles/ avec list_files.
  Si gabarit trouvé → export_pptx_template.
  Si aucun gabarit → export_pptx_outline (contenu libre) ou export_pptx_json (tableaux).
tags: [powerpoint, présentation, export, pptx, slides, gabarit, template]
version: 3.0
---

# Guide création PowerPoint

## ⚠ PROTOCOLE IMPÉRATIF — suivre dans cet ordre à chaque demande de présentation

```
ÉTAPE 1 — Chercher un gabarit (TOUJOURS, même si l'utilisateur n'en parle pas)
  → list_files(path="~/Modèles")
  → list_files(path="~/Modèles/pptx") si le premier ne retourne rien

ÉTAPE 2 — Choisir l'outil selon le résultat

  Gabarit .pptx trouvé ?
    OUI → export_pptx_template   ← PRIORITAIRE
    NON → export_pptx_outline    (contenu libre, pas de tableaux)
          export_pptx_json       (si tableaux nécessaires)

ÉTAPE 3 — Générer en UN SEUL appel avec le contenu complet
```

**Ne jamais sauter l'étape 1.** Un gabarit peut exister sans que l'utilisateur le mentionne.

---

## Outil A : `export_pptx_template` — gabarit organisationnel trouvé à l'étape 1

Préserve intégralement thème, couleurs, polices et logos du gabarit.

```json
{
  "template_path": "~/Modèles/presentation_corp.pptx",
  "presentation": {
    "title": "Titre de la présentation",
    "subtitle": "Sous-titre optionnel",
    "slides": [
      {
        "title": "Titre du slide",
        "layout_index": 1,
        "bullets": ["Point 1", "Point 2", "Point 3"],
        "notes": "Note du présentateur"
      },
      {
        "title": "Slide avec texte libre",
        "layout_index": 1,
        "content": "Texte libre si pas de puces"
      }
    ]
  },
  "keep_example_slides": false,
  "output_path": "~/export/ma_presentation.pptx"
}
```

**Layouts courants** (index 0-based) :
- 0 = couverture/titre
- 1 = titre + contenu ← le plus utilisé
- 5 = titre seul
- 6 = vide

Les noms exacts sont retournés dans `layouts_available` après le premier appel.

---

## Outil B : `export_pptx_outline` — aucun gabarit disponible, contenu libre

```
# Titre du slide        → nouveau slide
Sous-titre ou phase     → texte sans puce
- Puce principale       → point principal
  - Sous-puce           → sous-point (2 espaces)
> Note présentateur     → note invisible
```

Exemple :
```
# Contexte
Situation au 1er janvier 2026
- Budget reconduit à l'identique
- Effectifs stables : 1 247 agents
> Mentionner le contexte budgétaire contraint

# Axes prioritaires
Phase 1 — Formation
- Déploiement du plan obligatoire
- Partenariat INSP pour cadres A+
Phase 2 — Recrutement
- 3 concours internes prévus
- Renforcement filière numérique
```

Appel :
```json
{
  "outline": "# Slide 1\n- Point 1\n- Point 2\n# Slide 2\n- Point A",
  "title": "Titre global",
  "output_path": "~/export/presentation.pptx"
}
```

---

## Outil C : `export_pptx_json` — aucun gabarit, slides avec tableaux

Utiliser uniquement si des tableaux sont nécessaires dans les slides.

```json
{
  "title": "Titre de la présentation",
  "slides": [
    {
      "title": "Comparaison",
      "table": {
        "headers": ["Critère", "Option A", "Option B"],
        "rows": [["Coût", "10 k€", "15 k€"], ["Délai", "3 mois", "1 mois"]]
      }
    },
    {
      "title": "Slide avec puces",
      "bullets": ["Point 1", "Point 2"]
    }
  ]
}
```

---

## Règles de conception des slides

- **Maximum 5 puces par slide**, maximum 10 mots par puce
- Fragments nominaux, pas de phrases complètes
- Un concept = un slide
- Commencer par le premier slide de contenu — pas de slide de titre générique vide

```
❌  « Il convient de noter que les effectifs ont sensiblement progressé »
✅  « Effectifs : +3,2 % en un an »
```

| Contenu | Format recommandé |
|---|---|
| Chiffres clés | 3-4 grands chiffres, 1 ligne de contexte chacun |
| Comparaison | Tableau 2-3 colonnes (`export_pptx_json`) |
| Processus séquentiel | Puces avec sous-niveaux Phase 1 / Phase 2 |
| Décision / recommandation | 1 puce en gras + 3 arguments max |

---

## Erreurs fréquentes

| Erreur | Correction |
|---|---|
| Sauter l'étape 1 (recherche gabarit) | Toujours appeler `list_files("~/Modèles")` en premier |
| Utiliser `export_pptx_outline` quand un gabarit existe | Vérifier `~/Modèles/` avant tout export |
| Plusieurs appels pour une même présentation | Construire l'outline/JSON complet, un seul appel |
| Phrases longues dans les puces | Reformuler en fragment nominal ≤ 10 mots |
| `\n` manquants dans l'outline | Utiliser `\n` pour séparer les lignes dans la chaîne JSON |

---

## Chemin de sortie

Si `output_path` n'est pas précisé → fichier créé dans `~/Exports/Prométhée/`.
Toujours communiquer le chemin exact du fichier généré à l'utilisateur.
