---
name: Guide SQL — accès aux bases de données
description: >
  Protocole pour interroger et manipuler des bases de données avec les outils SQL.
  Workflow de connexion, exploration du schéma, requêtes SELECT et écriture,
  export CSV, bonnes pratiques de sécurité.
  Supporte SQLite, PostgreSQL et MySQL/MariaDB.
tags: [sql, base de données, sqlite, postgresql, mysql, requête, données]
version: 1.0
---

# Guide SQL — Accès aux bases de données

Guide opérationnel pour exploiter les outils SQL disponibles dans Prométhée.

---

## 1. Workflow type

```
ÉTAPE 1 — Se connecter à la base
  → sql_connect(nom="ma_base", driver="sqlite", chemin="~/data/base.db")

ÉTAPE 2 — Explorer le schéma
  → sql_list_tables(connexion="ma_base")
  → sql_describe(connexion="ma_base", table="nom_table")

ÉTAPE 3 — Interroger
  → sql_query(connexion="ma_base", sql="SELECT ...")

ÉTAPE 4 — Fermer la connexion quand c'est terminé
  → sql_disconnect(connexion="ma_base")
```

---

## 2. `sql_connect` — ouvrir une connexion

### SQLite (fichier local)
```json
{
  "nom": "ma_base",
  "driver": "sqlite",
  "chemin": "~/Documents/data.db"
}
```

### PostgreSQL
```json
{
  "nom": "pg_prod",
  "driver": "postgresql",
  "host": "localhost",
  "port": 5432,
  "database": "mon_schema",
  "user": "mon_user",
  "password": "..."
}
```

### MySQL / MariaDB
```json
{
  "nom": "mysql_local",
  "driver": "mysql",
  "host": "localhost",
  "port": 3306,
  "database": "ma_db",
  "user": "root",
  "password": "..."
}
```

`nom` est un alias libre utilisé dans tous les appels suivants pour référencer cette connexion.

---

## 3. Explorer le schéma

### Lister les tables
```json
{
  "connexion": "ma_base"
}
```
→ `sql_list_tables` : retourne nom, type (table/vue), nombre de lignes (SQLite).

### Décrire une table
```json
{
  "connexion": "ma_base",
  "table": "agents"
}
```
→ `sql_describe` : colonnes, types, nullabilité, clés primaires et étrangères.

---

## 4. `sql_query` — lire des données (SELECT)

```json
{
  "connexion": "ma_base",
  "sql": "SELECT id, nom, grade FROM agents WHERE actif = 1 ORDER BY nom LIMIT 50",
  "limite": 100
}
```

- `limite` : nombre max de lignes retournées (défaut 500, max 5000)
- Utiliser `sql_explain` pour analyser les performances avant d'exécuter une requête coûteuse

---

## 5. `sql_execute` — écrire des données (INSERT / UPDATE / DELETE / DDL)

⚠ **Opération potentiellement irréversible.** Les `DROP` et `TRUNCATE` demandent une confirmation explicite.

```json
{
  "connexion": "ma_base",
  "sql": "UPDATE agents SET grade = 'B' WHERE id = 42",
  "confirmer": true
}
```

- `confirmer: true` requis pour les opérations destructives (DROP, TRUNCATE, DELETE sans WHERE)
- Toujours utiliser des requêtes **paramétrées** — ne jamais interpoler des valeurs utilisateur dans le SQL

---

## 6. `sql_export_csv` — exporter vers un fichier CSV

```json
{
  "connexion": "ma_base",
  "sql": "SELECT * FROM agents ORDER BY nom",
  "chemin": "~/Exports/agents.csv",
  "separateur": ";"
}
```

Utile pour transférer les résultats vers Excel (`export_xlsx_csv` ou ouverture directe).

---

## 7. Gestion des connexions actives

```json
{ }   ← sql_list_connections : liste toutes les connexions actives de la session
```

La session conserve les connexions ouvertes entre les appels. Toujours fermer avec `sql_disconnect` en fin de travail.

---

## 8. Bonnes pratiques de sécurité

- **Ne jamais construire des requêtes par concaténation de chaînes** avec des données utilisateur → risque d'injection SQL.
- Utiliser des requêtes avec paramètres (`?` pour SQLite, `%s` pour PostgreSQL/MySQL) quand les valeurs proviennent de l'utilisateur.
- **Préférer `sql_query`** (lecture seule) à `sql_execute` pour toute exploration.
- Pour les bases de production, commencer par des SELECT avant tout UPDATE ou DELETE.
- `sql_explain` avant toute requête complexe sur une grande table.

---

## 9. Erreurs fréquentes à éviter

| Erreur | Correction |
|---|---|
| Oublier de fermer la connexion | Appeler `sql_disconnect` en fin de session |
| Dépasser la limite de lignes | Ajuster `limite` dans `sql_query` ou filtrer avec WHERE |
| DROP / TRUNCATE sans `confirmer: true` | L'outil retourne `cancelled` — repasser avec `confirmer: true` |
| Connexion non trouvée | Vérifier le nom exact avec `sql_list_connections` |
| Requête lente sur une grande table | Utiliser `sql_explain` pour diagnostiquer, ajouter un index si nécessaire |
