# Programmes Officiels (Eduscol)

Ce dossier sert de source locale pour le moteur RAG (Génération Augmentée par la Recherche) de Prométhée concernant les programmes de Physique-Chimie.

## Fonctionnement

Lorsque le LLM est interrogé sur les limites du programme, l'outil `get_curriculum_guidelines` vérifie la présence de fichiers texte ou PDF dans ce dossier.
Si des fichiers sont présents, ils sont vectorisés (`rag_engine.ingest_file()`) et utilisés pour contraindre scrupuleusement les réponses de l'IA aux seules capacités exigibles mentionnées.

## Comment utiliser ?

1. Téléchargez les B.O. (Bulletins Officiels) officiels sur le site d'Eduscol au format PDF.
2. Déposez-les simplement dans ce dossier `data/programmes_eduscol/`.
3. (Optionnel) Renommez-les avec des noms clairs (ex: `Terminale_Specialite.pdf`, `Seconde.pdf`) pour faciliter leur identification par le modèle, bien que Prométhée gère la recherche sémantique complète du contenu.

L'ingestion sera faite automatiquement à la prochaine requête !
