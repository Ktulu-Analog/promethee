---
slug: guide_web_tools
name: Guide des outils web — web_tools.py
version: "1.2"
tags: [web, recherche, scraping, navigation, fetch, rss, téléchargement, extraction]
description: >
  Référence complète des 10 outils web exposés par web_tools.py.
  À consulter avant tout appel à web_search, web_fetch, web_extract,
  web_screenshot, web_links, web_tables, web_rss, web_download_file,
  web_search_news ou web_search_engine. Contient les signatures, les
  paramètres, les valeurs de retour, les règles de chaînage entre outils,
  et le protocole de repli obligatoire en cas d'échec.
---

# Guide des outils web — `web_tools.py`

## Vue d'ensemble

`web_tools.py` expose **10 outils** répartis en trois familles :

| Famille | Outils |
|---------|--------|
| **Recherche** | `web_search`, `web_search_news`, `web_search_engine` |
| **Lecture de pages** | `web_fetch`, `web_screenshot`, `web_extract` |
| **Utilitaires** | `web_links`, `web_tables`, `web_rss`, `web_download_file` |

---

## Configuration `.env` (optionnelle)

| Variable | Valeur par défaut | Rôle |
|----------|-------------------|------|
| `WEB_SEARCH_ENGINE` | `ddg` | Moteur actif : `"ddg"` (DuckDuckGo) ou `"searxng"` |
| `WEB_SEARCH_SEARXNG_URL` | `http://localhost:8080` | URL de l'instance SearXNG locale |
| `WEB_SEARCH_DEFAULT_LANG` | `fr-FR` | Langue par défaut des résultats |

**Important :** le filtre temporel de `web_search_news` n'est pleinement efficace
qu'avec SearXNG. Avec DuckDuckGo, seule la période `"jour"` bénéficie d'un
biais de requête ; les autres périodes retournent les résultats habituels.

---

## Limites globales

| Constante | Valeur |
|-----------|--------|
| Timeout par défaut | 15 secondes |
| Résultats maximum (`web_search`) | 25 |
| Taille maximale du contenu retourné (`web_fetch`) | 40 000 caractères |

---

## Famille 1 — Recherche

### `web_search` 🔍

Recherche générale multi-moteurs. Retourne titres, URLs et extraits.
Pour lire le contenu complet d'un résultat, enchaîner avec `web_fetch`.

```json
{
  "requete": "pandas read_csv documentation",
  "limite": 10,
  "langue": "fr-FR",
  "filtre_domaine": "wikipedia.org",
  "timeout": 15
}
```

Seul `requete` est obligatoire. Supporte les opérateurs avancés :
`site:`, `filetype:`, `"phrase exacte"`, `-mot_exclu`.

**Retour :**
```json
{
  "status": "success",
  "requete": "…",
  "moteur": "ddg",
  "nombre": 8,
  "resultats": [
    { "titre": "…", "url": "…", "extrait": "…", "domaine": "…", "moteur": "DuckDuckGo" }
  ]
}
```

---

### `web_search_news` 📰

Recherche d'actualités récentes avec filtre temporel.

```json
{
  "requete": "RGPD actualité 2024",
  "periode": "semaine",
  "limite": 10,
  "langue": "fr-FR",
  "timeout": 15
}
```

Valeurs de `periode` : `"jour"` · `"semaine"` (défaut) · `"mois"` · `"annee"`.

**Retour :** même structure que `web_search`, avec le champ `"periode"` ajouté.

---

### `web_search_engine` ⚙️

Retourne la configuration du moteur actif et vérifie sa disponibilité.
Aucun paramètre requis.

```json
{}
```

**Retour :**
```json
{
  "status": "success",
  "moteur_actif": "searxng",
  "searxng_url": "http://localhost:8080",
  "searxng_version": "2.x",
  "searxng_statut": "disponible",
  "langue_defaut": "fr-FR"
}
```

Appeler cet outil en premier en cas d'erreur de connexion pour diagnostiquer
si le moteur configuré est accessible.

---

## Famille 2 — Lecture de pages

### `web_fetch` 🌐

Télécharge une page et retourne son contenu en Markdown nettoyé.
Navigation, publicités et sidebars sont supprimées par défaut.

```json
{
  "url": "https://example.com/article",
  "nettoyer": true,
  "max_caracteres": 40000,
  "timeout": 15
}
```

Seul `url` est obligatoire. Ne fonctionne qu'avec des pages HTML/XML.
Pour les fichiers binaires (PDF, images, ZIP), utiliser `web_download_file`.

**Retour :**
```json
{
  "status": "success",
  "url": "https://…",
  "titre": "Titre de la page",
  "description": "Meta description",
  "contenu": "# Titre\n\nCorps du texte…",
  "tronque": false,
  "taille_originale": 12500,
  "code_http": 200
}
```

Si `"tronque": true`, le contenu dépasse `max_caracteres`. Réduire le périmètre
avec `web_extract` + sélecteur CSS pour cibler la section utile.

---

### `web_screenshot` 📸

Retourne la structure DOM d'une page (balises, attributs, textes courts).
Outil de préparation avant d'écrire un sélecteur CSS pour `web_extract`.

```json
{
  "url": "https://example.com",
  "profondeur": 3,
  "timeout": 15
}
```

`profondeur` : de 1 (racine uniquement) à 6. Défaut : 3.

**Retour :**
```json
{
  "status": "success",
  "url": "https://…",
  "titre": "…",
  "structure_dom": "<body>\n  <main id=\"content\">\n    <article>…",
  "tronque": false
}
```

---

### `web_extract` 🎯

Extrait des éléments précis d'une page via un sélecteur CSS.
Utiliser `web_screenshot` au préalable si la structure de la page est inconnue.

```json
{
  "url": "https://example.com/produit",
  "selecteur": ".price",
  "attribut": null,
  "limite": 50,
  "timeout": 15
}
```

Paramètres obligatoires : `url` et `selecteur`.

`attribut` : si fourni, extrait l'attribut HTML plutôt que le texte.
Exemples : `"href"` (liens), `"src"` (images), `"data-id"`.

**Retour sans `attribut` :**
```json
{
  "status": "success",
  "selecteur": ".price",
  "nombre": 3,
  "nombre_retournes": 3,
  "resultats": [
    { "texte": "29,90 €", "html": "<span class=\"price\">29,90 €</span>" }
  ]
}
```

**Retour avec `attribut: "href"` :**
```json
{
  "resultats": [
    { "attribut": "href", "valeur": "https://example.com/page" }
  ]
}
```

---

## Famille 3 — Utilitaires

### `web_links` 🔗

Extrait tous les liens d'une page avec leurs textes d'ancre.
Peut filtrer par regex ou se limiter aux liens internes.

```json
{
  "url": "https://example.com",
  "filtre": "\\.pdf$",
  "internes_seulement": false,
  "limite": 100,
  "timeout": 15
}
```

Seul `url` est obligatoire.

`filtre` : expression régulière appliquée sur les URLs absolues.
Exemples utiles : `"\\.pdf$"` · `"legifrance"` · `"^https://example\\.com"`.

**Retour :**
```json
{
  "status": "success",
  "url": "https://…",
  "nombre": 14,
  "filtre_applique": "\\.pdf$",
  "liens": [
    { "url": "https://example.com/doc.pdf", "texte": "Rapport 2024", "domaine": "example.com" }
  ]
}
```

---

### `web_tables` 📊

Extrait les tableaux HTML d'une page et les retourne en JSON structuré.
Idéal pour des données tabulaires : cours, statistiques, comparatifs, horaires.

```json
{
  "url": "https://example.com/stats",
  "index": 0,
  "timeout": 15
}
```

Seul `url` est obligatoire. Si `index` est omis, retourne tous les tableaux.

**Retour (tableau unique) :**
```json
{
  "status": "success",
  "index": 0,
  "tableau": {
    "legende": "Résultats trimestriels",
    "colonnes": ["Trimestre", "CA", "Variation"],
    "nb_lignes": 4,
    "donnees": [
      { "Trimestre": "T1", "CA": "1,2 M€", "Variation": "+3 %" }
    ]
  }
}
```

Maximum 200 lignes retournées par tableau.

---

### `web_rss` 📡

Lit un flux RSS ou Atom et retourne les derniers articles.
De nombreux sites exposent leur flux à `/feed`, `/rss`, `/atom` ou `/feed.xml`.

```json
{
  "url": "https://example.com/feed",
  "limite": 10,
  "timeout": 15
}
```

Seul `url` est obligatoire. `limite` : de 1 à 50, défaut 10.

**Retour :**
```json
{
  "status": "success",
  "url": "https://…",
  "flux_titre": "Le Blog de l'Exemple",
  "format": "RSS",
  "nombre": 10,
  "articles": [
    {
      "titre": "Titre de l'article",
      "lien": "https://example.com/article-1",
      "date": "Mon, 06 Jan 2025 10:00:00 +0000",
      "resume": "Début du contenu de l'article (500 car. max)…"
    }
  ]
}
```

---

### `web_download_file` ⬇️

Télécharge un fichier binaire (PDF, image, CSV, ZIP…) et le sauvegarde localement.
Retourne le chemin du fichier enregistré.

```json
{
  "url": "https://example.com/rapport.pdf",
  "destination": "~/Documents/rapports/",
  "timeout": 60,
  "taille_max_mo": 100
}
```

Seul `url` est obligatoire.

`destination` : dossier ou chemin complet. Si dossier, le nom de fichier est
déduit de l'URL ou du header `Content-Disposition`. Si omis : `~/Téléchargements/`
ou `~/Downloads/`.

En cas de nom de fichier déjà existant, un suffixe horodaté est ajouté
automatiquement (ex. `rapport_1736150400.pdf`).

**Retour :**
```json
{
  "status": "success",
  "url": "https://…",
  "fichier": "/home/user/Documents/rapports/rapport.pdf",
  "nom": "rapport.pdf",
  "taille": "1.23 Mo",
  "type_mime": "application/pdf"
}
```

---

## Codes d'erreur communs

Tous les outils retournent `{"status": "error", "error": "…"}` en cas d'échec.

| Message | Cause probable | Action |
|---------|---------------|--------|
| `Timeout après Ns` | Serveur trop lent ou injoignable | Augmenter `timeout` ou vérifier l'URL |
| `Erreur HTTP 403` | Site bloque les requêtes automatisées | Impossible à contourner avec cet outil |
| `Erreur HTTP 404` | Page inexistante | Vérifier l'URL ou chercher une URL alternative |
| `Connexion impossible` | Pas de réseau ou domaine invalide | Vérifier la connectivité, appeler `web_search_engine` |
| `Contenu non-HTML` | URL pointant vers un PDF/image | Utiliser `web_download_file` à la place de `web_fetch` |
| `Fichier trop volumineux` | Dépasse `taille_max_mo` | Augmenter `taille_max_mo` dans `web_download_file` |

---

## Chaînages recommandés

### Rechercher puis lire un article

```
1. web_search(requete="…")               → obtenir les URLs
2. web_fetch(url="URL du meilleur résultat") → lire le contenu complet
```

### Scraping ciblé d'une donnée précise

```
1. web_screenshot(url="…")               → inspecter la structure DOM
2. web_extract(url="…", selecteur="…")   → extraire les éléments voulus
```

### Récupérer des fichiers listés sur une page

```
1. web_links(url="…", filtre="\\.pdf$")  → lister les URLs de fichiers
2. web_download_file(url="…")            → télécharger chaque fichier
```

### Veille d'actualité

```
1. web_search_news(requete="…", periode="semaine") → articles récents
2. web_fetch(url="URL article")                    → lire l'article complet
   — ou —
   web_rss(url="https://site.com/feed")            → flux structuré directement
```

---

## Erreurs fréquentes

| Erreur | Correction |
|--------|------------|
| Appeler `web_fetch` sur une URL de fichier PDF | Utiliser `web_download_file` |
| Écrire un sélecteur CSS sans connaître la structure | Appeler `web_screenshot` d'abord |
| Filtres temporels absents avec DDG | Configurer `WEB_SEARCH_ENGINE=searxng` pour les filtres de date fiables |
| Résultat tronqué dans `web_fetch` | Réduire la zone avec `web_extract` + sélecteur CSS |
| `web_search_engine` non consulté lors d'une erreur de connexion | Toujours appeler `web_search_engine` pour diagnostiquer la configuration active |
| Oublier d'encoder le regex dans `web_links` | Échapper les points : `"\\.pdf$"` et non `".pdf$"` |
| Capituler après un échec et demander à l'utilisateur quoi faire | Appliquer le protocole de repli ci-dessous — ne jamais rendre la main sans avoir épuisé les alternatives |

---

## ⚠ Règle de plafond d'appels — OBLIGATOIRE

**Ne jamais enchaîner des appels d'outils indéfiniment sans produire de texte.**
Cette règle s'applique indépendamment de toute limite technique côté serveur.

```
PLAFOND : 3 appels d'outils consécutifs du même type sans résultat satisfaisant
→ arrêter la recherche et rédiger une réponse avec ce qui a été trouvé.

PLAFOND GLOBAL : 5 appels d'outils au total sans avoir produit une seule phrase
→ produire immédiatement une réponse intermédiaire, même partielle.
```

Exemples de comportements corrects :

```
✅  web_search → aucun résultat → web_search (reformulé) → aucun résultat
    → web_fetch direct sur URL prévisible → résultat → RÉDIGER LA RÉPONSE

✅  web_search → résultat → web_fetch → web_fetch → web_fetch
    → (3 fetch atteints) → RÉDIGER avec les données collectées

❌  web_search × 5 → web_fetch × 4 → web_fetch × 3 → web_search × 3
    → (aucun texte produit) → boucle infinie jusqu'à la limite système
```

**Après chaque appel d'outil**, se poser la question :
> « Ai-je suffisamment d'information pour répondre, même partiellement ? »
> Si oui → rédiger immédiatement.
> Si non → un seul appel supplémentaire maximum avant de rédiger de toute façon.

---

## ⚠ Protocole de repli en cas d'échec — OBLIGATOIRE

**Règle fondamentale : un échec de `web_search` n'est jamais une raison de
s'arrêter et de demander à l'utilisateur comment procéder.**
L'IA doit parcourir les étapes de repli suivantes de manière autonome,
dans l'ordre, avant de conclure qu'une information est inaccessible.

### Étape 1 — `web_search` ne retourne aucun résultat

```
Action : reformuler la requête avec des termes alternatifs.

Exemple — "DINUM Wikipedia" → aucun résultat
  Repli 1 : web_search(requete="Direction interministérielle du numérique")
  Repli 2 : web_search(requete="DINUM site:fr.wikipedia.org")
  Repli 3 : web_search(requete="DINUM administration numérique France")
```

Reformulations à essayer systématiquement :
- Passer du sigle à l'intitulé complet (ou inversement)
- Supprimer ou ajouter la langue/région
- Simplifier à 2-3 mots clés
- Ajouter le nom du site cible dans la requête (`site:wikipedia.org`)

### Étape 2 — L'URL cible est connue ou devinable → `web_fetch` direct

Si la page à consulter est une ressource dont l'URL est prévisible
(Wikipedia, Légifrance, documentation officielle, etc.),
**ne pas attendre un résultat de `web_search`** : appeler `web_fetch` directement.

```
Exemples d'URLs prévisibles :
  Wikipedia FR  → https://fr.wikipedia.org/wiki/[Nom_avec_underscores]
  Wikipedia EN  → https://en.wikipedia.org/wiki/[Name]
  Légifrance    → https://www.legifrance.gouv.fr/  (puis web_search pour l'article précis)
  PyPI          → https://pypi.org/project/[nom-du-paquet]/
  MDN           → https://developer.mozilla.org/fr/docs/Web/[Sujet]
```

Protocole Wikipedia (cas le plus fréquent) :
```
1. Construire l'URL : https://fr.wikipedia.org/wiki/DINUM
2. web_fetch(url="https://fr.wikipedia.org/wiki/DINUM")
3. Si HTTP 404 → essayer la variante anglaise ou une orthographe différente
   web_fetch(url="https://fr.wikipedia.org/wiki/Direction_interminist%C3%A9rielle_du_num%C3%A9rique")
```

### Étape 3 — `web_fetch` échoue (403, timeout, contenu vide)

```
Action : chercher une source alternative contenant la même information.

  web_search(requete="DINUM présentation officielle")
  → identifier une autre URL (site officiel, rapport public, presse)
  → web_fetch sur cette URL alternative
```

Sources alternatives à privilégier, dans cet ordre :
1. Site officiel de l'organisme (`.gouv.fr`, `.org`, etc.)
2. Fiche sur un annuaire public (data.gouv.fr, bottin-admin.fr…)
3. Article de presse récent
4. Cache ou version archivée (web.archive.org si nécessaire)

### Étape 4 — Toutes les tentatives ont échoué

Seulement après avoir épuisé les étapes 1 à 3, l'IA peut informer
l'utilisateur de l'échec. Le message doit :
- Lister les tentatives effectuées et leurs résultats
- Préciser la cause probable (site bloqué, ressource inexistante, réseau)
- Proposer une synthèse basée sur les connaissances internes **si et seulement si**
  l'information est suffisamment stable pour ne pas nécessiter de vérification en ligne

```
✅  « J'ai tenté web_search avec trois formulations différentes et web_fetch
    directement sur la page Wikipedia, sans succès (HTTP 403).
    Je peux vous fournir une synthèse basée sur mes connaissances internes
    sur la DINUM, mais elle n'est pas garantie à jour. Souhaitez-vous que
    je procède ainsi ? »

❌  « Je n'ai pas pu obtenir la page. Souhaitez-vous que je reformule
    la requête ou que je fournisse une synthèse ? »
    (→ trop vague, l'IA n'a pas encore essayé les reformulations)
```

### Récapitulatif visuel

```
web_search → 0 résultat
    │
    ├─→ Reformuler (3 variantes max)        ──► résultat trouvé → web_fetch → ✅
    │
    └─→ Toujours rien
            │
            ├─→ URL prévisible ? → web_fetch direct              ──────────── ✅
            │
            └─→ web_fetch échoue
                    │
                    ├─→ Source alternative → web_fetch alternatif ─────────── ✅
                    │
                    └─→ Échec total → informer l'utilisateur avec bilan ───── ⚠
```
