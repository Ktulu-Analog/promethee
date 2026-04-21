# Contribuer à Prométhée AI

Merci de votre intérêt pour le projet ! Ce guide explique comment contribuer efficacement.

---

## Prérequis

- Python **3.10+** (testé avec 3.12)
- Node.js **20+** et npm
- Docker & Docker Compose (pour tester la stack complète)

---

## Mise en place de l'environnement de développement

```bash
# 1. Cloner le dépôt
git clone https://github.com/Ktulu-Analog/promethee.git
cd promethee

# 2. Backend Python
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 3. Frontend React
cd frontend
npm install
cd ..

# 4. Configuration
cp .env.example .env
# Éditer .env avec vos paramètres
```

---

## Lancement en mode développement

**Backend :**
```bash
python main.py
# ou :
uvicorn server.main:app --reload --port 8000
```

**Frontend (hot-reload) :**
```bash
cd frontend
npm run dev
# Disponible sur http://localhost:5173
```

---

## Conventions de code

### Python
- **Formateur / linter** : [Ruff](https://docs.astral.sh/ruff/) — configuration dans `pyproject.toml`
- Longueur de ligne max : **100 caractères**
- Docstrings en français pour les modules métier, anglais accepté pour les utilitaires génériques

```bash
# Vérifier
ruff check .
# Formater
ruff format .
```

### TypeScript / React
- Composants fonctionnels avec hooks
- Types stricts (voir `tsconfig.json`)

---

## Tests

```bash
# Lancer tous les tests
pytest tests/

# Avec couverture
pytest tests/ --cov=core --cov=tools

# Un seul fichier
pytest tests/test_rag.py -v
```

Tout nouveau code doit être accompagné de tests unitaires dans `tests/`.

---

## Créer un nouvel outil

Consultez [`documentation/doc_developpeur_tools.pdf`](documentation/doc_developpeur_tools.pdf) et le fichier modèle [`documentation/modele_tools.py`](documentation/modele_tools.py) avant de commencer.

---

## Soumettre une Pull Request

1. Créer une branche depuis `main` : `git checkout -b feat/ma-fonctionnalite`
2. Commiter avec des messages clairs (préfixe `feat:`, `fix:`, `docs:`, `refactor:`, `test:`)
3. S'assurer que `ruff check .` et `pytest tests/` passent sans erreur
4. Ouvrir la PR en décrivant le contexte, les changements effectués et comment tester

---

## Signaler un bug

Utiliser les [Issues GitHub](https://github.com/Ktulu-Analog/promethee/issues) en précisant :
- La version de Prométhée (`APP_VERSION` dans `.env`)
- Les étapes pour reproduire le problème
- Le comportement attendu vs observé
- Les logs pertinents (disponibles via `scripts/logview.py`)
