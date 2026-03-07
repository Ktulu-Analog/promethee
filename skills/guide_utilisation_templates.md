---
name: Guide utilisation des modèles bureautiques
description: >
  Comment produire des documents conformes aux gabarits de l'organisation avec
  export_docx_template, export_pptx_template et list_docx_template_styles.
  À utiliser dès que l'utilisateur mentionne un modèle, gabarit, charte graphique,
  papier à en-tête, ou souhaite un document « aux couleurs de l'organisation ».
tags: [template, gabarit, modèle, charte, docx, pptx, export, organisation, administratif]
version: 1.0
---

# Guide utilisation des modèles bureautiques

Produire des documents respectant la charte graphique et les gabarits de l'organisation.

---

## 1. Quand utiliser les outils de gabarit

| Situation | Outil recommandé |
|---|---|
| Un fichier `.docx` de modèle est disponible | `export_docx_template` |
| Un fichier `.pptx` de modèle est disponible | `export_pptx_template` |
| On veut connaître les styles d'un gabarit Word | `list_docx_template_styles` |
| Aucun gabarit disponible | `export_docx` / `export_pptx_json` |

**Règle d'or** : dès qu'un fichier gabarit existe, préférer les outils `_template`
à leurs équivalents génériques. Ils préservent en-têtes, pieds de page, logos, polices
et couleurs de l'organisation sans aucune manipulation supplémentaire.

---

## 2. Workflow recommandé — document Word

### Étape 1 : découvrir les styles du gabarit
```
list_docx_template_styles(template_path="~/Modèles/note_de_service.docx")
```
→ retourne les noms exacts des styles et des signets disponibles.

### Étape 2 : générer le document
```json
export_docx_template(
  template_path = "~/Modèles/note_de_service.docx",
  document = {
    "title": "Note relative à la mise en place du télétravail",
    "bookmarks": {
      "date":      "Toulon, le 5 juin 2026",
      "reference": "RH-2026-042",
      "emetteur":  "Direction des Ressources Humaines"
    },
    "sections": [
      {
        "heading": "Objet",
        "style": "Titre 1",
        "paragraphs": [
          "La présente note a pour objet de définir les modalités...",
          "Elle s'applique à l'ensemble des agents de la Direction..."
        ]
      },
      {
        "heading": "Dispositions applicables",
        "style": "Titre 1",
        "intro": "Conformément au décret n° 2016-151 du 11 février 2016 :",
        "bullets": [
          "Maximum 3 jours de télétravail par semaine",
          "Formulaire de demande à déposer avant le 1er du mois"
        ],
        "bullet_style": "Puce"
      }
    ]
  },
  clear_body = true,
  output_path = "~/Documents/note_teletravail_2026.docx"
)
```

### clear_body : quand le mettre à false ?
- `true` (défaut) : vide le corps du gabarit → partir d'une page blanche avec les styles.
- `false` : garder le contenu existant du gabarit (ex : en-tête de courrier pré-rempli
  avec logo et adresse) et **ajouter** le contenu après.

---

## 3. Workflow recommandé — présentation PowerPoint

### Étape 1 : identifier les layouts disponibles
Les noms de layouts sont retournés dans la réponse de `export_pptx_template`
(champ `layouts_available`). Layouts typiques :
- Index 0 : slide de titre (couverture)
- Index 1 : titre + contenu (avec zone de texte)
- Index 2 : titre + deux colonnes
- Index 5 : titre seul
- Index 6 : vide

### Étape 2 : générer la présentation
```json
export_pptx_template(
  template_path = "~/Modèles/presentation_corp.pptx",
  presentation = {
    "title":    "Bilan d'activité 2025",
    "subtitle": "Direction Générale des Services",
    "slides": [
      {
        "title":        "Faits saillants",
        "layout_index": 1,
        "bullets": [
          "Augmentation de 12 % des dossiers traités",
          "Déploiement du SI RH sur 3 sites supplémentaires",
          "Satisfaction usager : 87 % (+ 4 pts)"
        ],
        "notes": "Insister sur le gain de productivité lié au SI RH."
      },
      {
        "title":        "Objectifs 2026",
        "layout_name":  "Titre, Contenu",
        "content":      "Consolider les acquis et étendre le déploiement...",
        "notes":        "Mentionner le calendrier prévisionnel en annexe."
      }
    ]
  },
  keep_example_slides = false,
  output_path = "~/Documents/bilan_2025.pptx"
)
```

---

## 4. Utilisation des signets (bookmarks) Word

Les signets permettent de remplacer des zones prédéfinies dans le gabarit
(date, référence, destinataire, émetteur, etc.) sans toucher au reste de la mise en page.

### Créer un signet dans un gabarit Word (pour les administrateurs)
1. Dans Word, sélectionner le texte de substitution (ex : `«DATE»`).
2. Menu Insertion → Signet → Nommer le signet (ex : `date`) → Ajouter.
3. Sauvegarder le gabarit.

### Utiliser les signets dans export_docx_template
```json
"bookmarks": {
  "date":        "Toulon, le 12 juin 2026",
  "destinataire": "Monsieur le Directeur Général",
  "reference":   "DGS-2026-0089",
  "objet":       "Réponse à votre courrier du 3 juin 2026"
}
```

L'outil `list_docx_template_styles` liste les signets disponibles dans le gabarit
(champ `bookmarks` de la réponse JSON).

---

## 5. Styles courants selon les gabarits administratifs français

| Type de contenu | Noms de styles typiques |
|---|---|
| Titre niveau 1 | `Titre 1`, `Heading 1`, `Titre organisation` |
| Titre niveau 2 | `Titre 2`, `Heading 2` |
| Corps de texte | `Corps texte`, `Body Text`, `Normal` |
| Puce | `Puce`, `List Bullet`, `Liste à puces` |
| Puce numérotée | `Liste numérotée`, `List Number` |
| Tableau | `Tableau grille`, `Table Grid`, `Tableau organisation` |
| Citation | `Citation`, `Intense Quote` |
| Note de bas de page | `Note de bas de page`, `Footnote Text` |

**Important** : toujours utiliser `list_docx_template_styles` pour obtenir
les noms exacts définis dans le gabarit de l'organisation.

---

## 6. Gestion des erreurs fréquentes

| Erreur | Cause probable | Solution |
|---|---|---|
| `gabarit introuvable` | Chemin incorrect | Vérifier le chemin avec `~` pour le home |
| Style non trouvé → style par défaut appliqué | Nom de style mal orthographié | Appeler `list_docx_template_styles` |
| Signet non substitué | Signet absent du gabarit ou nom incorrect | Vérifier dans `list_docx_template_styles` → champ `bookmarks` |
| Layout non trouvé → layout 0 utilisé | `layout_name` incorrect | Vérifier `layouts_available` dans la réponse |

---

## 7. Emplacements recommandés pour les gabarits

L'application cherche les gabarits dans l'ordre suivant (convention) :
```
~/Modèles/                  ← dossier personnel de l'utilisateur
~/Organisation/Modèles/     ← dossier partagé monté localement
/etc/promethee/templates/   ← templates système déployés par l'administrateur
```

L'utilisateur peut aussi fournir un chemin absolu complet.
