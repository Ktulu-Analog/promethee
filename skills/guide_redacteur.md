---
slug: guide_redacteur
name: Guide rédactionnel — Reformulation de transcriptions
version: "1.0"
tags: [rédaction, reformulation, transcription, compte-rendu, oral-vers-écrit]
description: >
  Protocole et conventions rédactionnelles pour la reformulation de transcriptions
  orales de réunion en français écrit professionnel. À lire impérativement avant
  tout appel à reformuler_docx.
---

# Guide rédactionnel — Reformulation de transcriptions orales

## Objet de ce skill

Ce guide définit les conventions rédactionnelles à appliquer lors de la
reformulation de transcriptions de réunions (comptes rendus, séances de conseil,
réunions de direction, commissions, etc.) passées de la forme orale vers la forme
écrite professionnelle.

Il est automatiquement injecté dans le prompt de `reformuler_docx` et de
`reformuler_chunk_test`.

---

## 1. Principes généraux

### 1.1 Fidélité au fond, travail sur la forme

La reformulation n'est **pas un résumé**. La règle d'or est :

> **Tout ce qui a été dit doit se retrouver dans le texte reformulé.**
> Seule la forme change, jamais le fond.

Sont conservés intégralement :
- Toutes les décisions prises et les engagements formulés.
- Tous les chiffres, dates, montants, délais, références réglementaires.
- Tous les noms propres (personnes, organismes, lieux, projets).
- Toutes les positions exprimées, y compris les désaccords et les réserves.
- Les questions posées sans réponse (elles figurent avec la mention « sans suite »
  si elles restent ouvertes en fin de séance).

### 1.2 Longueur de la reformulation

Le texte reformulé **doit rester d'une longueur proche de l'original**.
Un document de 70 pages transcrit doit produire un compte rendu d'environ
50 à 65 pages : la compression naturelle due à la suppression des scories orales
est de l'ordre de 10 à 25 %, pas davantage.

Ne jamais chercher à « aller à l'essentiel » au détriment de la complétude.

---

## 2. Suppressions autorisées (scories orales)

Supprimer **uniquement** les éléments suivants, sans les remplacer :

| Catégorie | Exemples |
|-----------|----------|
| Hésitations / phatiques | « euh », « ben », « bah », « voilà », « donc voilà », « hein » |
| Relances sans contenu | « Oui, donc, comme je disais… », « Donc on reprend… » |
| Répétitions strictes | Même phrase ou même idée répétée deux fois de suite à l'identique |
| Phrases manifestement inachevées | Phrase interrompue sans reprise de l'idée |
| Apartés hors sujet brefs | Échanges de politesse en début/fin de prise de parole (« Merci. — Je vous en prie. ») |

**Attention** : une répétition peut avoir une valeur d'insistance rhétorique.
En cas de doute, la conserver.

---

## 3. Transformations à effectuer

### 3.1 Syntaxe

- Corriger les fautes de concordance des temps et d'accord.
- Transformer les constructions orales en constructions écrites :
  - « C'est vrai que… » → « Il est vrai que… »
  - « Y'a » → « Il y a »
  - « On va faire » → « Il sera procédé à » (si contexte institutionnel)
    ou « Nous procéderons à » (si compte rendu rédigé à la 1ʳᵉ personne du pluriel)
- Compléter les phrases elliptiques dont le sens est clair.
- Mettre les nombres en toutes lettres quand ils sont inférieurs à dix et qu'ils
  ne désignent pas une mesure, un montant ou une référence.

### 3.2 Ponctuation et typographie

- Utiliser les guillemets français (« ») pour les citations, titres de documents
  cités oralement, et termes techniques employés pour la première fois.
- Respecter les règles de l'espace insécable avant « : », « ; », « ! », « ? »,
  « » » et après « « ».
- Écrire les sigles en majuscules sans points (DGSIP, pas D.G.S.I.P.).
- Dates : jour en chiffres, mois en toutes lettres, année en chiffres
  (ex. : 15 janvier 2026).

### 3.3 Structure en paragraphes

- Un paragraphe = une idée ou une prise de parole cohérente.
- Longueur cible : 4 à 8 lignes par paragraphe.
- Éviter les paragraphes d'une seule ligne (les fusionner avec le précédent ou
  le suivant si le sens le permet).
- Séparer les paragraphes d'une ligne vide.

### 3.4 Attribution des prises de parole

Si la transcription attribue les propos à des intervenants nommés :

- Conserver le prénom et le nom en début de paragraphe en **gras** ou sous la
  forme « M. / Mme [Nom] indique que… ».
- Utiliser le même format d'attribution tout au long du document (uniformité).
- Si un intervenant est désigné par sa fonction (« le Directeur », « la
  Présidente »), conserver cette désignation.

---

## 4. Registre et ton

| Contexte | Registre cible |
|----------|----------------|
| Conseil municipal / départemental / régional | Administratif formel |
| Réunion de direction d'entreprise | Professionnel neutre |
| Commission technique / groupe de travail | Professionnel technique |
| Réunion de coordination interne | Professionnel courant |

**Règle générale** : en l'absence d'instruction contraire, adopter le registre
**professionnel neutre** (vouvoiement, 3ᵉ personne, phrases complètes, absence
de familiarités).

---

## 5. Traitement des passages difficiles

### 5.1 Passage inaudible ou incompréhensible dans la transcription

Si la transcription source contient des passages manifestement erronés ou
inintelligibles (souvent indiqués par « [inaudible] », « ??? » ou une suite de
mots incohérents), les signaler de la façon suivante :

> [Passage non restituable — transcription source incomplète]

Ne jamais inventer un contenu de substitution.

### 5.2 Termes techniques ou jargon métier

- Conserver les termes techniques tels quels (ne pas les simplifier).
- Si un terme semble être une erreur de transcription phonétique (homophonie),
  corriger vers la forme la plus vraisemblable dans le contexte, sans annotation.

### 5.3 Chiffres et données

- Ne jamais modifier un chiffre, même s'il semble incohérent.
- En cas d'incohérence manifeste (ex. : « 120 % » dans un contexte où cela
  semble impossible), restituer le chiffre tel quel.

---

## 6. Ce qu'il ne faut jamais faire

- ❌ Résumer, synthétiser ou « aller à l'essentiel »
- ❌ Ajouter des informations non présentes dans la source
- ❌ Interpréter une intention non explicite
- ❌ Corriger une position exprimée même si elle semble erronée
- ❌ Supprimer des désaccords ou des tensions entre intervenants
- ❌ Modifier l'ordre chronologique des échanges
- ❌ Ajouter des titres ou sous-titres non présents dans la source
  (sauf si l'outil est configuré pour le faire via `instructions_supplementaires`)

---

## 7. Auto-vérification avant de retourner la reformulation

Avant de retourner le texte reformulé, le LLM doit vérifier mentalement :

1. [ ] Tous les chiffres et dates de la source sont-ils présents ?
2. [ ] Tous les noms propres sont-ils conservés ?
3. [ ] Toutes les décisions et engagements sont-ils restitués ?
4. [ ] La longueur est-elle raisonnablement proche de l'original ?
5. [ ] Le texte ne commence-t-il pas par un commentaire ou un préambule ?
   (retourner directement le texte reformulé, sans introduction)
