# Titre : ⚛️ Nouvelle surcouche "Physique-Chimie" et déploiement via Bot Telegram

## 🎯 Quel est le but de cette Pull Request ?
Cette Pull Request introduit une refonte complète permettant d'utiliser Prométhée comme un assistant spécialisé pour l'enseignement des Sciences Physiques et Chimiques, tout en le rendant accessible à distance via une **interface autonome Telegram**.

Elle ajoute également un nouveau modèle de **Vision Scientifique** capable de lire des schémas manuscrits complexes pour la correction automatique de copies.

---

## ✨ Nouvelles Fonctionnalités

### 📱 1. Serveur Telegram Autonome (`main_telegram.py`)
- **Indépendance totale** de l'interface GUI PyQt6 : un serveur léger gère l'historique et la mémoire par utilisateur.
- **Support des fichiers multi-formats** : Envoi de plus de 30 formats automatiquement (scripts Python `.py`, images, fichiers LaTeX `.tex`, `.docx`, etc.) avec injection d'un prompt système dictant à l'agent l'utilisation de `write_file`.
- **Rendu LaTeX ➔ Unicode** : Un convertisseur interne `_latex_to_telegram` permet d'afficher lisiblement les équations dans l'application Telegram (les balises telles que `\rightarrow`, `\frac`, ou `H_2O` sont remplacées à la volée).

### 📸 2. Batching Asynchrone pour la correction de copies
- Nouveau système `handle_photo` qui capture les photos envoyées.
- **Timer asyncio intelligent (30s)** : le bot attend avant d'analyser les photos pour permettre à l'utilisateur d'envoyer une copie entière (4, 5, 6 pages).
- **Prompt académique de notation** : La correction finale est imposée sur une note globale sur 20 (normalisation proportionnelle si les barèmes de l'enseignant ne totalisent pas 20).

### 👁️ 3. OCR avec Vision Scientifique via OpenRouter (`ocr_tools.py`)
- L'outil a été amélioré pour déléguer l'analyse visuelle à **Qwen3-VL-235B**, un modèle spécialisé en STEM.
- Extraction parfaite de l'écriture manuscrite, interprétation des schémas électriques, des forces mécaniques, et des mécanismes réactionnels.

### 🧰 4. Nouveaux outils pédagogiques (`tools/`)
- `physics_tools.py` : Base de constantes fondamentales (NIST / CODATA).
- `chemistry_tools.py` : Recherche moléculaire via l'API PubChem.
- `curriculum_tools.py` : Accès aux BO et programmes officiels de l'Éducation Nationale (Eduscol), jusqu'aux classes prépas (MPSI/MP). Refondu avec un système RAG (Qdrant) 100% hors-ligne alimenté par un dossier local `data/programmes_eduscol/`.
- `lms_tools.py` : Fonctionnalité pour exporter le fruit du LLM au format **Moodle XML** (pour l'import direct de quiz).
- **Hardening des descriptions d'outils** : Ajout explicite des mots-clés d'appel (comme "Eduscol" ou "NIST") dans la docstring des outils pour que le LLM sache parfaitement quand les invoquer.

### 🛠 5. Fiabilité de l'export des PDF LaTeX (`export_tools.py`)
- Ajout d'un pré-processeur `_sanitize_latex` qui nettoie le code généré par l'IA (injection automatique des paquets `amsmath`, encapsulation dans le document, etc.).
- Compilation en **2 passes**.
- Extraction et affichage clair de la ligne d'erreur `!` dans les logs de `pdflatex`.

---

## 🏗️ Impact sur l'existant
* **Backward compatibility** : L'interface PyQt6 native (lancée avec `main.py`) n'est pas altérée et hérite de toutes ces améliorations ! (Les outils `physics_tools`, `lms_tools`, etc. y sont présents).
* Le fichier `README.md` a été refondé pour documenter l'installation des deux interfaces côte à côte.
* Nettoyage du backend dans `core/` et ajout des variables `OPENROUTER_API_KEY` et `TELEGRAM_TOKEN` au fichier `.env.example`.

## 🧑‍🔬 Auteur et Licence
**Contribution soumise par :** Vincent Durieux, Professeur agrégé de Chimie.  
La licence AGPL-3.0 originale est préservée.
