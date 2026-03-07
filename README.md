# 🔥 Prométhée AI

**Assistant IA desktop souverain** — Interface PyQt6 connectée à un LLM (OpenAI-compatible, Albert API ou Ollama), avec outils intégrés, RAG, et support Légifrance/Judilibre.

---

## ✨ Fonctionnalités

- 💬 **Chat en streaming** avec historique chiffré (AES-GCM)
- 🔧 **Outils intégrés** : web, données, export (docx/pptx/pdf), analyse de données, Python, SQL, OCR, Légifrance, Judilibre, data.gouv.fr, Thunderbird
- 📚 **RAG** (Retrieval-Augmented Generation) via Qdrant
- 🏛️ **Légifrance & Judilibre** via API PISTE
- 🖥️ **100% local possible** avec Ollama
- 🔒 **Chiffrement optionnel** de la base de données SQLite
- 🎨 **Thème clair/sombre**

---

## 🚀 Installation

### Prérequis

- Python **3.10+ (testé avec 3.12.8)**
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) *(optionnel, pour l'OCR)*

```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng

# macOS
brew install tesseract tesseract-lang
```

### Installation des dépendances

```bash
# Cloner le dépôt
git clone https://github.com/Ktulu-Analog/promethee.git
cd promethee

# Créer un environnement virtuel (recommandé)
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Installer les dépendances
pip install -r requirements.txt
```

### Configuration

```bash
# Copier le fichier de configuration
cp .env.example .env

# Éditer .env avec vos paramètres
nano .env
```

Les paramètres clés à configurer dans `.env` :

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Clé API (Albert, OpenAI, etc.) |
| `OPENAI_API_BASE` | URL du serveur LLM |
| `OPENAI_MODEL` | Modèle à utiliser |
| `OAUTH_CLIENT_ID` | Identifiants PISTE (Légifrance / Judilibre) |
| `QDRANT_URL` | URL Qdrant pour le RAG |
| `GRIST_API_KEY` | Clé API Grist |
| `GRIST_BASE_URL` | URL de l'instance Grist (défaut : `https://docs.getgrist.com`) |

### Lancement

```bash
python main.py
```

---

## 📁 Structure du projet

```
promethee/
├── core/               # Moteur : config, BDD, LLM, RAG, mémoire, outils
├── tools/              # Outils disponibles pour l'agent
├── ui/                 # Interface graphique PyQt6
│   ├── panels/         # Panneaux : chat, RAG, monitoring
│   ├── widgets/        # Composants réutilisables
│   └── dialogs/        # Boîtes de dialogue
├── skills/             # Guides de compétences injectés en contexte
├── assets/             # Logo, KaTeX
├── tests/              # Tests unitaires (pytest)
├── main.py             # Point d'entrée
├── prompts.yml         # Prompts système
├── pyproject.toml      # Métadonnées du projet
├── requirements.txt    # Dépendances Python
└── .env.example        # Modèle de configuration
```

---

## 🛠️ Outils disponibles

| Outil | Description |
|---|---|
| `web_tools` | Navigation, scraping web et recherche DuckDuckGo / SearXNG |
| `export_tools` | Génération docx, pptx, pdf, xlsx, md, odt/odp/ods (LibreOffice) |
| `export_template_tools` | Génération docx et pptx depuis un gabarit organisationnel |
| `data_tools` | Manipulation et analyse de données |
| `data_file_tools` | Chargement, transformation et export de fichiers CSV/Excel (pandas) |
| `sql_tools` | Requêtes SQL (SQLite, PostgreSQL, MySQL) |
| `ocr_tools` | OCR via Tesseract |
| `python_tools` | Exécution de code Python sandboxé (venv isolé) |
| `system_tools` | Opérations système (fichiers, dossiers, diff) |
| `skill_tools` | Consultation dynamique des guides de bonnes pratiques (skills) |
| `grist_tools` | API Grist : lecture et écriture dans des tableurs collaboratifs |
| `legifrance_tools` | API Légifrance (PISTE) |
| `judilibre_tools` | API Judilibre (PISTE) |
| `datagouv_tools` | API data.gouv.fr |
| `thunderbird_tools` | Lecture des e-mails Thunderbird |

---

## 🧪 Tests

```bash
pytest tests/
# Avec couverture :
pytest tests/ --cov=core --cov=tools
```

---

## ⚙️ Options avancées

### Utilisation avec Ollama (100% local)

Dans `.env` :
```env
LOCAL=ON
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=nemotron-3-nano:latest
```

### Chiffrement de la base de données

Dans `.env` :
```env
DB_ENCRYPTION=ON
```
Au premier lancement, une passphrase vous sera demandée.

### RAG avec Qdrant

1. Lancer Qdrant : `docker run -p 6333:6333 qdrant/qdrant`
2. Dans `.env` : `QDRANT_URL=http://localhost:6333`
3. Utiliser le panneau RAG dans l'interface pour ingérer des documents

---

## 📄 Licence

Ce projet est distribué sous licence **AGPL-3.0**.  
Voir [https://www.gnu.org/licenses/agpl-3.0.html](https://www.gnu.org/licenses/agpl-3.0.html).

---

## 👤 Auteur

Pierre COUGET — 2026
