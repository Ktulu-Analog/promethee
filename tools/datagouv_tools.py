# ============================================================================
# ============================================================================
# Prométhée — Assistant IA avancé
# ============================================================================
# Auteur  : Pierre COUGET ktulu.analog@gmail.com
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
tools/datagouv_tools.py — Outils data.gouv.fr pour Prométhée
=============================================================

Intègre 10 outils data.gouv.fr dans le moteur d'outils de Prométhée.
Suit le même pattern que legifrance_tools, web_search_tools et system_tools.

L'implémentation sous forme d'outils Prométhée suit le modèle utilisé
par le serveur mcp datagouv-mcp : https://github.com/datagouv/datagouv-mcp


Usage dans main.py ou app.py :
    import tools.datagouv_tools  # noqa — enregistre les outils au démarrage

Ou via register_all() dans tools/__init__.py :
    from tools import register_all
    register_all()

Les outils sont ensuite automatiquement disponibles dans agent_loop()
via get_tool_schemas() et call_tool().

Configuration optionnelle (.env) :
    DATAGOUV_ENV=prod   # "prod" (défaut) ou "demo"

Outils disponibles (10 au total) :

  Datasets (5) :
    - datagouv_search_datasets        : recherche de jeux de données par mots-clés
    - datagouv_get_dataset_info       : métadonnées détaillées d'un jeu de données
    - datagouv_list_dataset_resources : liste les fichiers d'un jeu de données
    - datagouv_get_resource_info      : détails d'une ressource + dispo Tabular API
    - datagouv_get_metrics            : statistiques d'utilisation (visites, télécharg.)

  Données (2) :
    - datagouv_query_resource_data    : requête tabulaire sans téléchargement (CSV/XLSX)
    - datagouv_download_resource      : télécharge et parse une ressource (CSV/JSON/JSONL)

  Dataservices (3) :
    - datagouv_search_dataservices    : recherche d'APIs tierces référencées
    - datagouv_get_dataservice_info   : métadonnées d'une API tierce
    - datagouv_get_dataservice_spec   : résumé de la spec OpenAPI/Swagger d'une API

Workflow typique datasets :
    datagouv_search_datasets → datagouv_list_dataset_resources
    → datagouv_query_resource_data  (CSV/XLSX, requête rapide)
    → datagouv_download_resource    (JSON/JSONL ou analyse complète)

Workflow typique dataservices :
    datagouv_search_dataservices → datagouv_get_dataservice_info
    → datagouv_get_dataservice_spec → appel direct de l'API via base_api_url

Prérequis :
    pip install httpx pyyaml
"""

import csv
import gzip
import io
import json
import logging
import os
from typing import Any, Optional

import httpx

from core.tools_engine import tool, set_current_family, _TOOL_ICONS

# ---------------------------------------------------------------------------
# Famille et icônes
# ---------------------------------------------------------------------------

set_current_family("datagouv_tools", "Data.gouv.fr", "🇫🇷")

_TOOL_ICONS.update({
    "datagouv_search_datasets":        "🔍",
    "datagouv_get_dataset_info":       "📂",
    "datagouv_list_dataset_resources": "📋",
    "datagouv_get_resource_info":      "ℹ️",
    "datagouv_query_resource_data":    "📊",
    "datagouv_download_resource":      "⬇️",
    "datagouv_search_dataservices":    "🔎",
    "datagouv_get_dataservice_info":   "🌐",
    "datagouv_get_dataservice_spec":   "📖",
    "datagouv_get_metrics":            "📈",
})

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration des URLs selon l'environnement
# ---------------------------------------------------------------------------

_ENV_URLS = {
    "prod": {
        "api":     "https://www.data.gouv.fr/api/",
        "site":    "https://www.data.gouv.fr/",
        "tabular": "https://tabular-api.data.gouv.fr/api/",
        "metrics": "https://metric-api.data.gouv.fr/api/",
    },
    "demo": {
        "api":     "https://demo.data.gouv.fr/api/",
        "site":    "https://demo.data.gouv.fr/",
        "tabular": "https://tabular-api.preprod.data.gouv.fr/api/",
        "metrics": "https://metric-api.data.gouv.fr/api/",
    },
}


def _base(key: str) -> str:
    """Retourne l'URL de base pour la clé donnée selon DATAGOUV_ENV."""
    env = os.getenv("DATAGOUV_ENV", "prod").strip().lower()
    return _ENV_URLS.get(env, _ENV_URLS["prod"])[key]


# ---------------------------------------------------------------------------
# Client HTTP singleton — même pattern que LegifranceClient
# ---------------------------------------------------------------------------

class _DatagouvClient:
    """
    Client HTTP synchrone réutilisable pour toutes les requêtes data.gouv.fr.
    Instancié une seule fois au chargement du module (singleton _http).
    Le pool de connexions TLS est maintenu entre les appels, identique
    au pattern de legifrance_tools.py.

    Deux clients distincts :
      - _api  : requêtes API légères (timeout 30s)
      - _dl   : téléchargements de fichiers (timeout 300s)
    """

    def __init__(self) -> None:
        self._api = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        self._dl = httpx.Client(
            timeout=httpx.Timeout(300.0, connect=10.0),
            follow_redirects=True,
        )

    def get_json(self, url: str, params: Optional[dict] = None) -> dict[str, Any]:
        """GET JSON avec raise_for_status automatique."""
        resp = self._api.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def get_raw(self, url: str, timeout: float = 30.0) -> httpx.Response:
        """GET brut sur le client API (pour les endpoints non-JSON : profil Tabular, spec OpenAPI)."""
        return self._api.get(url, timeout=timeout)

    def get_bytes(self, url: str, max_size: int) -> tuple[bytes, str, str]:
        """
        Télécharge un fichier binaire avec limite de taille stricte.
        Retourne (contenu_bytes, filename, content_type).
        Lève ValueError si le fichier dépasse max_size.
        """
        resp = self._dl.get(url)
        resp.raise_for_status()

        cl = resp.headers.get("Content-Length")
        if cl and int(cl) > max_size:
            raise ValueError(
                f"Fichier trop volumineux : {int(cl) / 1024**2:.1f} Mo "
                f"(limite : {max_size / 1024**2:.0f} Mo)"
            )

        content = bytearray()
        for chunk in resp.iter_bytes(8192):
            content.extend(chunk)
            if len(content) > max_size:
                raise ValueError(
                    f"Fichier trop volumineux : dépasse {max_size / 1024**2:.0f} Mo"
                )

        # Extraction du nom de fichier
        filename = url.split("/")[-1].split("?")[0] or "resource"
        cd = resp.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            filename = cd.split("filename=")[1].strip("\"'")

        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        return bytes(content), filename, content_type


# Singleton partagé par tous les outils du module
_http = _DatagouvClient()


# ---------------------------------------------------------------------------
# Nettoyage des requêtes (stop-words — l'API data.gouv utilise la logique AND)
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "données", "donnee", "donnees",
    "fichier", "fichiers",
    "tableau", "tableaux",
    "csv", "excel", "xlsx", "json", "xml",
})


def _clean_query(query: str) -> str:
    """Supprime les mots génériques qui cassent la recherche AND de l'API."""
    words = [w for w in query.split() if w.lower().strip() not in _STOP_WORDS]
    cleaned = " ".join(words)
    if cleaned != query:
        logger.debug("Requête nettoyée : '%s' → '%s'", query, cleaned)
    return cleaned or query


# ---------------------------------------------------------------------------
# Formatage de la taille des fichiers
# ---------------------------------------------------------------------------

def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    else:
        return f"{size / 1024 ** 3:.1f} GB"


# ---------------------------------------------------------------------------
# Parsing CSV / JSON (synchrone)
# ---------------------------------------------------------------------------

def _parse_csv_bytes(content: bytes, is_gzip: bool = False) -> list[dict[str, Any]]:
    if is_gzip:
        content = gzip.decompress(content)
    text = content.decode("utf-8-sig")
    sample = "\n".join(text.split("\n")[:5])
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except (csv.Error, AttributeError):
        counts = {d: sample.count(d) for d in ",;\t|"}
        best = max(counts, key=lambda d: counts[d])
        if counts[best] >= 2:
            delimiter = best
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


def _parse_json_bytes(content: bytes, is_gzip: bool = False) -> list[dict[str, Any]]:
    if is_gzip:
        content = gzip.decompress(content)
    text = content.decode("utf-8")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass
    # Fallback JSONL (une ligne = un objet JSON)
    result = []
    for line in text.strip().split("\n"):
        if line.strip():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return result


# ============================================================================
# Outil 1 — Recherche de jeux de données
# ============================================================================

@tool(
    name="datagouv_search_datasets",
    description=(
        "Recherche des jeux de données (datasets) sur data.gouv.fr par mots-clés. "
        "C'est généralement la première étape pour explorer le portail open data français. "
        "Utiliser des requêtes courtes et spécifiques : l'API utilise la logique AND, "
        "donc les mots génériques comme 'données' ou 'fichier' donnent zéro résultat. "
        "Workflow typique : datagouv_search_datasets → datagouv_list_dataset_resources "
        "→ datagouv_query_resource_data ou datagouv_download_resource."
    ),
    parameters={
        "type": "object",
        "properties": {
            "requete": {
                "type": "string",
                "description": (
                    "Mots-clés de recherche. Exemples : 'population communes France', "
                    "'accidents routiers', 'prénom bébés 2023', 'budget état'."
                ),
            },
            "page": {
                "type": "integer",
                "description": "Numéro de page (défaut : 1).",
            },
            "taille_page": {
                "type": "integer",
                "description": "Résultats par page (défaut : 20, max : 100).",
            },
        },
        "required": ["requete"],
    },
)
def datagouv_search_datasets(
    requete: str,
    page: int = 1,
    taille_page: int = 20,
) -> str:
    cleaned = _clean_query(requete)
    params = {"q": cleaned, "page": page, "page_size": min(taille_page, 100)}

    try:
        data = _http.get_json(f"{_base('api')}1/datasets/", params)
    except httpx.HTTPStatusError as e:
        return f"Erreur HTTP {e.response.status_code} : {e}"
    except Exception as e:
        return f"Erreur : {e}"

    datasets = data.get("data", [])

    # Fallback sur la requête originale si aucun résultat avec la requête nettoyée
    if not datasets and cleaned != requete:
        params["q"] = requete
        try:
            data = _http.get_json(f"{_base('api')}1/datasets/", params)
            datasets = data.get("data", [])
        except Exception:
            pass

    if not datasets:
        return f"Aucun jeu de données trouvé pour : « {requete} »"

    lines = [
        f"Résultats pour « {requete} » : {data.get('total', len(datasets))} jeux de données",
        f"Page {page} :\n",
    ]
    for i, ds in enumerate(datasets, 1):
        lines.append(f"{i}. {ds.get('title', 'Sans titre')}")
        lines.append(f"   ID : {ds.get('id')}")
        if ds.get("description_short"):
            lines.append(f"   Description : {ds['description_short'][:200]}…")
        if ds.get("organization"):
            org = ds["organization"]
            org_name = org.get("name") if isinstance(org, dict) else org
            lines.append(f"   Organisation : {org_name}")
        tags = [
            t if isinstance(t, str) else t.get("name", "")
            for t in ds.get("tags", [])[:5]
        ]
        if tags:
            lines.append(f"   Tags : {', '.join(tags)}")
        lines.append(f"   Ressources : {len(ds.get('resources', []))}")
        slug = ds.get("slug") or ds.get("id", "")
        lines.append(f"   URL : {_base('site')}datasets/{slug}/")
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# Outil 2 — Informations sur un jeu de données
# ============================================================================

@tool(
    name="datagouv_get_dataset_info",
    description=(
        "Retourne les métadonnées détaillées d'un jeu de données data.gouv.fr : "
        "titre, description, organisation, tags, nombre de ressources, "
        "dates de création/mise à jour, licence et fréquence de mise à jour. "
        "Nécessite l'ID ou le slug du dataset (obtenus via datagouv_search_datasets)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dataset_id": {
                "type": "string",
                "description": "Identifiant ou slug du jeu de données.",
            },
        },
        "required": ["dataset_id"],
    },
)
def datagouv_get_dataset_info(dataset_id: str) -> str:
    try:
        data = _http.get_json(f"{_base('api')}1/datasets/{dataset_id}/")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Erreur : jeu de données « {dataset_id} » introuvable."
        return f"Erreur HTTP {e.response.status_code} : {e}"
    except Exception as e:
        return f"Erreur : {e}"

    lines = [f"Jeu de données : {data.get('title', 'Inconnu')}", ""]
    if data.get("id"):
        lines.append(f"ID : {data['id']}")
    if data.get("slug"):
        lines.append(f"Slug : {data['slug']}")
        lines.append(f"URL : {_base('site')}datasets/{data['slug']}/")
    if data.get("description_short"):
        lines.extend(["", f"Description : {data['description_short']}"])
    desc = data.get("description", "")
    desc_short = data.get("description_short", "")
    if desc and desc != desc_short:
        lines.extend(["", f"Description complète : {desc[:500]}…"])

    org = data.get("organization")
    if org and isinstance(org, dict):
        lines.extend(["", f"Organisation : {org.get('name', 'Inconnue')}"])
        if org.get("id"):
            lines.append(f"  ID org : {org['id']}")

    tags = [
        t if isinstance(t, str) else t.get("name", "")
        for t in data.get("tags", [])[:10]
        if t
    ]
    if tags:
        lines.extend(["", f"Tags : {', '.join(tags)}"])

    resources = data.get("resources", [])
    lines.extend(["", f"Ressources : {len(resources)} fichier(s)"])

    if data.get("created_at"):
        lines.extend(["", f"Créé le : {data['created_at']}"])
    if data.get("last_update"):
        lines.append(f"Dernière mise à jour : {data['last_update']}")
    if data.get("license"):
        lines.extend(["", f"Licence : {data['license']}"])
    if data.get("frequency"):
        lines.append(f"Fréquence de mise à jour : {data['frequency']}")

    return "\n".join(lines)


# ============================================================================
# Outil 3 — Liste des ressources d'un jeu de données
# ============================================================================

@tool(
    name="datagouv_list_dataset_resources",
    description=(
        "Liste toutes les ressources (fichiers) d'un jeu de données avec leurs métadonnées : "
        "ID, titre, format, taille et URL de téléchargement. "
        "Étape suivante : datagouv_query_resource_data pour les fichiers CSV/XLSX, "
        "ou datagouv_download_resource pour JSON/JSONL ou les gros fichiers."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dataset_id": {
                "type": "string",
                "description": "ID ou slug du jeu de données.",
            },
        },
        "required": ["dataset_id"],
    },
)
def datagouv_list_dataset_resources(dataset_id: str) -> str:
    try:
        data = _http.get_json(f"{_base('api')}1/datasets/{dataset_id}/")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Erreur : jeu de données « {dataset_id} » introuvable."
        return f"Erreur HTTP {e.response.status_code} : {e}"
    except Exception as e:
        return f"Erreur : {e}"

    resources = data.get("resources", [])
    title = data.get("title", "Inconnu")

    lines = [
        f"Ressources du jeu de données : {title}",
        f"ID dataset : {dataset_id}",
        f"Total : {len(resources)} ressource(s)\n",
    ]

    if not resources:
        lines.append("Ce jeu de données ne contient aucune ressource.")
        return "\n".join(lines)

    for i, r in enumerate(resources, 1):
        rid = r.get("id")
        if not rid:
            continue
        rtitle = r.get("title") or r.get("name") or "Sans titre"
        lines.append(f"{i}. {rtitle}")
        lines.append(f"   ID ressource : {rid}")
        if r.get("format"):
            lines.append(f"   Format : {r['format']}")
        if isinstance(r.get("filesize"), int):
            lines.append(f"   Taille : {_human_size(r['filesize'])}")
        if r.get("mime"):
            lines.append(f"   Type MIME : {r['mime']}")
        if r.get("type"):
            lines.append(f"   Type : {r['type']}")
        if r.get("url"):
            lines.append(f"   URL : {r['url']}")
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# Outil 4 — Informations sur une ressource
# ============================================================================

@tool(
    name="datagouv_get_resource_info",
    description=(
        "Retourne les informations détaillées d'une ressource (fichier) data.gouv.fr : "
        "format, taille, type MIME, URL, dataset parent, "
        "et vérifie si la ressource est disponible via l'API Tabular (requêtes sans téléchargement). "
        "Permet de choisir la meilleure stratégie d'accès aux données."
    ),
    parameters={
        "type": "object",
        "properties": {
            "resource_id": {
                "type": "string",
                "description": "Identifiant UUID de la ressource.",
            },
        },
        "required": ["resource_id"],
    },
)
def datagouv_get_resource_info(resource_id: str) -> str:
    try:
        data = _http.get_json(f"{_base('api')}2/datasets/resources/{resource_id}/")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Erreur : ressource « {resource_id} » introuvable."
        return f"Erreur HTTP {e.response.status_code} : {e}"
    except Exception as e:
        return f"Erreur : {e}"

    resource = data.get("resource", {})
    if not resource.get("id"):
        return f"Erreur : ressource « {resource_id} » introuvable."

    rtitle = resource.get("title") or resource.get("name") or "Inconnue"
    lines = [f"Ressource : {rtitle}", "", f"ID : {resource_id}"]

    if resource.get("format"):
        lines.append(f"Format : {resource['format']}")
    if isinstance(resource.get("filesize"), int):
        lines.append(f"Taille : {_human_size(resource['filesize'])}")
    if resource.get("mime"):
        lines.append(f"Type MIME : {resource['mime']}")
    if resource.get("type"):
        lines.append(f"Type : {resource['type']}")
    if resource.get("url"):
        lines.extend(["", f"URL : {resource['url']}"])
    if resource.get("description"):
        lines.extend(["", f"Description : {resource['description']}"])

    dataset_id = data.get("dataset_id")
    if dataset_id:
        lines.extend(["", f"Dataset ID : {dataset_id}"])
        try:
            ds = _http.get_json(f"{_base('api')}1/datasets/{dataset_id}/")
            if ds.get("title"):
                lines.append(f"Dataset : {ds['title']}")
        except Exception:
            pass

    # Vérification disponibilité API Tabular
    lines.extend(["", "Disponibilité API Tabular :"])
    try:
        resp = _http.get_raw(f"{_base('tabular')}resources/{resource_id}/profile/")
        if resp.status_code == 200:
            lines.append("✅ Disponible via l'API Tabular (requêtes sans téléchargement)")
        else:
            lines.append("⚠️  Non disponible via l'API Tabular")
    except Exception:
        lines.append("⚠️  Impossible de vérifier la disponibilité Tabular")

    return "\n".join(lines)


# ============================================================================
# Outil 5 — Requête sur les données tabulaires (via API Tabular)
# ============================================================================

@tool(
    name="datagouv_query_resource_data",
    description=(
        "Interroge les données tabulaires d'une ressource CSV/XLSX via l'API Tabular, "
        "sans téléchargement du fichier. Idéal pour prévisualiser la structure, "
        "filtrer ou trier des données. "
        "Commencer avec une taille_page petite (20) pour découvrir les colonnes. "
        "Opérateurs de filtre disponibles : exact, contains, less, greater, "
        "strictly_less, strictly_greater. "
        "Pour les gros datasets (>1000 lignes) nécessitant une analyse complète, "
        "préférer datagouv_download_resource."
    ),
    parameters={
        "type": "object",
        "properties": {
            "resource_id": {
                "type": "string",
                "description": "UUID de la ressource à interroger.",
            },
            "question": {
                "type": "string",
                "description": "Question ou contexte de la requête (pour traçabilité).",
            },
            "page": {
                "type": "integer",
                "description": "Numéro de page (défaut : 1).",
            },
            "taille_page": {
                "type": "integer",
                "description": "Lignes par page (défaut : 20, max : 200).",
            },
            "colonne_filtre": {
                "type": "string",
                "description": "Nom de la colonne sur laquelle filtrer.",
            },
            "valeur_filtre": {
                "type": "string",
                "description": "Valeur du filtre.",
            },
            "operateur_filtre": {
                "type": "string",
                "description": (
                    "Opérateur de comparaison : exact (défaut), contains, "
                    "less, greater, strictly_less, strictly_greater."
                ),
                "enum": ["exact", "contains", "less", "greater", "strictly_less", "strictly_greater"],
            },
            "colonne_tri": {
                "type": "string",
                "description": "Colonne sur laquelle trier les résultats.",
            },
            "sens_tri": {
                "type": "string",
                "description": "Sens du tri : 'asc' (défaut) ou 'desc'.",
                "enum": ["asc", "desc"],
            },
        },
        "required": ["resource_id", "question"],
    },
)
def datagouv_query_resource_data(
    resource_id: str,
    question: str,
    page: int = 1,
    taille_page: int = 20,
    colonne_filtre: Optional[str] = None,
    valeur_filtre: Optional[str] = None,
    operateur_filtre: str = "exact",
    colonne_tri: Optional[str] = None,
    sens_tri: str = "asc",
) -> str:
    taille_page = max(1, min(taille_page, 200))

    # Récupération des métadonnées de la ressource
    resource_title = "Inconnue"
    dataset_title = "Inconnu"
    dataset_id = None
    try:
        meta = _http.get_json(f"{_base('api')}2/datasets/resources/{resource_id}/")
        r = meta.get("resource", {})
        resource_title = r.get("title") or r.get("name") or resource_title
        dataset_id = meta.get("dataset_id")
        if dataset_id:
            ds = _http.get_json(f"{_base('api')}1/datasets/{dataset_id}/")
            dataset_title = ds.get("title", dataset_title)
    except Exception:
        pass

    lines = [
        f"Ressource interrogée : {resource_title}",
        f"ID ressource : {resource_id}",
    ]
    if dataset_id:
        lines.append(f"Dataset : {dataset_title} (ID : {dataset_id})")
    lines.extend([f"Question : {question}", ""])

    # Construction des paramètres de l'API Tabular
    params: dict[str, Any] = {"page": page, "page_size": taille_page}
    if colonne_filtre and valeur_filtre is not None:
        params[f"{colonne_filtre}__{operateur_filtre}"] = valeur_filtre
        lines.append(f"Filtre : {colonne_filtre} {operateur_filtre} {valeur_filtre}")
    if colonne_tri:
        params[f"{colonne_tri}__sort"] = sens_tri
        lines.append(f"Tri : {colonne_tri} ({sens_tri})")
    if colonne_filtre or colonne_tri:
        lines.append("")

    try:
        resp = _http._api.get(
            f"{_base('tabular')}resources/{resource_id}/data/",
            params=params,
        )
        if resp.status_code == 404:
            return "\n".join(lines) + (
                "\n⚠️  Cette ressource n'est pas disponible via l'API Tabular. "
                "Utiliser datagouv_download_resource à la place."
            )
        resp.raise_for_status()
        tabular = resp.json()
    except httpx.HTTPStatusError as e:
        return "\n".join(lines) + f"\n❌ Erreur API Tabular : HTTP {e.response.status_code}"
    except Exception as e:
        return "\n".join(lines) + f"\n❌ Erreur : {e}"

    rows = tabular.get("data", [])
    meta_info = tabular.get("meta", {})
    total = meta_info.get("total")
    page_size_meta = meta_info.get("page_size")
    page_info = meta_info.get("page")

    if not rows:
        lines.append("⚠️  Aucune ligne retournée (ressource vide ou filtre trop restrictif).")
        return "\n".join(lines)

    if total is not None:
        lines.append(f"Total lignes (API Tabular) : {total:,}")
        if page_size_meta and page_size_meta > 0:
            total_pages = (total + page_size_meta - 1) // page_size_meta
            lines.append(f"Pages totales : {total_pages} (taille page : {page_size_meta})")
    lines.append(f"Lignes retournées : {len(rows)} (page {page_info or page})")

    cols = [str(k) for k in rows[0].keys()]
    lines.append(f"Colonnes : {', '.join(cols)}")
    lines.extend(["", f"Données ({len(rows)} ligne(s)) :"])

    for i, row in enumerate(rows, 1):
        lines.append(f"  Ligne {i} :")
        for k, v in row.items():
            val = str(v) if v is not None else ""
            if len(val) > 100:
                val = val[:100] + "…"
            lines.append(f"    {k} : {val}")

    if tabular.get("links", {}).get("next"):
        next_page = page + 1
        if total and total > 1000:
            lines.extend([
                "",
                f"⚠️  Grand dataset ({total:,} lignes). "
                "Pour une analyse complète, utiliser datagouv_download_resource.",
                f"   Pour continuer page par page : page={next_page}.",
            ])
        else:
            lines.extend(["", f"📄 Suite disponible. Utiliser page={next_page}."])

    return "\n".join(lines)


# ============================================================================
# Outil 6 — Téléchargement et parsing direct d'une ressource
# ============================================================================

@tool(
    name="datagouv_download_resource",
    description=(
        "Télécharge et parse directement une ressource data.gouv.fr. "
        "Utile pour les fichiers JSON/JSONL, les archives CSV.GZ, "
        "ou quand une analyse complète du dataset est nécessaire. "
        "Formats supportés : CSV, CSV.GZ, JSON, JSONL. "
        "Commencer avec max_lignes=20 pour découvrir la structure, "
        "puis augmenter si besoin. "
        "Pour les CSV/XLSX avec prévisualisation rapide, préférer datagouv_query_resource_data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "resource_id": {
                "type": "string",
                "description": "UUID de la ressource à télécharger.",
            },
            "max_lignes": {
                "type": "integer",
                "description": "Nombre maximum de lignes à retourner (défaut : 20).",
            },
            "taille_max_mo": {
                "type": "integer",
                "description": "Taille maximale du fichier à télécharger en Mo (défaut : 500).",
            },
        },
        "required": ["resource_id"],
    },
)
def datagouv_download_resource(
    resource_id: str,
    max_lignes: int = 20,
    taille_max_mo: int = 500,
) -> str:
    try:
        data = _http.get_json(f"{_base('api')}2/datasets/resources/{resource_id}/")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Erreur : ressource « {resource_id} » introuvable."
        return f"Erreur HTTP {e.response.status_code} : {e}"
    except Exception as e:
        return f"Erreur : {e}"

    resource = data.get("resource", {})
    if not resource.get("id"):
        return f"Erreur : ressource « {resource_id} » introuvable."

    url = resource.get("url")
    if not url:
        return f"Erreur : la ressource {resource_id} n'a pas d'URL de téléchargement."

    rtitle = resource.get("title") or resource.get("name") or "Inconnue"
    lines = [
        f"Téléchargement de la ressource : {rtitle}",
        f"ID ressource : {resource_id}",
        f"URL : {url}",
        "",
    ]

    # Téléchargement via le client dédié _dl (timeout 300s)
    max_size = taille_max_mo * 1024 * 1024
    try:
        content_bytes, filename, content_type = _http.get_bytes(url, max_size)
    except ValueError as e:
        return "\n".join(lines) + f"\n❌ {e}"
    except Exception as e:
        return "\n".join(lines) + f"\n❌ Erreur de téléchargement : {e}"

    lines.append(f"Téléchargé : {len(content_bytes) / 1024**2:.2f} Mo")

    # Détection du format
    fn_lower = filename.lower()
    ct_lower = content_type.lower()
    is_gzip = fn_lower.endswith(".gz") or "gzip" in ct_lower

    if fn_lower.endswith(".csv") or fn_lower.endswith(".csv.gz") or "csv" in ct_lower:
        fmt = "csv"
    elif fn_lower.endswith((".json", ".jsonl", ".ndjson")) or "json" in ct_lower:
        fmt = "json"
    elif fn_lower.endswith(".xlsx") or "excel" in ct_lower or "spreadsheet" in ct_lower:
        fmt = "xlsx"
    elif fn_lower.endswith(".xls"):
        fmt = "xls"
    elif fn_lower.endswith(".xml") or "xml" in ct_lower:
        fmt = "xml"
    else:
        fmt = "inconnu"

    # Parsing
    rows: list[dict[str, Any]] = []
    if fmt == "csv":
        lines.append("Format : CSV")
        try:
            rows = _parse_csv_bytes(content_bytes, is_gzip=is_gzip)
        except Exception as e:
            return "\n".join(lines) + f"\n❌ Erreur de parsing CSV : {e}"
    elif fmt == "json":
        lines.append("Format : JSON/JSONL")
        try:
            rows = _parse_json_bytes(content_bytes, is_gzip=is_gzip)
        except Exception as e:
            return "\n".join(lines) + f"\n❌ Erreur de parsing JSON : {e}"
    elif fmt == "xlsx":
        return "\n".join(lines) + (
            "\nFormat : XLSX\n"
            "⚠️  Le parsing XLSX nécessite openpyxl. "
            "Utiliser datagouv_query_resource_data pour les fichiers XLSX."
        )
    elif fmt == "xls":
        return "\n".join(lines) + "\nFormat : XLS\n⚠️  Format XLS non supporté. Convertir en CSV/XLSX."
    elif fmt == "xml":
        return "\n".join(lines) + "\nFormat : XML\n⚠️  Parsing XML non implémenté."
    else:
        return "\n".join(lines) + (
            f"\nFormat inconnu (fichier : {filename}, type : {content_type}).\n"
            "Formats supportés : CSV, CSV.GZ, JSON, JSONL."
        )

    if not rows:
        lines.extend(["", "⚠️  Aucune ligne trouvée dans le fichier."])
        return "\n".join(lines)

    total_rows = len(rows)
    rows = rows[:max_lignes]
    lines.extend(["", f"Total lignes dans le fichier : {total_rows:,}"])
    lines.append(f"Lignes retournées : {len(rows)}")
    cols = [str(k) for k in rows[0].keys()]
    lines.append(f"Colonnes : {', '.join(cols)}")
    lines.extend(["", f"Données ({len(rows)} ligne(s)) :"])

    for i, row in enumerate(rows, 1):
        lines.append(f"  Ligne {i} :")
        for k, v in row.items():
            val = str(v) if v is not None else ""
            if len(val) > 100:
                val = val[:100] + "…"
            lines.append(f"    {k} : {val}")

    if total_rows > max_lignes:
        lines.extend([
            "",
            f"⚠️  Fichier complet : {total_rows:,} lignes. "
            f"Seules les {max_lignes} premières sont affichées. "
            "Augmenter max_lignes pour voir plus.",
        ])

    return "\n".join(lines)


# ============================================================================
# Outil 7 — Recherche de dataservices (APIs tierces)
# ============================================================================

@tool(
    name="datagouv_search_dataservices",
    description=(
        "Recherche des dataservices (APIs tierces référencées) sur data.gouv.fr. "
        "Les dataservices sont des APIs externes offrant un accès programmatique "
        "aux données (contrairement aux datasets qui sont des fichiers statiques). "
        "Workflow : datagouv_search_dataservices → datagouv_get_dataservice_info "
        "→ datagouv_get_dataservice_spec → appel direct de l'API."
    ),
    parameters={
        "type": "object",
        "properties": {
            "requete": {
                "type": "string",
                "description": (
                    "Mots-clés de recherche. Exemples : 'adresse', 'sirene entreprises', "
                    "'cadastre', 'DVF transactions immobilières'."
                ),
            },
            "page": {
                "type": "integer",
                "description": "Numéro de page (défaut : 1).",
            },
            "taille_page": {
                "type": "integer",
                "description": "Résultats par page (défaut : 20, max : 100).",
            },
        },
        "required": ["requete"],
    },
)
def datagouv_search_dataservices(
    requete: str,
    page: int = 1,
    taille_page: int = 20,
) -> str:
    cleaned = _clean_query(requete)
    params = {"q": cleaned, "page": page, "page_size": min(taille_page, 100)}

    try:
        data = _http.get_json(f"{_base('api')}1/dataservices/", params)
    except httpx.HTTPStatusError as e:
        return f"Erreur HTTP {e.response.status_code} : {e}"
    except Exception as e:
        return f"Erreur : {e}"

    services = data.get("data", [])

    if not services and cleaned != requete:
        params["q"] = requete
        try:
            data = _http.get_json(f"{_base('api')}1/dataservices/", params)
            services = data.get("data", [])
        except Exception:
            pass

    if not services:
        return f"Aucun dataservice trouvé pour : « {requete} »"

    lines = [
        f"Résultats pour « {requete} » : {data.get('total', len(services))} dataservice(s)",
        f"Page {page} :\n",
    ]
    for i, ds in enumerate(services, 1):
        lines.append(f"{i}. {ds.get('title', 'Sans titre')}")
        lines.append(f"   ID : {ds.get('id')}")
        if ds.get("description"):
            lines.append(f"   Description : {ds['description'][:200]}…")
        if ds.get("organization"):
            org = ds["organization"]
            org_name = org.get("name") if isinstance(org, dict) else org
            lines.append(f"   Organisation : {org_name}")
        if ds.get("base_api_url"):
            lines.append(f"   URL API : {ds['base_api_url']}")
        tags = [
            t if isinstance(t, str) else t.get("name", "")
            for t in ds.get("tags", [])[:5]
        ]
        if tags:
            lines.append(f"   Tags : {', '.join(tags)}")
        lines.append(f"   URL : {_base('site')}dataservices/{ds.get('id', '')}/")
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# Outil 8 — Informations sur un dataservice
# ============================================================================

@tool(
    name="datagouv_get_dataservice_info",
    description=(
        "Retourne les métadonnées détaillées d'un dataservice (API tierce) data.gouv.fr : "
        "titre, description, organisation, URL de base de l'API, "
        "URL de la spec OpenAPI/Swagger, licence et dates. "
        "Étape préalable avant datagouv_get_dataservice_spec."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dataservice_id": {
                "type": "string",
                "description": "Identifiant UUID du dataservice.",
            },
        },
        "required": ["dataservice_id"],
    },
)
def datagouv_get_dataservice_info(dataservice_id: str) -> str:
    try:
        data = _http.get_json(f"{_base('api')}1/dataservices/{dataservice_id}/")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Erreur : dataservice « {dataservice_id} » introuvable."
        return f"Erreur HTTP {e.response.status_code} : {e}"
    except Exception as e:
        return f"Erreur : {e}"

    lines = [f"Dataservice : {data.get('title', 'Inconnu')}", ""]
    if data.get("id"):
        lines.append(f"ID : {data['id']}")
    lines.append(f"URL : {_base('site')}dataservices/{data.get('id', '')}/")

    if data.get("description"):
        lines.extend(["", f"Description : {data['description'][:500]}…"])

    lines.append("")
    if data.get("base_api_url"):
        lines.append(f"URL de base de l'API : {data['base_api_url']}")
    if data.get("machine_documentation_url"):
        lines.append(f"Spec OpenAPI/Swagger : {data['machine_documentation_url']}")

    org = data.get("organization")
    if org and isinstance(org, dict):
        lines.extend(["", f"Organisation : {org.get('name', 'Inconnue')}"])
        if org.get("id"):
            lines.append(f"  ID org : {org['id']}")

    tags = [
        t if isinstance(t, str) else t.get("name", "")
        for t in data.get("tags", [])[:10]
        if t
    ]
    if tags:
        lines.extend(["", f"Tags : {', '.join(tags)}"])

    if data.get("created_at"):
        lines.extend(["", f"Créé le : {data['created_at']}"])
    if data.get("last_update"):
        lines.append(f"Dernière mise à jour : {data['last_update']}")
    if data.get("license"):
        lines.extend(["", f"Licence : {data['license']}"])

    datasets = data.get("datasets", {})
    if isinstance(datasets, dict) and datasets.get("total"):
        lines.extend(["", f"Datasets liés : {datasets['total']}"])

    return "\n".join(lines)


# ============================================================================
# Outil 9 — Spec OpenAPI d'un dataservice
# ============================================================================

def _summarize_openapi(spec: dict[str, Any]) -> str:
    """Résume une spec OpenAPI en texte compact (endpoints + paramètres)."""
    parts: list[str] = []

    info = spec.get("info", {})
    if info.get("title"):
        parts.append(f"API : {info['title']}")
    if info.get("version"):
        parts.append(f"Version : {info['version']}")
    if info.get("description"):
        parts.append(f"Description : {info['description'][:300]}…")

    servers = spec.get("servers", [])
    if servers:
        parts.extend(["", "Serveurs :"])
        for s in servers[:3]:
            u = s.get("url", "")
            d = s.get("description", "")
            parts.append(f"  - {u}" + (f" ({d})" if d else ""))

    if spec.get("host"):
        scheme = (spec.get("schemes") or ["https"])[0]
        base_path = spec.get("basePath", "")
        parts.append(f"\nURL de base : {scheme}://{spec['host']}{base_path}")

    paths = spec.get("paths", {})
    if paths:
        parts.extend(["", f"Endpoints ({len(paths)} chemins) :"])
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, details in methods.items():
                if method.startswith("x-") or method == "parameters":
                    continue
                if not isinstance(details, dict):
                    continue
                summary = details.get("summary") or details.get("description", "")
                summary = summary.split("\n")[0][:120] if summary else ""
                parts.append(f"  {method.upper()} {path}")
                if summary:
                    parts.append(f"    {summary}")
                for p in details.get("parameters", []):
                    name = p.get("name", "?")
                    loc = p.get("in", "")
                    required = " (requis)" if p.get("required") else ""
                    ptype = p.get("schema", {}).get("type", "")
                    parts.append(f"      - {name} [{loc}, {ptype}]{required}")

    return "\n".join(parts)


@tool(
    name="datagouv_get_dataservice_spec",
    description=(
        "Récupère et résume la spec OpenAPI/Swagger d'un dataservice data.gouv.fr. "
        "Retourne la liste des endpoints avec leurs paramètres, "
        "permettant de comprendre comment appeler l'API. "
        "Utiliser datagouv_get_dataservice_info en amont pour obtenir l'ID."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dataservice_id": {
                "type": "string",
                "description": "UUID du dataservice dont on veut la spec OpenAPI.",
            },
        },
        "required": ["dataservice_id"],
    },
)
def datagouv_get_dataservice_spec(dataservice_id: str) -> str:
    try:
        data = _http.get_json(f"{_base('api')}1/dataservices/{dataservice_id}/")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Erreur : dataservice « {dataservice_id} » introuvable."
        return f"Erreur HTTP {e.response.status_code} : {e}"
    except Exception as e:
        return f"Erreur : {e}"

    doc_url = data.get("machine_documentation_url")
    base_url = data.get("base_api_url")
    title = data.get("title", "Inconnu")

    if not doc_url:
        msg = f"Le dataservice « {title} » n'a pas de spec OpenAPI (machine_documentation_url absent)."
        if base_url:
            msg += f"\nURL de base de l'API : {base_url}"
        return msg

    try:
        resp = _http.get_raw(doc_url, timeout=15.0)
        resp.raise_for_status()
        text = resp.text
    except httpx.HTTPStatusError as e:
        return f"Erreur HTTP {e.response.status_code} lors de la récupération de la spec."
    except Exception as e:
        return f"Erreur lors de la récupération de la spec : {e}"

    # Parsing JSON ou YAML
    spec: dict[str, Any] = {}
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
            spec = yaml.safe_load(text)
        except ImportError:
            return (
                "Le module 'pyyaml' est nécessaire pour parser les specs YAML.\n"
                "Installer avec : pip install pyyaml"
            )
        except Exception:
            return f"Impossible de parser la spec depuis : {doc_url}"

    lines = [f"Spec OpenAPI de : {title}", f"Source : {doc_url}"]
    if base_url:
        lines.append(f"URL de base de l'API : {base_url}")
    lines.extend(["", _summarize_openapi(spec)])

    return "\n".join(lines)


# ============================================================================
# Outil 10 — Métriques d'utilisation
# ============================================================================

@tool(
    name="datagouv_get_metrics",
    description=(
        "Retourne les statistiques d'utilisation mensuelles (visites, téléchargements) "
        "pour un jeu de données ou une ressource data.gouv.fr. "
        "Au moins un des deux paramètres dataset_id ou resource_id doit être fourni. "
        "Résultats triés du plus récent au plus ancien. "
        "Note : uniquement disponible en environnement de production (DATAGOUV_ENV=prod)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dataset_id": {
                "type": "string",
                "description": "ID du jeu de données dont on veut les métriques.",
            },
            "resource_id": {
                "type": "string",
                "description": "ID de la ressource dont on veut les métriques.",
            },
            "limite": {
                "type": "integer",
                "description": "Nombre de mois à retourner (défaut : 12, max : 100).",
            },
        },
        "required": [],
    },
)
def datagouv_get_metrics(
    dataset_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    limite: int = 12,
) -> str:
    env = os.getenv("DATAGOUV_ENV", "prod").strip().lower()
    if env == "demo":
        return (
            "Erreur : l'API Métriques n'est pas disponible en environnement demo.\n"
            "Définir DATAGOUV_ENV=prod pour accéder aux métriques."
        )
    if not dataset_id and not resource_id:
        return "Erreur : fournir au moins dataset_id ou resource_id."

    limite = max(1, min(limite, 100))
    lines: list[str] = []

    def _fetch_metrics(entity_type: str, entity_id: str) -> list[dict]:
        try:
            data = _http.get_json(
                f"{_base('metrics')}{entity_type}/{entity_id}/metrics/",
                params={"limit": limite},
            )
            return data if isinstance(data, list) else data.get("data", [])
        except Exception as e:
            logger.warning("Erreur métriques %s/%s : %s", entity_type, entity_id, e)
            return []

    # Métriques dataset
    if dataset_id:
        ds_id = str(dataset_id).strip()
        ds_title = "Inconnu"
        try:
            ds = _http.get_json(f"{_base('api')}1/datasets/{ds_id}/")
            ds_title = ds.get("title", ds_title)
        except Exception:
            pass

        lines.extend([f"Métriques du dataset : {ds_title}", f"ID dataset : {ds_id}", ""])

        metrics = _fetch_metrics("datasets", ds_id)
        if not metrics:
            lines.append("Aucune métrique disponible pour ce dataset.")
        else:
            lines.extend([
                "Statistiques mensuelles :",
                "-" * 60,
                f"{'Mois':<12} {'Visites':<15} {'Téléchargements':<15}",
                "-" * 60,
            ])
            total_v = total_d = 0
            for entry in metrics:
                month = entry.get("metric_month", "Inconnu")
                visits = entry.get("monthly_visit", 0)
                dls = entry.get("monthly_download_resource", 0)
                total_v += visits
                total_d += dls
                lines.append(f"{month:<12} {visits:<15,} {dls:<15,}")
            lines.extend(["-" * 60, f"{'Total':<12} {total_v:<15,} {total_d:<15,}"])

        if resource_id:
            lines.extend(["", ""])

    # Métriques ressource
    if resource_id:
        r_id = str(resource_id).strip()
        r_title = "Inconnue"
        try:
            meta = _http.get_json(f"{_base('api')}2/datasets/resources/{r_id}/")
            r = meta.get("resource", {})
            r_title = r.get("title") or r.get("name") or r_title
        except Exception:
            pass

        lines.extend([f"Métriques de la ressource : {r_title}", f"ID ressource : {r_id}", ""])

        metrics = _fetch_metrics("resources", r_id)
        if not metrics:
            lines.append("Aucune métrique disponible pour cette ressource.")
        else:
            lines.extend([
                "Statistiques mensuelles :",
                "-" * 40,
                f"{'Mois':<12} {'Téléchargements':<15}",
                "-" * 40,
            ])
            total_d = 0
            for entry in metrics:
                month = entry.get("metric_month", "Inconnu")
                dls = entry.get("monthly_download_resource", 0)
                total_d += dls
                lines.append(f"{month:<12} {dls:<15,}")
            lines.extend(["-" * 40, f"{'Total':<12} {total_d:<15,}"])

    return "\n".join(lines)
