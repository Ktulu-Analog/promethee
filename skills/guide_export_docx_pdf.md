---
name: Guide export Word et PDF
description: >
  PROTOCOLE OBLIGATOIRE avant tout export de document Word ou PDF.
  Étape 1 : chercher un gabarit .docx dans ~/Modèles/ avec list_files.
  Étape 2 : si gabarit trouvé → list_docx_template_styles pour obtenir les styles et signets exacts.
  Étape 3 : export_docx_template (avec gabarit) ou export_docx / export_pdf (sans gabarit).
  Choisir export_pdf uniquement pour les documents destinés à la diffusion externe non modifiable.
tags: [word, docx, pdf, export, gabarit, template, document, rapport, note, courrier]
version: 1.0
---

# Guide export Word et PDF

## ⚠ PROTOCOLE IMPÉRATIF — suivre dans cet ordre à chaque demande de document

```
ÉTAPE 1 — Chercher un gabarit (TOUJOURS, même si l'utilisateur n'en parle pas)
  → list_files(path="~/Modèles")
  → list_files(path="~/Modèles/docx") si le premier ne retourne rien

ÉTAPE 2 — Inspecter le gabarit si trouvé (OBLIGATOIRE)
  → list_docx_template_styles(template_path="~/Modèles/note.docx")
  Retourne les noms EXACTS des styles et des signets disponibles.
  Ne jamais inventer ou supposer un nom de style.

ÉTAPE 3 — Choisir l'outil selon le résultat

  Gabarit .docx trouvé ?
    OUI → export_docx_template   ← PRIORITAIRE (préserve charte, polices, logos)
    NON → export_docx            (document éditable sans charte)
          export_pdf             (diffusion externe non modifiable uniquement)

ÉTAPE 4 — Générer en UN SEUL appel avec le contenu complet et développé
```

**Ne jamais sauter les étapes 1 et 2.** Un gabarit peut exister sans que l'utilisateur le mentionne.

---

## Outil A : `export_docx_template` — gabarit trouvé à l'étape 1

### Structure de l'appel

```json
{
  "template_path": "~/Modèles/note.docx",
  "document": {
    "title": "Note relative à...",
    "bookmarks": {
      "date":      "Toulon, le 12 juin 2026",
      "reference": "RH-2026-042"
    },
    "sections": [
      {
        "heading": "Objet",
        "style": "Titre 1",
        "paragraphs": [
          "La présente note a pour objet de...",
          "Elle fait suite à..."
        ]
      },
      {
        "heading": "Contexte",
        "style": "Titre 1",
        "paragraphs": ["Par décision du ..., il a été décidé de..."],
        "bullets": ["Point 1", "Point 2"],
        "bullet_style": "Puce"
      }
    ]
  },
  "clear_body": true,
  "output_path": "~/Documents/ma_note.docx"
}
```

### Règles impératives

- `style` dans chaque section = **nom exact** retourné par `list_docx_template_styles`
- `bullet_style` = **nom exact** du style de liste retourné par cet outil
- `bookmarks` = substitutions des zones fixes du gabarit (en-tête, référence, date)
- `clear_body: true` → vide le corps du gabarit avant remplissage (défaut)
- `clear_body: false` → conserver un en-tête ou contenu fixe pré-rempli, puis ajouter le contenu après

### Correspondances de styles typiques dans les gabarits FR

| Rôle | Noms fréquents |
|---|---|
| Titre principal | `Titre`, `Titre du document`, `Title` |
| Titre section niv. 1 | `Titre 1`, `Heading 1` |
| Titre section niv. 2 | `Titre 2`, `Heading 2` |
| Corps de texte | `Corps texte`, `Corps de texte`, `Body Text`, `Normal` |
| Liste à puces | `Puce`, `Liste à puces`, `List Bullet` |
| Liste numérotée | `Liste numérotée`, `List Number` |
| Tableau | `Tableau grille`, `Table Grid` |

⚠ Ces noms sont indicatifs — **toujours vérifier avec `list_docx_template_styles`**.

---

## Outil B : `export_docx` — sans gabarit, document éditable

```json
{
  "title": "Note relative à...",
  "sections": [
    {
      "heading": "Objet",
      "paragraphs": [
        "La présente note a pour objet de...",
        "Elle fait suite à..."
      ]
    },
    {
      "heading": "Contexte",
      "paragraphs": [
        "Par décision du ..., il a été décidé de...",
        "Cette mesure s'inscrit dans le cadre de..."
      ],
      "bullets": ["Point 1", "Point 2"]
    }
  ],
  "output_path": "~/Documents/ma_note.docx"
}
```

---

## Outil C : `export_pdf` — diffusion externe non modifiable

Même structure que `export_docx`. À préférer uniquement quand le document est destiné à être diffusé en lecture seule (publication, envoi externe, archivage).

**Moteur de rendu : WeasyPrint (HTML/CSS → PDF).** Supporte nativement les formules LaTeX.

```json
{
  "title": "Rapport annuel 2025",
  "sections": [ ... ],
  "output_path": "~/Documents/rapport_2025.pdf"
}
```

### Support LaTeX dans `export_pdf`

Les formules mathématiques LaTeX peuvent être insérées dans **tout champ textuel** des sections (`paragraphs`, `content`, `intro`, `bullets`, `heading`) du document PDF.

| Syntaxe | Usage | Exemple |
|---|---|---|
| `$formule$` | Formule **inline** (dans le texte courant) | `La loi de Newton est $F = ma$.` |
| `$$formule$$` | Formule **display** (bloc centré, grande taille) | `$$\int_0^\infty e^{-x^2}dx = \frac{\sqrt{\pi}}{2}$$` |

**Rendu :** chaque formule est compilée par un vrai moteur **LaTeX** (`latex` + `dvipng`) et embarquée en base64 dans le HTML source. Support complet de `amsmath`, `amssymb`, `bm`, `\boldsymbol`, `\oint`, `\displaystyle`, `\partial`, etc. Fond transparent, résolution 200–220 dpi.

**Exemple de section avec LaTeX :**

```json
{
  "heading": "Équation de Schrödinger",
  "paragraphs": [
    "L'équation de Schrödinger dépendante du temps s'écrit :",
    "$$i\\hbar\\frac{\\partial}{\\partial t}\\Psi(\\mathbf{r},t) = \\hat{H}\\Psi(\\mathbf{r},t)$$",
    "où $\\hat{H}$ est l'opérateur hamiltonien et $\\hbar$ la constante de Planck réduite.",
    "Pour une particule libre, l'énergie cinétique vaut $E = \\frac{p^2}{2m}$."
  ]
}
```

> ⚠ Les antislashes LaTeX doivent être **doublés** dans les chaînes JSON : `\\frac`, `\\int`, `\\hbar`, etc.

### Prérequis système (export_pdf avec LaTeX)

```
pip install weasyprint
apt install texlive-latex-base texlive-latex-extra dvipng
```

Si `weasyprint` est absent, l'outil bascule automatiquement sur `reportlab` (sans rendu LaTeX). Si `latex`/`dvipng` sont absents, les formules sont remplacées par un bloc `<code>` de repli.

---

## Exigences de contenu pour les documents professionnels

- **Rédiger un contenu COMPLET et DÉVELOPPÉ**, proportionnel au sujet traité.
- Utiliser `paragraphs` (liste) pour plusieurs paragraphes rédigés par section — pas un simple squelette de puces.
- **Rapport ou note de fond** : viser au minimum **15 sections**.
- **Courrier ou compte rendu court** : 3 à 5 sections suffisent.
- Ne pas se limiter à des titres vides ou des listes minimalistes.

---

## Chemin de sortie

Si `output_path` n'est pas précisé → fichier créé dans `~/Exports/Prométhée/`.
Toujours communiquer le chemin exact du fichier généré à l'utilisateur.

---

## Erreurs fréquentes à éviter

| Erreur | Correction |
|---|---|
| Sauter la recherche de gabarit | Toujours appeler `list_files("~/Modèles")` en premier |
| Inventer un nom de style | Toujours utiliser `list_docx_template_styles` pour obtenir les noms exacts |
| Utiliser un style inexistant | Vérifier l'orthographe exacte dans la réponse de `list_docx_template_styles` |
| Signet non substitué | Vérifier dans `list_docx_template_styles` → champ `bookmarks` |
| Document trop court / squelette de puces | Développer chaque section avec plusieurs paragraphes rédigés |
| Utiliser `export_pdf` pour un document à éditer | Préférer `export_docx` si l'utilisateur doit modifier le document |
| Antislash simple dans LaTeX JSON | Doubler les antislashes dans les strings JSON : `\\frac`, `\\int`, `\\hbar` |
| Formule LaTeX dans export_docx | LaTeX n'est rendu que dans `export_pdf` (moteur WeasyPrint + matplotlib) |
