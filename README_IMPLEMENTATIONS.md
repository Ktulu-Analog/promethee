# Prométhée — Bot Telegram Physique-Chimie

## Implémentations réalisées (session mars 2026)

### Architecture

```
promethee-physiquechimie/
├── main_telegram.py          # Bot Telegram (point d'entrée)
├── core/
│   ├── config.py             # Configuration (.env, clés API)
│   ├── llm_service.py        # Client OpenAI → Albert IA
│   └── tools_engine.py       # Moteur d'exécution des outils
├── tools/
│   ├── ocr_tools.py          # OCR Tesseract + Vision OpenRouter
│   ├── export_tools.py       # Export PDF/DOCX/PPTX/LaTeX
│   ├── legifrance_tools.py   # 62 outils juridiques
│   └── judilibre_tools.py    # 6 outils jurisprudence
└── .env                      # Clés API (TELEGRAM_TOKEN, OPENAI_API_KEY, OPENROUTER_API_KEY)
```

---

### 1. Interface Telegram (`main_telegram.py`)

**Commandes :** `/start`, `/help`, `/clear`

**Handlers :**
- `handle_message` — texte utilisateur → `agent_loop()` → réponse
- `handle_photo` — photos de copies → **accumulation avec timer 30s** → correction consolidée
- `handle_document` — PDF/CSV/XLSX → analyse automatique

#### Système de correction multi-photos (batching)

Quand un utilisateur envoie plusieurs photos d'une copie :
1. Chaque photo est téléchargée et ajoutée au buffer `context.user_data["photo_buffer"]`
2. Un timer `asyncio` de **30 secondes** se reset à chaque nouvelle photo
3. Quand le timer expire → `_process_photo_batch()` envoie toutes les pages à l'agent en **un seul appel**
4. Le prompt inclut des **règles strictes** :
   - Transcription OCR page par page via `ocr_vision_openrouter`
   - Consolidation en un seul document
   - **UNE seule note globale sur 20**
   - **Normalisation proportionnelle** si le barème total ≠ 20 (`note = (obtenu/total) × 20`)

#### Convertisseur LaTeX → Unicode (`_latex_to_telegram`)

Telegram ne supporte pas le rendu LaTeX. Toutes les réponses passent par un convertisseur :

| LaTeX | Unicode |
|-------|---------|
| `\alpha`, `\Delta`, `\omega` | α, Δ, ω |
| `\rightarrow`, `\Rightarrow` | →, ⇒ |
| `\frac{a}{b}` | a/b |
| `x^2`, `H_2O` | x², H₂O |
| `\times`, `\pm`, `\leq` | ×, ±, ≤ |
| `\( ... \)`, `\[ ... \]` | Retrait des délimiteurs |
| Tableaux Markdown `\|col\|` | Texte structuré avec bullets ▸▹ |

#### Envoi automatique de fichiers (30 formats)

Tout fichier généré par les outils est détecté dans la réponse et envoyé automatiquement via `context.bot.send_document()`.

| Catégorie | Extensions |
|---|---|
| **Scripts/Web** | `.py`, `.sh`, `.js`, `.html`, `.css` |
| **Images** | `.jpg`, `.jpeg`, `.png`, `.gif`, `.svg` |
| **Documents** | `.pdf`, `.docx`, `.doc`, `.odt`, `.txt`, `.csv`, `.md`, `.json`, `.yaml`, `.yml` |
| **Tableurs/Présentations** | `.xlsx`, `.xls`, `.pptx`, `.ppsx`, `.ods`, `.odp` |
| **Autres** | `.tex`, `.xml`, `.zip`, `.tar`, `.gz` |

Un **prompt système** est injecté à la première interaction pour que l'IA utilise `write_file` et affiche le chemin absolu du fichier — ce qui déclenche l'envoi automatique.

---

### 2. OCR Vision scientifique (`tools/ocr_tools.py`)

**Outil :** `ocr_vision_openrouter`

- **Modèle :** `qwen/qwen3-vl-235b-a22b-thinking` (235B paramètres, spécialisé STEM)
- **Transport :** Encodage Base64 + requête HTTP POST vers OpenRouter API
- **Prompt scientifique injecté automatiquement** avant le prompt utilisateur :
  - Transcription fidèle du texte et des formules (LaTeX `$` et `$$`)
  - Description exhaustive des schémas :
    - Circuits électriques (convention européenne)
    - Courbes de titrage (points d'équivalence)
    - Mécanismes réactionnels (flèches courbes)
    - Vecteurs forces/vitesses

---

### 3. Export PDF LaTeX (`tools/export_tools.py`)

**Outil :** `export_pdf_latex`

- Compilation via `pdflatex` en 2 passes (timeout 180s)
- **Pré-processeur `_sanitize_latex()`** pour corriger les erreurs LLM :
  - Auto-encapsulation si pas de `\documentclass`
  - Injection automatique des packages `amsmath`, `amssymb`, `inputenc`, `fontenc`
  - Conversion Markdown → LaTeX (`**gras**` → `\textbf{}`, `# Titre` → `\section{}`)
  - Retrait des clôtures ` ```latex ``` `
  - Conversion `---` → `\hrule`
- **Messages d'erreur améliorés** : extraction des lignes `!` du log LaTeX + suggestions de packages

---

### 4. Configuration sécurisée (`core/config.py` + `main_telegram.py`)

- **Purge des variables shell parasites** au démarrage (`OPENAI_API_KEY`, `OPENAI_BASE_URL` issues de DeepSeek/OpenCode)
- `load_dotenv(override=True)` pour que le `.env` du projet prenne toujours le dessus
- Exports DeepSeek commentés dans `~/.bashrc` (préfixe `#DISABLED_BY_PROMETHEE#`)

---

### Clés API requises (`.env`)

```env
# Albert IA (modèle principal)
OPENAI_API_KEY=sk-eyJ...
OPENAI_BASE_URL=https://albert.api.etalab.gouv.fr/v1

# OpenRouter (OCR Vision Qwen3-VL)
OPENROUTER_API_KEY=sk-or-v1-...

# Telegram Bot
TELEGRAM_TOKEN=1234567890:AAH...
```

### Lancement

```bash
cd promethee-physiquechimie
source .venv/bin/activate
python3 main_telegram.py
```

### Prérequis système

- Python 3.11+
- TeX Live (`pdflatex`) pour l'export PDF LaTeX
- Packages Python : `python-telegram-bot>=20`, `python-dotenv`, `openai`, `requests`
