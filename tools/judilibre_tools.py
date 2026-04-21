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
tools/judilibre_tools.py — Outils JUDILIBRE pour Chaton Desktop AI
===================================================================

Intègre les outils JUDILIBRE (moteur de recherche jurisprudentiel de la
Cour de cassation — Open Data des décisions de justice) dans le moteur
d'outils de Prométhée AI Desktop. Suit le même pattern que legifrance_tools.py.

Usage dans main.py ou app.py :
    import tools.judilibre_tools  # noqa — enregistre les outils au démarrage

Prérequis dans .env :
    JUDILIBRE_CLIENT_ID=votre_client_id
    JUDILIBRE_CLIENT_SECRET=votre_client_secret

API : https://api.piste.gouv.fr/cassation/judilibre/v1.0
Auth : OAuth2 client_credentials (PISTE)

Outils disponibles (6 au total) :
  judilibre_rechercher         — GET /search   : recherche plein texte
  judilibre_decision           — GET /decision : décision complète par ID
  judilibre_scan               — GET /scan     : export par lot
  judilibre_taxonomie          — GET /taxonomy : référentiel des valeurs
  judilibre_stats              — GET /stats    : statistiques de la base
  judilibre_historique         — GET /transactionalhistory : opérations BDD
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from core.tools_engine import set_current_family, tool

set_current_family("judilibre_tools", "JUDILIBRE", "⚖️")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Icônes pour l'UI Chaton Desktop
# ---------------------------------------------------------------------------
try:
    from core.tools_engine import _TOOL_ICONS
    _TOOL_ICONS.update({
        "judilibre_rechercher":   "🔍",
        "judilibre_decision":     "📋",
        "judilibre_scan":         "📦",
        "judilibre_taxonomie":    "🗂️",
        "judilibre_stats":        "📊",
        "judilibre_historique":   "🔄",
    })
except Exception:
    pass


# ---------------------------------------------------------------------------
# Client JUDILIBRE (singleton, même pattern que _LegifranceClient)
# ---------------------------------------------------------------------------

class _JudiLibreClient:
    """
    Client OAuth2 PISTE pour l'API JUDILIBRE.
    Lit JUDILIBRE_CLIENT_ID et JUDILIBRE_CLIENT_SECRET depuis l'environnement.
    """

    BASE_URL  = "https://api.piste.gouv.fr/cassation/judilibre/v1.0"
    OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expiry: float  = 0
        self._http = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

    @property
    def client_id(self) -> Optional[str]:
        try:
            from core.request_context import get_user_config
            uc = get_user_config()
            if uc:
                return uc.JUDILIBRE_CLIENT_ID or os.getenv("JUDILIBRE_CLIENT_ID")
        except ImportError:
            pass
        return os.getenv("JUDILIBRE_CLIENT_ID")

    @property
    def client_secret(self) -> Optional[str]:
        try:
            from core.request_context import get_user_config
            uc = get_user_config()
            if uc:
                return uc.JUDILIBRE_CLIENT_SECRET or os.getenv("JUDILIBRE_CLIENT_SECRET")
        except ImportError:
            pass
        return os.getenv("JUDILIBRE_CLIENT_SECRET")

    def _check_credentials(self):
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "Identifiants JUDILIBRE manquants.\n"
                "Ajoutez dans votre .env :\n"
                "  JUDILIBRE_CLIENT_ID=...\n"
                "  JUDILIBRE_CLIENT_SECRET=..."
            )

    def _get_token(self) -> str:
        self._check_credentials()
        if self._token and time.time() < (self._token_expiry - 60):
            return self._token
        r = self._http.post(
            self.OAUTH_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     self.client_id,
                "client_secret": self.client_secret,
                "scope":         "openid",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        d = r.json()
        self._token        = d["access_token"]
        self._token_expiry = time.time() + d.get("expires_in", 3600)
        return self._token

    def _req(self, path: str, params: Optional[Dict] = None) -> Dict:
        """Effectue un GET authentifié sur l'API JUDILIBRE."""
        url = f"{self.BASE_URL}{path}"
        # Nettoyage des params None et listes vides
        clean_params: Dict[str, Any] = {}
        if params:
            for k, v in params.items():
                if v is None:
                    continue
                if isinstance(v, list) and len(v) == 0:
                    continue
                clean_params[k] = v

        for attempt in range(3):
            try:
                resp = self._http.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._get_token()}",
                        "Accept":        "application/json",
                    },
                    params=clean_params or None,
                )
                if resp.status_code == 401 and attempt == 0:
                    self._token = None
                    continue
                if resp.status_code == 429:
                    raise RuntimeError("Limite de débit API JUDILIBRE atteinte (429)")
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if attempt == 2 or e.response.status_code < 500:
                    raise RuntimeError(
                        f"Erreur HTTP {e.response.status_code} sur {path}"
                    )
                time.sleep(2 ** attempt)
            except httpx.RequestError as e:
                if attempt == 2:
                    raise RuntimeError(f"Erreur réseau : {e}")
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Échec après 3 tentatives sur {path}")


# Singleton partagé
_client: Optional[_JudiLibreClient] = None

def _get_client() -> _JudiLibreClient:
    global _client
    if _client is None:
        _client = _JudiLibreClient()
    return _client


# ---------------------------------------------------------------------------
# Helpers de formatage
# ---------------------------------------------------------------------------

def _fmt_decision_short(d: Dict) -> str:
    """Formate un résumé court d'une décision."""
    lines = []
    rid      = d.get("id", "")
    juri     = d.get("jurisdiction", "")
    chamber  = d.get("chamber", "")
    number   = d.get("number", "")
    date     = d.get("decision_date", "")
    solution = d.get("solution", "")
    summary  = d.get("summary", "")
    themes   = d.get("themes", [])
    ecli     = d.get("ecli", "")

    header = f"**{number}**" if number else "**Décision**"
    if date:
        header += f" — {date}"
    if solution:
        header += f" — *{solution}*"
    lines.append(header)

    meta = []
    if juri:
        meta.append(juri)
    if chamber:
        meta.append(chamber)
    if ecli:
        meta.append(f"ECLI : {ecli}")
    if rid:
        meta.append(f"ID : `{rid}`")
    if meta:
        lines.append("  " + " | ".join(meta))

    if themes:
        lines.append(f"  Matières : {', '.join(themes[:5])}")
    if summary:
        lines.append(f"  {summary[:300]}{'…' if len(summary) > 300 else ''}")

    return "\n".join(lines)


def _fmt_decision_full(d: Dict) -> str:
    """Formate le contenu complet d'une décision."""
    lines = [_fmt_decision_short(d)]

    visa = d.get("visa", [])
    if visa:
        lines.append(f"\n**Textes appliqués ({len(visa)})** :")
        for v in visa[:10]:
            lines.append(f"  - {v.get('title', '')}")

    rapprochements = d.get("rapprochements", [])
    if rapprochements:
        lines.append(f"\n**Rapprochements ({len(rapprochements)})** :")
        for r in rapprochements[:5]:
            lines.append(f"  - {r.get('title', '')} ({r.get('number', '')})")

    files = d.get("files", [])
    if files:
        lines.append(f"\n**Documents associés ({len(files)})** :")
        for f in files:
            lines.append(f"  - {f.get('name', '')} ({f.get('type', '')})")

    text = d.get("text", "") or d.get("text_highlight", "")
    if text:
        lines.append(f"\n**Texte intégral** :\n\n{text[:6000]}")
        if len(text) > 6000:
            lines.append(
                f"\n*[Texte tronqué — {len(text)} caractères au total. "
                "Consultez judilibre.fr pour le texte intégral]*"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Définition des outils JUDILIBRE
# ---------------------------------------------------------------------------

@tool(
    name="judilibre_rechercher",
    description=(
        "Recherche dans la base Open Data des décisions de justice françaises (JUDILIBRE). "
        "Couvre la Cour de cassation, les cours d'appel et les tribunaux judiciaires. "
        "Retourne une liste paginée de décisions avec leurs métadonnées et sommaires. "
        "Utilisez judilibre_decision pour obtenir le texte intégral d'une décision."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termes de recherche en texte libre (ex: 'responsabilité civile', 'licenciement')",
            },
            "operateur": {
                "type": "string",
                "enum": ["or", "and", "exact"],
                "default": "or",
                "description": "Opérateur logique : 'or' (défaut), 'and', ou 'exact' pour une expression exacte",
            },
            "champs": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Zones ciblées par la recherche parmi : expose, moyens, motivations, "
                    "dispositif, annexes, sommaire, titrage. "
                    "Si vide, recherche dans tout le texte intégral."
                ),
            },
            "juridiction": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par juridiction : 'cc' (Cour de cassation), 'ca' (cour d'appel), 'tj' (tribunal judiciaire)",
            },
            "chambre": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par chambre (ex: 'civ1', 'civ2', 'civ3', 'com', 'soc', 'crim'). Valeurs via judilibre_taxonomie(id='chamber')",
            },
            "formation": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par formation (ex: 'fs', 'fp', 'fplr'). Valeurs via judilibre_taxonomie(id='formation')",
            },
            "type_decision": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par nature : 'arret', 'qpc', 'ordonnance', 'saisie'… Valeurs via judilibre_taxonomie(id='type')",
            },
            "solution": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par solution : 'cassation', 'rejet', 'annulation', 'avis', 'irrecevabilite'… Valeurs via judilibre_taxonomie(id='solution')",
            },
            "publication": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par niveau de publication : 'b' (Bulletin), 'r' (Rapport), 'l' (ECLI), 'c' (Communiqué). Valeurs via judilibre_taxonomie(id='publication')",
            },
            "matiere": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par matière/thème. Valeurs via judilibre_taxonomie(id='theme')",
            },
            "localisation": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par siège de juridiction (ex: 'ca_paris', 'tj33063'). Valeurs via judilibre_taxonomie(id='location')",
            },
            "date_debut": {
                "type": "string",
                "description": "Date de début au format YYYY-MM-DD",
            },
            "date_fin": {
                "type": "string",
                "description": "Date de fin au format YYYY-MM-DD",
            },
            "tri": {
                "type": "string",
                "enum": ["scorepub", "score", "date"],
                "default": "scorepub",
                "description": "Critère de tri : 'scorepub' (pertinence + publication, défaut), 'score' (pertinence), 'date'",
            },
            "ordre": {
                "type": "string",
                "enum": ["desc", "asc"],
                "default": "desc",
                "description": "Ordre de tri : 'desc' (défaut) ou 'asc'",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 10,
                "description": "Résultats par page (max 50, défaut 10)",
            },
            "page": {
                "type": "integer",
                "default": 0,
                "description": "Numéro de page (commence à 0)",
            },
            "interet_particulier": {
                "type": "boolean",
                "description": "Si true, restreint aux décisions d'intérêt particulier",
            },
        },
        "required": ["query"],
    },
)
def judilibre_rechercher(
    query: str,
    operateur: str = "or",
    champs: Optional[List[str]] = None,
    juridiction: Optional[List[str]] = None,
    chambre: Optional[List[str]] = None,
    formation: Optional[List[str]] = None,
    type_decision: Optional[List[str]] = None,
    solution: Optional[List[str]] = None,
    publication: Optional[List[str]] = None,
    matiere: Optional[List[str]] = None,
    localisation: Optional[List[str]] = None,
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
    tri: str = "scorepub",
    ordre: str = "desc",
    nb_resultats: int = 10,
    page: int = 0,
    interet_particulier: Optional[bool] = None,
) -> str:
    c = _get_client()
    params: Dict[str, Any] = {
        "query":            query,
        "operator":         operateur,
        "sort":             tri,
        "order":            ordre,
        "page_size":        min(max(1, nb_resultats), 50),
        "page":             page,
        "resolve_references": True,
    }
    if champs:
        params["field"]       = champs
    if juridiction:
        params["jurisdiction"] = juridiction
    if chambre:
        params["chamber"]     = chambre
    if formation:
        params["formation"]   = formation
    if type_decision:
        params["type"]        = type_decision
    if solution:
        params["solution"]    = solution
    if publication:
        params["publication"] = publication
    if matiere:
        params["theme"]       = matiere
    if localisation:
        params["location"]    = localisation
    if date_debut:
        params["date_start"]  = date_debut
    if date_fin:
        params["date_end"]    = date_fin
    if interet_particulier is not None:
        params["particularInterest"] = interet_particulier

    data    = c._req("/search", params=params)
    total   = data.get("total", 0)
    results = data.get("results", [])
    took    = data.get("took", 0)

    if not results:
        return f"Aucun résultat pour : « {query} »"

    lines = [
        f"**{total} décision(s) pour « {query} »** — "
        f"{len(results)} affichée(s) — page {page} — {took} ms\n"
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {_fmt_decision_short(r)}")
        lines.append("")

    next_page = data.get("next_page")
    if next_page:
        lines.append(f"*Page suivante disponible (page {page + 1})*")

    return "\n".join(lines)


@tool(
    name="judilibre_decision",
    description=(
        "Récupère le texte intégral et toutes les métadonnées d'une décision de justice "
        "par son identifiant unique JUDILIBRE. "
        "Retourne : texte complet pseudonymisé, zones structurées (introduction, exposé du litige, "
        "moyens, motivations, dispositif), titrage, sommaire, textes appliqués, "
        "rapprochements de jurisprudence et documents associés (communiqués, notes, rapports…). "
        "L'identifiant s'obtient via judilibre_rechercher."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Identifiant unique de la décision (ex: '5fca7d162a251e6bf9c78514')",
            },
            "query": {
                "type": "string",
                "description": (
                    "Termes à surligner dans le texte intégral retourné "
                    "(les correspondances seront délimitées par des balises <em>)"
                ),
            },
            "operateur": {
                "type": "string",
                "enum": ["or", "and", "exact"],
                "default": "or",
                "description": "Opérateur logique pour le surlignage (si query fourni)",
            },
        },
        "required": ["id"],
    },
)
def judilibre_decision(
    id: str,
    query: Optional[str] = None,
    operateur: str = "or",
) -> str:
    c = _get_client()
    params: Dict[str, Any] = {
        "id":                 id,
        "resolve_references": True,
    }
    if query:
        params["query"]    = query
        params["operator"] = operateur

    data = c._req("/decision", params=params)
    if not data:
        return f"Décision `{id}` introuvable."
    return _fmt_decision_full(data)


@tool(
    name="judilibre_scan",
    description=(
        "Export par lot de décisions de justice complètes (texte intégral inclus). "
        "Destiné à l'indexation et la réutilisation du corpus. "
        "Remplace l'endpoint /export (déprécié). "
        "Retourne jusqu'à 1000 décisions par lot, navigables via search_after. "
        "Filtres identiques à judilibre_rechercher."
    ),
    parameters={
        "type": "object",
        "properties": {
            "juridiction": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par juridiction : 'cc', 'ca', 'tj'",
            },
            "chambre": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par chambre. Valeurs via judilibre_taxonomie(id='chamber')",
            },
            "formation": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par formation",
            },
            "type_decision": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par nature : 'arret', 'qpc', 'ordonnance'…",
            },
            "solution": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par solution : 'cassation', 'rejet'…",
            },
            "publication": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par niveau de publication",
            },
            "matiere": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par matière",
            },
            "localisation": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par siège de juridiction",
            },
            "date_debut": {
                "type": "string",
                "description": "Date de début ISO-8601 (ex: '2024-01-01')",
            },
            "date_fin": {
                "type": "string",
                "description": "Date de fin ISO-8601 (ex: '2024-12-31')",
            },
            "type_date": {
                "type": "string",
                "enum": ["creation", "update"],
                "description": "Type de date pour le filtre : 'creation' ou 'update'",
            },
            "ordre": {
                "type": "string",
                "enum": ["asc", "desc"],
                "default": "asc",
                "description": "Ordre de tri par date : 'asc' (défaut) ou 'desc'",
            },
            "taille_lot": {
                "type": "integer",
                "default": 10,
                "description": "Nombre de décisions par lot (max 1000, défaut 10)",
            },
            "search_after": {
                "type": "string",
                "description": "ID de la dernière décision du lot précédent pour paginer",
            },
            "abrege": {
                "type": "boolean",
                "default": False,
                "description": "Si true, retourne la version abrégée (sans texte intégral)",
            },
            "type_fichier": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtrer par type de document associé : 'prep_rapp', 'prep_avis', 'comm_comm', 'comm_note'…",
            },
            "interet_particulier": {
                "type": "boolean",
                "description": "Si true, restreint aux décisions d'intérêt particulier",
            },
        },
    },
)
def judilibre_scan(
    juridiction: Optional[List[str]] = None,
    chambre: Optional[List[str]] = None,
    formation: Optional[List[str]] = None,
    type_decision: Optional[List[str]] = None,
    solution: Optional[List[str]] = None,
    publication: Optional[List[str]] = None,
    matiere: Optional[List[str]] = None,
    localisation: Optional[List[str]] = None,
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
    type_date: Optional[str] = None,
    ordre: str = "asc",
    taille_lot: int = 10,
    search_after: Optional[str] = None,
    abrege: bool = False,
    type_fichier: Optional[List[str]] = None,
    interet_particulier: Optional[bool] = None,
) -> str:
    c = _get_client()
    params: Dict[str, Any] = {
        "order":              ordre,
        "batch_size":         min(max(1, taille_lot), 1000),
        "resolve_references": True,
        "abridged":           abrege,
    }
    if juridiction:
        params["jurisdiction"]  = juridiction
    if chambre:
        params["chamber"]       = chambre
    if formation:
        params["formation"]     = formation
    if type_decision:
        params["type"]          = type_decision
    if solution:
        params["solution"]      = solution
    if publication:
        params["publication"]   = publication
    if matiere:
        params["theme"]         = matiere
    if localisation:
        params["location"]      = localisation
    if date_debut:
        params["date_start"]    = date_debut
    if date_fin:
        params["date_end"]      = date_fin
    if type_date:
        params["date_type"]     = type_date
    if search_after:
        params["search_after"]  = search_after
    if type_fichier:
        params["withFileOfType"] = type_fichier
    if interet_particulier is not None:
        params["particularInterest"] = interet_particulier

    data    = c._req("/scan", params=params)
    total   = data.get("total", 0)
    results = data.get("results", [])
    took    = data.get("took", 0)

    if not results:
        return "Aucune décision trouvée pour ces critères."

    lines = [
        f"**{total} décision(s) au total** — "
        f"{len(results)} dans ce lot — {took} ms\n"
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {_fmt_decision_short(r)}")
        lines.append("")

    next_batch = data.get("next_batch")
    if next_batch:
        # Extraire le search_after du next_batch pour faciliter la pagination
        last_id = results[-1].get("id", "") if results else ""
        lines.append(
            f"*Lot suivant disponible — utilisez `search_after='{last_id}'` pour continuer*"
        )

    return "\n".join(lines)


@tool(
    name="judilibre_taxonomie",
    description=(
        "Récupère les listes de termes (taxonomie) utilisés par l'API JUDILIBRE : "
        "juridictions, chambres, formations, types de décision, solutions, niveaux de publication, "
        "matières, champs de recherche, types de fichiers, sièges de juridiction, etc. "
        "Indispensable pour connaître les valeurs valides des filtres de judilibre_rechercher et judilibre_scan. "
        "Exemples : judilibre_taxonomie(id='chamber', contexte='cc') pour les chambres de la Cour de cassation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": (
                    "Identifiant de l'entrée de taxonomie : "
                    "'type', 'jurisdiction', 'chamber', 'formation', 'publication', "
                    "'theme', 'solution', 'field', 'zones', 'location', 'filetype'. "
                    "Sans paramètre, retourne la liste des taxonomies disponibles."
                ),
            },
            "cle": {
                "type": "string",
                "description": "Clé dont on veut l'intitulé complet (ex: 'cc' → 'Cour de cassation'). Nécessite id.",
            },
            "valeur": {
                "type": "string",
                "description": "Intitulé dont on veut la clé (ex: 'Cour de cassation' → 'cc'). Nécessite id.",
            },
            "contexte": {
                "type": "string",
                "description": "Contextualise certaines listes : 'cc' pour Cour de cassation, 'ca' pour cours d'appel (défaut: 'cc')",
            },
        },
    },
)
def judilibre_taxonomie(
    id: Optional[str] = None,
    cle: Optional[str] = None,
    valeur: Optional[str] = None,
    contexte: Optional[str] = None,
) -> str:
    c = _get_client()
    params: Dict[str, Any] = {}
    if id:
        params["id"] = id
    if cle:
        params["key"] = cle
    if valeur:
        params["value"] = valeur
    if contexte:
        params["context_value"] = contexte

    data = c._req("/taxonomy", params=params or None)

    # Résolution d'une clé ou d'une valeur spécifique
    if cle or valeur:
        result = data.get("result", {})
        if result:
            k = result.get("key", data.get("key", cle or ""))
            v = result.get("value", "")
            return f"**{k}** → {v}"
        return "Aucun résultat de taxonomie trouvé."

    # Liste complète d'une taxonomie
    if id:
        items = data.get("result", data.get("results", data))
        if isinstance(items, list):
            lines = [f"**Taxonomie '{id}'** ({len(items)} entrée(s))\n"]
            for item in items:
                if isinstance(item, dict):
                    k = item.get("key", "")
                    v = item.get("value", "")
                    lines.append(f"- `{k}` — {v}")
                else:
                    lines.append(f"- {item}")
            return "\n".join(lines)
        elif isinstance(items, dict):
            lines = [f"**Taxonomie '{id}'**\n"]
            for k, v in items.items():
                lines.append(f"- `{k}` — {v}")
            return "\n".join(lines)

    # Liste des taxonomies disponibles (sans paramètre)
    if isinstance(data, list):
        lines = [f"**Taxonomies disponibles ({len(data)})**\n"]
        for item in data:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('key', item.get('id', ''))}` — {item.get('value', '')}")
            else:
                lines.append(f"- {item}")
        return "\n".join(lines)

    # Fallback : retourner brut
    return str(data)


@tool(
    name="judilibre_stats",
    description=(
        "Récupère des statistiques sur le contenu de la base JUDILIBRE : "
        "nombre total de décisions indexées, dates extrêmes, "
        "répartition par juridiction, chambre, année, solution, matière, etc. "
        "Les statistiques sont mises à jour quotidiennement."
    ),
    parameters={
        "type": "object",
        "properties": {
            "juridiction": {
                "type": "string",
                "description": "Filtrer par type de juridiction : 'cc', 'ca', 'tj', 'tcom'",
            },
            "localisation": {
                "type": "string",
                "description": "Filtrer par juridiction précise (ex: 'ca_paris,ca_rennes')",
            },
            "date_debut": {
                "type": "string",
                "description": "Date minimale au format YYYY-MM-DD",
            },
            "date_fin": {
                "type": "string",
                "description": "Date maximale au format YYYY-MM-DD",
            },
            "agregations": {
                "type": "string",
                "description": (
                    "Variables d'agrégation séparées par des virgules parmi : "
                    "year, month, jurisdiction, source, location, theme, "
                    "formation, chamber, solution, type, publication. "
                    "Ex: 'jurisdiction,chamber' ou 'year,solution'"
                ),
            },
            "interet_particulier": {
                "type": "string",
                "description": "Filtrer sur l'intérêt particulier : 'true'",
            },
        },
    },
)
def judilibre_stats(
    juridiction: Optional[str] = None,
    localisation: Optional[str] = None,
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
    agregations: Optional[str] = None,
    interet_particulier: Optional[str] = None,
) -> str:
    c = _get_client()
    params: Dict[str, Any] = {}
    if juridiction:
        params["jurisdiction"]      = juridiction
    if localisation:
        params["location"]          = localisation
    if date_debut:
        params["date_start"]        = date_debut
    if date_fin:
        params["date_end"]          = date_fin
    if agregations:
        params["keys"]              = agregations
    if interet_particulier:
        params["particularInterest"] = interet_particulier

    data    = c._req("/stats", params=params or None)
    results = data.get("results", {})
    query   = data.get("query", {})

    lines = ["**Statistiques JUDILIBRE**\n"]

    # Contexte de la requête
    if query:
        ctx = []
        if query.get("jurisdiction"):
            ctx.append(f"juridiction : {query['jurisdiction']}")
        if query.get("keys"):
            ctx.append(f"agrégation : {query['keys']}")
        if ctx:
            lines.append(f"*Filtres : {', '.join(ctx)}*\n")

    # Chiffres globaux
    total = results.get("total_decisions", 0)
    min_d = results.get("min_decision_date", "")
    max_d = results.get("max_decision_date", "")
    lines.append(f"**Total décisions indexées** : {total:,}".replace(",", "\u202f"))
    if min_d:
        lines.append(f"**Décision la plus ancienne** : {min_d}")
    if max_d:
        lines.append(f"**Décision la plus récente** : {max_d}")

    # Agrégations
    agg = results.get("aggregated_data", [])
    if agg:
        lines.append(f"\n**Répartition ({len(agg)} bucket(s))**\n")
        for bucket in agg[:50]:
            key    = bucket.get("key", {})
            count  = bucket.get("decisions_count", 0)
            label  = " | ".join(f"{k}: {v}" for k, v in key.items())
            lines.append(f"- {label} → **{count}** décision(s)")
        if len(agg) > 50:
            lines.append(f"*… {len(agg) - 50} bucket(s) supplémentaire(s)*")

    return "\n".join(lines)


@tool(
    name="judilibre_historique",
    description=(
        "Consulte l'historique transactionnel de la base JUDILIBRE : "
        "liste des opérations create, update et delete effectuées sur les décisions "
        "depuis une date donnée. "
        "Destiné aux réutilisateurs souhaitant maintenir leur propre index à jour "
        "en synchronisant les créations, modifications et suppressions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date à partir de laquelle remonter les opérations, au format ISO-8601 (ex: '2024-01-01T00:00:00Z')",
            },
            "taille_page": {
                "type": "integer",
                "description": "Nombre d'opérations par requête (10 minimum, 500 maximum, défaut 500)",
            },
            "from_id": {
                "type": "string",
                "description": "ID à partir duquel continuer la pagination (fourni par la réponse précédente via next_page)",
            },
        },
        "required": ["date"],
    },
)
def judilibre_historique(
    date: str,
    taille_page: Optional[int] = None,
    from_id: Optional[str] = None,
) -> str:
    c = _get_client()
    params: Dict[str, Any] = {"date": date}
    if taille_page is not None:
        params["page_size"] = max(10, min(500, taille_page))
    if from_id:
        params["from_id"] = from_id

    data         = c._req("/transactionalhistory", params=params)
    transactions = data.get("transactions", [])
    total        = data.get("total", 0)
    page_size    = data.get("page_size", 0)
    query_date   = data.get("query_date", "")
    next_page    = data.get("next_page", "")

    if not transactions:
        return f"Aucune opération trouvée depuis le {date}."

    # Comptage par type d'opération
    counts: Dict[str, int] = {}
    for t in transactions:
        action = t.get("action", "unknown")
        counts[action] = counts.get(action, 0) + 1

    lines = [
        f"**{total} opération(s) depuis le {date}** — "
        f"{len(transactions)} affichée(s) — requête du {query_date}\n"
    ]

    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    lines.append(f"*Répartition : {summary}*\n")

    for t in transactions[:100]:
        action = t.get("action", "")
        tid    = t.get("id", "")
        tdate  = t.get("date", "")
        icon   = {"created": "✅", "updated": "🔄", "deleted": "🗑️"}.get(action, "•")
        lines.append(f"{icon} **{action}** — `{tid}` — {tdate}")

    if len(transactions) > 100:
        lines.append(f"\n*… {len(transactions) - 100} opération(s) supplémentaire(s) non affichée(s)*")

    if next_page:
        lines.append(
            f"\n*Suite disponible — utilisez `from_id` extrait du paramètre next_page*"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Confirmation de chargement
# ---------------------------------------------------------------------------
_tools_count = sum(1 for _ in [
    "judilibre_rechercher",
    "judilibre_decision",
    "judilibre_scan",
    "judilibre_taxonomie",
    "judilibre_stats",
    "judilibre_historique",
])
logger.info(f"✅ tools.judilibre_tools : {_tools_count} outils enregistrés dans Chaton Desktop")
