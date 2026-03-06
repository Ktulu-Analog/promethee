---
description: Comment envoyer (push) le projet vers GitHub et la Forge Commune
---
# Procédures de déploiement Git (Push)

Ce document décrit comment pousser les modifications de Prométhée vers les deux dépôts distants : GitHub et la Forge des Communs Numériques.

## 1. Pousser vers GitHub (origin)

Le remote `origin` correspond au fork sur GitHub (`https://github.com/Prof-Krapu/promethee-physiquechimie.git`).

Si un nouveau commit a été créé localement :
```bash
git push origin main
```
*Note : Le Personal Access Token de GitHub est déjà configuré dans l'URL du remote `origin`.*

## 2. Pousser vers la Forge des Communs Numériques (forge)

Le remote `forge` correspond au dépôt sur la Forge de l'Éducation Nationale (`git@forge.apps.education.fr:durieuxvincent/promethee.git`).

Si un nouveau commit a été créé localement :
```bash
git push forge main
```
*Note : L'authentification se fait via la clé SSH ou le jeton enregistré pour ce remote.*

## Procédure complète de mise à jour

Pour valider vos modifications locales et les envoyer sur les **deux** dépôts en même temps, suivez ces étapes :

```bash
# 1. Ajouter toutes les modifications
git add -A

# 2. Créer le commit avec un message descriptif
git commit -m "feat: [votre message de modification]"

# 3. Envoyer vers GitHub
// turbo
git push origin main

# 4. Envoyer vers la Forge
// turbo
git push forge main
```
