# Dépendances système — Prométhée

Paquets à installer sur le système d'exploitation **avant** `pip install -r requirements.txt`.

---

## Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y \
    # ── OCR ──────────────────────────────────────────────────
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    \
    # ── PDF → images (pdf2image / pdftoppm) ──────────────────
    poppler-utils \
    \
    # ── LaTeX (rendu équations, export_pdf, export_pdf_from_tex)
    texlive-latex-base \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-science \
    dvipng \
    \
    # ── WeasyPrint (export_pdf HTML→PDF) — dépendances système
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    shared-mime-info \
    fonts-liberation \
    \
    # ── Conversion documents Office (export_libreoffice) ─────
    libreoffice-nogui \
    \
    # ── Extraction .doc legacy ────────────────────────────────
    antiword
```

---

## macOS (Homebrew)

```bash
brew install \
    tesseract \
    tesseract-lang \
    poppler \
    dvipng \
    pango \
    cairo \
    shared-mime-info \
    libreoffice \
    antiword
```

> **LaTeX** : installer [MacTeX](https://tug.org/mactex/) ou `brew install --cask mactex-no-gui`.

---

## Windows

| Composant | Source |
|-----------|--------|
| Tesseract | https://github.com/UB-Mannheim/tesseract/wiki |
| Poppler | https://github.com/oschwartz10612/poppler-windows/releases |
| LibreOffice | https://www.libreoffice.org/download/download-libreoffice/ |
| antiword | https://www.winfield.demon.nl/ |
| MiKTeX (LaTeX + dvipng) | https://miktex.org/download |
| GTK3 Runtime (WeasyPrint) | https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases |

Ajouter les dossiers `bin/` de chaque outil au `PATH` système.

> **WeasyPrint sur Windows** : les bibliothèques GTK/Pango/Cairo sont distribuées via le GTK3 Runtime ci-dessus.
> Installer ce runtime **avant** `pip install weasyprint`.

---

## Détail par fonctionnalité

| Fonctionnalité | Paquet(s) système | Obligatoire |
|---|---|:---:|
| OCR sur images et PDF | `tesseract-ocr`, `tesseract-ocr-fra` | Non* |
| Conversion PDF → images | `poppler-utils` (`pdftoppm`, `pdfinfo`) | Non* |
| Rendu équations LaTeX inline (`export_pdf`) | `texlive-latex-base`, `texlive-latex-extra`, `texlive-latex-recommended`, `texlive-science`, `dvipng` | Non* |
| Compilation fichier `.tex` (`export_pdf_from_tex`) | `texlive-latex-base` (`pdflatex`) | Non* |
| Polices LaTeX complémentaires | `texlive-fonts-recommended` | Non* |
| Export PDF via WeasyPrint (`export_pdf`) | `libpango-1.0-0`, `libpangoft2-1.0-0`, `libpangocairo-1.0-0`, `libcairo2`, `libgdk-pixbuf2.0-0`, `shared-mime-info`, `fonts-liberation` | Non* |
| Export LibreOffice (odt/ods/odp) | `libreoffice-nogui` | Non* |
| Extraction fichiers `.doc` legacy | `antiword` | Non* |

\* Fonctionnalité dégradée si absent, mais l'application démarre quand même.

---

## Scripts post-installation

Après `pip install -r requirements.txt`, télécharger les assets JS locaux :

```bash
python scripts/download_mermaid.py   # diagrammes Mermaid
python scripts/download_katex.py     # rendu mathématiques KaTeX
```

---

## Note : `weasyprint`

`weasyprint` n'est pas dans `requirements.txt` car ses dépendances système (Pango/Cairo/GTK)
peuvent être lourdes à installer. Pour activer l'export PDF haute qualité :

```bash
# 1. Installer les libs système (Ubuntu/Debian) — voir section ci-dessus
# 2. Puis :
pip install weasyprint
```

Sans WeasyPrint, `export_pdf` bascule automatiquement sur `reportlab` (rendu simplifié, sans formules LaTeX).

---

## Note : `pdf2image`

Le script `scripts/ingest3.py` utilise `pdf2image` (pip) en complément de
`poppler-utils` (système). Ce paquet pip est absent de `requirements.txt` car
il n'est nécessaire que pour l'ingestion RAG via ce script. Pour l'utiliser :

```bash
pip install pdf2image
```
