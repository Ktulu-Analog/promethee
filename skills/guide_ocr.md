---
name: Guide OCR — extraction de texte
description: >
  Protocole pour extraire du texte depuis des images et des PDFs scannés avec les outils OCR.
  Choisir le bon outil selon le type de fichier (image vs PDF), détecter les PDFs mixtes,
  paramétrer les langues et le seuil de confiance.
tags: [ocr, image, pdf, scan, extraction, texte, tesseract]
version: 1.0
---

# Guide OCR — Extraction de texte

Guide pour extraire du texte depuis des images numérisées et des PDFs avec les outils Tesseract disponibles.

---

## 1. Choisir le bon outil

| Situation | Outil recommandé |
|---|---|
| Fichier image (PNG, JPG, TIFF, BMP, WebP…) | `ocr_image` |
| Fichier PDF (tout type) | `ocr_pdf` |
| Vérifier si un PDF est scanné ou numérique avant traitement | `ocr_pdf_detect` ← appeler en premier |
| Connaître les langues Tesseract disponibles | `ocr_languages` |

**Règle d'or :** pour un PDF, toujours appeler `ocr_pdf_detect` en premier pour connaître la nature des pages avant d'appeler `ocr_pdf`.

---

## 2. Workflow recommandé pour un PDF

```
ÉTAPE 1 — Détecter la nature du PDF
  → ocr_pdf_detect(chemin="~/Documents/scan.pdf")
  Retourne pour chaque page : "numerique", "scannee" ou "mixte"

ÉTAPE 2 — Extraire le texte
  → ocr_pdf(chemin="~/Documents/scan.pdf", langues="fra")
  Gère automatiquement les pages numériques ET scannées.
  Pour les PDFs volumineux → utiliser pages_max ou pages pour limiter.
```

---

## 3. `ocr_image` — extraction depuis une image

```json
{
  "chemin": "~/Documents/formulaire_scan.png",
  "langues": "fra",
  "confiance_min": 60
}
```

**Paramètres :**
- `chemin` : chemin vers l'image (PNG, JPG, TIFF, BMP, WebP)
- `langues` : code(s) Tesseract séparés par `+` (défaut : `fra`)
- `confiance_min` : seuil 0–100 pour filtrer les mots mal reconnus (défaut : 0 = tout inclure)

**Exemples de codes langue :**

| Langue | Code |
|---|---|
| Français | `fra` |
| Anglais | `eng` |
| Allemand | `deu` |
| Espagnol | `spa` |
| Français + Anglais | `fra+eng` |

---

## 4. `ocr_pdf` — extraction depuis un PDF

```json
{
  "chemin": "~/Documents/rapport_scanne.pdf",
  "langues": "fra",
  "pages_max": 50
}
```

Pour traiter uniquement certaines pages :
```json
{
  "chemin": "~/Documents/rapport.pdf",
  "langues": "fra",
  "pages": "1-5,10,15-20"
}
```

**Paramètres :**
- `chemin` : chemin vers le PDF
- `langues` : langues pour les pages scannées (ignoré pour les pages avec texte natif)
- `pages_max` : nombre maximum de pages à traiter (pour les PDFs volumineux)
- `pages` : plage de pages au format `"1-5,10,15-20"`

**Retour :** texte page par page avec indication de la méthode utilisée (`"ocr"` ou `"natif"`).

---

## 5. `ocr_pdf_detect` — détecter la nature d'un PDF

```json
{
  "chemin": "~/Documents/rapport.pdf"
}
```

Rapide (n'effectue pas d'OCR). Utile pour :
- Confirmer que l'OCR est nécessaire avant de lancer `ocr_pdf`
- Connaître les pages problématiques d'un PDF mixte

---

## 6. `ocr_languages` — lister les langues disponibles

```json
{}
```

Retourne la liste des paquets de langues Tesseract installés sur le système.
Appeler si une langue spécifique n'est pas reconnue.

---

## 7. Bonnes pratiques

- **Qualité du scan** : l'OCR fonctionne mieux sur des images à 300 dpi minimum, bien contrastées et droites (sans rotation).
- **Seuil de confiance** : utiliser `confiance_min: 60` pour filtrer les reconnaissances douteuses sur des scans de mauvaise qualité.
- **PDFs volumineux** : utiliser `pages_max` ou `pages` pour éviter les timeouts sur des fichiers de plusieurs centaines de pages.
- **Langue mixte** : pour un document contenant du français et de l'anglais, utiliser `"fra+eng"` — meilleur résultat qu'une seule langue.

---

## 8. Erreurs fréquentes à éviter

| Erreur | Correction |
|---|---|
| Utiliser `ocr_image` sur un PDF | Utiliser `ocr_pdf` à la place |
| OCR lent sur un PDF numérique | Appeler `ocr_pdf_detect` d'abord — un PDF numérique peut être extrait sans OCR |
| Résultat avec beaucoup de caractères parasites | Augmenter `confiance_min` à 60–70 |
| Langue inconnue / mauvais résultat | Vérifier les langues disponibles avec `ocr_languages` |
| Timeout sur un gros PDF | Utiliser `pages_max` pour traiter par tranches |
