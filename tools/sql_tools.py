# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
tools/sql_tools.py — Outils SQL génériques (SQLite, PostgreSQL, MySQL)
=======================================================================

Outils exposés (10) :

  Connexions (2) :
    - sql_connect       : ouvre une connexion nommée vers une base de données
    - sql_disconnect    : ferme une connexion et libère les ressources

  Exploration (3) :
    - sql_list_tables   : liste les tables/vues d'une base
    - sql_describe      : décrit le schéma d'une table (colonnes, types, clés)
    - sql_list_connections : liste les connexions actives en session

  Exécution (3) :
    - sql_query         : exécute un SELECT et retourne les résultats en JSON
    - sql_execute       : exécute INSERT/UPDATE/DELETE/CREATE (avec confirmation)
    - sql_explain       : affiche le plan d'exécution d'une requête

  Utilitaires (2) :
    - sql_export_csv         : exporte le résultat d'une requête en CSV local
    - sql_detect_instances   : détecte les instances de BdD actives sur le système local

Stratégie :
  - Les connexions sont nommées et maintenues en mémoire pour la session
  - SQLite : natif Python, aucune dépendance
  - PostgreSQL : nécessite psycopg2 (pip install psycopg2-binary)
  - MySQL/MariaDB : nécessite pymysql (pip install pymysql)
  - Les requêtes SELECT sont limitées en nombre de lignes (défaut 500)
  - sql_execute requiert confirm=true pour les opérations destructives (DROP, TRUNCATE)

Format d'URL de connexion :
  SQLite    : sqlite:///chemin/vers/base.db  ou  sqlite:///:memory:
  PostgreSQL: postgresql://user:password@host:5432/database
  MySQL     : mysql://user:password@host:3306/database
"""

import csv
import json
import re
import sqlite3
import time
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Any

from core.tools_engine import tool, set_current_family, _TOOL_ICONS

set_current_family("sql_tools", "SQL", "🗄️")

# ── Icônes ────────────────────────────────────────────────────────────────────
_TOOL_ICONS.update({
    "sql_connect":          "🔌",
    "sql_disconnect":       "🔒",
    "sql_list_tables":      "📋",
    "sql_describe":         "🔎",
    "sql_list_connections": "📡",
    "sql_query":            "🗃️",
    "sql_execute":          "⚡",
    "sql_explain":          "🧠",
    "sql_export_csv":       "📤",
    "sql_detect_instances": "🔍",
})

# ── Registre de connexions (session) ─────────────────────────────────────────
# { nom: { "conn": objet_connexion, "driver": str, "url_safe": str,
#           "opened_at": str, "read_only": bool } }
_CONNECTIONS: dict[str, dict] = {}

_MAX_ROWS = 500          # limite SELECT par défaut
_MAX_ROWS_HARD = 5000    # limite absolue
_DESTRUCTIVE_KEYWORDS = frozenset(["DROP", "TRUNCATE", "DELETE", "UPDATE", "INSERT",
                                    "CREATE", "ALTER", "REPLACE", "MERGE"])


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _detect_driver(url: str) -> str:
    """Détecte le driver depuis l'URL de connexion."""
    u = url.lower().strip()
    if u.startswith("sqlite"):
        return "sqlite"
    if u.startswith("postgresql") or u.startswith("postgres"):
        return "postgresql"
    if u.startswith("mysql") or u.startswith("mariadb"):
        return "mysql"
    raise ValueError(
        f"Format d'URL non reconnu : '{url[:40]}'. "
        "Formats supportés : sqlite:///..., postgresql://..., mysql://..."
    )


def _safe_url(url: str) -> str:
    """Masque le mot de passe dans l'URL pour l'affichage."""
    return re.sub(r"(:)[^:@]+(@)", r"\1****\2", url)


def _open_connection(url: str, read_only: bool = False):
    """Ouvre une connexion selon le driver détecté. Retourne (conn, driver).

    En mode read_only=True :
      - SQLite    : ouverture via URI avec ?mode=ro (rejet OS-level de toute écriture)
      - PostgreSQL: SET default_transaction_read_only = on après connexion
      - MySQL     : SET SESSION TRANSACTION READ ONLY
    """
    driver = _detect_driver(url)

    if driver == "sqlite":
        path = re.sub(r"^sqlite:///", "", url, flags=re.I)
        if not path:
            path = ":memory:"
        if path != ":memory:":
            p = Path(path).expanduser()
            if read_only:
                # URI SQLite avec mode=ro : toute écriture est rejetée par le driver
                conn = sqlite3.connect(
                    f"file:{p}?mode=ro",
                    uri=True,
                    check_same_thread=False,
                )
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(p), check_same_thread=False)
        else:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

    if driver == "postgresql":
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise ImportError(
                "psycopg2 non installé. Installez-le avec l'outil python_install : "
                "pip install psycopg2-binary"
            )
        m = re.match(
            r"postgresql://(?:([^:@]+)(?::([^@]*))?@)?([^:/]+)(?::(\d+))?/(.+)",
            url, re.I
        )
        if not m:
            raise ValueError(f"URL PostgreSQL invalide : {_safe_url(url)}")
        user, pwd, host, port, dbname = m.groups()
        conn = psycopg2.connect(
            host=host, port=int(port or 5432),
            dbname=dbname, user=user, password=pwd or "",
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        conn.autocommit = False
        if read_only:
            cur = conn.cursor()
            cur.execute("SET default_transaction_read_only = on")
            conn.commit()
        return conn, "postgresql"

    if driver == "mysql":
        try:
            import pymysql
            import pymysql.cursors
        except ImportError:
            raise ImportError(
                "pymysql non installé. Installez-le avec l'outil python_install : "
                "pip install pymysql"
            )
        m = re.match(
            r"mysql://(?:([^:@]+)(?::([^@]*))?@)?([^:/]+)(?::(\d+))?/(.+)",
            url, re.I
        )
        if not m:
            raise ValueError(f"URL MySQL invalide : {_safe_url(url)}")
        user, pwd, host, port, dbname = m.groups()
        conn = pymysql.connect(
            host=host, port=int(port or 3306),
            db=dbname, user=user, password=pwd or "",
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
        if read_only:
            cur = conn.cursor()
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            conn.commit()
        return conn, "mysql"

    raise ValueError(f"Driver non supporté : {driver}")


def _serialize(val: Any) -> Any:
    """Convertit les types non-JSON-sérialisables."""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, timedelta):
        return str(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, bytes):
        return f"<binaire {len(val)} octets>"
    if isinstance(val, memoryview):
        return f"<binaire {len(val)} octets>"
    return val


def _row_to_dict(row) -> dict:
    """Convertit une Row (sqlite/psycopg2/pymysql) en dict sérialisable."""
    if isinstance(row, sqlite3.Row):
        d = dict(row)
    elif isinstance(row, dict):
        d = row
    else:
        d = dict(row)
    return {k: _serialize(v) for k, v in d.items()}


def _get_conn(nom: str) -> tuple:
    """Retourne (conn, driver) pour une connexion nommée, ou lève une erreur."""
    if nom not in _CONNECTIONS:
        noms = list(_CONNECTIONS.keys())
        hint = f" Connexions actives : {noms}." if noms else " Aucune connexion active."
        raise KeyError(
            f"Connexion '{nom}' introuvable.{hint} "
            "Utilisez sql_connect pour ouvrir une connexion."
        )
    return _CONNECTIONS[nom]["conn"], _CONNECTIONS[nom]["driver"]


def _is_destructive(sql: str) -> bool:
    """Vérifie si la requête est une opération d'écriture/destructive."""
    first_word = sql.strip().split()[0].upper() if sql.strip() else ""
    return first_word in _DESTRUCTIVE_KEYWORDS


def _execute_query(conn, driver: str, sql: str, params=None):
    """Exécute une requête et retourne le curseur."""
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur


# ══════════════════════════════════════════════════════════════════════════════
# OUTILS
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="sql_connect",
    description=(
        "Ouvre une connexion vers une base de données et l'enregistre sous un nom. "
        "Supporte SQLite, PostgreSQL et MySQL/MariaDB. "
        "La connexion reste active pour toute la session. "
        "Utilisez read_only=true pour une connexion en lecture seule : "
        "sql_execute sera alors systématiquement bloqué sur cette connexion, "
        "même si le LLM tente une écriture. "
        "Formats d'URL : "
        "sqlite:///chemin/vers/base.db — "
        "postgresql://user:password@host:5432/database — "
        "mysql://user:password@host:3306/database. "
        "Pour SQLite en mémoire : sqlite:///:memory:"
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL de connexion à la base de données.",
            },
            "nom": {
                "type": "string",
                "description": (
                    "Nom court pour identifier cette connexion dans les autres outils "
                    "(ex: 'prod', 'local', 'analytics'). Défaut : 'default'."
                ),
            },
            "read_only": {
                "type": "boolean",
                "description": (
                    "Si true, la connexion est ouverte en lecture seule : "
                    "sql_execute sera bloqué, seuls sql_query et sql_export_csv "
                    "sont autorisés. Recommandé pour les bases de production. "
                    "Défaut : false."
                ),
            },
        },
        "required": ["url"],
    },
)
def sql_connect(url: str, nom: str = "default", read_only: bool = False) -> dict:
    try:
        # Fermer une connexion existante avec le même nom
        if nom in _CONNECTIONS:
            try:
                _CONNECTIONS[nom]["conn"].close()
            except Exception:
                pass

        conn, driver = _open_connection(url, read_only=read_only)

        _CONNECTIONS[nom] = {
            "conn":       conn,
            "driver":     driver,
            "url_safe":   _safe_url(url),
            "opened_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "read_only":  read_only,
        }

        # Test de connexion
        if driver == "sqlite":
            cur = conn.execute("SELECT sqlite_version()")
            version = cur.fetchone()[0]
        elif driver == "postgresql":
            cur = conn.cursor()
            cur.execute("SELECT version()")
            version = cur.fetchone()["version"].split()[0:2]
            version = " ".join(version)
            conn.rollback()
        else:  # mysql
            cur = conn.cursor()
            cur.execute("SELECT VERSION()")
            row = cur.fetchone()
            version = list(row.values())[0] if isinstance(row, dict) else str(row)

        mode = "lecture seule 🔒" if read_only else "lecture/écriture"
        return {
            "status":    "success",
            "nom":       nom,
            "driver":    driver,
            "url":       _safe_url(url),
            "version":   version,
            "read_only": read_only,
            "message":   f"Connexion '{nom}' ouverte ({driver}, {mode}).",
        }

    except ImportError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Impossible de se connecter : {e}"}


@tool(
    name="sql_disconnect",
    description=(
        "Ferme une connexion à une base de données et libère les ressources. "
        "Utilisez sql_list_connections pour voir les connexions actives."
    ),
    parameters={
        "type": "object",
        "properties": {
            "nom": {
                "type": "string",
                "description": "Nom de la connexion à fermer (défaut: 'default').",
            },
        },
        "required": [],
    },
)
def sql_disconnect(nom: str = "default") -> dict:
    if nom not in _CONNECTIONS:
        return {
            "status": "error",
            "error": f"Connexion '{nom}' introuvable.",
            "connexions_actives": list(_CONNECTIONS.keys()),
        }
    try:
        _CONNECTIONS[nom]["conn"].close()
    except Exception:
        pass
    info = _CONNECTIONS.pop(nom)
    return {
        "status":  "success",
        "nom":     nom,
        "driver":  info["driver"],
        "message": f"Connexion '{nom}' fermée.",
    }


@tool(
    name="sql_list_connections",
    description=(
        "Liste toutes les connexions SQL actives en session : "
        "nom, driver, URL (mot de passe masqué), heure d'ouverture."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def sql_list_connections() -> dict:
    if not _CONNECTIONS:
        return {
            "status":    "success",
            "nombre":    0,
            "connexions": [],
            "message":   "Aucune connexion active. Utilisez sql_connect pour en ouvrir une.",
        }
    connexions = [
        {
            "nom":        nom,
            "driver":     info["driver"],
            "url":        info["url_safe"],
            "ouverte_le": info["opened_at"],
            "read_only":  info.get("read_only", False),
            "mode":       "lecture seule 🔒" if info.get("read_only") else "lecture/écriture",
        }
        for nom, info in _CONNECTIONS.items()
    ]
    return {
        "status":     "success",
        "nombre":     len(connexions),
        "connexions": connexions,
    }


@tool(
    name="sql_list_tables",
    description=(
        "Liste toutes les tables (et vues) disponibles dans une base de données. "
        "Retourne le nom, le type (table/vue) et pour SQLite la taille estimée."
    ),
    parameters={
        "type": "object",
        "properties": {
            "connexion": {
                "type": "string",
                "description": "Nom de la connexion (défaut: 'default').",
            },
            "schema": {
                "type": "string",
                "description": "Schéma à lister (PostgreSQL uniquement, défaut: 'public').",
            },
        },
        "required": [],
    },
)
def sql_list_tables(connexion: str = "default", schema: str = "public") -> dict:
    try:
        conn, driver = _get_conn(connexion)
        tables = []

        if driver == "sqlite":
            cur = conn.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY type, name"
            )
            for row in cur.fetchall():
                name, typ = row[0], row[1]
                count_cur = conn.execute(f'SELECT COUNT(*) FROM "{name}"')
                nb = count_cur.fetchone()[0]
                tables.append({"nom": name, "type": typ, "nb_lignes_approx": nb})

        elif driver == "postgresql":
            cur = conn.cursor()
            cur.execute(
                """SELECT table_name, table_type
                   FROM information_schema.tables
                   WHERE table_schema = %s
                   ORDER BY table_type, table_name""",
                (schema,)
            )
            for row in cur.fetchall():
                tables.append({
                    "nom":  row["table_name"],
                    "type": "vue" if row["table_type"] == "VIEW" else "table",
                })
            conn.rollback()

        else:  # mysql
            cur = conn.cursor()
            cur.execute(
                "SELECT TABLE_NAME, TABLE_TYPE, TABLE_ROWS "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "ORDER BY TABLE_TYPE, TABLE_NAME"
            )
            for row in cur.fetchall():
                tables.append({
                    "nom":  row["TABLE_NAME"],
                    "type": "vue" if row["TABLE_TYPE"] == "VIEW" else "table",
                    "nb_lignes_approx": row.get("TABLE_ROWS"),
                })

        return {
            "status":  "success",
            "connexion": connexion,
            "driver":  _CONNECTIONS[connexion]["driver"],
            "nombre":  len(tables),
            "tables":  tables,
        }

    except KeyError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Erreur liste tables : {e}"}


@tool(
    name="sql_describe",
    description=(
        "Décrit le schéma d'une table : colonnes, types, nullabilité, "
        "valeurs par défaut, clés primaires et étrangères."
    ),
    parameters={
        "type": "object",
        "properties": {
            "table": {
                "type": "string",
                "description": "Nom de la table à décrire.",
            },
            "connexion": {
                "type": "string",
                "description": "Nom de la connexion (défaut: 'default').",
            },
            "schema": {
                "type": "string",
                "description": "Schéma PostgreSQL (défaut: 'public').",
            },
        },
        "required": ["table"],
    },
)
def sql_describe(table: str, connexion: str = "default", schema: str = "public") -> dict:
    try:
        conn, driver = _get_conn(connexion)
        colonnes = []
        cles_primaires = []
        cles_etrangeres = []

        if driver == "sqlite":
            cur = conn.execute(f'PRAGMA table_info("{table}")')
            for row in cur.fetchall():
                col = {
                    "nom":        row["name"],
                    "type":       row["type"],
                    "nullable":   not row["notnull"],
                    "defaut":     row["dflt_value"],
                    "cle_primaire": bool(row["pk"]),
                }
                colonnes.append(col)
                if row["pk"]:
                    cles_primaires.append(row["name"])

            # Clés étrangères
            cur_fk = conn.execute(f'PRAGMA foreign_key_list("{table}")')
            for row in cur_fk.fetchall():
                cles_etrangeres.append({
                    "colonne":     row["from"],
                    "table_ref":   row["table"],
                    "colonne_ref": row["to"],
                })

        elif driver == "postgresql":
            cur = conn.cursor()
            cur.execute(
                """SELECT
                    c.column_name, c.data_type, c.is_nullable,
                    c.column_default, c.character_maximum_length,
                    c.numeric_precision
                   FROM information_schema.columns c
                   WHERE c.table_schema = %s AND c.table_name = %s
                   ORDER BY c.ordinal_position""",
                (schema, table)
            )
            for row in cur.fetchall():
                colonnes.append({
                    "nom":      row["column_name"],
                    "type":     row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "defaut":   row["column_default"],
                    "longueur": row["character_maximum_length"],
                })
            # Clés primaires
            cur.execute(
                """SELECT kcu.column_name
                   FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu
                     ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                   WHERE tc.table_schema = %s AND tc.table_name = %s
                     AND tc.constraint_type = 'PRIMARY KEY'
                   ORDER BY kcu.ordinal_position""",
                (schema, table)
            )
            cles_primaires = [r["column_name"] for r in cur.fetchall()]
            # Clés étrangères
            cur.execute(
                """SELECT
                    kcu.column_name,
                    ccu.table_name  AS table_ref,
                    ccu.column_name AS colonne_ref
                   FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu
                     ON tc.constraint_name = kcu.constraint_name
                   JOIN information_schema.constraint_column_usage ccu
                     ON ccu.constraint_name = tc.constraint_name
                   WHERE tc.table_schema = %s AND tc.table_name = %s
                     AND tc.constraint_type = 'FOREIGN KEY'""",
                (schema, table)
            )
            cles_etrangeres = [dict(r) for r in cur.fetchall()]
            conn.rollback()

        else:  # mysql
            cur = conn.cursor()
            cur.execute(f"DESCRIBE `{table}`")
            for row in cur.fetchall():
                is_pk = "PRI" in (row.get("Key") or "")
                colonnes.append({
                    "nom":          row["Field"],
                    "type":         row["Type"],
                    "nullable":     row["Null"] == "YES",
                    "defaut":       row["Default"],
                    "cle_primaire": is_pk,
                    "extra":        row.get("Extra", ""),
                })
                if is_pk:
                    cles_primaires.append(row["Field"])

        if not colonnes:
            return {
                "status": "error",
                "error":  f"Table '{table}' introuvable ou vide.",
            }

        return {
            "status":          "success",
            "connexion":       connexion,
            "table":           table,
            "nb_colonnes":     len(colonnes),
            "colonnes":        colonnes,
            "cles_primaires":  cles_primaires,
            "cles_etrangeres": cles_etrangeres,
        }

    except KeyError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Erreur describe : {e}"}


@tool(
    name="sql_query",
    description=(
        "Exécute une requête SELECT et retourne les résultats en JSON. "
        "Limité à 500 lignes par défaut (configurable jusqu'à 5000). "
        "Supporte les paramètres liés pour éviter les injections SQL : "
        "utiliser ? (SQLite/MySQL) ou %s (PostgreSQL) comme placeholders, "
        "et passer les valeurs dans le champ 'params'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Requête SELECT à exécuter.",
            },
            "connexion": {
                "type": "string",
                "description": "Nom de la connexion (défaut: 'default').",
            },
            "params": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Valeurs des paramètres liés (ex: ['Alice', '2024']).",
            },
            "limite": {
                "type": "integer",
                "description": f"Nombre max de lignes (défaut: {_MAX_ROWS}, max: {_MAX_ROWS_HARD}).",
            },
        },
        "required": ["sql"],
    },
)
def sql_query(
    sql: str,
    connexion: str = "default",
    params: Optional[list] = None,
    limite: int = _MAX_ROWS,
) -> dict:
    limite = min(max(1, limite), _MAX_ROWS_HARD)
    sql_clean = sql.strip()

    # Sécurité : n'autoriser que les SELECT (et WITH pour les CTE)
    first_word = sql_clean.split()[0].upper() if sql_clean else ""
    if first_word not in ("SELECT", "WITH", "EXPLAIN", "PRAGMA", "SHOW", "DESCRIBE"):
        return {
            "status": "error",
            "error":  (
                f"sql_query n'accepte que les requêtes de lecture (SELECT, WITH, EXPLAIN…). "
                f"Pour les écritures, utilisez sql_execute. Requête rejetée : '{first_word}'."
            ),
        }

    try:
        conn, driver = _get_conn(connexion)

        # Adapter les placeholders selon le driver
        sql_exec = sql_clean
        if driver == "postgresql" and params:
            sql_exec = sql_clean.replace("?", "%s")

        # Ajouter LIMIT si absent
        if "LIMIT" not in sql_exec.upper():
            sql_exec = f"{sql_exec.rstrip(';')} LIMIT {limite}"

        t0 = time.perf_counter()
        cur = _execute_query(conn, driver, sql_exec, params)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        if driver == "postgresql":
            conn.rollback()

        rows_raw = cur.fetchall()
        colonnes = [desc[0] for desc in cur.description] if cur.description else []
        rows = [_row_to_dict(r) for r in rows_raw]

        return {
            "status":       "success",
            "connexion":    connexion,
            "sql":          sql_clean,
            "nb_lignes":    len(rows),
            "tronque":      len(rows) >= limite,
            "colonnes":     colonnes,
            "lignes":       rows,
            "duree_ms":     elapsed_ms,
        }

    except KeyError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Erreur requête : {e}"}


@tool(
    name="sql_execute",
    description=(
        "Exécute une requête d'écriture : INSERT, UPDATE, DELETE, CREATE, ALTER, DROP. "
        "⚠️ Les opérations destructives (DROP, TRUNCATE, DELETE sans WHERE) "
        "nécessitent confirmer=true. "
        "Retourne le nombre de lignes affectées et valide automatiquement (COMMIT). "
        "En cas d'erreur, effectue un ROLLBACK."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Requête SQL à exécuter (INSERT, UPDATE, DELETE, CREATE…).",
            },
            "connexion": {
                "type": "string",
                "description": "Nom de la connexion (défaut: 'default').",
            },
            "params": {
                "type": "array",
                "items": {},
                "description": "Valeurs des paramètres liés.",
            },
            "confirmer": {
                "type": "boolean",
                "description": (
                    "Requis à true pour DROP, TRUNCATE et DELETE sans clause WHERE."
                ),
            },
        },
        "required": ["sql"],
    },
)
def sql_execute(
    sql: str,
    connexion: str = "default",
    params: Optional[list] = None,
    confirmer: bool = False,
) -> dict:
    sql_clean = sql.strip()
    first_word = sql_clean.split()[0].upper() if sql_clean else ""

    # ── Vérification read_only avant tout ────────────────────────────────────
    # Ce contrôle est applicatif (couche de défense) ; pour SQLite le driver
    # bloque aussi au niveau OS (uri?mode=ro), et pour PG/MySQL la session est
    # configurée en read-only côté serveur. Les trois niveaux sont cumulatifs.
    if connexion in _CONNECTIONS and _CONNECTIONS[connexion].get("read_only"):
        return {
            "status": "error",
            "error": (
                f"La connexion '{connexion}' est en lecture seule (read_only=true). "
                "sql_execute est interdit sur cette connexion. "
                "Utilisez sql_query pour les lectures, ou ouvrez une nouvelle connexion "
                "sans read_only pour les écritures."
            ),
            "sql": sql_clean,
        }

    # ── Vérification des opérations destructives ─────────────────────────────
    needs_confirm = (
        first_word in ("DROP", "TRUNCATE") or
        (first_word == "DELETE" and "WHERE" not in sql_clean.upper())
    )
    if needs_confirm and not confirmer:
        return {
            "status":  "warning",
            "message": (
                f"L'opération '{first_word}' est potentiellement destructive et irréversible. "
                "Passez confirmer=true pour l'exécuter."
            ),
            "sql": sql_clean,
        }

    try:
        conn, driver = _get_conn(connexion)

        sql_exec = sql_clean
        if driver == "postgresql" and params:
            sql_exec = sql_clean.replace("?", "%s")

        t0 = time.perf_counter()
        try:
            cur = _execute_query(conn, driver, sql_exec, params)
            conn.commit()
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {"status": "error", "error": f"Erreur exécution (rollback effectué) : {e}"}

        # Récupérer l'ID inséré si disponible
        last_id = None
        try:
            if driver == "sqlite":
                last_id = cur.lastrowid
            elif driver in ("postgresql", "mysql"):
                last_id = cur.lastrowid
        except Exception:
            pass

        return {
            "status":        "success",
            "connexion":     connexion,
            "sql":           sql_clean,
            "lignes_affectees": cur.rowcount if cur.rowcount >= 0 else 0,
            "dernier_id":    last_id,
            "duree_ms":      elapsed_ms,
            "message":       "Opération validée (COMMIT).",
        }

    except KeyError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Erreur inattendue : {e}"}


@tool(
    name="sql_explain",
    description=(
        "Affiche le plan d'exécution d'une requête SELECT pour analyser les performances. "
        "Utile pour détecter les scans complets de table, les index manquants, etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Requête SELECT à analyser.",
            },
            "connexion": {
                "type": "string",
                "description": "Nom de la connexion (défaut: 'default').",
            },
            "verbose": {
                "type": "boolean",
                "description": "Activer EXPLAIN ANALYZE (PostgreSQL) ou EXPLAIN VERBOSE (défaut: false).",
            },
        },
        "required": ["sql"],
    },
)
def sql_explain(
    sql: str,
    connexion: str = "default",
    verbose: bool = False,
) -> dict:
    try:
        conn, driver = _get_conn(connexion)
        sql_clean = sql.strip().rstrip(";")

        if driver == "sqlite":
            # SQLite EXPLAIN ne supporte pas les paramètres liés :
            # on les remplace par des littéraux NULL pour le plan
            explain_sql = f"EXPLAIN QUERY PLAN {re.sub(r'[?]', 'NULL', sql_clean)}"
        elif driver == "postgresql":
            explain_sql = f"EXPLAIN {'ANALYZE ' if verbose else ''}{sql_clean}"
        else:  # mysql
            explain_sql = f"EXPLAIN {sql_clean}"

        cur = _execute_query(conn, driver, explain_sql)
        rows_raw = cur.fetchall()

        if driver == "postgresql":
            conn.rollback()

        plan_lines = []
        for row in rows_raw:
            if isinstance(row, sqlite3.Row):
                plan_lines.append(dict(row))
            elif isinstance(row, dict):
                plan_lines.append(row)
            else:
                plan_lines.append(dict(row))

        # Format texte lisible
        plan_text = "\n".join(
            " | ".join(str(v) for v in r.values()) for r in plan_lines
        )

        return {
            "status":     "success",
            "connexion":  connexion,
            "driver":     driver,
            "sql":        sql_clean,
            "plan":       plan_lines,
            "plan_texte": plan_text,
        }

    except KeyError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Erreur explain : {e}"}


@tool(
    name="sql_export_csv",
    description=(
        "Exécute une requête SELECT et exporte les résultats dans un fichier CSV local. "
        "Utile pour extraire des données vers un tableur ou un autre outil. "
        "Retourne le chemin du fichier créé."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Requête SELECT dont les résultats seront exportés.",
            },
            "connexion": {
                "type": "string",
                "description": "Nom de la connexion (défaut: 'default').",
            },
            "destination": {
                "type": "string",
                "description": (
                    "Chemin du fichier CSV de sortie. "
                    "Défaut : ~/export_<timestamp>.csv"
                ),
            },
            "separateur": {
                "type": "string",
                "description": "Séparateur de colonnes (défaut: ',').",
            },
            "params": {
                "type": "array",
                "items": {},
                "description": "Valeurs des paramètres liés.",
            },
            "limite": {
                "type": "integer",
                "description": f"Nombre max de lignes exportées (défaut: {_MAX_ROWS_HARD}).",
            },
        },
        "required": ["sql"],
    },
)
def sql_export_csv(
    sql: str,
    connexion: str = "default",
    destination: Optional[str] = None,
    separateur: str = ",",
    params: Optional[list] = None,
    limite: int = _MAX_ROWS_HARD,
) -> dict:
    limite = min(max(1, limite), _MAX_ROWS_HARD)
    sql_clean = sql.strip()

    # Résoudre le chemin de destination
    if destination:
        dest = Path(destination).expanduser()
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = Path.home() / f"export_{ts}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn, driver = _get_conn(connexion)

        sql_exec = sql_clean
        if driver == "postgresql" and params:
            sql_exec = sql_clean.replace("?", "%s")
        if "LIMIT" not in sql_exec.upper():
            sql_exec = f"{sql_exec.rstrip(';')} LIMIT {limite}"

        t0 = time.perf_counter()
        cur = _execute_query(conn, driver, sql_exec, params)
        colonnes = [desc[0] for desc in cur.description] if cur.description else []

        if driver == "postgresql":
            conn.rollback()

        rows_raw = cur.fetchall()
        nb_lignes = len(rows_raw)

        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, fieldnames=colonnes, delimiter=separateur,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in rows_raw:
                d = _row_to_dict(row)
                writer.writerow(d)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        taille = dest.stat().st_size
        taille_str = f"{taille / 1024:.1f} Ko" if taille < 1_048_576 else f"{taille / 1_048_576:.2f} Mo"

        return {
            "status":     "success",
            "connexion":  connexion,
            "fichier":    str(dest),
            "nb_lignes":  nb_lignes,
            "nb_colonnes": len(colonnes),
            "colonnes":   colonnes,
            "taille":     taille_str,
            "duree_ms":   elapsed_ms,
            "message":    f"{nb_lignes} lignes exportées dans {dest.name}.",
        }

    except KeyError as e:
        return {"status": "error", "error": str(e)}
    except PermissionError:
        return {"status": "error", "error": f"Permission refusée : {dest}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur export : {e}"}


# ══════════════════════════════════════════════════════════════════════════════
# sql_detect_instances
# ══════════════════════════════════════════════════════════════════════════════

_KNOWN_ENGINES: list[dict] = [
    # (port, driver, nom_affichage, url_template, noms_processus)
    {
        "port": 5432,
        "driver": "postgresql",
        "nom": "PostgreSQL",
        "url_template": "postgresql://user:password@localhost:5432/database",
        "processus": ["postgres", "postmaster"],
    },
    {
        "port": 3306,
        "driver": "mysql",
        "nom": "MySQL / MariaDB",
        "url_template": "mysql://user:password@localhost:3306/database",
        "processus": ["mysqld", "mariadbd", "mysqld_safe"],
    },
    {
        "port": 5433,
        "driver": "postgresql",
        "nom": "PostgreSQL (port alternatif)",
        "url_template": "postgresql://user:password@localhost:5433/database",
        "processus": ["postgres", "postmaster"],
    },
    {
        "port": 3307,
        "driver": "mysql",
        "nom": "MySQL / MariaDB (port alternatif)",
        "url_template": "mysql://user:password@localhost:3307/database",
        "processus": ["mysqld", "mariadbd"],
    },
    {
        "port": 5984,
        "driver": None,
        "nom": "CouchDB",
        "url_template": None,
        "processus": ["beam.smp", "couchdb"],
    },
    {
        "port": 27017,
        "driver": None,
        "nom": "MongoDB",
        "url_template": None,
        "processus": ["mongod"],
    },
    {
        "port": 6379,
        "driver": None,
        "nom": "Redis",
        "url_template": None,
        "processus": ["redis-server"],
    },
    {
        "port": 9200,
        "driver": None,
        "nom": "Elasticsearch",
        "url_template": None,
        "processus": ["java", "elasticsearch"],
    },
    {
        "port": 1433,
        "driver": None,
        "nom": "Microsoft SQL Server",
        "url_template": None,
        "processus": ["sqlservr"],
    },
    {
        "port": 1521,
        "driver": None,
        "nom": "Oracle Database",
        "url_template": None,
        "processus": ["oracle", "tnslsnr"],
    },
    {
        "port": 5439,
        "driver": "postgresql",
        "nom": "Amazon Redshift (local)",
        "url_template": "postgresql://user:password@localhost:5439/database",
        "processus": [],
    },
]


def _tcp_ping(port: int, timeout: float = 0.3) -> bool:
    """Tente une connexion TCP sur localhost:port. Retourne True si le port répond."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _process_info_for_port(port: int, processus_cibles: list[str]) -> dict | None:
    """
    Tente de retrouver le PID et le nom du processus qui écoute sur ce port.
    Stratégie : psutil d'abord (cross-platform), puis ss/netstat en fallback Unix.
    Retourne un dict {pid, nom, cmdline} ou None.
    """
    import subprocess as _sp

    # ── Stratégie 1 : psutil (si disponible) ────────────────────────────────
    try:
        import psutil  # type: ignore
        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                try:
                    proc = psutil.Process(conn.pid)
                    return {
                        "pid":     conn.pid,
                        "nom":     proc.name(),
                        "cmdline": " ".join(proc.cmdline())[:120],
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return {"pid": conn.pid, "nom": "?", "cmdline": ""}
    except ImportError:
        pass
    except Exception:
        pass

    # ── Stratégie 2 : ss (Linux) ────────────────────────────────────────────
    try:
        r = _sp.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if f":{port}" in line:
                    # Extraire pid=XXXX depuis la colonne "users:(("prog",pid=NNN,...))"
                    import re as _re
                    m = _re.search(r'pid=(\d+)', line)
                    pid = int(m.group(1)) if m else None
                    mn = _re.search(r'"([^"]+)"', line)
                    nom = mn.group(1) if mn else "?"
                    return {"pid": pid, "nom": nom, "cmdline": ""}
    except Exception:
        pass

    # ── Stratégie 3 : netstat (macOS / Linux sans ss) ───────────────────────
    try:
        r = _sp.run(
            ["netstat", "-tlnp"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            import re as _re
            for line in r.stdout.splitlines():
                if f":{port} " in line or f":{port}\t" in line:
                    parts = line.split()
                    if parts:
                        pid_prog = parts[-1]  # ex: "1234/postgres"
                        pid_str, _, prog = pid_prog.partition("/")
                        try:
                            return {"pid": int(pid_str), "nom": prog or "?", "cmdline": ""}
                        except ValueError:
                            return {"pid": None, "nom": prog or "?", "cmdline": ""}
    except Exception:
        pass

    return None


def _find_sqlite_files(repertoires: list[str], profondeur_max: int = 4) -> list[dict]:
    """
    Recherche récursive de fichiers SQLite (.db, .sqlite, .sqlite3) dans les
    répertoires indiqués, jusqu'à profondeur_max niveaux.
    """
    import os
    extensions = {".db", ".sqlite", ".sqlite3", ".db3", ".s3db"}
    _ignorer = {
        ".git", ".hg", "__pycache__", "node_modules", ".venv", "venv",
        ".tox", "dist", "build", ".mypy_cache", "site-packages",
    }
    trouvés: list[dict] = []

    def _walk(path: Path, depth: int) -> None:
        if depth > profondeur_max:
            return
        try:
            for entry in os.scandir(path):
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in _ignorer:
                        _walk(Path(entry.path), depth + 1)
                elif entry.is_file(follow_symlinks=False):
                    p = Path(entry.path)
                    if p.suffix.lower() in extensions and p.stat().st_size > 0:
                        # Vérifier le magic number SQLite ("SQLite format 3\x00")
                        try:
                            with open(p, "rb") as f:
                                header = f.read(16)
                            if header[:6] == b"SQLite":
                                taille = p.stat().st_size
                                taille_str = (
                                    f"{taille / 1024:.1f} Ko"
                                    if taille < 1_048_576
                                    else f"{taille / 1_048_576:.2f} Mo"
                                )
                                trouvés.append({
                                    "chemin":  str(p),
                                    "taille":  taille_str,
                                    "url":     f"sqlite:///{p}",
                                })
                        except OSError:
                            pass
        except PermissionError:
            pass

    for rep in repertoires:
        rp = Path(rep).expanduser()
        if rp.exists():
            _walk(rp, 0)

    return trouvés



@tool(
    name="sql_detect_instances",
    description=(
        "Détecte les instances de bases de données actives sur le système local : "
        "scan des ports standards (PostgreSQL, MySQL/MariaDB…), identification du processus "
        "(PID, nom) via psutil ou ss/netstat, et recherche de fichiers SQLite dans les "
        "répertoires courants. Retourne pour chaque instance détectée une URL de connexion "
        "prête à passer à sql_connect."
    ),
    parameters={
        "type": "object",
        "properties": {
            "inclure_sqlite": {
                "type": "boolean",
                "description": (
                    "Rechercher des fichiers SQLite dans les répertoires courants "
                    "(défaut: true)."
                ),
            },
            "repertoires_sqlite": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Répertoires à scanner pour les fichiers SQLite "
                    "(défaut: ['~', '~/Documents', '~/Projets', '.'])."
                ),
            },
            "timeout_port": {
                "type": "number",
                "description": (
                    "Délai d'attente en secondes pour chaque test TCP (défaut: 0.3)."
                ),
            },
        },
        "required": [],
    },
)
def sql_detect_instances(
    inclure_sqlite: bool = True,
    repertoires_sqlite: list[str] | None = None,
    timeout_port: float = 0.3,
) -> dict:
    """
    Détecte les instances de bases de données actives sur le système local.

    Méthode :
      1. Scan TCP sur les ports standards de chaque moteur connu.
      2. Pour chaque port ouvert : identification du processus via psutil,
         ss ou netstat.
      3. Optionnel : recherche de fichiers SQLite dans les répertoires indiqués.
    """
    instances_reseau: list[dict] = []

    # ── 1. Scan des ports réseau ─────────────────────────────────────────────
    for moteur in _KNOWN_ENGINES:
        port = moteur["port"]
        if not _tcp_ping(port, timeout=max(0.05, min(float(timeout_port), 5.0))):
            continue

        proc = _process_info_for_port(port, moteur["processus"])

        instance: dict = {
            "moteur":  moteur["nom"],
            "driver":  moteur["driver"],
            "port":    port,
            "host":    "localhost",
            "statut":  "actif ✅",
        }
        if moteur["url_template"]:
            instance["url_connexion"] = moteur["url_template"]
            if moteur["driver"] in ("postgresql", "mysql"):
                instance["note"] = (
                    "Remplacer user, password et database dans l'URL avant sql_connect."
                )
        else:
            instance["note"] = (
                f"{moteur['nom']} détecté mais non supporté par sql_connect "
                "(aucun driver intégré)."
            )
        if proc:
            instance["processus"] = proc

        instances_reseau.append(instance)

    # ── 2. Recherche fichiers SQLite ─────────────────────────────────────────
    fichiers_sqlite: list[dict] = []
    if inclure_sqlite:
        reps = repertoires_sqlite or ["~", "~/Documents", "~/Projets", "."]
        fichiers_sqlite = _find_sqlite_files(reps)

    # ── 3. Construction de la réponse ────────────────────────────────────────
    total = len(instances_reseau) + len(fichiers_sqlite)

    if total == 0:
        return {
            "status":  "success",
            "total":   0,
            "message": (
                "Aucune instance de base de données détectée sur ce système. "
                "Vérifiez que le serveur est démarré et que les ports standards "
                "ne sont pas filtrés."
            ),
            "instances_reseau": [],
            "fichiers_sqlite":  [],
        }

    return {
        "status":            "success",
        "total":             total,
        "instances_reseau":  instances_reseau,
        "fichiers_sqlite":   fichiers_sqlite,
        "message": (
            f"{len(instances_reseau)} instance(s) réseau détectée(s)"
            + (f", {len(fichiers_sqlite)} fichier(s) SQLite trouvé(s)" if fichiers_sqlite else "")
            + "."
        ),
    }
