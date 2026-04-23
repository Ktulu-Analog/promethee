# Changelog — Prométhée AI

Toutes les modifications notables sont documentées dans ce fichier.  
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versioning [SemVer](https://semver.org/lang/fr/).

---
## [3.0.2] — 2026-04-23

### Modifié
- 🐛 Correction d'une régression sur l'analyse d'image
- 🐛 Modification du fichier Docker pour fonctionner avec les proxies transparents (forçage HTTPS)

## [3.0.1] — 2026-04-22

### Modifié
- 🐛 Mise en cohérence de bibliothèques : suppression d'utilisation résiduelle de requests pour alignement sur httpx

### Ajouté
- 📚 Fonctions de recherche d'images dans web_tools (première source : Wikimedia)



## [3.0.0] — 2026-04-17

### Ajouté
- **Dockerisation complète** : stack Docker Compose (Prométhée + Qdrant + Garage + services init)
- **VFS avec Garage** : stockage des fichiers virtuels utilisateurs via Garage (compatible S3), en remplacement du VFS SQLite embarqué
- **Frontend React/TypeScript** (Vite) : interface web multi-utilisateurs en remplacement de l'interface Qt6 desktop
  - Authentification JWT, thème clair/sombre
  - Panneau VFS avec navigation, upload, téléchargement et quota
  - Panneau RAG, panneau Profils/Skills, panneau Admin
  - Panneau outils et composant ECharts pour la visualisation de graphiques
- **Multi-utilisateurs** : gestion complète des comptes, rôles et isolation des données
- **API FastAPI** avec WebSocket pour le streaming, routeurs REST pour auth, RAG, VFS, settings, admin
- **Bibliothèques de rendu** : LaTeX (KaTeX, assets locaux) et diagrammes Mermaid (v11, bundle local)
- **ECharts** : rendu de graphiques interactifs dans le chat via blocs `echarts`
- **Docker multi-stage** : build React intégré au Dockerfile, assets KaTeX/Mermaid téléchargés au build
- **Configuration Garage** : `garage.toml`, `Dockerfile.garage-init`, service `garage-config` Alpine pour la substitution de secrets

### Modifié
- Architecture passée de **mono-utilisateur desktop (Qt6)** à **web multi-utilisateurs (FastAPI + React)**
- VFS migré de SQLite local vers **stockage objet S3 (Garage)**
- Toutes les dépendances mises à jour (voir `requirements.txt` et `frontend/package.json`)

### Supprimé
- Interface Qt6 / PySide6
- VFS SQLite embarqué (remplacé par Garage)
- Dépendances Qt (`PySide6`, `pyqtgraph`, etc.)

---

## [2.2.4] — 2026-03

### Ajouté
- Export structuré du contenu de la réponse vers Word/LibreOffice depuis l'interface de chat (copier/coller brut markdown ou riche RTF)

### Corrigé
- Corrections de bugs sur des cas limites dans le RAG

---

## [2.2.3] — 2026-02

### Ajouté
- Outil de reformulation des comptes rendus oraux vers un style adapté à l'écrit
- Profil « Rédacteur » et skill dédié

### Corrigé
- Corrections de bugs dans le rendu LaTeX et Mermaid

---

## [2.2.2] — 2026-02

### Corrigé
- Corrections de bugs dans le RAG avec Qdrant

---

## [2.2.1] — 2026-01

### Ajouté
- Suppression de la mémoire long terme possible depuis l'interface

### Modifié
- Amélioration de la mémoire long terme (LTM) : réduction des souvenirs parasites
- Refactorisation de plusieurs modules pour améliorer la maintenabilité

### Corrigé
- Affichage des images dans le chat
- Correctifs divers sur l'interface utilisateur
