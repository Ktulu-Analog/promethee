---
name: Guide Grist — tableur collaboratif
description: >
  Protocole pour interagir avec une instance Grist via les outils grist_*.
  Naviguer dans les organisations et documents, lire et écrire des données,
  créer des tables et colonnes, exécuter des requêtes SQL en lecture seule.
  Grist est un tableur collaboratif open-source compatible SQLite.
tags: [grist, tableur, collaboratif, données, sql, api, organisation]
version: 1.0
---

# Guide Grist — Tableur collaboratif

Guide pour interagir avec une instance Grist via les outils disponibles dans Prométhée.

---

## 1. Workflow d'exploration

```
ÉTAPE 1 — Lister les organisations accessibles
  → grist_list_orgs()

ÉTAPE 2 — Lister les espaces de travail d'une organisation
  → grist_list_workspaces(org_id=...)
  Retourne aussi les documents contenus dans chaque workspace

ÉTAPE 3 — Explorer un document
  → grist_list_tables(doc_id="...")
  → grist_list_columns(doc_id="...", table_id="...")

ÉTAPE 4 — Lire les données
  → grist_list_records(doc_id="...", table_id="...")
  OU
  → grist_run_sql(doc_id="...", sql="SELECT ...")
```

---

## 2. Navigation dans la structure Grist

### Lister les organisations
```json
{}
```
→ `grist_list_orgs` : id, name, domain de chaque organisation accessible.

### Lister les espaces de travail
```json
{ "org_id": 42 }
```
→ `grist_list_workspaces` : workspaces avec la liste des documents qu'ils contiennent.

### Lister les documents d'un workspace
```json
{ "workspace_id": 123 }
```
→ `grist_list_docs` : id, name, isPinned, urlId pour chaque document.

### Décrire un document
```json
{ "doc_id": "ABC123xyz" }
```
→ `grist_describe_doc` : métadonnées complètes du document et de son workspace parent.

---

## 3. Explorer les tables et colonnes

### Lister les tables
```json
{ "doc_id": "ABC123xyz" }
```
→ `grist_list_tables` : identifiants techniques des tables (ex: `Table1`, `Agents`, `Congés`).

### Décrire les colonnes d'une table
```json
{
  "doc_id": "ABC123xyz",
  "table_id": "Agents"
}
```
→ `grist_list_columns` : id et champs (label, type, formule) de chaque colonne.

---

## 4. Lire les données

### Récupérer des enregistrements
```json
{
  "doc_id": "ABC123xyz",
  "table_id": "Agents",
  "limit": 100
}
```
→ `grist_list_records` : tableau d'enregistrements avec leurs champs.

### Requête SQL (lecture seule)
```json
{
  "doc_id": "ABC123xyz",
  "sql": "SELECT Nom, Grade, Service FROM Agents WHERE Actif = 1 ORDER BY Nom"
}
```
→ `grist_run_sql` : tous les documents Grist étant des bases SQLite, toute requête SELECT est possible. **Lecture seule uniquement.**

**Conseil :** utiliser `grist_run_sql` pour les requêtes complexes (jointures, agrégations, filtres) — plus puissant que `grist_list_records`.

---

## 5. Écrire des données

### Ajouter des enregistrements
```json
{
  "doc_id": "ABC123xyz",
  "table_id": "Agents",
  "records": [
    { "Nom": "Dupont", "Grade": "A", "Service": "DRH" },
    { "Nom": "Martin", "Grade": "B", "Service": "DSI" }
  ]
}
```
→ `grist_add_records` : retourne les IDs des enregistrements créés.

### Modifier des enregistrements existants
```json
{
  "doc_id": "ABC123xyz",
  "table_id": "Agents",
  "records": [
    { "id": 5, "Grade": "A+" },
    { "id": 12, "Service": "DNUM" }
  ]
}
```
→ `grist_update_records` : chaque enregistrement doit avoir un `id` (entier).

### Supprimer des enregistrements
```json
{
  "doc_id": "ABC123xyz",
  "table_id": "Agents",
  "record_ids": [5, 12, 23]
}
```
→ `grist_delete_records` ⚠️ irréversible.

---

## 6. Gérer la structure (tables et colonnes)

### Créer une table
```json
{
  "doc_id": "ABC123xyz",
  "table_id": "NouvelleTable",
  "columns": [
    { "id": "Nom",    "fields": { "label": "Nom",    "type": "Text" } },
    { "id": "Valeur", "fields": { "label": "Valeur", "type": "Numeric" } }
  ]
}
```
→ `grist_create_table`

### Ajouter des colonnes à une table existante
```json
{
  "doc_id": "ABC123xyz",
  "table_id": "Agents",
  "columns": [
    { "id": "DateEntree", "fields": { "label": "Date d'entrée", "type": "Date" } }
  ]
}
```
→ `grist_add_columns`

### Supprimer une table
```json
{
  "doc_id": "ABC123xyz",
  "table_id": "AncienneTable"
}
```
→ `grist_delete_table` ⚠️ toutes les données de la table sont perdues, irréversible.

---

## 7. Gestion des documents

| Action | Outil | Remarque |
|---|---|---|
| Créer un document vide | `grist_create_doc` | Retourne le `docId` |
| Déplacer en corbeille | `grist_move_doc_to_trash` | Restaurable depuis l'interface |
| Supprimer définitivement | `grist_delete_doc` | ⚠️ Irréversible |

---

## 8. Bonnes pratiques

- **Toujours explorer avant d'écrire** : `grist_list_tables` → `grist_list_columns` avant tout `grist_add_records` ou `grist_update_records`.
- **Préférer `grist_run_sql`** pour les lectures complexes — plus flexible et plus rapide que de charger tous les enregistrements.
- **Les IDs de colonnes sont sensibles à la casse** : utiliser exactement les noms retournés par `grist_list_columns`.
- **Les suppressions sont irréversibles** : `grist_move_doc_to_trash` est toujours préférable à `grist_delete_doc` pour les documents.

---

## 9. Erreurs fréquentes

| Erreur | Correction |
|---|---|
| Table introuvable | Vérifier l'id exact avec `grist_list_tables` (sensible à la casse) |
| Colonne non trouvée à l'écriture | Vérifier les ids avec `grist_list_columns` |
| `grist_run_sql` échoue | Vérifier que la requête est un SELECT (lecture seule uniquement) |
| Enregistrement non modifié | Vérifier que le champ `id` est bien un entier, pas une chaîne |
