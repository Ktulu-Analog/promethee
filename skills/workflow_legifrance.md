---
name: Workflow Légifrance
description: Protocole de recherche juridique avec les outils Légifrance — ordre des appels, identifiants, cas d'usage, erreurs fréquentes
tags: [légifrance, judilibre, juridique, droit, recherche, protocole, jurisprudence, fonction-publique, CGFP]
version: 4.6
---

# Workflow Légifrance

## Principe : large → précis. Stopper dès les IDs obtenus.

**Règle critique d'économie** : dès qu'un appel retourne des résultats pertinents, utiliser directement les IDs trouvés. Ne PAS relancer de recherche avec une formulation différente sauf si 0 résultat utile. Chaque appel supplémentaire inutile consomme du contexte et ralentit la réponse.

```
Besoin flou    → legifrance_suggerer            → identifier le texte
Besoin ciblé   → legifrance_rechercher          → obtenir les IDs (nb_resultats=5 suffit)
Lecture code   → legifrance_consulter_code      → table des matières + CIDs
Lecture article → legifrance_article_par_numero → plus simple que le LEGIARTI
```

---

## 1. Workflows types

### Cas 1 — Article de code
```
1. legifrance_lister_codes() → trouver le code_id (LEGITEXT...)
2. legifrance_article_par_numero(code_id, num="L1234-5")
   OU legifrance_consulter_code(code_id, date) → CIDs des sections
3. legifrance_obtenir_article(article_id="LEGIARTI...")
```

### Cas 2 — Recherche thématique
```
1. legifrance_rechercher(query="télétravail agent public", fond="CODE_DATE")
2. legifrance_obtenir_article(article_id="LEGIARTI...")
```

### Cas 3 — Loi ou décret récent
```
1. legifrance_lister_loda(natures=["DECRET"], date_debut="2023-01-01", date_fin="2024-12-31")
   OU legifrance_rechercher(query="...", fond="ALL")
   ⚠️ Ne jamais passer fond="LODA" → HTTP 400. Valeurs correctes: LODA_DATE, LODA_ETAT.
2. legifrance_loi_decret(text_id="JORFTEXT...")
```

### Cas 3bis — Décrets de nomination / cessation de fonctions
Ces décrets sont abrogés dès la nomination suivante → ne pas filtrer sur en_vigueur.
```
1. legifrance_rechercher(
       query="nomination [nom complet de l'organisme]",
       fond="JORF",
       date_debut="2020-01-01",
       tri="PERTINENCE"    ← toujours PERTINENCE, jamais DATE_PUBLI_DESC
   )
   → Les décrets pertinents remontent dans les 10 premiers résultats.
   STOPPER immédiatement dès que des JORFTEXT de nominations sont identifiés.
   Ne PAS relancer avec une formulation différente si des résultats pertinents sont présents.

   OU pour lister exhaustivement par plage de dates :
   legifrance_lister_loda(
       natures=["DECRET"],
       en_vigueur_seulement=False,   ← OBLIGATOIRE
       date_debut="2020-01-01",
       date_fin="2024-12-31"
   )

2. legifrance_jorf(text_id="JORFTEXT...")       → métadonnées
3. legifrance_jorf_part(text_id="JORFTEXT...")  → contenu
```

### Cas 4 — Version à une date précise
```
legifrance_version_canonique(cid_text="LEGITEXT...", date="2019-06-01")
legifrance_version_canonique_article(article_id="LEGIARTI...")
```

### Cas 5 — Convention collective
```
1. legifrance_conventions(query="bâtiment") ou legifrance_conventions(idcc="1596")
2. legifrance_convention_texte(text_id="KALITEXT...")
```

### Cas 6 — Jurisprudence
```
1. legifrance_rechercher(query="responsabilité contractuelle", fond="JURI")
2. legifrance_jurisprudence(decision_id="JURITEXT...")
```

---

## 2. Fonds valides pour legifrance_rechercher

| Fond | Contenu |
|------|---------|
| `ALL` | Tous (défaut) |
| `CODE_DATE` / `CODE_ETAT` | Codes juridiques (par date / par état) |
| `LODA_DATE` / `LODA_ETAT` | Lois/décrets autonomes (par date / par état) |
| `JORF` | Journal Officiel |
| `JURI` / `JUFI` | Jurisprudence judiciaire |
| `CETAT` | Conseil d'État |
| `CONSTIT` | Conseil Constitutionnel |
| `KALI` | Conventions collectives |
| `CNIL` | Délibérations CNIL |
| `CIRC` | Circulaires |
| `ACCO` | Accords d'entreprise |

⚠️ `LODA`, `CODE`, `JADE` n'existent PAS → HTTP 400.

---

## 3. Identifiants

| Préfixe | Usage |
|---------|-------|
| `LEGITEXT...` | Codes, lois codifiées → legifrance_loi_decret, legifrance_consulter_code |
| `LEGIARTI...` | Article précis → legifrance_obtenir_article |
| `LEGISCTA...` | Section → legifrance_section_par_cid |
| `JORFTEXT...` | Texte JO → legifrance_jorf, legifrance_jorf_part |
| `KALITEXT...` | Convention collective → legifrance_convention_texte |
| `JURITEXT...` | Décision judiciaire → legifrance_jurisprudence |
| NOR | Code JO court (ex: EQUA2400123A) → legifrance_jo_par_nor |
| IDCC | Numéro convention (ex: 1596) → legifrance_convention_par_idcc |

---

## 4. Référence outils

**Codes** : `legifrance_lister_codes` · `legifrance_consulter_code(code_id, date)` · `legifrance_article_par_numero(code_id, num)` · `legifrance_obtenir_article(article_id)` · `legifrance_section_par_cid(cid)`

**LODA** : `legifrance_lister_loda(natures, date_debut, date_fin, en_vigueur_seulement)` · `legifrance_loi_decret(text_id)`
Natures : `LOI` `ORDONNANCE` `DECRET` `DECRET_LOI` `ARRETE` `CONSTITUTION` `DECISION` `CONVENTION` `DECLARATION` `ACCORD_FONCTION_PUBLIQUE`

**JO** : `legifrance_derniers_jo(nb)` · `legifrance_sommaire_jorf(date)` · `legifrance_jo_par_nor(nor)` · `legifrance_jorf(text_id)` · `legifrance_jorf_part(text_id)`

**Jurisprudence** : `legifrance_rechercher(fond="JURI"|"CETAT")` · `legifrance_jurisprudence(decision_id)` · `legifrance_jurisprudence_plan_classement(pdc_id)` · `legifrance_suggerer_pdc(query)`

**KALI** : `legifrance_conventions(query, idcc)` · `legifrance_convention_par_idcc(idcc)` · `legifrance_convention_texte(text_id)` · `legifrance_convention_article(article_id)` · `legifrance_convention_section(section_id)`

**ACCO** : `legifrance_suggerer_acco(query)` · `legifrance_acco(accord_id)` · `legifrance_lister_bocc(annee)` · `legifrance_lister_bocc_textes(bocc_id, idcc)`

**Circulaires** : `legifrance_circulaire(circulaire_id)` · `legifrance_lister_docs_admins(annee)`

**Parlementaire** : `legifrance_lister_legislatures()` · `legifrance_lister_dossiers_legislatifs(legislature_id)` · `legifrance_dossier_legislatif(dossier_id)` · `legifrance_lister_debats_parlementaires(legislature_id)` · `legifrance_debat(debat_id)` · `legifrance_lister_questions_parlementaires(legislature_id)`

**Versions** : `legifrance_versions_article(article_id)` · `legifrance_historique_texte(text_id, date_debut)` · `legifrance_version_canonique(cid_text, date)` · `legifrance_version_canonique_article(article_id)` · `legifrance_version_proche(cid_text, date)` · `legifrance_a_des_versions(text_id)`

**Recherche** : `legifrance_rechercher(query, fond, date_debut, date_fin, tri)` · `legifrance_suggerer(query)` · `legifrance_cnil(deliberation_id)`
Tri : `PERTINENCE` (défaut, recommandé) · `SIGNATURE_DATE_DESC` (après pertinence satisfaisante). ⚠️ `DATE_PUBLI_DESC` sans query précise retourne les documents les plus récents de la plage, ignorant la pertinence.

---

## 5. Bonnes pratiques

- **Stopper dès les IDs obtenus** : ne pas relancer si les résultats sont déjà pertinents.
- **Vérifier la date d'entrée en vigueur** : passer `date="YYYY-MM-DD"` pour obtenir la version historique.
- **Conventions collectives** : préférer l'IDCC (4 chiffres) à la recherche textuelle.
- **URLs Légifrance** : utiliser exclusivement le champ `legifrance_url` retourné par les outils — ne jamais construire manuellement.

---

## 5bis. Droit public — règle critique

**Fonctionnaires, ouvriers d'État et contractuels de droit public → Code général de la fonction publique (CGFP), pas Code du travail.**

| Population | Code applicable |
|---|---|
| Fonctionnaires (titulaires) | CGFP |
| Contractuels de droit public | CGFP |
| Ouvriers d'État | CGFP |
| Salariés de droit privé | Code du travail |
| Contractuels de droit privé (EPA, certains EPIC) | Code du travail selon statut |

Le Code du travail ne s'applique à un agent public que si un texte spécifique y renvoie expressément. En cas de doute, chercher dans le CGFP en premier.

```
legifrance_lister_codes() → repérer le LEGITEXT du CGFP
legifrance_article_par_numero(code_id="LEGITEXT...", num="L1xx-xx")
```

---

## 5ter. Décisions du Conseil d'État

Structure immuable : **Visas** → **Considérants** → **Dispositif** (après "DÉCIDE :" ou "Article 1er").
Toujours lire le dispositif en fin de décision : Rejet / Annulation / Renvoi / Sursis à exécution.
Ne pas conclure depuis les seuls considérants.

---

## 6. Judilibre (Cour de cassation)

⚠️ `www.judilibre.com` n'existe pas — utiliser les outils `judilibre_*`.

```
judilibre_rechercher(query) → liste avec identifiants
judilibre_decision(id)      → texte complet
```

| Besoin | Outil |
|--------|-------|
| Cour de cassation | `judilibre_*` |
| Jurisprudence judiciaire (index Légifrance) | `legifrance_rechercher(fond="JURI")` |
| Conseil d'État | `legifrance_rechercher(fond="CETAT")` |
| CAA | `legifrance_rechercher(fond="CETAT")` — pas de fond JADE |
| Conseil constitutionnel | `legifrance_rechercher(fond="CONSTIT")` |

---

## 7. Erreurs fréquentes

| Erreur | Correction |
|--------|------------|
| `legifrance_rechercher(fond="LODA")` | HTTP 400 → utiliser `LODA_DATE` ou `legifrance_lister_loda` |
| `legifrance_rechercher(fond="JADE")` | HTTP 400 → utiliser `fond="CETAT"` |
| `legifrance_rechercher(fond="CODE")` | HTTP 400 → utiliser `CODE_DATE` ou `CODE_ETAT` |
| Relancer une recherche après des résultats pertinents | Stopper et utiliser les IDs déjà obtenus |
| Résultats mélangés (nominations noyées dans du bruit) | Ajouter `date_debut` pour filtrer la période, garder `tri="PERTINENCE"` |
| `tri="DATE_PUBLI_DESC"` sans query ciblée | Retourne les docs les plus récents sans pertinence → résultats faux. Toujours utiliser `PERTINENCE` |
| Dates ignorées dans `lister_loda` | Vérifier que `date_debut`/`date_fin` sont bien passés |
| `en_vigueur_seulement=True` pour nominations | Ces décrets sont abrogés → toujours `False` |
| LEGIARTI dans `legifrance_loi_decret` | Attend un JORFTEXT |
| URL Légifrance construite manuellement | Utiliser le champ `legifrance_url` retourné par l'outil |
| `judilibre_*` pour le Conseil d'État | CE → `legifrance_rechercher(fond="CETAT")` |
