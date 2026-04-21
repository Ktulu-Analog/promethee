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
tools/docs_tools.py — Outils API Docs pour Prométhée
=====================================================

Famille d'outils permettant d'interagir avec une instance Docs via son API REST.
Docs est un éditeur de documents collaboratif open-source.

Outils exposés (30) :

  Utilisateurs (3) :
    - docs_get_me                    : informations sur l'utilisateur courant
    - docs_search_users              : recherche d'utilisateurs par nom ou email
    - docs_update_profile            : mise à jour partielle du profil utilisateur

  Documents — navigation (5) :
    - docs_list_documents            : liste les documents racine accessibles
    - docs_get_document              : récupère les métadonnées d'un document
    - docs_get_children              : liste les enfants directs d'un document
    - docs_get_tree                  : arbre ancêtres + enfants d'un document (sidebar)
    - docs_search_documents          : recherche de documents par texte

  Documents — création / modification (5) :
    - docs_create_document           : crée un document (racine ou enfant)
    - docs_update_document           : met à jour le titre et/ou le contenu
    - docs_delete_document           : déplace le document dans la corbeille
    - docs_restore_document          : restaure un document depuis la corbeille
    - docs_duplicate_document        : duplique un document (avec accès et/ou descendants)

  Documents — organisation (3) :
    - docs_move_document             : déplace un document dans l'arborescence
    - docs_get_content               : récupère le contenu lisible d'un document
    - docs_configure_link            : configure le partage par lien public

  Documents — favoris & masquage (4) :
    - docs_list_favorites            : liste les documents favoris
    - docs_add_favorite              : marque un document comme favori
    - docs_remove_favorite           : retire un document des favoris
    - docs_mask_document             : masque / démasque un document dans la liste

  Accès (3) :
    - docs_list_accesses             : liste les accès d'un document
    - docs_create_access             : accorde l'accès à un utilisateur ou une équipe
    - docs_update_access             : modifie le rôle d'un accès existant
    - docs_delete_access             : révoque un accès

  Invitations (3) :
    - docs_list_invitations          : liste les invitations en attente
    - docs_invite_user               : invite un utilisateur par email
    - docs_update_invitation         : modifie le rôle d'une invitation
    - docs_cancel_invitation         : annule une invitation

  Versions (3) :
    - docs_list_versions             : liste l'historique des versions d'un document
    - docs_get_version               : récupère le contenu d'une version spécifique
    - docs_delete_version            : supprime une version spécifique

  Commentaires (7) :
    - docs_list_threads              : liste les threads de commentaires actifs
    - docs_create_thread             : crée un thread avec un premier commentaire
    - docs_resolve_thread            : marque un thread comme résolu
    - docs_delete_thread             : supprime un thread
    - docs_list_comments             : liste les commentaires d'un thread
    - docs_add_comment               : ajoute un commentaire à un thread
    - docs_delete_comment            : supprime un commentaire

Configuration requise (.env) :
    DOCS_API_TOKEN=votre_bearer_token_oidc
    DOCS_BASE_URL=http://localhost:8071   # URL de base de l'instance Docs

Usage :
    import tools.docs_tools   # suffit à enregistrer les outils

Prérequis :
    pip install requests
"""

# ── Imports standard ──────────────────────────────────────────────────────────
import json
from typing import Optional

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

set_current_family("docs_tools", "Docs", "📝")

_TOOL_ICONS.update({
    # Utilisateurs
    "docs_get_me":                "👤",
    "docs_search_users":          "🔍",
    "docs_update_profile":        "✏️",
    # Navigation
    "docs_list_documents":        "📄",
    "docs_get_document":          "🔍",
    "docs_get_children":          "📂",
    "docs_get_tree":              "🌲",
    "docs_search_documents":      "🔎",
    # Création / modification
    "docs_create_document":       "➕",
    "docs_update_document":       "✏️",
    "docs_delete_document":       "🗑️",
    "docs_restore_document":      "♻️",
    "docs_duplicate_document":    "📋",
    # Organisation
    "docs_move_document":         "↔️",
    "docs_get_content":           "📖",
    "docs_configure_link":        "🔗",
    # Favoris & masquage
    "docs_list_favorites":        "⭐",
    "docs_add_favorite":          "⭐",
    "docs_remove_favorite":       "☆",
    "docs_mask_document":         "👁️",
    # Accès
    "docs_list_accesses":         "🔐",
    "docs_create_access":         "🔑",
    "docs_update_access":         "🔄",
    "docs_delete_access":         "❌",
    # Invitations
    "docs_list_invitations":      "📬",
    "docs_invite_user":           "✉️",
    "docs_update_invitation":     "🔄",
    "docs_cancel_invitation":     "❌",
    # Versions
    "docs_list_versions":         "🕐",
    "docs_get_version":           "📜",
    "docs_delete_version":        "🗑️",
    # Commentaires
    "docs_list_threads":          "💬",
    "docs_create_thread":         "💬",
    "docs_resolve_thread":        "✅",
    "docs_delete_thread":         "🗑️",
    "docs_list_comments":         "🗨️",
    "docs_add_comment":           "🗨️",
    "docs_delete_comment":        "🗑️",
})


# ══════════════════════════════════════════════════════════════════════════════
#  2. HELPERS INTERNES
# ══════════════════════════════════════════════════════════════════════════════

def _docs_cfg():
    """Retourne le UserConfig actif ou None (fallback sur Config global)."""
    try:
        from core.request_context import get_user_config
        uc = get_user_config()
        return uc if uc is not None else None
    except ImportError:
        return None


def _get_headers() -> dict:
    """Construit les headers HTTP avec le token Bearer Docs."""
    _uc = _docs_cfg()
    token = (_uc.DOCS_API_TOKEN if _uc else None) or Config.DOCS_API_TOKEN
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    """Retourne l'URL de base de l'API Docs (sans slash final)."""
    _uc = _docs_cfg()
    base = (_uc.DOCS_BASE_URL if _uc else None) or Config.DOCS_BASE_URL
    return base.rstrip("/")


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
    _uc = _docs_cfg()
    token = (_uc.DOCS_API_TOKEN if _uc else None) or Config.DOCS_API_TOKEN
    if not token:
        return "Erreur : DOCS_API_TOKEN est absent du fichier .env."
    base = (_uc.DOCS_BASE_URL if _uc else None) or Config.DOCS_BASE_URL
    if not base:
        return "Erreur : DOCS_BASE_URL est absent du fichier .env."
    return None


def _get(path: str, params: Optional[dict] = None) -> tuple[bool, any]:
    """Effectue une requête GET sur l'API Docs. Retourne (succès, données/erreur)."""
    try:
        url = f"{_base_url()}{path}"
        resp = requests.get(url, headers=_get_headers(), params=params, timeout=30)
        resp.raise_for_status()
        return True, resp.json() if resp.content else {}
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


def _post(path: str, payload: Optional[dict] = None) -> tuple[bool, any]:
    """Effectue une requête POST sur l'API Docs."""
    try:
        url = f"{_base_url()}{path}"
        resp = requests.post(url, headers=_get_headers(), json=payload or {}, timeout=30)
        resp.raise_for_status()
        return True, resp.json() if resp.content else {"status": "ok"}
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


def _patch(path: str, payload: dict) -> tuple[bool, any]:
    """Effectue une requête PATCH sur l'API Docs."""
    try:
        url = f"{_base_url()}{path}"
        resp = requests.patch(url, headers=_get_headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return True, resp.json() if resp.content else {"status": "ok"}
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


def _put(path: str, payload: dict) -> tuple[bool, any]:
    """Effectue une requête PUT sur l'API Docs."""
    try:
        url = f"{_base_url()}{path}"
        resp = requests.put(url, headers=_get_headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return True, resp.json() if resp.content else {"status": "ok"}
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


def _delete(path: str) -> tuple[bool, any]:
    """Effectue une requête DELETE sur l'API Docs."""
    try:
        url = f"{_base_url()}{path}"
        resp = requests.delete(url, headers=_get_headers(), timeout=30)
        resp.raise_for_status()
        return True, resp.json() if resp.content else {"status": "ok"}
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return False, f"Erreur HTTP {e.response.status_code} : {detail}"
    except requests.exceptions.RequestException as e:
        return False, f"Erreur réseau : {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  3. UTILISATEURS
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_get_me",
    description=(
        "Retourne les informations de l'utilisateur actuellement authentifié sur Docs "
        "(identifiant, nom, email, langue, statut onboarding). "
        "À appeler en priorité pour connaître l'identité de l'utilisateur courant "
        "avant toute opération nécessitant son ID."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def docs_get_me() -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress("👤 Récupération du profil utilisateur…")
    ok, data = _get("/users/me/")
    if not ok:
        return f"Erreur lors de la récupération du profil : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_search_users",
    description=(
        "Recherche des utilisateurs Docs par nom ou email (recherche trigram + Levenshtein). "
        "Les résultats sont limités aux utilisateurs partageant des documents avec l'utilisateur "
        "courant ou ayant le même domaine email. "
        "Retourne une liste JSON d'utilisateurs avec leurs id, nom et email. "
        "Utiliser avant docs_create_access pour obtenir l'ID d'un utilisateur à inviter."
    ),
    parameters={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "Requête de recherche : prénom, nom ou email. Ex : 'alice' ou 'alice@exemple.fr'.",
            },
            "document_id": {
                "type": "string",
                "description": "(Optionnel) UUID du document : exclut les utilisateurs déjà membres. "
                               "Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["q"],
    },
)
def docs_search_users(q: str, document_id: Optional[str] = None) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if len(q.strip()) < 2:
        return "Erreur : la requête de recherche doit contenir au moins 2 caractères."

    report_progress(f"🔍 Recherche d'utilisateurs : '{q}'…")
    params: dict = {"q": q}
    if document_id:
        params["document_id"] = document_id

    ok, data = _get("/users/", params=params)
    if not ok:
        return f"Erreur lors de la recherche d'utilisateurs : {data}"

    results = data if isinstance(data, list) else data.get("results", data)
    if not results:
        return f"Aucun utilisateur trouvé pour la requête '{q}'."
    return json.dumps(results, ensure_ascii=False, indent=2)


@tool(
    name="docs_update_profile",
    description=(
        "Met à jour partiellement le profil de l'utilisateur courant sur Docs. "
        "Permet de modifier le nom complet (full_name) ou la langue (language). "
        "Retourne le profil mis à jour au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "UUID de l'utilisateur courant (obtenu via docs_get_me). "
                               "Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "full_name": {
                "type": "string",
                "description": "(Optionnel) Nouveau nom complet. Ex : 'Alice Martin'.",
            },
            "language": {
                "type": "string",
                "description": "(Optionnel) Code de langue. Ex : 'fr-fr', 'en-us'.",
            },
        },
        "required": ["user_id"],
    },
)
def docs_update_profile(
    user_id: str,
    full_name: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    payload: dict = {}
    if full_name is not None:
        payload["full_name"] = full_name
    if language is not None:
        payload["language"] = language

    if not payload:
        return "Erreur : aucun champ à mettre à jour (full_name ou language requis)."

    report_progress("✏️ Mise à jour du profil…")
    ok, data = _patch(f"/users/{user_id}/", payload)
    if not ok:
        return f"Erreur lors de la mise à jour du profil : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  4. DOCUMENTS — NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_list_documents",
    description=(
        "Liste les documents racine accessibles par l'utilisateur courant sur Docs. "
        "Ne retourne que les documents de premier niveau (sans parent). "
        "Pour parcourir une arborescence, enchaîner avec docs_get_children. "
        "Retourne une liste JSON paginée avec id, titre, dates et rôle de l'utilisateur."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page": {
                "type": "integer",
                "description": "(Optionnel) Numéro de page (commence à 1). Défaut : 1.",
            },
            "page_size": {
                "type": "integer",
                "description": "(Optionnel) Nombre de résultats par page (1–100). Défaut : 20.",
            },
        },
        "required": [],
    },
)
def docs_list_documents(page: int = 1, page_size: int = 20) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress("📄 Récupération des documents…")
    params: dict = {"page": page, "page_size": page_size}
    ok, data = _get("/documents/", params=params)
    if not ok:
        return f"Erreur lors de la récupération des documents : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_get_document",
    description=(
        "Récupère les métadonnées complètes d'un document Docs : titre, id, dates de création "
        "et modification, rôle de l'utilisateur, configuration de partage par lien. "
        "Retourne un objet JSON. Ne retourne pas le contenu éditorial — utiliser docs_get_content pour cela."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_get_document(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🔍 Récupération du document {document_id}…")
    ok, data = _get(f"/documents/{document_id}/")
    if not ok:
        return f"Erreur lors de la récupération du document : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_get_children",
    description=(
        "Liste les documents enfants directs d'un document parent dans Docs. "
        "Permet de parcourir l'arborescence niveau par niveau. "
        "Retourne une liste JSON avec id, titre, et métadonnées de chaque enfant."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document parent. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_get_children(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"📂 Récupération des enfants du document {document_id}…")
    ok, data = _get(f"/documents/{document_id}/children/")
    if not ok:
        return f"Erreur lors de la récupération des enfants : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_get_tree",
    description=(
        "Retourne l'arbre de navigation centré sur un document : ses ancêtres et ses enfants directs. "
        "Utilisé pour situer un document dans la hiérarchie (équivalent de la sidebar). "
        "Retourne une structure JSON imbriquée avec les nœuds parent et enfants."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document central. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_get_tree(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🌲 Récupération de l'arbre du document {document_id}…")
    ok, data = _get(f"/documents/{document_id}/tree/")
    if not ok:
        return f"Erreur lors de la récupération de l'arbre : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_search_documents",
    description=(
        "Recherche des documents Docs par texte (titre et contenu). "
        "Utilise la recherche hybride/fulltext si configurée sur l'instance, "
        "sinon repli sur la recherche par titre. "
        "Retourne une liste JSON de documents correspondants avec id, titre et extrait."
    ),
    parameters={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "Requête de recherche. Ex : 'rapport annuel 2025'.",
            },
            "path": {
                "type": "string",
                "description": "(Optionnel) Restreindre la recherche à un sous-arbre "
                               "(chemin treebeard du document racine). "
                               "Ex : '0001.0002'.",
            },
        },
        "required": ["q"],
    },
)
def docs_search_documents(q: str, path: Optional[str] = None) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not q.strip():
        return "Erreur : la requête de recherche ne peut pas être vide."

    report_progress(f"🔎 Recherche de documents : '{q}'…")
    params: dict = {"q": q}
    if path:
        params["path"] = path

    ok, data = _get("/documents/search/", params=params)
    if not ok:
        return f"Erreur lors de la recherche de documents : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  5. DOCUMENTS — CRÉATION / MODIFICATION
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_create_document",
    description=(
        "Crée un nouveau document sur Docs. "
        "Peut créer un document racine ou un document enfant (si parent_id est fourni). "
        "Retourne les métadonnées du document créé au format JSON, dont son id. "
        "Le contenu est au format HTML ou Markdown selon la configuration de l'instance."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "(Optionnel) Titre du document. Ex : 'Compte-rendu réunion du 10/04/2026'.",
            },
            "content": {
                "type": "string",
                "description": "(Optionnel) Contenu initial du document en HTML ou Markdown.",
            },
            "parent_id": {
                "type": "string",
                "description": "(Optionnel) UUID du document parent pour créer un enfant. "
                               "Si absent, le document est créé à la racine. "
                               "Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": [],
    },
)
def docs_create_document(
    title: Optional[str] = None,
    content: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    payload: dict = {}
    if title:
        payload["title"] = title
    if content:
        payload["content"] = content

    if parent_id:
        report_progress(f"➕ Création d'un document enfant sous {parent_id}…")
        ok, data = _post(f"/documents/{parent_id}/children/", payload)
    else:
        report_progress("➕ Création d'un document racine…")
        ok, data = _post("/documents/", payload)

    if not ok:
        return f"Erreur lors de la création du document : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_update_document",
    description=(
        "Met à jour partiellement un document Docs : titre et/ou contenu. "
        "Au moins un des deux champs doit être fourni. "
        "Retourne les métadonnées du document mis à jour au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document à modifier. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "title": {
                "type": "string",
                "description": "(Optionnel) Nouveau titre du document.",
            },
            "content": {
                "type": "string",
                "description": "(Optionnel) Nouveau contenu du document en HTML ou Markdown.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_update_document(
    document_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if content is not None:
        payload["content"] = content

    if not payload:
        return "Erreur : au moins un champ à mettre à jour est requis (title ou content)."

    report_progress(f"✏️ Mise à jour du document {document_id}…")
    ok, data = _patch(f"/documents/{document_id}/", payload)
    if not ok:
        return f"Erreur lors de la mise à jour du document : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_delete_document",
    description=(
        "Déplace un document Docs dans la corbeille (soft-delete). "
        "Le document est conservé pendant le nombre de jours configuré (TRASHBIN_CUTOFF_DAYS) "
        "et peut être restauré via docs_restore_document. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document à supprimer. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_delete_document(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🗑️ Déplacement du document {document_id} dans la corbeille…")
    ok, data = _delete(f"/documents/{document_id}/")
    if not ok:
        return f"Erreur lors de la suppression du document : {data}"
    return f"Document {document_id} déplacé dans la corbeille avec succès."


@tool(
    name="docs_restore_document",
    description=(
        "Restaure un document précédemment déplacé dans la corbeille sur Docs. "
        "À utiliser dans la période de rétention configurée (TRASHBIN_CUTOFF_DAYS). "
        "Retourne les métadonnées du document restauré au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document à restaurer. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_restore_document(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"♻️ Restauration du document {document_id}…")
    ok, data = _post(f"/documents/{document_id}/restore/")
    if not ok:
        return f"Erreur lors de la restauration du document : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_duplicate_document",
    description=(
        "Duplique un document Docs. Par défaut, seul le document est copié (sans ses accès ni ses enfants). "
        "Avec with_accesses=true, les droits d'accès sont copiés. "
        "Avec with_descendants=true, toute la sous-arborescence est dupliquée. "
        "Retourne les métadonnées du nouveau document au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document à dupliquer. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "with_accesses": {
                "type": "boolean",
                "description": "(Optionnel) Copier les accès du document original. Défaut : false.",
            },
            "with_descendants": {
                "type": "boolean",
                "description": "(Optionnel) Copier toute la sous-arborescence (documents enfants). Défaut : false.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_duplicate_document(
    document_id: str,
    with_accesses: bool = False,
    with_descendants: bool = False,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"📋 Duplication du document {document_id}…")
    payload = {
        "with_accesses": with_accesses,
        "with_descendants": with_descendants,
    }
    ok, data = _post(f"/documents/{document_id}/duplicate/", payload)
    if not ok:
        return f"Erreur lors de la duplication du document : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  6. DOCUMENTS — ORGANISATION
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_move_document",
    description=(
        "Déplace un document dans l'arborescence Docs. "
        "La position détermine l'emplacement par rapport au document cible : "
        "'first-child' (premier enfant), 'last-child' (dernier enfant), "
        "'left' (frère gauche), 'right' (frère droit). "
        "L'utilisateur doit avoir le droit de déplacement sur la source et la cible. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document à déplacer. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "target_document_id": {
                "type": "string",
                "description": "UUID du document cible (parent ou frère selon position). "
                               "Ex : 'b2c3d4e5-f6a7-8901-bcde-f12345678901'.",
            },
            "position": {
                "type": "string",
                "enum": ["first-child", "last-child", "left", "right"],
                "description": "Position relative au document cible : "
                               "'first-child' ou 'last-child' pour en faire un enfant, "
                               "'left' ou 'right' pour en faire un frère.",
            },
        },
        "required": ["document_id", "target_document_id", "position"],
    },
)
def docs_move_document(document_id: str, target_document_id: str, position: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    valid_positions = {"first-child", "last-child", "left", "right"}
    if position not in valid_positions:
        return f"Erreur : position invalide '{position}'. Valeurs acceptées : {', '.join(valid_positions)}."

    report_progress(f"↔️ Déplacement du document {document_id}…")
    payload = {"target_document_id": target_document_id, "position": position}
    ok, data = _post(f"/documents/{document_id}/move/", payload)
    if not ok:
        return f"Erreur lors du déplacement du document : {data}"
    return f"Document {document_id} déplacé avec succès (position : {position} de {target_document_id})."


@tool(
    name="docs_get_content",
    description=(
        "Récupère le contenu éditorial lisible d'un document Docs, converti par le service y-provider. "
        "Retourne le texte du document dans un format exploitable (Markdown ou HTML). "
        "À utiliser pour lire, résumer ou analyser le contenu d'un document."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_get_content(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"📖 Récupération du contenu du document {document_id}…")
    ok, data = _get(f"/documents/{document_id}/content/")
    if not ok:
        return f"Erreur lors de la récupération du contenu : {data}"
    # Le contenu peut être une chaîne brute ou un objet JSON
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_configure_link",
    description=(
        "Configure le mode de partage par lien d'un document Docs. "
        "link_reach contrôle qui peut accéder au document via le lien : "
        "'restricted' (accès sur invitation uniquement), "
        "'authenticated' (tout utilisateur connecté), "
        "'public' (accès sans authentification). "
        "link_role définit le niveau d'accès accordé : 'reader' ou 'editor'. "
        "Retourne la configuration mise à jour au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "link_reach": {
                "type": "string",
                "enum": ["restricted", "authenticated", "public"],
                "description": "Portée du lien : 'restricted', 'authenticated' ou 'public'.",
            },
            "link_role": {
                "type": "string",
                "enum": ["reader", "editor"],
                "description": "(Optionnel) Rôle accordé via le lien : 'reader' ou 'editor'.",
            },
        },
        "required": ["document_id", "link_reach"],
    },
)
def docs_configure_link(
    document_id: str,
    link_reach: str,
    link_role: Optional[str] = None,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    payload: dict = {"link_reach": link_reach}
    if link_role:
        payload["link_role"] = link_role

    report_progress(f"🔗 Configuration du partage par lien du document {document_id}…")
    ok, data = _put(f"/documents/{document_id}/link-configuration/", payload)
    if not ok:
        return f"Erreur lors de la configuration du lien : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  7. DOCUMENTS — FAVORIS & MASQUAGE
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_list_favorites",
    description=(
        "Liste les documents marqués comme favoris par l'utilisateur courant sur Docs. "
        "Retourne une liste JSON paginée avec id, titre et métadonnées de chaque favori."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page": {
                "type": "integer",
                "description": "(Optionnel) Numéro de page. Défaut : 1.",
            },
            "page_size": {
                "type": "integer",
                "description": "(Optionnel) Nombre de résultats par page. Défaut : 20.",
            },
        },
        "required": [],
    },
)
def docs_list_favorites(page: int = 1, page_size: int = 20) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress("⭐ Récupération des favoris…")
    ok, data = _get("/documents/favorite_list/", params={"page": page, "page_size": page_size})
    if not ok:
        return f"Erreur lors de la récupération des favoris : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_add_favorite",
    description=(
        "Marque un document Docs comme favori pour l'utilisateur courant. "
        "Le document apparaîtra dans la liste retournée par docs_list_favorites. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document à ajouter aux favoris. "
                               "Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_add_favorite(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"⭐ Ajout du document {document_id} aux favoris…")
    ok, data = _post(f"/documents/{document_id}/favorite/")
    if not ok:
        return f"Erreur lors de l'ajout aux favoris : {data}"
    return f"Document {document_id} ajouté aux favoris avec succès."


@tool(
    name="docs_remove_favorite",
    description=(
        "Retire un document des favoris de l'utilisateur courant sur Docs. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document à retirer des favoris. "
                               "Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_remove_favorite(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"☆ Suppression du document {document_id} des favoris…")
    ok, data = _delete(f"/documents/{document_id}/favorite/")
    if not ok:
        return f"Erreur lors de la suppression des favoris : {data}"
    return f"Document {document_id} retiré des favoris avec succès."


@tool(
    name="docs_mask_document",
    description=(
        "Masque ou démasque un document dans la liste de l'utilisateur courant sur Docs. "
        "Un document masqué n'apparaît plus dans la liste principale mais reste accessible. "
        "Utiliser action='mask' pour masquer, action='unmask' pour démasquer. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "action": {
                "type": "string",
                "enum": ["mask", "unmask"],
                "description": "'mask' pour masquer le document, 'unmask' pour le démasquer.",
            },
        },
        "required": ["document_id", "action"],
    },
)
def docs_mask_document(document_id: str, action: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if action == "mask":
        report_progress(f"👁️ Masquage du document {document_id}…")
        ok, data = _post(f"/documents/{document_id}/mask/")
        label = "masqué"
    elif action == "unmask":
        report_progress(f"👁️ Démasquage du document {document_id}…")
        ok, data = _delete(f"/documents/{document_id}/mask/")
        label = "démasqué"
    else:
        return "Erreur : action invalide. Valeurs acceptées : 'mask' ou 'unmask'."

    if not ok:
        return f"Erreur lors du masquage/démasquage : {data}"
    return f"Document {document_id} {label} avec succès."


# ══════════════════════════════════════════════════════════════════════════════
#  8. ACCÈS
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_list_accesses",
    description=(
        "Liste tous les accès (membres et leurs rôles) d'un document Docs. "
        "Nécessite que la fonctionnalité document_access soit activée sur l'instance. "
        "Retourne une liste JSON avec id, utilisateur/équipe et rôle pour chaque accès."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_list_accesses(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🔐 Récupération des accès du document {document_id}…")
    ok, data = _get(f"/documents/{document_id}/accesses/")
    if not ok:
        return f"Erreur lors de la récupération des accès : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_create_access",
    description=(
        "Accorde l'accès à un document Docs pour un utilisateur ou une équipe. "
        "Fournir user (UUID d'utilisateur) OU team (UUID d'équipe), mais pas les deux. "
        "Rôles disponibles : 'owner', 'administrator', 'editor', 'reader'. "
        "Utiliser docs_search_users pour obtenir l'UUID d'un utilisateur. "
        "Retourne l'objet accès créé au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "role": {
                "type": "string",
                "enum": ["owner", "administrator", "editor", "reader"],
                "description": "Rôle à accorder : 'owner', 'administrator', 'editor' ou 'reader'.",
            },
            "user": {
                "type": "string",
                "description": "(Optionnel) UUID de l'utilisateur à qui accorder l'accès. "
                               "Exclusif avec 'team'. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "team": {
                "type": "string",
                "description": "(Optionnel) UUID de l'équipe à qui accorder l'accès. "
                               "Exclusif avec 'user'.",
            },
        },
        "required": ["document_id", "role"],
    },
)
def docs_create_access(
    document_id: str,
    role: str,
    user: Optional[str] = None,
    team: Optional[str] = None,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not user and not team:
        return "Erreur : 'user' ou 'team' est requis pour créer un accès."
    if user and team:
        return "Erreur : 'user' et 'team' sont mutuellement exclusifs."

    payload: dict = {"role": role}
    if user:
        payload["user"] = user
    if team:
        payload["team"] = team

    report_progress(f"🔑 Création d'un accès sur le document {document_id}…")
    ok, data = _post(f"/documents/{document_id}/accesses/", payload)
    if not ok:
        return f"Erreur lors de la création de l'accès : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_update_access",
    description=(
        "Modifie le rôle d'un accès existant sur un document Docs. "
        "Utiliser docs_list_accesses pour obtenir l'access_id. "
        "Rôles disponibles : 'owner', 'administrator', 'editor', 'reader'. "
        "Retourne l'accès mis à jour au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "access_id": {
                "type": "string",
                "description": "UUID de l'accès à modifier (obtenu via docs_list_accesses).",
            },
            "role": {
                "type": "string",
                "enum": ["owner", "administrator", "editor", "reader"],
                "description": "Nouveau rôle : 'owner', 'administrator', 'editor' ou 'reader'.",
            },
        },
        "required": ["document_id", "access_id", "role"],
    },
)
def docs_update_access(document_id: str, access_id: str, role: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🔄 Mise à jour de l'accès {access_id}…")
    ok, data = _put(f"/documents/{document_id}/accesses/{access_id}/", {"role": role})
    if not ok:
        return f"Erreur lors de la mise à jour de l'accès : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_delete_access",
    description=(
        "Révoque un accès sur un document Docs. "
        "Utiliser docs_list_accesses pour obtenir l'access_id à supprimer. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "access_id": {
                "type": "string",
                "description": "UUID de l'accès à supprimer (obtenu via docs_list_accesses).",
            },
        },
        "required": ["document_id", "access_id"],
    },
)
def docs_delete_access(document_id: str, access_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"❌ Suppression de l'accès {access_id}…")
    ok, data = _delete(f"/documents/{document_id}/accesses/{access_id}/")
    if not ok:
        return f"Erreur lors de la suppression de l'accès : {data}"
    return f"Accès {access_id} supprimé avec succès du document {document_id}."


# ══════════════════════════════════════════════════════════════════════════════
#  9. INVITATIONS
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_list_invitations",
    description=(
        "Liste les invitations en attente d'un document Docs. "
        "Nécessite que la fonctionnalité document_invitation soit activée sur l'instance. "
        "Retourne une liste JSON avec id, email, rôle et date d'expiration de chaque invitation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_list_invitations(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"📬 Récupération des invitations du document {document_id}…")
    ok, data = _get(f"/documents/{document_id}/invitations/")
    if not ok:
        return f"Erreur lors de la récupération des invitations : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_invite_user",
    description=(
        "Invite un utilisateur à accéder à un document Docs par email. "
        "Un email d'invitation lui sera envoyé. "
        "Rôles disponibles : 'owner', 'administrator', 'editor', 'reader'. "
        "Retourne l'invitation créée au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "email": {
                "type": "string",
                "description": "Adresse email de la personne à inviter. Ex : 'alice@exemple.fr'.",
            },
            "role": {
                "type": "string",
                "enum": ["owner", "administrator", "editor", "reader"],
                "description": "Rôle à accorder : 'owner', 'administrator', 'editor' ou 'reader'.",
            },
        },
        "required": ["document_id", "email", "role"],
    },
)
def docs_invite_user(document_id: str, email: str, role: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if "@" not in email:
        return f"Erreur : adresse email invalide '{email}'."

    report_progress(f"✉️ Envoi d'une invitation à {email}…")
    ok, data = _post(f"/documents/{document_id}/invitations/", {"email": email, "role": role})
    if not ok:
        return f"Erreur lors de l'envoi de l'invitation : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_update_invitation",
    description=(
        "Modifie le rôle d'une invitation en attente sur un document Docs. "
        "Utiliser docs_list_invitations pour obtenir l'inv_id. "
        "Retourne l'invitation mise à jour au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "inv_id": {
                "type": "string",
                "description": "UUID de l'invitation à modifier (obtenu via docs_list_invitations).",
            },
            "role": {
                "type": "string",
                "enum": ["owner", "administrator", "editor", "reader"],
                "description": "Nouveau rôle : 'owner', 'administrator', 'editor' ou 'reader'.",
            },
        },
        "required": ["document_id", "inv_id", "role"],
    },
)
def docs_update_invitation(document_id: str, inv_id: str, role: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🔄 Mise à jour de l'invitation {inv_id}…")
    ok, data = _patch(f"/documents/{document_id}/invitations/{inv_id}/", {"role": role})
    if not ok:
        return f"Erreur lors de la mise à jour de l'invitation : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_cancel_invitation",
    description=(
        "Annule une invitation en attente sur un document Docs. "
        "Utiliser docs_list_invitations pour obtenir l'inv_id. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "inv_id": {
                "type": "string",
                "description": "UUID de l'invitation à annuler (obtenu via docs_list_invitations).",
            },
        },
        "required": ["document_id", "inv_id"],
    },
)
def docs_cancel_invitation(document_id: str, inv_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"❌ Annulation de l'invitation {inv_id}…")
    ok, data = _delete(f"/documents/{document_id}/invitations/{inv_id}/")
    if not ok:
        return f"Erreur lors de l'annulation de l'invitation : {data}"
    return f"Invitation {inv_id} annulée avec succès."


# ══════════════════════════════════════════════════════════════════════════════
#  10. VERSIONS
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_list_versions",
    description=(
        "Liste l'historique des versions S3 d'un document Docs. "
        "Les résultats sont filtrés à partir de la date d'accès de l'utilisateur au document. "
        "Retourne une liste JSON paginée avec version_id, date et taille de chaque version."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "page_size": {
                "type": "integer",
                "description": "(Optionnel) Nombre de versions par page. Défaut : 20.",
            },
            "version_id": {
                "type": "string",
                "description": "(Optionnel) Curseur de pagination : version de départ.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_list_versions(
    document_id: str,
    page_size: int = 20,
    version_id: Optional[str] = None,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🕐 Récupération des versions du document {document_id}…")
    params: dict = {"page_size": page_size}
    if version_id:
        params["version_id"] = version_id

    ok, data = _get(f"/documents/{document_id}/versions/", params=params)
    if not ok:
        return f"Erreur lors de la récupération des versions : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_get_version",
    description=(
        "Récupère le contenu d'une version spécifique d'un document Docs. "
        "Utiliser docs_list_versions pour obtenir les version_id disponibles. "
        "Retourne le contenu de la version au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "version_id": {
                "type": "string",
                "description": "Identifiant de la version (obtenu via docs_list_versions).",
            },
        },
        "required": ["document_id", "version_id"],
    },
)
def docs_get_version(document_id: str, version_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"📜 Récupération de la version {version_id}…")
    ok, data = _get(f"/documents/{document_id}/versions/{version_id}/")
    if not ok:
        return f"Erreur lors de la récupération de la version : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_delete_version",
    description=(
        "Supprime une version spécifique d'un document Docs dans S3. "
        "Utiliser docs_list_versions pour obtenir les version_id disponibles. "
        "Cette opération est irréversible. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "version_id": {
                "type": "string",
                "description": "Identifiant de la version à supprimer (obtenu via docs_list_versions).",
            },
        },
        "required": ["document_id", "version_id"],
    },
)
def docs_delete_version(document_id: str, version_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🗑️ Suppression de la version {version_id}…")
    ok, data = _delete(f"/documents/{document_id}/versions/{version_id}/")
    if not ok:
        return f"Erreur lors de la suppression de la version : {data}"
    return f"Version {version_id} du document {document_id} supprimée avec succès."


# ══════════════════════════════════════════════════════════════════════════════
#  11. COMMENTAIRES (THREADS & COMMENTS)
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="docs_list_threads",
    description=(
        "Liste les threads de commentaires actifs (non résolus) d'un document Docs. "
        "Retourne une liste JSON avec id, premier commentaire et date de chaque thread."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
        },
        "required": ["document_id"],
    },
)
def docs_list_threads(document_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"💬 Récupération des threads du document {document_id}…")
    ok, data = _get(f"/documents/{document_id}/threads/")
    if not ok:
        return f"Erreur lors de la récupération des threads : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_create_thread",
    description=(
        "Crée un nouveau thread de commentaires sur un document Docs avec un premier commentaire. "
        "Retourne le thread créé au format JSON, dont son thread_id."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "body": {
                "type": "string",
                "description": "Texte du premier commentaire du thread. Ex : 'À revoir : cette section manque de précision.'",
            },
        },
        "required": ["document_id", "body"],
    },
)
def docs_create_thread(document_id: str, body: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not body.strip():
        return "Erreur : le corps du commentaire ne peut pas être vide."

    report_progress(f"💬 Création d'un thread sur le document {document_id}…")
    ok, data = _post(f"/documents/{document_id}/threads/", {"body": body})
    if not ok:
        return f"Erreur lors de la création du thread : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_resolve_thread",
    description=(
        "Marque un thread de commentaires comme résolu sur un document Docs. "
        "Un thread résolu n'apparaît plus dans la liste retournée par docs_list_threads. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "thread_id": {
                "type": "string",
                "description": "UUID du thread à résoudre (obtenu via docs_list_threads).",
            },
        },
        "required": ["document_id", "thread_id"],
    },
)
def docs_resolve_thread(document_id: str, thread_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"✅ Résolution du thread {thread_id}…")
    ok, data = _post(f"/documents/{document_id}/threads/{thread_id}/resolve/")
    if not ok:
        return f"Erreur lors de la résolution du thread : {data}"
    return f"Thread {thread_id} marqué comme résolu avec succès."


@tool(
    name="docs_delete_thread",
    description=(
        "Supprime un thread de commentaires et tous ses commentaires d'un document Docs. "
        "Cette opération est irréversible. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "thread_id": {
                "type": "string",
                "description": "UUID du thread à supprimer (obtenu via docs_list_threads).",
            },
        },
        "required": ["document_id", "thread_id"],
    },
)
def docs_delete_thread(document_id: str, thread_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🗑️ Suppression du thread {thread_id}…")
    ok, data = _delete(f"/documents/{document_id}/threads/{thread_id}/")
    if not ok:
        return f"Erreur lors de la suppression du thread : {data}"
    return f"Thread {thread_id} supprimé avec succès."


@tool(
    name="docs_list_comments",
    description=(
        "Liste les commentaires d'un thread sur un document Docs. "
        "Retourne une liste JSON paginée avec id, auteur, corps et date de chaque commentaire."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "thread_id": {
                "type": "string",
                "description": "UUID du thread (obtenu via docs_list_threads).",
            },
            "page": {
                "type": "integer",
                "description": "(Optionnel) Numéro de page. Défaut : 1.",
            },
            "page_size": {
                "type": "integer",
                "description": "(Optionnel) Nombre de commentaires par page. Défaut : 20.",
            },
        },
        "required": ["document_id", "thread_id"],
    },
)
def docs_list_comments(
    document_id: str,
    thread_id: str,
    page: int = 1,
    page_size: int = 20,
) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🗨️ Récupération des commentaires du thread {thread_id}…")
    ok, data = _get(
        f"/documents/{document_id}/threads/{thread_id}/comments/",
        params={"page": page, "page_size": page_size},
    )
    if not ok:
        return f"Erreur lors de la récupération des commentaires : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_add_comment",
    description=(
        "Ajoute un commentaire à un thread existant sur un document Docs. "
        "Utiliser docs_list_threads pour obtenir le thread_id. "
        "Retourne le commentaire créé au format JSON."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "thread_id": {
                "type": "string",
                "description": "UUID du thread auquel ajouter le commentaire.",
            },
            "body": {
                "type": "string",
                "description": "Texte du commentaire à ajouter.",
            },
        },
        "required": ["document_id", "thread_id", "body"],
    },
)
def docs_add_comment(document_id: str, thread_id: str, body: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    if not body.strip():
        return "Erreur : le corps du commentaire ne peut pas être vide."

    report_progress(f"🗨️ Ajout d'un commentaire au thread {thread_id}…")
    ok, data = _post(
        f"/documents/{document_id}/threads/{thread_id}/comments/",
        {"body": body},
    )
    if not ok:
        return f"Erreur lors de l'ajout du commentaire : {data}"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool(
    name="docs_delete_comment",
    description=(
        "Supprime un commentaire d'un thread sur un document Docs. "
        "Utiliser docs_list_comments pour obtenir le comment_id. "
        "Cette opération est irréversible. "
        "Retourne un message de confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "UUID du document. Ex : 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'.",
            },
            "thread_id": {
                "type": "string",
                "description": "UUID du thread contenant le commentaire.",
            },
            "comment_id": {
                "type": "string",
                "description": "UUID du commentaire à supprimer (obtenu via docs_list_comments).",
            },
        },
        "required": ["document_id", "thread_id", "comment_id"],
    },
)
def docs_delete_comment(document_id: str, thread_id: str, comment_id: str) -> str:
    err = _check_prerequisites()
    if err:
        return err

    report_progress(f"🗑️ Suppression du commentaire {comment_id}…")
    ok, data = _delete(
        f"/documents/{document_id}/threads/{thread_id}/comments/{comment_id}/"
    )
    if not ok:
        return f"Erreur lors de la suppression du commentaire : {data}"
    return f"Commentaire {comment_id} supprimé avec succès."
