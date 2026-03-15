---
name: Guide data.gouv.fr
description: >
  Protocole pour rechercher et exploiter les données publiques françaises via data.gouv.fr.
  Rechercher des jeux de données, lister les ressources, interroger les données tabulaires
  directement ou télécharger les fichiers. Utile pour tout travail sur les données ouvertes
  de l'administration française.
tags: [datagouv, données, open-data, france, administration, csv, datasets]
version: 1.0
---

# Guide data.gouv.fr

Guide pour exploiter les données publiques françaises disponibles sur data.gouv.fr.

---

## 1. Workflow type

```
ÉTAPE 1 — Chercher un jeu de données
  → datagouv_search_datasets(query="population communes françaises")
  Retourne : liste de datasets avec id, titre, organisation, description

ÉTAPE 2 — Lister les ressources du dataset retenu
  → datagouv_list_dataset_resources(dataset_id="...")
  Retourne : liste des fichiers avec format (CSV, XLSX, JSON...), taille, URL

ÉTAPE 3a — Interroger sans télécharger (CSV/XLSX tabulaires)
  → datagouv_query_resource_data(resource_id="...", limit=100)
  Idéal pour un aperçu rapide ou un filtrage

ÉTAPE 3b — Télécharger et parser (JSON, JSONL, archives, fichiers volumineux)
  → datagouv_download_resource(resource_id="...")
```

---

## 2. `datagouv_search_datasets` — rechercher des jeux de données

```json
{
  "query": "accidents corporels circulation",
  "page_size": 10
}
```

Retourne pour chaque dataset : `id`, `title`, `organization`, `description`, `tags`, nombre de ressources.

**Conseil :** utiliser des termes précis — les jeux de données sont titrés par les producteurs (ministères, collectivités, INSEE, Santé publique France…).

---

## 3. `datagouv_list_dataset_resources` — lister les fichiers d'un dataset

```json
{
  "dataset_id": "53699233a3a729239d2046ac"
}
```

Retourne pour chaque ressource : `id`, `title`, `format`, `filesize`, URL de téléchargement.

**Règle de sélection :**
- Préférer le format `CSV` ou `XLSX` pour les données tabulaires → `datagouv_query_resource_data`
- Préférer `JSON` ou `JSONL` pour les données hiérarchiques → `datagouv_download_resource`
- Les archives `.csv.gz` sont gérées automatiquement par `datagouv_download_resource`

---

## 4. `datagouv_query_resource_data` — interroger les données tabulaires

Interroge les données CSV/XLSX via l'API Tabular de data.gouv.fr, **sans télécharger le fichier**.

```json
{
  "resource_id": "...",
  "limit": 50,
  "offset": 0
}
```

Utile pour : aperçu rapide, vérifier les colonnes disponibles, extraire un sous-ensemble.

**Limitation :** certains fichiers ne sont pas indexés dans l'API Tabular — dans ce cas, utiliser `datagouv_download_resource`.

---

## 5. `datagouv_download_resource` — télécharger et parser

```json
{
  "resource_id": "...",
  "output_path": "~/Downloads/donnees.csv"
}
```

Gère automatiquement : JSON, JSONL, CSV.GZ, et les fichiers non indexés dans Tabular.
Si `output_path` est omis, les données sont retournées directement.

---

## 6. `datagouv_get_dataset_info` — détails d'un dataset

```json
{
  "dataset_id": "..."
}
```

Retourne les métadonnées complètes : titre, description longue, organisation, tags, date de mise à jour, licence.

---

## 7. Dataservices (APIs tierces référencées)

Certaines organisations exposent des APIs directement référencées sur data.gouv.fr.

```
datagouv_search_dataservices(query="API adresse nationale")
→ liste les APIs disponibles

datagouv_get_dataservice_info(dataservice_id="...")
→ description, URL, organisation

datagouv_get_dataservice_spec(dataservice_id="...")
→ spec OpenAPI/Swagger : endpoints, paramètres, types de retour
```

---

## 8. Statistiques d'usage

```json
{
  "dataset_id": "..."
}
```
→ `datagouv_get_metrics` : visites et téléchargements mensuels.

---

## 9. Bonnes pratiques

- **Vérifier la date de mise à jour** avant d'utiliser un jeu de données — certains ne sont plus maintenus.
- **Vérifier la licence** (`datagouv_get_dataset_info`) : la plupart des données sont sous Licence Ouverte / ODbL, librement réutilisables.
- Pour les **grandes tables**, préférer `datagouv_query_resource_data` avec `limit` + `offset` pour paginer plutôt que de tout télécharger.
- En cas d'échec de `datagouv_query_resource_data` (fichier non indexé), basculer sur `datagouv_download_resource`.

---

## 10. Exemples de sources utiles

| Thème | Producteur typique |
|---|---|
| Population, emploi, logement | INSEE |
| Accidents de la route | Ministère de l'Intérieur |
| Données de santé | Santé publique France, ATIH |
| Marchés publics | Direction des Affaires Juridiques |
| Résultats électoraux | Ministère de l'Intérieur |
| Adresses et géographie | IGN, DINUM (Base Adresse Nationale) |
| Textes juridiques en masse | DILA (aussi disponible via Légifrance) |
