---
name: Workflow Légifrance
description: Protocole de recherche juridique avec les outils Légifrance — ordre des appels, identifiants, cas d'usage, erreurs fréquentes
tags: [légifrance, judilibre, juridique, droit, recherche, protocole, jurisprudence, fonction-publique, CGFP]
version: 4.0
---

# Workflow Légifrance

Guide opérationnel pour exploiter efficacement les outils Légifrance disponibles.

## Principe général : toujours partir du plus large vers le plus précis

```
Besoin flou    → legifrance_suggerer            → identifier le texte
Besoin ciblé   → legifrance_rechercher          → obtenir les CIDs/IDs
Lecture code   → legifrance_consulter_code      → table des matières + CIDs
Lecture article → legifrance_article_par_numero → plus simple que le LEGIARTI
```

---

## 1. Workflows types par cas d'usage

### Cas 1 — Trouver et lire un article de code (cas le plus fréquent)

```
1. legifrance_lister_codes()
   → trouver le code_id (ex: LEGITEXT000006070721 pour le Code du travail)

2. legifrance_article_par_numero(code_id="LEGITEXT...", num="L1234-5")
   → lecture directe si on connaît le numéro d'article

   OU

   legifrance_consulter_code(code_id="LEGITEXT...", date="YYYY-MM-DD")
   → table des matières avec les CIDs des sections

3. legifrance_obtenir_article(article_id="LEGIARTI...")
   → lecture d'un article par son identifiant LEGIARTI
```

### Cas 2 — Recherche thématique sans identifiant connu

```
1. legifrance_rechercher(query="télétravail agent public", fond="CODE")
   → liste de résultats avec leurs identifiants

2. legifrance_obtenir_article(article_id="LEGIARTI...")
   → lecture de l'article retenu
```

### Cas 3 — Trouver une loi ou un décret récent

```
1. legifrance_rechercher(query="...", fond="LODA")
   OU
   legifrance_lister_loda(nature="DECRET", date_debut="2023-01-01", date_fin="2024-12-31")

2. legifrance_loi_decret(text_id="JORFTEXT...")
   → texte complet
```

### Cas 4 — Vérifier la version en vigueur à une date précise

```
legifrance_version_canonique(text_id="...", date="2019-06-01")
legifrance_version_canonique_article(article_id="...", date="2019-06-01")
```

### Cas 5 — Convention collective (droit du travail privé)

```
1. legifrance_conventions(query="bâtiment") ou legifrance_conventions(idcc="1596")
   → obtenir le text_id (KALITEXT...)

2. legifrance_convention_texte(text_id="KALITEXT...")
   → texte complet de la convention
```

### Cas 6 — Jurisprudence

```
1. legifrance_rechercher(query="responsabilité contractuelle", fond="JURI")
   → liste de décisions avec identifiants

2. legifrance_jurisprudence(decision_id="JURITEXT...")
   → texte de la décision
```

---

## 2. Fonds de recherche disponibles

| Fond | Contenu |
|------|---------|
| `CODE` | Codes juridiques (Code civil, Code du travail, etc.) |
| `LODA` | Lois, ordonnances, décrets, arrêtés standalone |
| `JORF` | Journal Officiel de la République Française |
| `CNIL` | Délibérations CNIL |
| `CIRC` | Circulaires et instructions |
| `ACCO` | Accords d'entreprise |
| `KALI` | Conventions collectives |
| `JURI` | Jurisprudence judiciaire |
| `CETAT` | Jurisprudence administrative (Conseil d'État) |
| `JADE` | Jurisprudence des cours administratives d'appel |
| `CONSTIT` | Décisions du Conseil Constitutionnel |

---

## 3. Types d'identifiants : ne pas les confondre

| Identifiant | Format | Usage |
|-------------|--------|-------|
| `LEGITEXT...` | Texte dans la base | Codes, lois codifiées |
| `LEGIARTI...` | Article précis | legifrance_obtenir_article |
| `LEGISCTA...` | Section d'un code | legifrance_section_par_cid |
| `JORFTEXT...` | Texte publié au JO | legifrance_loi_decret, legifrance_jorf |
| `KALITEXT...` | Convention collective | legifrance_convention_texte |
| `JURITEXT...` | Décision judiciaire | legifrance_jurisprudence |
| NOR | Code de publication JO (`EQUA2400123A`) | legifrance_jo_par_nor |
| IDCC | Numéro de convention collective (`1596`) | legifrance_convention_par_idcc |

---

## 4. Référence des outils par famille

### Codes juridiques
```
legifrance_lister_codes()
legifrance_consulter_code(code_id, date)
legifrance_article_par_numero(code_id, num)
legifrance_obtenir_article(article_id)
legifrance_section_par_cid(cid)
```

### Lois, décrets, ordonnances (LODA)
```
legifrance_rechercher(query, fond="LODA")
legifrance_lister_loda(nature, date_debut, date_fin)
legifrance_loi_decret(text_id)
```
Natures disponibles : `LOI`, `ORDONNANCE`, `DECRET`, `ARRETE`

### Journal Officiel
```
legifrance_derniers_jo(nb)
legifrance_sommaire_jorf(date)
legifrance_jo_par_nor(nor)
legifrance_jorf(text_id)
```

### Jurisprudence
```
legifrance_rechercher(query, fond="JURI")      # judiciaire
legifrance_rechercher(query, fond="CETAT")     # administratif
legifrance_jurisprudence(decision_id)
legifrance_jurisprudence_plan_classement(pdc_id)
legifrance_suggerer_pdc(query)
```

### Conventions collectives (KALI)
```
legifrance_conventions(query, idcc)
legifrance_convention_par_idcc(idcc)
legifrance_convention_texte(text_id)
legifrance_convention_article(article_id)
legifrance_convention_section(section_id)
```

### Accords d'entreprise (ACCO)
```
legifrance_suggerer_acco(query)
legifrance_acco(accord_id)
legifrance_lister_bocc(annee)
legifrance_lister_bocc_textes(bocc_id, idcc)
```

### Circulaires et documents administratifs
```
legifrance_circulaire(circulaire_id)
legifrance_lister_docs_admins(annee)
```

### Travaux parlementaires
```
legifrance_lister_legislatures()
legifrance_lister_dossiers_legislatifs(legislature_id)
legifrance_dossier_legislatif(dossier_id)
legifrance_lister_debats_parlementaires(legislature_id)
legifrance_debat(debat_id)
legifrance_lister_questions_parlementaires(legislature_id)
```

### Historique et versions
```
legifrance_versions_article(article_id)
legifrance_historique_texte(text_id, date_debut)
legifrance_version_canonique(text_id, date)
legifrance_version_canonique_article(article_id, date)
legifrance_version_proche(text_id, date)
legifrance_a_des_versions(text_id)
```

### Recherche et suggestions
```
legifrance_rechercher(query, fond)
legifrance_suggerer(query)
legifrance_cnil(deliberation_id)
```

---

## 5. Bonnes pratiques

- **Toujours vérifier la date d'entrée en vigueur** : un article peut être abrogé ou modifié. Utiliser le paramètre `date` (format `YYYY-MM-DD`) pour obtenir le texte en vigueur à une date précise.
- **En cas d'identifiant inconnu** : commencer par `legifrance_suggerer` ou `legifrance_rechercher`, puis extraire l'identifiant de la réponse.
- **Fond LODA ≠ Fond CODE** : les lois standalone sont dans LODA, les articles codifiés sont dans CODE. Une même loi peut apparaître dans les deux.
- **Pour les conventions collectives** : toujours utiliser l'IDCC (numéro à 4 chiffres) quand connu — plus fiable que la recherche textuelle.
- **Ne jamais construire d'URL Légifrance manuellement** : utiliser exclusivement le champ `legifrance_url` retourné par les outils. Les URLs générées manuellement sont souvent fausses.

---

## 5bis. Droit public — règle critique

**Les fonctionnaires, ouvriers d'État et contractuels de droit public relèvent du Code général de la fonction publique (CGFP), pas du Code du travail.**

| Population | Code applicable |
|---|---|
| Fonctionnaires (titulaires) | Code général de la fonction publique |
| Contractuels de droit public | Code général de la fonction publique |
| Ouvriers d'État | Code général de la fonction publique |
| Salariés de droit privé | Code du travail |
| Agents contractuels de droit privé (EPA, certains EPIC) | Code du travail selon statut |

Le Code du travail ne s'applique à un agent public que si un texte spécifique y renvoie expressément (ex : certaines dispositions sur la formation, le harcèlement…). En cas de doute, chercher dans le CGFP en premier.

**Pour chercher dans le CGFP :**
```
legifrance_lister_codes()
→ repérer le LEGITEXT du Code général de la fonction publique

legifrance_article_par_numero(code_id="LEGITEXT...", num="L1xx-xx")
```

---

## 5ter. Lecture des décisions du Conseil d'État

Les décisions du Conseil d'État suivent une structure immuable :

```
1. Visas       → textes et pièces examinés (commence par "Vu...")
2. Considérants → raisonnement juridique (commence par "Considérant que...")
3. Dispositif  → LA DÉCISION EFFECTIVE (dernière partie, après "DÉCIDE :" ou "Article 1er")
```

**Toujours lire le dispositif en fin de décision** pour connaître l'issue réelle :
- **Rejet** : le recours est rejeté, l'acte attaqué est maintenu
- **Annulation** : l'acte attaqué est annulé
- **Renvoi** : l'affaire est renvoyée devant une autre juridiction
- **Sursis à exécution** : l'acte est suspendu temporairement

Ne pas conclure à partir des seuls considérants — le dispositif peut conclure différemment du raisonnement apparent.

---

## 6. Judilibre — jurisprudence de la Cour de cassation

Judilibre est distinct de Légifrance. Il expose la jurisprudence judiciaire de la Cour de cassation via ses propres outils `judilibre_*`.

**Point critique :** `www.judilibre.com` n'existe pas. Le site de référence est `www.courdecassation.fr`.

### Outils disponibles

```
judilibre_rechercher(query, ...) → liste de décisions avec identifiants
judilibre_decision(id)           → texte complet d'une décision
judilibre_scan(...)              → parcourir les décisions par lot
judilibre_taxonomie()            → récupérer les classifications thématiques
judilibre_stats()                → statistiques de la base
judilibre_historique(id)         → historique d'une décision
```

### Workflow type

```
1. judilibre_rechercher(query="responsabilité délictuelle préjudice")
   → liste de décisions avec leur identifiant

2. judilibre_decision(id="...")
   → texte intégral de la décision retenue
```

### Quand utiliser Judilibre vs Légifrance pour la jurisprudence

| Besoin | Outil |
|--------|-------|
| Jurisprudence judiciaire (Cour de cassation) | `judilibre_*` |
| Jurisprudence judiciaire (index Légifrance) | `legifrance_rechercher(fond="JURI")` |
| Jurisprudence administrative (Conseil d'État) | `legifrance_rechercher(fond="CETAT")` |
| Jurisprudence CAA | `legifrance_rechercher(fond="JADE")` |
| Décisions du Conseil constitutionnel | `legifrance_rechercher(fond="CONSTIT")` |

---

## 7. Erreurs fréquentes à éviter

| Erreur | Correction |
|--------|------------|
| Chercher un article codifié dans LODA | Utiliser le fond `CODE` |
| Utiliser un LEGIARTI dans `legifrance_loi_decret` | legifrance_loi_decret attend un JORFTEXT |
| Omettre le paramètre `date` | Sans `date`, on obtient la version actuelle — préciser la date si besoin historique |
| Confondre NOR et LEGIARTI | Le NOR est un code alphanumérique court (ex: EQUA2400123A), le LEGIARTI est long |
| Utiliser `judilibre_*` pour le Conseil d'État | Le CE est dans Légifrance fond `CETAT`, pas dans Judilibre |
| Accéder à Judilibre via www.judilibre.com | Ce site n'existe pas — utiliser les outils `judilibre_*` directement |
