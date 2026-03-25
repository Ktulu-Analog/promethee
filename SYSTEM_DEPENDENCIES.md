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
    # ── LaTeX (rendu équations) ───────────────────────────────
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    \
    # ── Conversion documents Office (export_libreoffice) ─────
    libreoffice-nogui \
    \
    # ── Extraction .doc legacy ────────────────────────────────
    antiword \
    \
    # ── Interface Qt6 / WebEngine (libs graphiques) ──────────
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libegl1 \
    libgl1 \
    libglib2.0-0 \
    libnss3 \
    libdbus-1-3
```

---

## macOS (Homebrew)

```bash
brew install \
    tesseract \
    tesseract-lang \
    poppler \
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
| MiKTeX (LaTeX) | https://miktex.org/download |

Ajouter les dossiers `bin/` de chaque outil au `PATH` système.

---

## Détail par fonctionnalité

| Fonctionnalité | Paquet(s) système | Obligatoire |
|---|---|:---:|
| OCR sur images et PDF | `tesseract-ocr`, `tesseract-ocr-fra` | Non* |
| Conversion PDF → images | `poppler-utils` (`pdftoppm`) | Non* |
| Rendu équations LaTeX | `texlive-latex-base` + extras | Non* |
| Export LibreOffice (odt/ods/odp) | `libreoffice-nogui` | Non* |
| Extraction fichiers `.doc` legacy | `antiword` | Non* |
| Affichage interface Qt6 (Linux) | libs `xcb`, `egl`, `gl` | **Oui** |

\* Fonctionnalité dégradée si absent, mais l'application démarre quand même.

---

## Scripts post-installation

Après `pip install -r requirements.txt`, télécharger les assets JS locaux :

```bash
python scripts/download_mermaid.py   # diagrammes Mermaid
python scripts/download_katex.py     # rendu mathématiques KaTeX
```

---

## Note : `pdf2image`

Le script `scripts/ingest3.py` utilise `pdf2image` (pip) en complément de
`poppler-utils` (système). Ce paquet pip est absent de `requirements.txt` car
il n'est nécessaire que pour l'ingestion RAG via ce script. Pour l'utiliser :

```bash
pip install pdf2image
```
