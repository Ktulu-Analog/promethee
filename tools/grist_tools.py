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
tools/grist_tools.py — Outils API Grist pour Prométhée
=======================================================

Famille d'outils permettant d'interagir avec une instance Grist via son API REST.
Grist est un tableur collaboratif open-source (https://www.getgrist.com).

Outils exposés (17) :

  Organisations (2) :
    - grist_list_orgs            : liste les organisations accessibles
    - grist_list_workspaces      : liste les espaces de travail d'une organisation

  Documents (5) :
    - grist_list_docs            : liste les documents d'un espace de travail
    - grist_describe_doc         : décrit les métadonnées d'un document
    - grist_create_doc           : crée un nouveau document vide
    - grist_delete_doc           : supprime définitivement un document
    - grist_move_doc_to_trash    : déplace un document dans la corbeille

  Tables (3) :
    - grist_list_tables          : liste les tables d'un document
    - grist_create_table         : crée une nouvelle table avec des colonnes
    - grist_delete_table         : supprime une table d'un document

  Colonnes (2) :
    - grist_list_columns         : liste les colonnes d'une table
    - grist_add_columns          : ajoute des colonnes à une table existante

  Enregistrements (4) :
    - grist_list_records         : récupère des enregistrements d'une table (avec filtres)
    - grist_add_records          : ajoute des enregistrements dans une table
    - grist_update_records       : modifie des enregistrements existants
    - grist_delete_records       : supprime des enregistrements par leurs IDs

  SQL (1) :
    - grist_run_sql              : exécute une requête SQL SELECT sur un document

Configuration requise (.env) :
    GRIST_API_KEY=votre_clé_api
    GRIST_BASE_URL=https://votre-instance.grist.com   # ou https://docs.getgrist.com

Usage :
    import tools.grist_tools   # suffit à enregistrer les outils

Prérequis :
    pip install requests
"""

# ── Imports standard ──────────────────────────────────────────────────────────
import json
from typing import Optional
from urllib.parse import urlencode

# ── Imports tiers ─────────────────────────────────────────────────────────────
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ── Imports Prométhée ─────────────────────────────────────────────────────────
from core.tools_engine import tool, set_current_family, report_progress, _TOOL_ICONS
from core.config import Config


# ══════════════════════════════════════════════════════════════════════════════
#  1. DÉCLARATION DE LA FAMILLE
# ══════════════════════════════════════════════════════════════════════════════

set_current_family("grist_tools", "Grist", "📊")

_TOOL_ICONS.update({
    "grist_list_orgs":         "🏢",
    "grist_list_workspaces":   "📁",
    "grist_list_docs":         "📄",
    "grist_describe_doc":      "🔍",
    "grist_create_doc":        "➕",
    "grist_delete_doc":        "🗑️",
    "grist_move_doc_to_trash": "🗑️",
    "grist_list_tables":       "📋",
    "grist_create_table":      "🆕",
    "grist_delete_table":      "❌",
    "grist_list_columns":      "📐",
    "grist_add_columns":       "➕",
    "grist_list_records":      "📊",
    "grist_add_records":       "✏️",
    "grist_update_records":    "🔄",
    "grist_delete_records":    "🗑️",
    "grist_run_sql":           "🛢️",
})


# ══════════════════════════════════════════════════════════════════════════════
#  2. HELPERS INTERNES
# ══════════════════════════════════════════════════════════════════════════════

def _get_headers() -> dict:
    """Construit les headers HTTP avec la clé API Grist."""
    return {
        "Authorization": f"Bearer {Config.GRIST_API_KEY}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    """Retourne l'URL de base de l'API Grist (sans slash final)."""
    return Config.GRIST_BASE_URL.rstrip("/") + "/api"


def _check_prerequisites() -> Optional[str]:
    """
    Vérifie que requests est installé et que les variables .env sont définies.
    Retourne un message d'erreur ou None si tout est OK.
    """
    if not _HAS_REQUESTS:
        return (
            "Erreur : la bibliothèque 'requests' est absente. "
            "Installez-la avec : pip install requests"
        )
    if not Config.GRIST_API_KEY:
        return "Erreur : GRIST_API_KEY est absent du fichier .env."
    if not Config.GRIST_BASE_URL:
        return "Erreur : GRIST_BASE_URL est absent du fichier .env."
    return None


def _get(path: str, params: Optional[dict] = None) -> tuple[bool, any]:
    """
    Effectue une requête GET sur l'API Grist.
    Retourne (succès: bool, données ou message d'erreur).
    """
    try:
        url = f"{_base_url()}{path}"
        resp = requests.get(url, headers=_get_headers(), params=params, timeout=30)
        resp.raise_for_status()
        return True, resp.json()
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


def _post(path: str, payload: dict) -> tuple[bool, any]:
    """Effectue une requête POST sur l'API Grist."""
    try:
        url = f"{_base_url()}{path}"
        resp = requests.post(url, headers=_get_headers(), json=payload, timeout=30)
        resp.raise_for_status()
        if resp.content:
            return True, resp.json()
        return True, {"status": "ok"}
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


def _patch(path: str, payload: dict) -> tuple[bool, any]:
    """Effectue une requête PATCH sur l'API Grist."""
    try:
        url = f"{_base_url()}{path}"
        resp = requests.patch(url, headers=_get_headers(), json=payload, timeout=30)
        resp.raise_for_status()
        if resp.content:
            return True, resp.json()
        return True, {"status": "ok"}
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


def _delete(path: str) -> tuple[bool, any]:
    """Effectue une requête DELETE sur l'API Grist."""
    try:
        url = f"{_base_url()}{path}"
        resp = requests.delete(url, headers=_get_headers(), timeout=30)
        resp.raise_for_status()
        if resp.content:
            return True, resp.json()
        return True, {"status": "ok"}
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  3. ORGANISATIONS
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="grist_list_orgs",
    description=(
        "Liste toutes les organisations Grist accessibles avec la clé API configurée. "
        "Une organisation correspond à un espace d'équipe (team site) ou à l'espace "
        "personnel de l'utilisateur. "
        "Retourne un tableau JSON d'organisations avec leurs id, name, domain, access. "
        "Utiliser en premier pour découvrir les organisations disponibles avant "
        "d'accéder à leurs espaces de travail et documents."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def grist_list_orgs() -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress("📊 Récupération des organisations Grist…")
    ok, data = _get("/orgs")
    if not ok:
        return f"Erreur : {data}"

    return json.dumps(data, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  4. ESPACES DE TRAVAIL
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="grist_list_workspaces",
    description=(
        "Liste les espaces de travail (workspaces) d'une organisation Grist "
        "ainsi que les documents qu'ils contiennent. "
        "Retourne un tableau JSON d'espaces de travail, chacun avec id, name, "
        "access, et la liste de ses documents (id, name, isPinned, urlId). "
        "Utiliser après grist_list_orgs pour explorer le contenu d'une organisation. "
        "L'orgId peut être un entier, un sous-domaine (ex: 'gristlabs') "
        "ou 'current' pour l'organisation courante."
    ),
    parameters={
        "type": "object",
        "properties": {
            "org_id": {
                "type": "string",
                "description": (
                    "Identifiant de l'organisation : entier numérique, sous-domaine "
                    "(ex: 'monequipe') ou 'current'. "
                    "Récupérable via grist_list_orgs."
                ),
            },
        },
        "required": ["org_id"],
    },
)
def grist_list_workspaces(org_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not org_id.strip():
        return "Erreur : org_id ne peut pas être vide."

    report_progress(f"📁 Récupération des espaces de travail de l'org '{org_id}'…")
    ok, data = _get(f"/orgs/{org_id}/workspaces")
    if not ok:
        return f"Erreur : {data}"

    return json.dumps(data, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  5. DOCUMENTS
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="grist_list_docs",
    description=(
        "Liste les documents contenus dans un espace de travail Grist. "
        "Retourne un tableau JSON de documents avec id, name, isPinned, urlId, access. "
        "L'ID du document (docId) retourné est nécessaire pour toutes les opérations "
        "sur les tables et enregistrements."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "integer",
                "description": (
                    "Identifiant entier de l'espace de travail. "
                    "Récupérable via grist_list_workspaces."
                ),
            },
        },
        "required": ["workspace_id"],
    },
)
def grist_list_docs(workspace_id: int) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"📄 Récupération des documents du workspace {workspace_id}…")
    ok, data = _get(f"/workspaces/{workspace_id}")
    if not ok:
        return f"Erreur : {data}"

    docs = data.get("docs", [])
    return json.dumps(docs, ensure_ascii=False, indent=2)


@tool(
    name="grist_describe_doc",
    description=(
        "Décrit les métadonnées d'un document Grist : id, name, isPinned, urlId, "
        "access, et l'espace de travail parent avec son organisation. "
        "Retourne un objet JSON. "
        "Utiliser pour vérifier l'existence d'un document ou obtenir ses informations."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document (UUID). Ex: '9PJhBDZPyCNoayZxaCwFfS'.",
            },
        },
        "required": ["doc_id"],
    },
)
def grist_describe_doc(doc_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."

    report_progress(f"🔍 Description du document '{doc_id}'…")
    ok, data = _get(f"/docs/{doc_id}")
    if not ok:
        return f"Erreur : {data}"

    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="grist_create_doc",
    description=(
        "Crée un nouveau document Grist vide dans un espace de travail. "
        "Retourne l'identifiant (docId) du document créé sous forme de chaîne. "
        "Le docId est nécessaire pour toutes les opérations ultérieures."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "integer",
                "description": "Identifiant de l'espace de travail destination. Ex: 97.",
            },
            "name": {
                "type": "string",
                "description": "Nom du nouveau document. Ex: 'Mon Suivi Projets'.",
            },
        },
        "required": ["workspace_id", "name"],
    },
)
def grist_create_doc(workspace_id: int, name: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not name.strip():
        return "Erreur : name ne peut pas être vide."

    report_progress(f"➕ Création du document '{name}' dans le workspace {workspace_id}…")
    ok, data = _post(f"/workspaces/{workspace_id}/docs", {"name": name})
    if not ok:
        return f"Erreur : {data}"

    return json.dumps({"doc_id": data}, ensure_ascii=False)


@tool(
    name="grist_delete_doc",
    description=(
        "Supprime définitivement un document Grist. "
        "⚠️ Cette action est irréversible. "
        "Pour un déplacement récupérable, utiliser grist_move_doc_to_trash à la place. "
        "Retourne un message de confirmation en cas de succès."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document à supprimer.",
            },
        },
        "required": ["doc_id"],
    },
)
def grist_delete_doc(doc_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."

    report_progress(f"🗑️ Suppression définitive du document '{doc_id}'…")
    ok, data = _delete(f"/docs/{doc_id}")
    if not ok:
        return f"Erreur : {data}"

    return f"Document '{doc_id}' supprimé avec succès."


@tool(
    name="grist_move_doc_to_trash",
    description=(
        "Déplace un document Grist dans la corbeille (soft delete). "
        "Le document peut être restauré ultérieurement via l'interface Grist. "
        "Préférer cet outil à grist_delete_doc pour éviter une perte irréversible. "
        "Retourne un message de confirmation en cas de succès."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document à mettre à la corbeille.",
            },
        },
        "required": ["doc_id"],
    },
)
def grist_move_doc_to_trash(doc_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."

    report_progress(f"🗑️ Déplacement du document '{doc_id}' dans la corbeille…")
    ok, data = _post(f"/docs/{doc_id}/remove", {})
    if not ok:
        return f"Erreur : {data}"

    return f"Document '{doc_id}' déplacé dans la corbeille."


# ══════════════════════════════════════════════════════════════════════════════
#  6. TABLES
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="grist_list_tables",
    description=(
        "Liste toutes les tables d'un document Grist. "
        "Retourne un tableau JSON d'objets avec id (identifiant technique, ex: 'Table1') "
        "et fields (tableRef, onDemand). "
        "L'id de la table (tableId) est nécessaire pour lire ou modifier ses données. "
        "À utiliser avant grist_list_records ou grist_list_columns."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
        },
        "required": ["doc_id"],
    },
)
def grist_list_tables(doc_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."

    report_progress(f"📋 Récupération des tables du document '{doc_id}'…")
    ok, data = _get(f"/docs/{doc_id}/tables")
    if not ok:
        return f"Erreur : {data}"

    return json.dumps(data.get("tables", data), ensure_ascii=False, indent=2)


@tool(
    name="grist_create_table",
    description=(
        "Crée une nouvelle table dans un document Grist, avec des colonnes définies. "
        "Retourne l'identifiant de la table créée. "
        "Le paramètre 'columns' est une liste de colonnes, chacune avec un id "
        "(identifiant technique sans espaces) et des fields optionnels (label, type). "
        "Types de colonnes disponibles : Text, Numeric, Int, Bool, Date, DateTime, "
        "Choice, ChoiceList, Ref:<tableId>, RefList:<tableId>, Attachments, Any."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "table_id": {
                "type": "string",
                "description": (
                    "Identifiant technique de la table (sans espaces, PascalCase recommandé). "
                    "Ex: 'Projets', 'SuiviDepenses'. Si omis, Grist en génère un."
                ),
            },
            "columns": {
                "type": "array",
                "description": (
                    "Liste des colonnes à créer. Chaque élément est un objet avec : "
                    "'id' (str, identifiant technique), et 'fields' optionnel avec "
                    "'label' (str) et 'type' (str, ex: 'Text', 'Int', 'Date'). "
                    "Ex: [{\"id\": \"nom\", \"fields\": {\"label\": \"Nom\", \"type\": \"Text\"}}, "
                    "{\"id\": \"montant\", \"fields\": {\"label\": \"Montant\", \"type\": \"Numeric\"}}]"
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["doc_id", "columns"],
    },
)
def grist_create_table(doc_id: str, columns: list, table_id: Optional[str] = None) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not isinstance(columns, list) or len(columns) == 0:
        return "Erreur : columns doit être une liste non vide."

    table_def = {"columns": columns}
    if table_id and table_id.strip():
        table_def["id"] = table_id.strip()

    payload = {"tables": [table_def]}
    label = table_id or "(auto)"
    report_progress(f"🆕 Création de la table '{label}' dans le document '{doc_id}'…")
    ok, data = _post(f"/docs/{doc_id}/tables", payload)
    if not ok:
        return f"Erreur : {data}"

    tables = data.get("tables", data)
    return json.dumps(tables, ensure_ascii=False, indent=2)


@tool(
    name="grist_delete_table",
    description=(
        "Supprime une table d'un document Grist via l'API user actions. "
        "⚠️ Toutes les données de la table seront perdues. Action irréversible. "
        "Retourne un message de confirmation en cas de succès."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "table_id": {
                "type": "string",
                "description": "Identifiant technique de la table à supprimer. Ex: 'Projets'.",
            },
        },
        "required": ["doc_id", "table_id"],
    },
)
def grist_delete_table(doc_id: str, table_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not table_id.strip():
        return "Erreur : table_id ne peut pas être vide."

    report_progress(f"❌ Suppression de la table '{table_id}' dans le document '{doc_id}'…")
    payload = [["RemoveTable", table_id]]
    ok, data = _post(f"/docs/{doc_id}/apply", payload)
    if not ok:
        return f"Erreur : {data}"

    return f"Table '{table_id}' supprimée avec succès."


# ══════════════════════════════════════════════════════════════════════════════
#  7. COLONNES
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="grist_list_columns",
    description=(
        "Liste les colonnes d'une table Grist. "
        "Retourne un tableau JSON de colonnes avec id (identifiant technique) "
        "et fields (label, type, formula, isFormula, colRef, etc.). "
        "Utiliser avant de lire ou modifier des enregistrements pour connaître "
        "les noms exacts des colonnes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "table_id": {
                "type": "string",
                "description": "Identifiant technique de la table. Ex: 'Table1', 'Projets'.",
            },
            "include_hidden": {
                "type": "boolean",
                "description": "Si true, inclut les colonnes cachées (ex: manualSort). Défaut: false.",
            },
        },
        "required": ["doc_id", "table_id"],
    },
)
def grist_list_columns(doc_id: str, table_id: str, include_hidden: bool = False) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not table_id.strip():
        return "Erreur : table_id ne peut pas être vide."

    report_progress(f"📐 Récupération des colonnes de '{table_id}' dans '{doc_id}'…")
    params = {"hidden": "true"} if include_hidden else {}
    ok, data = _get(f"/docs/{doc_id}/tables/{table_id}/columns", params=params)
    if not ok:
        return f"Erreur : {data}"

    return json.dumps(data.get("columns", data), ensure_ascii=False, indent=2)


@tool(
    name="grist_add_columns",
    description=(
        "Ajoute de nouvelles colonnes à une table Grist existante. "
        "Retourne la liste des colonnes créées (avec leurs ids). "
        "Chaque colonne est définie par un id (identifiant technique) et des fields "
        "optionnels (label, type, formula, isFormula, widgetOptions). "
        "Types disponibles : Text, Numeric, Int, Bool, Date, DateTime:<tz>, "
        "Choice, ChoiceList, Ref:<tableId>, RefList:<tableId>, Attachments, Any."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "table_id": {
                "type": "string",
                "description": "Identifiant technique de la table cible.",
            },
            "columns": {
                "type": "array",
                "description": (
                    "Liste des colonnes à ajouter. Chaque élément a : "
                    "'id' (str, identifiant technique sans espaces), "
                    "'fields' optionnel avec 'label' (str), 'type' (str), "
                    "'formula' (str, expression Python), 'isFormula' (bool). "
                    "Ex: [{\"id\": \"statut\", \"fields\": {\"label\": \"Statut\", "
                    "\"type\": \"Choice\", \"widgetOptions\": \"{\\\"choices\\\":[\\\"Actif\\\",\\\"Clôturé\\\"]}\"}}]"
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["doc_id", "table_id", "columns"],
    },
)
def grist_add_columns(doc_id: str, table_id: str, columns: list) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not table_id.strip():
        return "Erreur : table_id ne peut pas être vide."
    if not isinstance(columns, list) or len(columns) == 0:
        return "Erreur : columns doit être une liste non vide."

    report_progress(f"➕ Ajout de {len(columns)} colonne(s) à '{table_id}'…")
    payload = {"columns": columns}
    ok, data = _post(f"/docs/{doc_id}/tables/{table_id}/columns", payload)
    if not ok:
        return f"Erreur : {data}"

    return json.dumps(data.get("columns", data), ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  8. ENREGISTREMENTS (RECORDS)
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="grist_list_records",
    description=(
        "Récupère les enregistrements (lignes) d'une table Grist. "
        "Retourne un tableau JSON d'enregistrements, chacun avec id et fields "
        "(objet clé/valeur des colonnes). "
        "Supporte le filtrage, le tri et la limitation des résultats. "
        "Utiliser grist_list_columns au préalable pour connaître les noms de colonnes. "
        "Pour des requêtes complexes, préférer grist_run_sql."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "table_id": {
                "type": "string",
                "description": "Identifiant technique de la table. Ex: 'Projets'.",
            },
            "filter": {
                "type": "string",
                "description": (
                    "Filtre JSON (URL-encodé automatiquement) : objet mappant des noms "
                    "de colonnes à des tableaux de valeurs autorisées. "
                    "Ex: '{\"statut\": [\"Actif\"], \"categorie\": [\"A\", \"B\"]}'"
                ),
            },
            "sort": {
                "type": "string",
                "description": (
                    "Tri : nom de colonne pour ascendant, préfixé par '-' pour descendant. "
                    "Plusieurs colonnes séparées par des virgules. "
                    "Ex: 'nom,-date'"
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum d'enregistrements à retourner. 0 = pas de limite.",
            },
        },
        "required": ["doc_id", "table_id"],
    },
)
def grist_list_records(
    doc_id: str,
    table_id: str,
    filter: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not table_id.strip():
        return "Erreur : table_id ne peut pas être vide."

    params: dict = {}
    if filter:
        params["filter"] = filter
    if sort:
        params["sort"] = sort
    if limit is not None:
        params["limit"] = limit

    report_progress(f"📊 Récupération des enregistrements de '{table_id}'…")
    ok, data = _get(f"/docs/{doc_id}/tables/{table_id}/records", params=params)
    if not ok:
        return f"Erreur : {data}"

    records = data.get("records", data)
    return json.dumps(records, ensure_ascii=False, indent=2)


@tool(
    name="grist_add_records",
    description=(
        "Ajoute un ou plusieurs enregistrements dans une table Grist. "
        "Retourne la liste des IDs des enregistrements créés. "
        "Chaque enregistrement est un objet 'fields' mappant les noms de colonnes "
        "à leurs valeurs. "
        "Utiliser grist_list_columns pour connaître les identifiants exacts des colonnes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "table_id": {
                "type": "string",
                "description": "Identifiant technique de la table cible.",
            },
            "records": {
                "type": "array",
                "description": (
                    "Liste d'enregistrements à ajouter. Chaque élément est un objet "
                    "avec une clé 'fields' contenant les valeurs des colonnes. "
                    "Ex: [{\"fields\": {\"nom\": \"Alice\", \"age\": 30}}, "
                    "{\"fields\": {\"nom\": \"Bob\", \"age\": 25}}]"
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["doc_id", "table_id", "records"],
    },
)
def grist_add_records(doc_id: str, table_id: str, records: list) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not table_id.strip():
        return "Erreur : table_id ne peut pas être vide."
    if not isinstance(records, list) or len(records) == 0:
        return "Erreur : records doit être une liste non vide."

    report_progress(f"✏️ Ajout de {len(records)} enregistrement(s) dans '{table_id}'…")
    payload = {"records": records}
    ok, data = _post(f"/docs/{doc_id}/tables/{table_id}/records", payload)
    if not ok:
        return f"Erreur : {data}"

    created = data.get("records", data)
    ids = [r.get("id") for r in created if isinstance(r, dict) and "id" in r]
    return json.dumps(
        {"message": f"{len(ids)} enregistrement(s) créé(s).", "ids": ids},
        ensure_ascii=False,
        indent=2,
    )


@tool(
    name="grist_update_records",
    description=(
        "Modifie des enregistrements existants dans une table Grist. "
        "Chaque enregistrement à modifier doit avoir un 'id' (entier) et un objet "
        "'fields' avec les colonnes à mettre à jour (seules les colonnes fournies "
        "sont modifiées, les autres sont conservées). "
        "Retourne un message de succès. "
        "Utiliser grist_list_records pour obtenir les IDs des enregistrements."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "table_id": {
                "type": "string",
                "description": "Identifiant technique de la table.",
            },
            "records": {
                "type": "array",
                "description": (
                    "Liste d'enregistrements à modifier. Chaque élément doit avoir : "
                    "'id' (int, ID de la ligne), 'fields' (objet avec les colonnes à modifier). "
                    "Ex: [{\"id\": 1, \"fields\": {\"statut\": \"Clôturé\"}}, "
                    "{\"id\": 3, \"fields\": {\"montant\": 1500.0}}]"
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["doc_id", "table_id", "records"],
    },
)
def grist_update_records(doc_id: str, table_id: str, records: list) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not table_id.strip():
        return "Erreur : table_id ne peut pas être vide."
    if not isinstance(records, list) or len(records) == 0:
        return "Erreur : records doit être une liste non vide."

    # Validation minimale : chaque record doit avoir un id
    for r in records:
        if not isinstance(r, dict) or "id" not in r:
            return "Erreur : chaque enregistrement doit avoir un champ 'id'."

    report_progress(f"🔄 Mise à jour de {len(records)} enregistrement(s) dans '{table_id}'…")
    payload = {"records": records}
    ok, data = _patch(f"/docs/{doc_id}/tables/{table_id}/records", payload)
    if not ok:
        return f"Erreur : {data}"

    return f"{len(records)} enregistrement(s) mis à jour avec succès."


@tool(
    name="grist_delete_records",
    description=(
        "Supprime des enregistrements d'une table Grist par leurs IDs. "
        "⚠️ Cette suppression est irréversible. "
        "Retourne un message de confirmation. "
        "Utiliser grist_list_records pour obtenir les IDs avant suppression."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "table_id": {
                "type": "string",
                "description": "Identifiant technique de la table.",
            },
            "record_ids": {
                "type": "array",
                "description": (
                    "Liste des IDs (entiers) des enregistrements à supprimer. "
                    "Ex: [1, 5, 12]"
                ),
                "items": {"type": "integer"},
            },
        },
        "required": ["doc_id", "table_id", "record_ids"],
    },
)
def grist_delete_records(doc_id: str, table_id: str, record_ids: list) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not table_id.strip():
        return "Erreur : table_id ne peut pas être vide."
    if not isinstance(record_ids, list) or len(record_ids) == 0:
        return "Erreur : record_ids doit être une liste non vide."

    report_progress(f"🗑️ Suppression de {len(record_ids)} enregistrement(s) dans '{table_id}'…")
    ok, data = _post(
        f"/docs/{doc_id}/tables/{table_id}/records/delete",
        record_ids,
    )
    if not ok:
        return f"Erreur : {data}"

    return f"{len(record_ids)} enregistrement(s) supprimé(s) avec succès."


# ══════════════════════════════════════════════════════════════════════════════
#  9. SQL
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="grist_run_sql",
    description=(
        "Exécute une requête SQL SELECT en lecture seule sur un document Grist. "
        "Tous les documents Grist sont des bases SQLite : les tables sont accessibles "
        "directement par leur nom (ex: SELECT * FROM Projets). "
        "Retourne un tableau JSON des résultats avec leurs champs. "
        "Supporte les requêtes paramétrées (paramètre 'args') pour éviter les injections. "
        "⚠️ Uniquement des requêtes SELECT (pas d'INSERT, UPDATE, DELETE). "
        "Timeout par défaut : 1000ms."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": "Identifiant unique du document Grist.",
            },
            "sql": {
                "type": "string",
                "description": (
                    "Requête SQL SELECT. Pas de point-virgule final. "
                    "Les clauses WITH sont autorisées. "
                    "Ex: 'SELECT * FROM Projets WHERE statut = ? ORDER BY nom' "
                    "ou 'SELECT COUNT(*) as total FROM Depenses WHERE montant > 1000'"
                ),
            },
            "args": {
                "type": "array",
                "description": (
                    "Paramètres pour les '?' dans la requête SQL (optionnel). "
                    "Ex: [\"Actif\", 2024] pour 'WHERE statut = ? AND annee = ?'"
                ),
                "items": {},
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Timeout en millisecondes (max 1000, défaut 1000).",
            },
        },
        "required": ["doc_id", "sql"],
    },
)
def grist_run_sql(
    doc_id: str,
    sql: str,
    args: Optional[list] = None,
    timeout_ms: Optional[int] = None,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not doc_id.strip():
        return "Erreur : doc_id ne peut pas être vide."
    if not sql.strip():
        return "Erreur : sql ne peut pas être vide."

    # Vérification basique : seulement des SELECT
    sql_upper = sql.strip().upper()
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return "Erreur : seules les requêtes SELECT (ou WITH … SELECT) sont autorisées."

    payload: dict = {"sql": sql.strip()}
    if args:
        payload["args"] = args
    if timeout_ms is not None:
        payload["timeout"] = min(timeout_ms, 1000)

    report_progress(f"🛢️ Exécution SQL sur le document '{doc_id}'…")
    ok, data = _post(f"/docs/{doc_id}/sql", payload)
    if not ok:
        return f"Erreur : {data}"

    records = data.get("records", [])
    return json.dumps(records, ensure_ascii=False, indent=2)
