---
name: Guide création PowerPoint
description: >
  PROTOCOLE OBLIGATOIRE avant tout export PowerPoint.
  Étape 1 : chercher un gabarit .pptx dans ~/Modèles/ avec list_files.
  Étape 2 : si gabarit trouvé → inspect_pptx_template pour connaître les layouts et placeholders.
  Étape 3 : export_pptx_template en ciblant les placeholders par leur order.
  Si aucun gabarit → export_pptx_outline ou export_pptx_json.
tags: [powerpoint, présentation, export, pptx, slides, gabarit, template]
version: 4.0
---

# Guide création PowerPoint

## ⚠ PROTOCOLE IMPÉRATIF — suivre dans cet ordre à chaque demande de présentation

```
ÉTAPE 1 — Chercher un gabarit (TOUJOURS, même si l'utilisateur n'en parle pas)
  → list_files(path="~/Modèles")
  → list_files(path="~/Modèles/pptx") si le premier ne retourne rien

ÉTAPE 2 — Inspecter le gabarit si trouvé (OBLIGATOIRE)
  → inspect_pptx_template(template_path="~/Modèles/diaporama.pptx")
  Retourne pour chaque layout : index, nom, et pour chaque placeholder :
    order     → numéro d'ordre (0, 1, 2…) à utiliser dans le champ "placeholders"
    xml_type  → type du placeholder (title, body, obj, ftr, sldNum, dt…)
    name      → nom de la shape dans le gabarit
    w_cm      → largeur en cm (permet d'identifier le placeholder principal)
    is_title   → true si c'est un titre (ne pas y mettre le corps)
    is_content → true si c'est un placeholder de contenu

ÉTAPE 3 — Choisir l'outil selon le résultat

  Gabarit .pptx trouvé ?
    OUI → export_pptx_template   ← PRIORITAIRE
    NON → export_pptx_outline    (contenu libre, pas de tableaux)
          export_pptx_json       (si tableaux nécessaires)

ÉTAPE 4 — Générer en UN SEUL appel avec le contenu complet
```

**Ne jamais sauter les étapes 1 et 2.** Un gabarit peut exister sans que l'utilisateur le mentionne. Sans inspection préalable, le remplissage des placeholders sera incorrect.

---

## Outil 0 : `inspect_pptx_template` — toujours appeler avant export_pptx_template

```json
{
  "template_path": "~/Modèles/diaporama.pptx"
}
```

Exemple de retour (layout 3) :
```json
{
  "index": 3,
  "name": "diapo texte avec titre",
  "placeholders": [
    { "order": 0, "xml_type": "title", "name": "PlaceHolder 1", "w_cm": 26.39, "is_title": true,  "is_content": false },
    { "order": 1, "xml_type": "body",  "name": "PlaceHolder 2", "w_cm": 26.39, "is_title": false, "is_content": true  },
    { "order": 2, "xml_type": "ftr",   "name": "PlaceHolder 3", "w_cm": 9.29,  "is_title": false, "is_content": false },
    { "order": 3, "xml_type": "body",  "name": "PlaceHolder 4", "w_cm": 10.56, "is_title": false, "is_content": true  }
  ]
}
```

**Lecture du résultat :**
- `order=0, is_title=true` → placeholder du titre du slide
- `order=1, is_content=true, w_cm=26.39` → grand bloc de contenu principal ← **c'est celui-là**
- `order=3, is_content=true, w_cm=10.56` → petit bloc secondaire (colonne, logo…) ← ignorer

**Règle de sélection du placeholder principal :**
Parmi les placeholders `is_content=true`, prendre celui avec le **`w_cm` le plus grand**.

---

## Outil A : `export_pptx_template` — gabarit organisationnel trouvé à l'étape 1

Préserve intégralement thème, couleurs, polices et logos du gabarit.

### Cibler les placeholders par `order` (méthode recommandée après inspection)

Utiliser le champ `placeholders` avec comme clé l'`order` du placeholder identifié :

```json
{
  "template_path": "~/Modèles/diaporama.pptx",
  "presentation": {
    "title": "Titre de la présentation",
    "subtitle": "Sous-titre optionnel",
    "slides": [
      {
        "layout_index": 3,
        "placeholders": {
          "0": "Titre du slide",
          "1": "• Point principal 1\n• Point principal 2\n• Point principal 3"
        },
        "notes": "Note du présentateur"
      },
      {
        "layout_index": 3,
        "placeholders": {
          "0": "Deuxième slide",
          "1": "Texte libre si pas de puces"
        }
      }
    ]
  },
  "keep_example_slides": false,
  "output_path": "~/export/ma_presentation.pptx"
}
```

> **Important :** les clés de `placeholders` correspondent à l'`order` retourné par `inspect_pptx_template`, pas à l'`xml_idx`. C'est le numéro de position du placeholder dans la liste (0, 1, 2…).

### Utiliser `bullets` ou `content` (si l'inspection confirme la structure standard)

```json
{
  "template_path": "~/Modèles/diaporama.pptx",
  "presentation": {
    "title": "Titre de la présentation",
    "slides": [
      {
        "title": "Titre du slide",
        "layout_index": 3,
        "bullets": ["Point 1", "Point 2", "Point 3"]
      },
      {
        "title": "Slide avec texte libre",
        "layout_index": 3,
        "content": "Texte libre si pas de puces"
      }
    ]
  },
  "output_path": "~/export/ma_presentation.pptx"
}
```

> N'utiliser `bullets`/`content` que si l'inspection confirme que le gabarit a un placeholder `is_content=true` avec `xml_idx=1`. Sinon, toujours utiliser `placeholders` avec les `order` exacts.

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
| Sauter l'étape 2 (inspection gabarit) | Toujours appeler `inspect_pptx_template` avant `export_pptx_template` |
| Utiliser `bullets`/`content` sans vérifier la structure | Utiliser `placeholders` avec les `order` exacts issus de l'inspection |
| Remplir le petit placeholder secondaire au lieu du principal | Choisir `is_content=true` avec le `w_cm` le plus grand |
| Utiliser `export_pptx_outline` quand un gabarit existe | Vérifier `~/Modèles/` avant tout export |
| Plusieurs appels pour une même présentation | Construire le JSON complet, un seul appel |
| Phrases longues dans les puces | Reformuler en fragment nominal ≤ 10 mots |

---

## Chemin de sortie

Si `output_path` n'est pas précisé → fichier créé dans `~/Exports/Prométhée/`.
Toujours communiquer le chemin exact du fichier généré à l'utilisateur.
