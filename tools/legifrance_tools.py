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
tools/legifrance_tools.py — Outils Légifrance pour Prométhée
=====================================================================

Intègre les 57 outils Légifrance dans le moteur d'outils de Prométhée.
Suit le même pattern que math_tools, system_tools et data_tools.

Usage dans main.py ou app.py :
    import tools.legifrance_tools  # noqa — enregistre les outils au démarrage

Ou via register_all() dans tools/__init__.py :
    from tools import register_all
    register_all()

Les outils sont ensuite automatiquement disponibles dans agent_loop()
via get_tool_schemas() et call_tool().

Prérequis dans .env :
    LEGIFRANCE_CLIENT_ID=votre_client_id
    LEGIFRANCE_CLIENT_SECRET=votre_client_secret

Outils disponibles (57 au total) :
  Recherche (4)   : legifrance_rechercher, legifrance_version_canonique_article,
                    legifrance_version_canonique, legifrance_version_proche
  Consultation codes/lois (11) :
                    legifrance_consulter_code, legifrance_code_complet,
                    legifrance_code_par_ancien_id,
                    legifrance_obtenir_article, legifrance_article_par_numero,
                    legifrance_article_par_eli, legifrance_versions_article,
                    legifrance_articles_meme_numero,
                    legifrance_loi_decret, legifrance_legi_part,
                    legifrance_tables_annuelles
  Liens d'articles (4) :
                    legifrance_liens_concordance, legifrance_liens_relatifs,
                    legifrance_liens_service_public, legifrance_a_liens_service_public
  Consultation JORF (6) :
                    legifrance_jorf, legifrance_jorf_part,
                    legifrance_jo_par_nor, legifrance_eli_alias_texte,
                    legifrance_derniers_jo, legifrance_sommaire_jorf
  Consultation KALI (5) :
                    legifrance_convention_par_idcc, legifrance_convention_cont,
                    legifrance_convention_texte, legifrance_convention_article,
                    legifrance_convention_section
  Consultation jurisprudence (3) :
                    legifrance_jurisprudence, legifrance_jurisprudence_plan_classement,
                    legifrance_jurisprudence_ancien_id
  Consultation divers (7) :
                    legifrance_cnil, legifrance_cnil_ancien_id,
                    legifrance_acco, legifrance_circulaire,
                    legifrance_debat, legifrance_dossier_legislatif,
                    legifrance_section_par_cid
  Consultation BOCC (1) :
                    legifrance_bocc_pdf_metadata
  Chrono (3)      : legifrance_historique_texte, legifrance_versions_element,
                    legifrance_a_des_versions
  List (12)       : legifrance_lister_codes, legifrance_conventions,
                    legifrance_lister_loda, legifrance_lister_legislatures,
                    legifrance_lister_dossiers_legislatifs,
                    legifrance_lister_debats_parlementaires,
                    legifrance_lister_questions_parlementaires,
                    legifrance_lister_bocc, legifrance_lister_bocc_textes,
                    legifrance_lister_boccs_et_textes, legifrance_lister_docs_admins,
                    legifrance_lister_bodmr
  Suggest (3)     : legifrance_suggerer, legifrance_suggerer_acco,
                    legifrance_suggerer_pdc
  Misc (3)        : legifrance_dates_sans_jo, legifrance_annees_sans_table,
                    legifrance_commit_id
"""

import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from core.tools_engine import set_current_family, tool

set_current_family("legifrance_tools", "Légifrance", "⚖️")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Icônes pour l'UI Prométhée Desktop (ajoutées au registre _TOOL_ICONS)
# ---------------------------------------------------------------------------
try:
    from core.tools_engine import _TOOL_ICONS
    _TOOL_ICONS.update({
        # Recherche
        "legifrance_rechercher":                       "⚖️",
        "legifrance_version_canonique_article":        "🔍",
        "legifrance_version_canonique":                "📌",
        "legifrance_version_proche":                   "📍",
        # Consultation codes / lois
        "legifrance_consulter_code":                   "📖",
        "legifrance_obtenir_article":                  "📄",
        "legifrance_article_par_numero":               "🔢",
        "legifrance_versions_article":                 "🕐",
        "legifrance_loi_decret":                       "📜",
        "legifrance_jorf":                             "🗞️",
        "legifrance_jo_par_nor":                       "🗞️",
        "legifrance_derniers_jo":                      "📰",
        "legifrance_sommaire_jorf":                    "📑",
        # Conventions collectives (KALI)
        "legifrance_convention_par_idcc":              "🤝",
        "legifrance_convention_texte":                 "🤝",
        "legifrance_convention_article":               "🤝",
        "legifrance_convention_section":               "🤝",
        # Jurisprudence
        "legifrance_jurisprudence":                    "🏛️",
        "legifrance_jurisprudence_plan_classement":    "🗂️",
        # Consultation divers
        "legifrance_cnil":                             "🔒",
        "legifrance_acco":                             "🏢",
        "legifrance_circulaire":                       "📬",
        "legifrance_debat":                            "🎙️",
        "legifrance_dossier_legislatif":               "🗃️",
        "legifrance_section_par_cid":                  "📂",
        # Chrono
        "legifrance_historique_texte":                 "⏳",
        "legifrance_versions_element":                 "🕰️",
        "legifrance_a_des_versions":                   "✅",
        # List
        "legifrance_lister_codes":                     "📋",
        "legifrance_conventions":                      "🤝",
        "legifrance_lister_loda":                      "📜",
        "legifrance_lister_legislatures":              "🏛️",
        "legifrance_lister_dossiers_legislatifs":      "🗃️",
        "legifrance_lister_debats_parlementaires":     "🎙️",
        "legifrance_lister_questions_parlementaires":  "❓",
        "legifrance_lister_bocc":                      "📋",
        "legifrance_lister_bocc_textes":               "📄",
        "legifrance_lister_boccs_et_textes":           "📑",
        "legifrance_lister_docs_admins":               "🗂️",
        # Suggest
        "legifrance_suggerer":                         "💡",
        "legifrance_suggerer_acco":                    "🏢",
        "legifrance_suggerer_pdc":                     "🗂️",
        # Misc
        "legifrance_dates_sans_jo":                    "📅",
        "legifrance_annees_sans_table":                "📆",
        "legifrance_commit_id":                        "🔖",
        # List
        "legifrance_lister_bodmr":                     "🎖️",
        # Consult — codes
        "legifrance_code_complet":                     "📖",
        "legifrance_code_par_ancien_id":               "🔄",
        "legifrance_article_par_eli":                  "🔗",
        "legifrance_articles_meme_numero":             "🔢",
        # Consult — liens d'articles
        "legifrance_liens_concordance":                "🔀",
        "legifrance_liens_relatifs":                   "🔗",
        "legifrance_liens_service_public":             "🏛️",
        "legifrance_a_liens_service_public":           "✅",
        # Consult — JORF
        "legifrance_jorf_part":                        "🗞️",
        "legifrance_eli_alias_texte":                  "🔗",
        # Consult — KALI
        "legifrance_convention_cont":                  "🤝",
        # Consult — JURI
        "legifrance_jurisprudence_ancien_id":          "🏛️",
        # Consult — CNIL
        "legifrance_cnil_ancien_id":                   "🔒",
        # Consult — LEGI
        "legifrance_legi_part":                        "📜",
        # Consult — tables
        "legifrance_tables_annuelles":                 "📅",
        # Consult — BOCC
        "legifrance_bocc_pdf_metadata":                "📄",
    })
except Exception:
    pass


# ---------------------------------------------------------------------------
# Client Légifrance (autonome, lit le .env de l'applcaton)
# ---------------------------------------------------------------------------

class _LegifranceClient:
    """
    Client OAuth2 PISTE — singleton, partagé par tous les outils.
    Lit LEGIFRANCE_CLIENT_ID et LEGIFRANCE_CLIENT_SECRET depuis
    l'environnement (déjà chargé par config.py via python-dotenv).
    """

    PRODUCTION_BASE_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
    OAUTH_URL           = "https://oauth.piste.gouv.fr/api/oauth/token"

    # Noms de codes → ID Légifrance
    CODE_IDS: Dict[str, str] = {
        "civil":                    "LEGITEXT000006070721",
        "penal":                    "LEGITEXT000006070719",
        "travail":                  "LEGITEXT000006072050",
        "commerce":                 "LEGITEXT000005634379",
        "consommation":             "LEGITEXT000006069565",
        "procedure_civile":         "LEGITEXT000006070716",
        "procedure_penale":         "LEGITEXT000006071154",
        "sante_publique":           "LEGITEXT000006072665",
        "education":                "LEGITEXT000006071191",
        "environnement":            "LEGITEXT000006074220",
        "securite_sociale":         "LEGITEXT000006073189",
        "general_collectivites":    "LEGITEXT000006070633",
        "urbanisme":                "LEGITEXT000006074075",
        "propriete_intellectuelle": "LEGITEXT000006069414",
        "assurances":               "LEGITEXT000006073984",
        "monetaire_financier":      "LEGITEXT000006072026",
    }

    def __init__(self):
        # NE PAS lire os.getenv() ici : le .env peut ne pas encore être chargé
        # au moment de l'import du module. On lit en live à chaque appel.
        self._token: Optional[str] = None
        self._token_expiry: float  = 0
        self._http = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

    @property
    def client_id(self) -> Optional[str]:
        return os.getenv("LEGIFRANCE_CLIENT_ID")

    @property
    def client_secret(self) -> Optional[str]:
        return os.getenv("LEGIFRANCE_CLIENT_SECRET")

    def _check_credentials(self):
        # Relecture en live : capte les valeurs chargées par config.py
        # même si legifrance_tools a été importé avant le load_dotenv()
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "Identifiants Légifrance manquants.\n"
                "Ajoutez dans votre .env :\n"
                "  LEGIFRANCE_CLIENT_ID=...\n"
                "  LEGIFRANCE_CLIENT_SECRET=..."
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

    def _req(self, path: str, method: str = "POST", body: Optional[Dict] = None) -> Dict:
        url = f"{self.PRODUCTION_BASE_URL}{path}"
        for attempt in range(3):
            try:
                resp = self._http.request(
                    method=method.upper(),
                    url=url,
                    headers={
                        "Authorization":  f"Bearer {self._get_token()}",
                        "Accept":         "application/json",
                        "Content-Type":   "application/json",
                    },
                    json=body,
                )
                if resp.status_code == 401 and attempt == 0:
                    self._token = None
                    continue
                if resp.status_code == 429:
                    raise RuntimeError("Limite de débit API Légifrance atteinte (429)")
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "")
                if "application/json" in ct:
                    return resp.json()
                return {"content": resp.text}
            except httpx.HTTPStatusError as e:
                if attempt == 2 or e.response.status_code < 500:
                    raise RuntimeError(f"Erreur HTTP {e.response.status_code} sur {path}")
                time.sleep(2 ** attempt)
            except httpx.RequestError as e:
                if attempt == 2:
                    raise RuntimeError(f"Erreur réseau : {e}")
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Échec après 3 tentatives sur {path}")

    def resolve_code(self, code: str) -> str:
        """Résout un nom de code en ID Légifrance."""
        if code.startswith("LEGITEXT"):
            return code
        key = code.lower().replace(" ", "_").replace("-", "_")
        rid = self.CODE_IDS.get(key)
        if not rid:
            known = ", ".join(self.CODE_IDS.keys())
            raise ValueError(
                f"Code non reconnu : '{code}'.\n"
                f"Noms valides : {known}\n"
                f"Ou utilisez directement un ID LEGITEXT..."
            )
        return rid


# Singleton partagé
_client: Optional[_LegifranceClient] = None

def _get_client() -> _LegifranceClient:
    global _client
    if _client is None:
        _client = _LegifranceClient()
    return _client


# ---------------------------------------------------------------------------
# Formatage Markdown des résultats
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<p[^>]*>", "\n", text)
    text = re.sub(r"</p>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _fmt_search(data: Dict, query: str) -> str:
    results = data.get("results", [])
    total   = data.get("totalResultNumber", 0)
    if not results:
        return f"Aucun résultat pour : « {query} »"
    lines = [f"**{total} résultat(s) pour « {query} »** — {len(results)} affichés\n"]
    for i, r in enumerate(results, 1):
        t_list  = r.get("titles", [{}])
        title   = t_list[0].get("title",           r.get("title", "Sans titre"))
        nature  = t_list[0].get("nature",           r.get("nature", ""))
        rid     = t_list[0].get("id",               r.get("id", ""))
        date_p  = t_list[0].get("datePubliTexte",   "")
        lines.append(f"{i}. **{title}**")
        if nature: lines.append(f"   Nature : {nature}")
        if rid:    lines.append(f"   ID : `{rid}`")
        if date_p: lines.append(f"   Date : {date_p}")
        lines.append("")
    return "\n".join(lines)


def _fmt_article(data: Dict) -> str:
    a      = data.get("article", data)
    num    = a.get("num",    a.get("numero", ""))
    texte  = _strip_html(a.get("texte", a.get("content", a.get("texteHtml", ""))))
    rid    = a.get("id", "")
    etat   = a.get("etat", "")
    debut  = a.get("dateDebut", "")
    lines  = []
    if num:   lines.append(f"**Article {num}**")
    if rid:   lines.append(f"ID : `{rid}`")
    if etat:  lines.append(f"État : {etat}")
    if debut: lines.append(f"En vigueur depuis : {debut}")
    lines.append(f"\n{texte}" if texte else "\n*(texte non disponible)*")
    return "\n".join(lines)


def _fmt_toc(data: Dict, code: str) -> str:
    titre  = data.get("titre", data.get("title", code))
    lines  = [f"# {titre}\n"]

    def walk(items, depth=0):
        indent = "  " * depth
        for item in items:
            t   = item.get("titre", item.get("title", item.get("num", "")))
            rid = item.get("id", "")
            if t:
                if depth == 0:
                    lines.append(f"\n## {t}")
                else:
                    lines.append(f"{indent}- {t}" + (f" (`{rid}`)" if rid else ""))
            children = item.get("sections", item.get("articles", item.get("children", [])))
            if children and depth < 3:
                walk(children, depth + 1)

    walk(data.get("sections", data.get("articles", [])))
    return "\n".join(lines) if len(lines) > 1 else f"Structure vide pour {code}."


# ---------------------------------------------------------------------------
# Définition des outils Légifrance
# Préfixe "legifrance_" pour les distinguer des outils existants de Prométhée
# ---------------------------------------------------------------------------

@tool(
    name="legifrance_rechercher",
    description=(
        "Recherche de textes juridiques français dans Légifrance : codes, lois, décrets, "
        "arrêtés, circulaires, jurisprudence, conventions collectives, Journal Officiel. "
        "Retourne une liste avec titres, natures et identifiants."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Mots-clés (ex: 'responsabilité civile', 'licenciement abusif', 'RGPD')",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 10,
                "description": "Nombre de résultats (1–20, défaut: 10)",
            },
            "fond": {
                "type": "string",
                "enum": ["ALL", "JORF", "LODA", "CODE_DATE", "JURI", "KALI", "CNIL"],
                "default": "ALL",
                "description": "Fonds à interroger (ALL=tous, JURI=jurisprudence, KALI=conventions collectives…)",
            },
        },
        "required": ["query"],
    },
)
def legifrance_rechercher(query: str, nb_resultats: int = 10, fond: str = "ALL") -> str:
    c = _get_client()
    data = c._req("/search", body={
        "fond": fond,
        "recherche": {
            "champs": [{
                "typeChamp": "ALL",
                "criteres": [{"typeRecherche": "UN_DES_MOTS", "valeur": query, "operateur": "ET"}],
                "operateur": "ET",
            }],
            "operateur":      "ET",
            "pageSize":       min(max(1, nb_resultats), 20),
            "pageNumber":     1,
            "sort":           "PERTINENCE",
            "typePagination": "DEFAUT",
        },
    })
    return _fmt_search(data, query)


@tool(
    name="legifrance_consulter_code",
    description=(
        "Consulte la table des matières structurée d'un code juridique français "
        "(Code civil, pénal, du travail, de commerce, etc.). "
        "Retourne la hiérarchie des parties, livres, titres et articles avec leurs identifiants. "
        "Utilisez legifrance_obtenir_article ou legifrance_article_par_numero pour lire un article précis."
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Nom du code (civil, penal, travail, commerce, consommation, "
                    "procedure_civile, procedure_penale, sante_publique, education, "
                    "environnement, securite_sociale, urbanisme, assurances, "
                    "monetaire_financier, propriete_intellectuelle) "
                    "ou directement un ID Légifrance (LEGITEXT...)."
                ),
            },
            "date": {
                "type": "string",
                "description": "Date de consultation YYYY-MM-DD (défaut: aujourd'hui)",
            },
        },
        "required": ["code"],
    },
)
def legifrance_consulter_code(code: str, date: Optional[str] = None) -> str:
    c      = _get_client()
    try:
        tid = c.resolve_code(code)
    except ValueError as e:
        return str(e)
    data = c._req("/consult/legi/tableMatieres", body={
        "textId": tid,
        "date":   date or globals()["date"].today().isoformat(),
    })
    return _fmt_toc(data, code)


@tool(
    name="legifrance_obtenir_article",
    description=(
        "Récupère le texte complet d'un article juridique par son identifiant Légifrance "
        "(format LEGIARTI000XXXXXXXXX). L'ID s'obtient via legifrance_rechercher ou legifrance_consulter_code."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_id": {
                "type": "string",
                "description": "Identifiant Légifrance de l'article (ex: LEGIARTI000006419283)",
            },
        },
        "required": ["article_id"],
    },
)
def legifrance_obtenir_article(article_id: str) -> str:
    c    = _get_client()
    data = c._req("/consult/getArticle", body={"id": article_id})
    return _fmt_article(data)


@tool(
    name="legifrance_article_par_numero",
    description=(
        "Récupère un article d'un code ou d'un texte par son numéro (ex: '1382', 'L1234-5', 'R123-1'). "
        "Plus pratique que legifrance_obtenir_article quand on connaît le numéro mais pas l'ID."
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Nom du code (civil, travail…) ou ID Légifrance (LEGITEXT...)",
            },
            "numero": {
                "type": "string",
                "description": "Numéro de l'article (ex: '1382', 'L1234-5', 'R10')",
            },
        },
        "required": ["code", "numero"],
    },
)
def legifrance_article_par_numero(code: str, numero: str) -> str:
    c = _get_client()
    try:
        tid = c.resolve_code(code)
    except ValueError as e:
        return str(e)
    data = c._req("/consult/getArticleWithIdAndNum", body={"id": tid, "num": numero})
    return _fmt_article(data)


@tool(
    name="legifrance_versions_article",
    description=(
        "Récupère l'historique complet des versions d'un article pour suivre "
        "ses modifications législatives au fil du temps. Utilise le CID de l'article."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_cid": {
                "type": "string",
                "description": "CID (identifiant canonique) de l'article",
            },
        },
        "required": ["article_cid"],
    },
)
def legifrance_versions_article(article_cid: str) -> str:
    c        = _get_client()
    data     = c._req("/consult/getArticleByCid", body={"cid": article_cid})
    versions = data.get("listArticle", [])
    if not versions:
        return f"Aucune version trouvée pour le CID `{article_cid}`."
    lines = [f"**{len(versions)} version(s) de l'article `{article_cid}`**\n"]
    for v in versions:
        lines.append(_fmt_article(v))
        lines.append("\n---\n")
    return "\n".join(lines)


@tool(
    name="legifrance_loi_decret",
    description=(
        "Consulte le contenu complet d'une loi, d'un décret, d'une ordonnance ou d'un arrêté "
        "(fonds LODA) à partir de son identifiant et de sa date de vigueur."
        "Retourne les articles structurés du texte."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_id": {
                "type": "string",
                "description": "Identifiant Légifrance du texte (ex: LEGITEXT000006353440)",
            },
            "date": {
                "type": "string",
                "description": "Date de consultation YYYY-MM-DD (défaut: aujourd'hui)",
            },
        },
        "required": ["text_id"],
    },
)
def legifrance_loi_decret(text_id: str, date: Optional[str] = None) -> str:
    c    = _get_client()
    data = c._req("/consult/lawDecree", body={
        "textId": text_id,
        "date":   date or globals()["date"].today().isoformat(),
    })
    titre    = data.get("title", text_id)
    nature   = data.get("nature", "")
    nor      = data.get("nor", "")
    date_pub = data.get("dateParution", "")
    lines    = [f"# {titre}\n"]
    if nature:   lines.append(f"**Nature** : {nature}")
    if nor:      lines.append(f"**NOR** : {nor}")
    if date_pub: lines.append(f"**Publication** : {date_pub}")
    articles = data.get("articles", data.get("sections", []))
    if articles:
        lines.append(f"\n**{len(articles)} article(s)**\n")
        for a in articles[:50]:
            lines.append(_fmt_article(a))
            lines.append("")
        if len(articles) > 50:
            lines.append(f"*… {len(articles)-50} article(s) supplémentaires non affichés*")
    return "\n".join(lines)


@tool(
    name="legifrance_jorf",
    description=(
        "Consulte un texte publié au Journal Officiel de la République Française (JORF). "
        "Retourne le contenu et les métadonnées de publication."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_cid": {
                "type": "string",
                "description": "CID du texte JORF (ex: JORFTEXT000000000001)",
            },
        },
        "required": ["text_cid"],
    },
)
def legifrance_jorf(text_cid: str) -> str:
    c      = _get_client()
    data   = c._req("/consult/jorf", body={"textCid": text_cid})
    # ConsultJorfResponse → title, dateParution, nor, sections, articles (swagger)
    titre  = data.get("title", text_cid)
    date_p = data.get("dateParution", "")
    nor    = data.get("nor", "")
    lines  = [f"# {titre}\n"]
    if date_p: lines.append(f"**Publication JO** : {date_p}")
    if nor:    lines.append(f"**NOR** : {nor}")
    arts  = data.get("articles", [])
    sects = data.get("sections", [])
    nb    = len(arts) + sum(len(s.get("articles", [])) for s in sects)
    if nb: lines.append(f"\n*{nb} article(s) — utilisez legifrance_jorf_part pour le contenu*")
    return "\n".join(lines)


@tool(
    name="legifrance_jurisprudence",
    description=(
        "Consulte une décision de justice française (jurisprudence). "
        "Retourne le texte complet de la décision avec la juridiction et la date."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_id": {
                "type": "string",
                "description": "Identifiant de la décision (ex: JURITEXT000007587512)",
            },
        },
        "required": ["text_id"],
    },
)
def legifrance_jurisprudence(text_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/juri", body={"textId": text_id})
    # ConsultJuriTextResponse → text (list[TexteSimple]) (swagger)
    txt   = data.get("text") or [{}]
    txt   = txt[0] if isinstance(txt, list) else txt
    titre = txt.get("titre", text_id)
    juri  = txt.get("juridiction", "")
    dt    = txt.get("dateTexte", "")
    texte = _strip_html(txt.get("texteHtml", txt.get("texte", "")))
    lines = [f"# {titre}\n"]
    if juri:  lines.append(f"**Juridiction** : {juri}")
    if dt:    lines.append(f"**Date** : {dt}")
    if texte:
        lines.append(f"\n{texte[:5000]}")
        if len(texte) > 5000:
            lines.append("\n*[Texte tronqué]*")
    return "\n".join(lines)


@tool(
    name="legifrance_lister_codes",
    description=(
        "Liste tous les codes juridiques disponibles dans Légifrance avec leurs identifiants. "
        "Utile pour trouver l'ID d'un code avant de le consulter."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filtre": {
                "type": "string",
                "description": "Filtre par nom (optionnel, ex: 'code de la route', 'environnement')",
            },
            "en_vigueur_seulement": {
                "type": "boolean",
                "default": True,
                "description": "Retourner uniquement les codes en vigueur (défaut: true)",
            },
        },
    },
)
def legifrance_lister_codes(filtre: Optional[str] = None, en_vigueur_seulement: bool = True) -> str:
    c     = _get_client()
    body  = {"pageNumber": 1, "pageSize": 100}
    if filtre:               body["codeName"] = filtre
    if en_vigueur_seulement: body["states"]   = ["VIGUEUR"]
    data  = c._req("/list/code", body=body)
    # CodeListResponse → results (swagger)
    codes = data.get("results", [])
    if not codes:
        return "Aucun code trouvé."
    lines = [f"**{len(codes)} code(s)**\n"]
    for code in codes:
        t   = code.get("titre", code.get("title", ""))
        rid = code.get("id",    code.get("cid", ""))
        lines.append(f"- **{t}**" + (f" — `{rid}`" if rid else ""))
    return "\n".join(lines)


@tool(
    name="legifrance_conventions",
    description=(
        "Liste et recherche les conventions collectives disponibles dans Légifrance (fonds KALI). "
        "Filtrable par titre ou numéro IDCC."
    ),
    parameters={
        "type": "object",
        "properties": {
            "titre": {
                "type": "string",
                "description": "Recherche par titre (ex: 'métallurgie', 'bâtiment', 'commerce de détail')",
            },
            "idcc": {
                "type": "string",
                "description": "Numéro IDCC exact (ex: '0016', '1486')",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_conventions(
    titre: Optional[str] = None,
    idcc:  Optional[str] = None,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body = {"pageNumber": 1, "pageSize": nb_resultats}
    if titre: body["titre"] = titre
    if idcc:  body["idcc"]  = idcc
    data  = c._req("/list/conventions", body=body)
    # ConventionsListResponse → results (swagger)
    items = data.get("results", [])
    if not items:
        return "Aucune convention collective trouvée."
    lines = [f"**{len(items)} convention(s)**\n"]
    for cv in items:
        t    = cv.get("titre", cv.get("title", ""))
        idcc = cv.get("idcc", "")
        rid  = cv.get("id", "")
        lines.append(
            f"- **{t}**"
            + (f" (IDCC {idcc})" if idcc else "")
            + (f" — `{rid}`"     if rid  else "")
        )
    return "\n".join(lines)


@tool(
    name="legifrance_suggerer",
    description=(
        "Suggestions et autocomplétion pour identifier un texte juridique dont on connaît "
        "le début du nom. Utile avant une recherche ou consultation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texte": {
                "type": "string",
                "description": "Début du nom à compléter (ex: 'code de la consom', 'loi du 17 juil')",
            },
        },
        "required": ["texte"],
    },
)
def legifrance_suggerer(texte: str) -> str:
    c    = _get_client()
    data = c._req("/suggest", body={"searchText": texte})
    # SuggestResponse → results (object) (swagger)
    results = data.get("results", {})
    if not results:
        return f"Aucune suggestion pour : « {texte} »"
    total = data.get("totalResultNumber", "")
    lines = [f"**Suggestions pour « {texte} »**" + (f" ({total})" if total else "") + "\n"]
    # results est un objet dict (fonds → liste)
    if isinstance(results, dict):
        for fond, items in list(results.items())[:5]:
            for s in (items if isinstance(items, list) else [])[:5]:
                t = s.get("title", s.get("titre", s.get("text", str(s))))
                rid = s.get("id", "")
                lines.append(f"- [{fond}] {t}" + (f" (`{rid}`)" if rid else ""))
    return "\n".join(lines)


# ===========================================================================
# OUTILS SEARCH — versions canoniques
# ===========================================================================

@tool(
    name="legifrance_version_canonique_article",
    description=(
        "Récupère les informations de version canonique d'un article à partir de son identifiant. "
        "Utile pour résoudre l'identifiant stable (CID) d'un article dont on connaît l'ID versionnée."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_id": {
                "type": "string",
                "description": "Identifiant de l'article (ex: LEGIARTI000006436298)",
            },
        },
        "required": ["article_id"],
    },
)
def legifrance_version_canonique_article(article_id: str) -> str:
    c    = _get_client()
    data = c._req("/search/canonicalArticleVersion", body={"id": article_id})
    lines = [f"**Version canonique de l'article `{article_id}`**\n"]
    for k, v in data.items():
        if v:
            lines.append(f"- **{k}** : {v}")
    return "\n".join(lines) if len(lines) > 1 else f"Aucune information pour `{article_id}`."


@tool(
    name="legifrance_version_canonique",
    description=(
        "Récupère les informations de version canonique d'un texte à une date donnée. "
        "Permet de déterminer quelle version d'un texte était en vigueur à une date précise."
    ),
    parameters={
        "type": "object",
        "properties": {
            "cid_text": {
                "type": "string",
                "description": "CID du texte (ex: LEGITEXT000006070721)",
            },
            "date": {
                "type": "string",
                "description": "Date de référence au format YYYY-MM-DD",
            },
            "cid_section": {
                "type": "string",
                "description": "CID de la section (optionnel)",
            },
        },
        "required": ["cid_text", "date"],
    },
)
def legifrance_version_canonique(cid_text: str, date: str, cid_section: Optional[str] = None) -> str:
    c    = _get_client()
    body = {"cidText": cid_text, "date": date}
    if cid_section:
        body["cidSection"] = cid_section
    data  = c._req("/search/canonicalVersion", body=body)
    lines = [f"**Version canonique de `{cid_text}` au {date}**\n"]
    for k, v in data.items():
        if v:
            lines.append(f"- **{k}** : {v}")
    return "\n".join(lines) if len(lines) > 1 else "Aucune information de version canonique trouvée."


@tool(
    name="legifrance_version_proche",
    description=(
        "Récupère la version d'un texte la plus proche d'une date donnée. "
        "Utile quand la date exacte n'a pas de version et qu'on veut la version voisine."
    ),
    parameters={
        "type": "object",
        "properties": {
            "cid_text": {
                "type": "string",
                "description": "CID du texte (ex: LEGITEXT000006070721)",
            },
            "date": {
                "type": "string",
                "description": "Date de référence au format YYYY-MM-DD",
            },
            "cid_section": {
                "type": "string",
                "description": "CID de la section (optionnel)",
            },
        },
        "required": ["cid_text", "date"],
    },
)
def legifrance_version_proche(cid_text: str, date: str, cid_section: Optional[str] = None) -> str:
    c    = _get_client()
    body = {"cidText": cid_text, "date": date}
    if cid_section:
        body["cidSection"] = cid_section
    data  = c._req("/search/nearestVersion", body=body)
    lines = [f"**Version la plus proche de `{cid_text}` autour du {date}**\n"]
    for k, v in data.items():
        if v:
            lines.append(f"- **{k}** : {v}")
    return "\n".join(lines) if len(lines) > 1 else "Aucune version proche trouvée."


# ===========================================================================
# OUTILS CONSULT — Journal Officiel (JORF) complémentaires
# ===========================================================================

@tool(
    name="legifrance_jo_par_nor",
    description=(
        "Consulte un texte du Journal Officiel par son numéro NOR "
        "(Numéro d'Ordre du Registre, ex: PRMD2117108D). "
        "Retourne le contenu complet du texte publié au JO."
    ),
    parameters={
        "type": "object",
        "properties": {
            "nor": {
                "type": "string",
                "description": "Numéro NOR du texte (ex: PRMD2117108D, JUSB2123813A)",
            },
        },
        "required": ["nor"],
    },
)
def legifrance_jo_par_nor(nor: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/getJoWithNor", body={"nor": nor})
    # ConsultJorfResponse → title, dateParution, nor, sections (swagger)
    titre  = data.get("title", nor)
    date_p = data.get("dateParution", "")
    lines  = [f"# {titre}\n"]
    lines.append(f"**NOR** : {nor}")
    if date_p: lines.append(f"**Publication JO** : {date_p}")
    arts  = data.get("articles", [])
    sects = data.get("sections", [])
    nb    = len(arts) + sum(len(s.get("articles", [])) for s in sects)
    if nb: lines.append(f"\n*{nb} article(s) — utilisez legifrance_jorf_part pour le contenu*")
    return "\n".join(lines)


@tool(
    name="legifrance_derniers_jo",
    description=(
        "Récupère les dernières parutions du Journal Officiel. "
        "Retourne la liste des N derniers numéros publiés avec leurs dates et identifiants."
    ),
    parameters={
        "type": "object",
        "properties": {
            "nb": {
                "type": "integer",
                "default": 10,
                "description": "Nombre de JO à récupérer (défaut: 10)",
            },
        },
    },
)
def legifrance_derniers_jo(nb: int = 10) -> str:
    c    = _get_client()
    data = c._req("/consult/lastNJo", body={"nbElement": nb})
    # La réponse réelle utilise "containers" (GetJorfContResponse swagger)
    items = data.get("containers", [])
    if not items:
        return "Aucun Journal Officiel trouvé."
    total = data.get("totalNbResult", len(items))
    lines = [f"**{len(items)} dernier(s) Journal(aux) Officiel(s)** (total API : {total})\n"]
    for jo in items:
        date_p = jo.get("datePubli", "")          # clé réelle : datePubli
        num    = jo.get("num", jo.get("numero", ""))  # clé réelle : num
        cid    = jo.get("cid", jo.get("id", ""))  # préférer cid (stable)
        titre  = jo.get("titre", "")
        label  = f"JO du {date_p}" if date_p else "JO"
        if num:
            label += f" n°{num}"
        detail = f" — {titre}" if titre else ""
        lines.append(f"- **{label}**{detail}" + (f" — `{cid}`" if cid else ""))
    return "\n".join(lines)


@tool(
    name="legifrance_sommaire_jorf",
    description=(
        "Consulte le sommaire d'un numéro du Journal Officiel (JORF). "
        "Permet de lister les textes publiés dans un JO donné, filtrable par date ou numéro."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date de parution du JO au format YYYY-MM-DD (ex: '2024-01-15')",
            },
            "jorf_id": {
                "type": "string",
                "description": "Identifiant du conteneur JORF (optionnel, ex: JORFCONT000049456397)",
            },
            "recherche": {
                "type": "string",
                "description": "Texte à rechercher dans le sommaire (optionnel)",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_sommaire_jorf(
    date: Optional[str] = None,
    jorf_id: Optional[str] = None,
    recherche: Optional[str] = None,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"pageNumber": 1, "pageSize": nb_resultats}
    if jorf_id:
        body["id"] = jorf_id
    if date:
        body["date"] = date
    if recherche:
        body["searchText"] = recherche
    data  = c._req("/consult/jorfCont", body=body)
    # La réponse réelle utilise "items" (GetJosResponse swagger).
    # Chaque item est un dict { joCont: {...}, joInap: {...}, joEA: {...} }.
    # joCont est le conteneur principal : id, cid, titre, datePubli, nature, num.
    items = data.get("items", [])
    label = date or jorf_id or "JO"
    if not items:
        return f"Aucun résultat dans le sommaire du {label}."
    total = data.get("totalNbResult", len(items))
    lines = [f"**{total} résultat(s) au JO du {label}** — {len(items)} affiché(s)\n"]
    for item in items:
        cont = item.get("joCont") or item.get("joInap") or item.get("joEA") or item
        if not cont:
            continue
        titre  = cont.get("titre", "Sans titre")
        nature = cont.get("nature", "")
        date_p = cont.get("datePubli", "")
        cid    = cont.get("cid", cont.get("id", ""))
        num    = cont.get("num", "")
        suffix = " | ".join(filter(None, [nature, f"n°{num}" if num else "", date_p]))
        lines.append(f"- **{titre}**" + (f" ({suffix})" if suffix else "") + (f" — `{cid}`" if cid else ""))
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Conventions collectives (KALI)
# ===========================================================================

@tool(
    name="legifrance_convention_par_idcc",
    description=(
        "Consulte le conteneur (structure principale) d'une convention collective "
        "par son numéro IDCC. Retourne la structure et les métadonnées de la convention."
    ),
    parameters={
        "type": "object",
        "properties": {
            "idcc": {
                "type": "string",
                "description": "Numéro IDCC de la convention collective (ex: '0016', '1486', '3248')",
            },
        },
        "required": ["idcc"],
    },
)
def legifrance_convention_par_idcc(idcc: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/kaliContIdcc", body={"id": idcc})
    # ConsultKaliContResponse → titre, id, num, nature, sections (swagger)
    titre   = data.get("titre", f"Convention IDCC {idcc}")  # clé réelle : titre
    rid     = data.get("id", "")
    num     = data.get("num", "")
    nature  = data.get("nature", "")
    sects   = data.get("sections", [])
    lines   = [f"# {titre}\n", f"**IDCC** : {idcc}"]
    if rid:    lines.append(f"**ID** : `{rid}`")
    if num:    lines.append(f"**Numéro** : {num}")
    if nature: lines.append(f"**Nature** : {nature}")
    if sects:
        lines.append(f"\n**{len(sects)} section(s)**")
        for s in sects[:20]:
            t = s.get("titre", s.get("num", ""))
            if t: lines.append(f"  - {t}")
        if len(sects) > 20:
            lines.append(f"  *… {len(sects)-20} élément(s) supplémentaires*")
    return "\n".join(lines)


@tool(
    name="legifrance_convention_texte",
    description=(
        "Consulte le texte complet d'une convention collective par son identifiant KALI "
        "(format KALITEXTXXXXXXXXX). Retourne le contenu structuré de la convention."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_id": {
                "type": "string",
                "description": "Identifiant KALI du texte (ex: KALITEXT000005635374)",
            },
        },
        "required": ["text_id"],
    },
)
def legifrance_convention_texte(text_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/kaliText", body={"id": text_id})
    # ConsultKaliTextResponse → title, nor, etat (swagger)
    titre = data.get("title", text_id)   # clé réelle : title (pas titre)
    nor   = data.get("nor", "")
    lines = [f"# {titre}\n"]
    if nor: lines.append(f"**NOR** : {nor}")
    etat = data.get("etat", "")
    if etat:
        lines.append(f"**État** : {etat}")
    articles = data.get("articles", data.get("sections", []))
    if articles:
        lines.append(f"\n**{len(articles)} article(s)/section(s)**\n")
        for a in articles[:30]:
            lines.append(_fmt_article(a))
            lines.append("")
        if len(articles) > 30:
            lines.append(f"*… {len(articles)-30} élément(s) supplémentaire(s) non affiché(s)*")
    return "\n".join(lines)


@tool(
    name="legifrance_convention_article",
    description=(
        "Consulte un article spécifique d'une convention collective par son identifiant "
        "(format KALIARTXXXXXXXXX). Retourne le texte complet de l'article."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_id": {
                "type": "string",
                "description": "Identifiant de l'article KALI (ex: KALIARTI000005635375)",
            },
        },
        "required": ["article_id"],
    },
)
def legifrance_convention_article(article_id: str) -> str:
    c    = _get_client()
    data = c._req("/consult/kaliArticle", body={"id": article_id})
    return _fmt_article(data)


@tool(
    name="legifrance_convention_section",
    description=(
        "Consulte une section d'une convention collective par son identifiant "
        "(format KALISECTXXXXXXXXX). Retourne le contenu de la section."
    ),
    parameters={
        "type": "object",
        "properties": {
            "section_id": {
                "type": "string",
                "description": "Identifiant de la section KALI (ex: KALISECT000005635376)",
            },
        },
        "required": ["section_id"],
    },
)
def legifrance_convention_section(section_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/kaliSection", body={"id": section_id})
    # ConsultKaliTextResponse → title, articles, sections (swagger)
    titre    = data.get("title", section_id)  # clé réelle : title
    articles = data.get("articles", [])
    sects    = data.get("sections", [])
    lines    = [f"**Section : {titre}**\n"]
    if articles:
        lines.append(f"**{len(articles)} article(s)**\n")
        for a in articles:
            lines.append(_fmt_article(a))
            lines.append("")
    if sects:
        lines.append(f"*{len(sects)} sous-section(s)*")
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Jurisprudence complémentaire
# ===========================================================================

@tool(
    name="legifrance_jurisprudence_plan_classement",
    description=(
        "Consulte le plan de classement de la jurisprudence (arborescence thématique). "
        "Permet de naviguer dans les catégories de jurisprudence par thème ou matière."
    ),
    parameters={
        "type": "object",
        "properties": {
            "libelle": {
                "type": "string",
                "description": "Libellé à rechercher dans le plan de classement (ex: 'contrat', 'responsabilité')",
            },
            "fond": {
                "type": "string",
                "description": "Fond juridictionnel (optionnel, ex: 'juri', 'CASS', 'CE')",
            },
            "niveau": {
                "type": "integer",
                "description": "Niveau hiérarchique (optionnel, 1=racine)",
            },
        },
    },
)
def legifrance_jurisprudence_plan_classement(
    libelle: Optional[str] = None,
    fond: Optional[str] = None,
    niveau: Optional[int] = None,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {}
    if libelle:
        body["libelle"] = libelle
    if fond:
        body["fond"] = fond
    if niveau is not None:
        body["niveau"] = niveau
    data  = c._req("/consult/getJuriPlanClassement", body=body)
    # GetListPlanClassementJuriResponse → listPlanClassementJuri (swagger)
    items = data.get("listPlanClassementJuri", [])
    if not items:
        return "Aucune entrée de plan de classement trouvée."
    lines = [f"**Plan de classement jurisprudence**\n"]
    for item in items[:30]:
        libelle_item = item.get("libelle", item.get("title", ""))
        rid          = item.get("id", "")
        nb           = item.get("nbDocuments", "")
        line         = f"- **{libelle_item}**"
        if nb:
            line += f" ({nb} décision(s))"
        if rid:
            line += f" — `{rid}`"
        lines.append(line)
    if len(items) > 30:
        lines.append(f"\n*… {len(items)-30} entrée(s) supplémentaire(s)*")
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Divers (CNIL, accords, circulaires, débats, dossiers)
# ===========================================================================

@tool(
    name="legifrance_cnil",
    description=(
        "Consulte une délibération ou une décision de la CNIL (Commission Nationale de l'Informatique "
        "et des Libertés) par son identifiant. Retourne le texte complet de la décision."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_id": {
                "type": "string",
                "description": "Identifiant du texte CNIL (ex: CNILTEXT000017651305)",
            },
        },
        "required": ["text_id"],
    },
)
def legifrance_cnil(text_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/cnil", body={"textId": text_id})
    # ConsultCnilTextResponse → text (list[TexteSimple]) (swagger)
    txt   = data.get("text") or [{}]
    txt   = txt[0] if isinstance(txt, list) else txt
    titre = txt.get("titre", text_id)
    date_d = txt.get("dateTexte", "")
    texte  = _strip_html(txt.get("texteHtml", txt.get("texte", "")))
    lines  = [f"# {titre}\n"]
    if date_d:
        lines.append(f"**Date** : {date_d}")
    if texte:
        lines.append(f"\n{texte[:5000]}")
        if len(texte) > 5000:
            lines.append("\n*[Texte tronqué]*")
    return "\n".join(lines)


@tool(
    name="legifrance_acco",
    description=(
        "Consulte un accord d'entreprise (fonds ACCO) par son identifiant. "
        "Les accords d'entreprise sont des conventions signées entre employeurs et représentants du personnel."
    ),
    parameters={
        "type": "object",
        "properties": {
            "acco_id": {
                "type": "string",
                "description": "Identifiant de l'accord d'entreprise",
            },
        },
        "required": ["acco_id"],
    },
)
def legifrance_acco(acco_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/acco", body={"id": acco_id})
    # ConsultAccoResponse → acco (list[Accord]) (swagger)
    acc   = data.get("acco") or [{}]
    acc   = acc[0] if isinstance(acc, list) else acc
    titre = acc.get("titreTexte", acco_id)  # Accord.titreTexte
    siret = acc.get("siret", "")
    rs    = acc.get("raisonSociale", "")
    date_d = acc.get("dateDepot", "")
    lines  = [f"# {titre}\n"]
    if siret:  lines.append(f"**SIRET** : {siret}")
    if rs:     lines.append(f"**Entreprise** : {rs}")
    if date_d: lines.append(f"**Date de dépôt** : {date_d}")
    return "\n".join(lines)


@tool(
    name="legifrance_circulaire",
    description=(
        "Consulte une circulaire administrative (fonds CIRC) par son identifiant. "
        "Retourne le contenu de la circulaire avec ses métadonnées."
    ),
    parameters={
        "type": "object",
        "properties": {
            "circulaire_id": {
                "type": "string",
                "description": "Identifiant de la circulaire",
            },
        },
        "required": ["circulaire_id"],
    },
)
def legifrance_circulaire(circulaire_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/circulaire", body={"id": circulaire_id})
    # ConsultCirculaireResponse → circulaire (list[Circulaire]) (swagger)
    circ  = data.get("circulaire") or [{}]
    circ  = circ[0] if isinstance(circ, list) else circ
    titre = circ.get("titre", circulaire_id)  # Circulaire.titre
    nor   = circ.get("nor", "")
    date_p = circ.get("dateSignature", "")  # dateSignature (pas datePubliTexte)
    lines  = [f"# {titre}\n"]
    if nor:    lines.append(f"**NOR** : {nor}")
    if date_p: lines.append(f"**Date de signature** : {date_p}")
    return "\n".join(lines)


@tool(
    name="legifrance_debat",
    description=(
        "Consulte le compte-rendu d'un débat parlementaire par son identifiant. "
        "Couvre les séances de l'Assemblée Nationale et du Sénat."
    ),
    parameters={
        "type": "object",
        "properties": {
            "debat_id": {
                "type": "string",
                "description": "Identifiant du débat parlementaire",
            },
        },
        "required": ["debat_id"],
    },
)
def legifrance_debat(debat_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/debat", body={"id": debat_id})
    # ConsultDebatResponse → debat (list[Debat]) (swagger)
    deb   = data.get("debat") or [{}]
    deb   = deb[0] if isinstance(deb, list) else deb
    date_s = deb.get("dateSeance", "")
    assemblee = deb.get("typeAssemblee", "")  # typeAssemblee (pas typeParlement)
    legis  = deb.get("legislature", "")
    session = deb.get("session", "")
    rid    = deb.get("id", debat_id)
    lines  = [f"# Débat parlementaire `{rid}`\n"]
    if date_s:   lines.append(f"**Séance du** : {date_s}")
    if assemblee: lines.append(f"**Assemblée** : {assemblee}")
    if legis:    lines.append(f"**Législature** : {legis}")
    if session:  lines.append(f"**Session** : {session}")
    return "\n".join(lines)


@tool(
    name="legifrance_dossier_legislatif",
    description=(
        "Consulte un dossier législatif complet par son identifiant. "
        "Un dossier législatif regroupe tous les documents liés à l'élaboration d'une loi : "
        "projets, amendements, rapports, textes adoptés."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dossier_id": {
                "type": "string",
                "description": "Identifiant du dossier législatif",
            },
        },
        "required": ["dossier_id"],
    },
)
def legifrance_dossier_legislatif(dossier_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/dossierLegislatif", body={"id": dossier_id})
    # ConsultDossierLegislatifResponse → dossierLegislatif (list[DossierLegislatif]) (swagger)
    dos   = data.get("dossierLegislatif") or [{}]
    dos   = dos[0] if isinstance(dos, list) else dos
    titre = dos.get("titre", dossier_id)          # DossierLegislatif.titre
    type_d = dos.get("type", "")
    legis  = dos.get("legislature", "")
    date_c = dos.get("dateCreation", "")
    date_m = dos.get("dateDerniereModification", "")
    lines  = [f"# {titre}\n"]
    if type_d: lines.append(f"**Type** : {type_d}")
    if legis:  lines.append(f"**Législature** : {legis}")
    if date_c: lines.append(f"**Créé le** : {date_c}")
    if date_m: lines.append(f"**Modifié le** : {date_m}")
    return "\n".join(lines)


@tool(
    name="legifrance_section_par_cid",
    description=(
        "Récupère le contenu d'une section de code ou de texte par son CID canonique "
        "(format LEGISCTA...). Utile pour naviguer dans la structure d'un code."
    ),
    parameters={
        "type": "object",
        "properties": {
            "cid": {
                "type": "string",
                "description": "CID de la section (ex: LEGISCTA000006150321)",
            },
        },
        "required": ["cid"],
    },
)
def legifrance_section_par_cid(cid: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/getSectionByCid", body={"cid": cid})
    # GetListSectionResponse → listSection (list[Section]) (swagger)
    sects = data.get("listSection", [])
    if not sects:
        return f"Aucune section trouvée pour le CID `{cid}`."
    lines = [f"**{len(sects)} section(s) pour** `{cid}`\n"]
    for s in sects[:20]:
        titre_s = s.get("titre", "")
        cid_s   = s.get("cid", s.get("id", ""))
        debut   = s.get("dateDebut", "")
        lines.append(f"- **{titre_s}**" + (f" `{cid_s}`" if cid_s else "") + (f" ({debut})" if debut else ""))
    return "\n".join(lines)


# ===========================================================================
# OUTILS CHRONO — Historique des versions de textes
# ===========================================================================

@tool(
    name="legifrance_historique_texte",
    description=(
        "Récupère l'historique complet des versions d'un texte juridique sur une période donnée. "
        "Permet de suivre l'évolution législative d'un code ou d'une loi dans le temps."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_cid": {
                "type": "string",
                "description": "CID chronologique du texte (ex: LEGITEXT000006070721 pour le Code civil)",
            },
            "annee_debut": {
                "type": "integer",
                "description": "Année de début de la période détaillée (ex: 2015)",
            },
            "annee_fin": {
                "type": "integer",
                "description": "Année de fin de la période détaillée (ex: 2024)",
            },
            "date_consult": {
                "type": "string",
                "description": "Date de référence au format YYYY-MM-DD (défaut: aujourd'hui)",
            },
        },
        "required": ["text_cid", "annee_debut", "annee_fin"],
    },
)
def legifrance_historique_texte(
    text_cid: str,
    annee_debut: int,
    annee_fin: int,
    date_consult: Optional[str] = None,
) -> str:
    c = _get_client()
    if date_consult is None:
        date_consult = globals()["date"].today().isoformat()
    data     = c._req("/chrono/textCid", body={
        "textCid":     text_cid,
        "dateConsult": date_consult,
        "startYear":   annee_debut,
        "endYear":     annee_fin,
    })
    # ChronolegiResponse → regroupements (list[RegroupementDTO]) (swagger)
    regroupements = data.get("regroupements", [])
    if not regroupements:
        return f"Aucune version trouvée pour `{text_cid}` entre {annee_debut} et {annee_fin}."
    lines = [f"**{len(regroupements)} regroupement(s) de `{text_cid}` ({annee_debut}–{annee_fin})**\n"]
    for rg in regroupements:
        title_rg = rg.get("title", "")
        vers     = rg.get("versions", [])
        lines.append(f"- **{title_rg}** ({len(vers)} version(s))")
    return "\n".join(lines)


@tool(
    name="legifrance_versions_element",
    description=(
        "Récupère toutes les versions chronologiques d'un article ou d'une section "
        "au sein d'un texte donné. Permet de voir toutes les modifications d'un article."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_cid": {
                "type": "string",
                "description": "CID du texte contenant l'élément (ex: LEGITEXT000006070721)",
            },
            "element_cid": {
                "type": "string",
                "description": "CID de l'article ou de la section (ex: LEGIARTI000006436298)",
            },
        },
        "required": ["text_cid", "element_cid"],
    },
)
def legifrance_versions_element(text_cid: str, element_cid: str) -> str:
    c        = _get_client()
    data     = c._req("/chrono/textCidAndElementCid", body={
        "textCid":    text_cid,
        "elementCid": element_cid,
    })
    # ChronolegiResponse → regroupements (list[RegroupementDTO]) (swagger)
    regroupements = data.get("regroupements", [])
    if not regroupements:
        return f"Aucune version trouvée pour l'élément `{element_cid}`."
    lines = [f"**{len(regroupements)} regroupement(s) pour `{element_cid}`**\n"]
    for rg in regroupements:
        title_rg = rg.get("title", "")
        vers     = rg.get("versions", [])
        lines.append(f"- **{title_rg}** ({len(vers)} version(s))")
    return "\n".join(lines)


@tool(
    name="legifrance_a_des_versions",
    description=(
        "Vérifie rapidement si un texte juridique possède des versions historiques "
        "sans charger toutes les données. Utile avant d'appeler legifrance_historique_texte."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_cid": {
                "type": "string",
                "description": "CID du texte (ex: LEGITEXT000006070721)",
            },
        },
        "required": ["text_cid"],
    },
)
def legifrance_a_des_versions(text_cid: str) -> str:
    c    = _get_client()
    data = c._req(f"/chrono/textCid/{text_cid}", method="GET")
    has  = data.get("hasChronolegi", data.get("hasVersions", False))
    if has:
        return f"✅ Le texte `{text_cid}` **possède** un historique de versions. Utilisez `legifrance_historique_texte` pour les récupérer."
    return f"ℹ️ Le texte `{text_cid}` **ne possède pas** de versions historiques enregistrées."


# ===========================================================================
# OUTILS LIST — Listages complémentaires
# ===========================================================================

@tool(
    name="legifrance_lister_loda",
    description=(
        "Liste les lois, ordonnances et décrets autonomes disponibles dans Légifrance (fonds LODA). "
        "Filtrable par nature (LOI, ORDONNANCE, DECRET…) et état juridique."
    ),
    parameters={
        "type": "object",
        "properties": {
            "natures": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Natures à filtrer (ex: ['LOI', 'ORDONNANCE', 'DECRET', 'ARRETE'])",
            },
            "en_vigueur_seulement": {
                "type": "boolean",
                "default": True,
                "description": "Retourner uniquement les textes en vigueur (défaut: true)",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_lister_loda(
    natures: Optional[List[str]] = None,
    en_vigueur_seulement: bool = True,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"pageNumber": 1, "pageSize": nb_resultats}
    if natures:
        body["natures"] = natures
    if en_vigueur_seulement:
        body["legalStatus"] = ["VIGUEUR"]
    data  = c._req("/list/loda", body=body)
    # LODAListResponse → results, totalResultNumber (swagger)
    # LODAListResult : titre, cid, etat, dateDebut, dateFin, lastUpdate
    items = data.get("results", [])
    if not items:
        return "Aucun texte LODA trouvé."
    total = data.get("totalResultNumber", len(items))
    lines = [f"**{total} texte(s) LODA** — {len(items)} affiché(s)\n"]
    for t in items:
        titre  = t.get("titre", "")
        etat   = t.get("etat", "")
        cid    = t.get("cid", t.get("id", ""))
        debut  = t.get("dateDebut", "")
        line   = f"- **{titre}**"
        if etat:  line += f" ({etat})"
        if debut: line += f" — {debut}"
        if cid:   line += f" — `{cid}`"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="legifrance_lister_legislatures",
    description=(
        "Liste toutes les législatures disponibles dans Légifrance. "
        "Retourne les identifiants nécessaires pour lister les dossiers législatifs."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
)
def legifrance_lister_legislatures() -> str:
    c     = _get_client()
    data  = c._req("/list/legislatures", body={})
    # LegislaturesListResponse → legislatures (swagger)
    items = data.get("legislatures", [])
    if not items:
        return "Aucune législature trouvée."
    lines = [f"**{len(items)} législature(s)**\n"]
    for leg in items:
        num   = leg.get("numero", leg.get("num", leg.get("id", "")))
        debut = leg.get("dateDebut", leg.get("startDate", ""))
        fin   = leg.get("dateFin",   leg.get("endDate", "en cours"))
        rid   = leg.get("id", "")
        line  = f"- **Législature {num}**"
        if debut:
            line += f" : {debut} → {fin}"
        if rid:
            line += f" — `{rid}`"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="legifrance_lister_dossiers_legislatifs",
    description=(
        "Liste les dossiers législatifs d'une législature donnée. "
        "Utilisez legifrance_lister_legislatures pour obtenir l'ID de législature."
    ),
    parameters={
        "type": "object",
        "properties": {
            "legislature_id": {
                "type": "integer",
                "description": "Numéro/identifiant de la législature (ex: 16 pour la XVIe législature)",
            },
            "type_dossier": {
                "type": "string",
                "description": "Type de dossier (ex: 'LOI_PUBLIEE', 'EN_COURS', 'LOI_ORDINAIRE')",
                "default": "LOI_PUBLIEE",
            },
        },
        "required": ["legislature_id"],
    },
)
def legifrance_lister_dossiers_legislatifs(
    legislature_id: int,
    type_dossier: str = "LOI_PUBLIEE",
) -> str:
    c     = _get_client()
    data  = c._req("/list/dossiersLegislatifs", body={
        "legislatureId": legislature_id,
        "type":          type_dossier,
    })
    # DossiersLegislatifsListResponse → dossiersLegislatifs (swagger)
    # DossierLegislatifResult : titre, id, dateCreation, dateDerniereModification, type
    items = data.get("dossiersLegislatifs", [])
    if not items:
        return f"Aucun dossier législatif trouvé pour la législature {legislature_id} (type: {type_dossier})."
    lines = [f"**{len(items)} dossier(s)** — législature {legislature_id} / {type_dossier}\n"]
    for d in items:
        titre = d.get("titre", "Sans titre")
        rid   = d.get("id", "")
        type_d = d.get("type", "")
        line  = f"- **{titre}**"
        if type_d: line += f" ({type_d})"
        if rid:    line += f" — `{rid}`"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="legifrance_lister_debats_parlementaires",
    description=(
        "Liste les débats parlementaires disponibles dans Légifrance. "
        "Couvre les comptes-rendus de l'Assemblée Nationale (AN) et du Sénat."
    ),
    parameters={
        "type": "object",
        "properties": {
            "types_publication": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Types de publication (ex: ['AN'] pour Assemblée Nationale, ['SENAT'] pour Sénat)",
            },
            "date_parution": {
                "type": "string",
                "description": "Date de parution au format YYYY-MM-DD (optionnel)",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_lister_debats_parlementaires(
    types_publication: Optional[List[str]] = None,
    date_parution: Optional[str] = None,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"pageNumber": 1, "pageSize": nb_resultats}
    if types_publication:
        body["typesPublication"] = types_publication
    if date_parution:
        body["dateParution"] = date_parution
    data  = c._req("/list/debatsParlementaires", body=body)
    # DebatsParlementairesListResponse → results (swagger)
    # Debat : dateParution, dateSeance, typeAssemblee, id, legislature
    items = data.get("results", [])
    if not items:
        return "Aucun débat parlementaire trouvé."
    total = data.get("totalResultNumber", len(items))
    lines = [f"**{total} débat(s)** — {len(items)} affiché(s)\n"]
    for d in items:
        date_s    = d.get("dateSeance", d.get("dateParution", ""))
        assemblee = d.get("typeAssemblee", "")  # typeAssemblee (pas typeParlement)
        rid       = d.get("id", "")
        line      = f"- **{date_s or rid}**"
        if assemblee: line += f" ({assemblee})"
        if rid:       line += f" — `{rid}`"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="legifrance_lister_questions_parlementaires",
    description=(
        "Liste les questions écrites parlementaires (questions de députés ou sénateurs "
        "aux ministres) disponibles dans Légifrance."
    ),
    parameters={
        "type": "object",
        "properties": {
            "parlement_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Types de parlement (ex: ['AN'] pour Assemblée Nationale, ['SENAT'])",
            },
            "periode_publication": {
                "type": "string",
                "description": "Période de publication (optionnel, ex: '01/01/2024 > 31/12/2024')",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_lister_questions_parlementaires(
    parlement_types: Optional[List[str]] = None,
    periode_publication: Optional[str] = None,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"pageNumber": 1, "pageSize": nb_resultats}
    if parlement_types:
        body["parlementTypes"] = parlement_types
    if periode_publication:
        body["periodePublication"] = periode_publication
    data  = c._req("/list/questionsEcritesParlementaires", body=body)
    # QuestionsEcritesParlementairesListResponse → results (swagger)
    # EsQuestionsEcritesParlementaires : emetteur, dateParution, id, url, origine
    items = data.get("results", [])
    if not items:
        return "Aucune question parlementaire trouvée."
    total = data.get("totalResultNumber", len(items))
    lines = [f"**{total} question(s) parlementaire(s)** — {len(items)} affiché(e)(s)\n"]
    for q in items:
        emetteur = q.get("emetteur", "")
        date_p   = q.get("dateParution", "")
        rid      = q.get("id", "")
        line     = f"- **{emetteur or rid}**"
        if date_p: line += f" — {date_p}"
        if rid:
            line += f" — `{rid}`"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="legifrance_lister_bocc",
    description=(
        "Liste les Bulletins Officiels des Conventions Collectives (BOCC). "
        "Le BOCC publie les textes des accords collectifs et avenants."
    ),
    parameters={
        "type": "object",
        "properties": {
            "interval_publication": {
                "type": "string",
                "description": "Intervalle de publication (ex: '01/01/2024 > 31/03/2024')",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_lister_bocc(
    interval_publication: Optional[str] = None,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"pageNumber": 1, "pageSize": nb_resultats}
    if interval_publication:
        body["intervalPublication"] = interval_publication
    data  = c._req("/list/bocc", body=body)
    # BoccGlobalListResponse → results (swagger)
    # EsParutionBocc : id, refInjection, globalBocc, texts
    items = data.get("results", [])
    if not items:
        return "Aucun BOCC trouvé."
    total = data.get("totalResultNumber", len(items))
    lines = [f"**{total} BOCC** — {len(items)} affiché(s)\n"]
    for b in items:
        rid  = b.get("id", "")
        glob = b.get("globalBocc") or {}
        num  = glob.get("numero", glob.get("num", ""))
        line = f"- **BOCC {num or rid}**"
        if rid: line += f" — `{rid}`"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="legifrance_lister_bocc_textes",
    description=(
        "Liste les textes d'un numéro de BOCC donné. "
        "Filtrable par IDCC pour voir les accords d'une convention collective spécifique."
    ),
    parameters={
        "type": "object",
        "properties": {
            "bocc_id": {
                "type": "string",
                "description": "Identifiant du BOCC principal",
            },
            "idccs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste d'IDCC pour filtrer (ex: ['0016', '1486'])",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_lister_bocc_textes(
    bocc_id: Optional[str] = None,
    idccs: Optional[List[str]] = None,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"pageNumber": 1, "pageSize": nb_resultats}
    if bocc_id:
        body["idMainBocc"] = bocc_id
    if idccs:
        body["idccs"] = idccs
    data  = c._req("/list/boccTexts", body=body)
    # BoccTextsListResponse → texts, totalResultNumber (swagger)
    # EsTextBocc : title, idccs, department, enteteTitle
    items = data.get("texts", [])
    if not items:
        return "Aucun texte BOCC trouvé."
    total = data.get("totalResultNumber", len(items))
    lines = [f"**{total} texte(s) BOCC** — {len(items)} affiché(s)\n"]
    for t in items:
        titre = t.get("title", t.get("enteteTitle", "Sans titre"))
        idccs = t.get("idccs", [])
        idcc_str = ", ".join(str(i) for i in idccs[:3]) if idccs else ""
        line  = f"- **{titre}**"
        if idcc_str: line += f" (IDCC {idcc_str})"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="legifrance_lister_boccs_et_textes",
    description=(
        "Recherche combinée dans les BOCCs et leurs textes associés. "
        "Filtrable par titre de convention ou par numéro IDCC."
    ),
    parameters={
        "type": "object",
        "properties": {
            "idcc": {
                "type": "string",
                "description": "Numéro IDCC (ex: '0016')",
            },
            "titre": {
                "type": "string",
                "description": "Texte à rechercher dans les titres",
            },
            "interval_publication": {
                "type": "string",
                "description": "Intervalle de publication (ex: '01/01/2024 > 31/12/2024')",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_lister_boccs_et_textes(
    idcc: Optional[str] = None,
    titre: Optional[str] = None,
    interval_publication: Optional[str] = None,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"pageNumber": 1, "pageSize": nb_resultats}
    if idcc:
        body["idcc"] = idcc
    if titre:
        body["titre"] = titre
    if interval_publication:
        body["intervalPublication"] = interval_publication
    data  = c._req("/list/boccsAndTexts", body=body)
    # BoccGlobalListResponse → results (swagger)
    items = data.get("results", [])
    if not items:
        return "Aucun résultat BOCC/texte trouvé."
    total = data.get("totalResultNumber", len(items))
    lines = [f"**{total} résultat(s)** — {len(items)} affiché(s)\n"]
    for t in items:
        titre_item = t.get("titre", t.get("title", "Sans titre"))
        idcc_item  = t.get("idcc", "")
        date_p     = t.get("datePublication", t.get("date", ""))
        rid        = t.get("id", "")
        line       = f"- **{titre_item}**"
        if idcc_item:
            line += f" (IDCC {idcc_item})"
        if date_p:
            line += f" — {date_p}"
        if rid:
            line += f" — `{rid}`"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="legifrance_lister_docs_admins",
    description=(
        "Liste les documents administratifs disponibles dans Légifrance pour une ou plusieurs années. "
        "Retourne les bulletins officiels et documents administratifs publiés."
    ),
    parameters={
        "type": "object",
        "properties": {
            "annees": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Liste d'années à rechercher (ex: [2023, 2024])",
            },
        },
    },
)
def legifrance_lister_docs_admins(annees: Optional[List[int]] = None) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {}
    if annees:
        body["years"] = annees
    data  = c._req("/list/docsAdmins", body=body)
    # DocsAdminsListResponse → results (swagger)
    items = data.get("results", [])
    if not items:
        return "Aucun document administratif trouvé."
    lines = [f"**{len(items)} document(s) administratif(s)**\n"]
    for d in items:
        titre = d.get("titre", d.get("title", "Sans titre"))
        annee = d.get("annee", d.get("year", ""))
        rid   = d.get("id", "")
        line  = f"- **{titre}**"
        if annee:
            line += f" ({annee})"
        if rid:
            line += f" — `{rid}`"
        lines.append(line)
    return "\n".join(lines)


# ===========================================================================
# OUTILS SUGGEST — Suggestions complémentaires
# ===========================================================================

@tool(
    name="legifrance_suggerer_acco",
    description=(
        "Suggestions de SIRET et raisons sociales pour les accords d'entreprise. "
        "Utile pour identifier une entreprise avant de rechercher ses accords."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texte": {
                "type": "string",
                "description": "Début de la raison sociale ou numéro SIRET (ex: 'Renault', 'Airbus', '351')",
            },
        },
        "required": ["texte"],
    },
)
def legifrance_suggerer_acco(texte: str) -> str:
    c    = _get_client()
    data = c._req("/suggest/acco", body={"searchText": texte})
    # SuggestAccoResponse → results (swagger)
    results = data.get("results", {})
    if not results:
        return f"Aucune suggestion entreprise pour : « {texte} »"
    lines = [f"**Entreprises suggérées pour « {texte} »**\n"]
    items = results if isinstance(results, list) else []
    for s in items[:15]:
        rs    = s.get("raisonSociale", s.get("title", str(s)))
        siret = s.get("siret", "")
        lines.append(f"- **{rs}**" + (f" (SIRET : {siret})" if siret else ""))
    return "\n".join(lines)


@tool(
    name="legifrance_suggerer_pdc",
    description=(
        "Suggestions de libellés pour le plan de classement (PDC) de Légifrance. "
        "Utile pour naviguer dans l'arborescence thématique avant une recherche avancée."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texte": {
                "type": "string",
                "description": "Terme à compléter dans le plan de classement (ex: 'contrat de travail', 'bail')",
            },
            "fond": {
                "type": "string",
                "description": "Fond à interroger (optionnel, ex: 'JURI', 'LODA')",
            },
        },
        "required": ["texte"],
    },
)
def legifrance_suggerer_pdc(texte: str, fond: Optional[str] = None) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"searchText": texte}
    if fond:
        body["fond"] = fond
    data = c._req("/suggest/pdc", body=body)
    # SuggestResponse → results (object dict fonds→liste) (swagger)
    results = data.get("results", {})
    if not results:
        return f"Aucune suggestion de plan de classement pour : « {texte} »"
    lines = [f"**Plan de classement — suggestions pour « {texte} »**\n"]
    if isinstance(results, dict):
        for fond_k, items in list(results.items())[:5]:
            for s in (items if isinstance(items, list) else [])[:5]:
                libelle = s.get("libelle", s.get("title", str(s)))
                rid     = s.get("id", "")
                lines.append(f"- [{fond_k}] {libelle}" + (f" (`{rid}`)" if rid else ""))
    return "\n".join(lines)


# ===========================================================================
# OUTILS MISC — Services utilitaires
# ===========================================================================

@tool(
    name="legifrance_dates_sans_jo",
    description=(
        "Retourne la liste des dates où aucun Journal Officiel n'a été publié. "
        "Utile pour vérifier si une date particulière est un jour de parution du JO."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
)
def legifrance_dates_sans_jo() -> str:
    c     = _get_client()
    data  = c._req("/misc/datesWithoutJo", method="GET")
    # DatesWithNoJoResponse → lstDateDisabled (swagger)
    dates = data.get("lstDateDisabled", [])
    if not dates:
        return "Aucune date sans JO trouvée (ou liste indisponible)."
    lines = [f"**{len(dates)} date(s) sans Journal Officiel**\n"]
    for d in dates[:50]:
        if isinstance(d, str):
            lines.append(f"- {d}")
        elif isinstance(d, dict):
            lines.append(f"- {d.get('date', str(d))}")
    if len(dates) > 50:
        lines.append(f"\n*… {len(dates)-50} date(s) supplémentaire(s)*")
    return "\n".join(lines)


@tool(
    name="legifrance_annees_sans_table",
    description=(
        "Retourne la liste des années pour lesquelles aucune table annuelle du JO n'est disponible. "
        "La table annuelle recense tous les textes publiés au JO pour une année donnée."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
)
def legifrance_annees_sans_table() -> str:
    c      = _get_client()
    data   = c._req("/misc/yearsWithoutTable", method="GET")
    # YearsWithNoTableResponse → lstYearDisabled (swagger)
    annees = data.get("lstYearDisabled", [])
    if not annees:
        return "Aucune année sans table trouvée (ou liste indisponible)."
    lines = [f"**{len(annees)} année(s) sans table annuelle du JO**\n"]
    for a in annees:
        lines.append(f"- {a}")
    return "\n".join(lines)


# ===========================================================================
# OUTILS MISC — Versioning
# ===========================================================================

@tool(
    name="legifrance_commit_id",
    description=(
        "Retourne les informations de déploiement et de versioning de l'API Légifrance. "
        "Utile pour connaître la version exacte de l'API en cours d'utilisation."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
)
def legifrance_commit_id() -> str:
    c    = _get_client()
    data = c._req("/misc/commitId", method="GET")
    if not data:
        return "Informations de version indisponibles."
    lines = ["**Informations de version de l'API Légifrance**\n"]
    for k, v in data.items():
        if v:
            lines.append(f"- **{k}** : {v}")
    return "\n".join(lines) if len(lines) > 1 else "Aucune information de version disponible."


# ===========================================================================
# OUTILS LIST — BODMR
# ===========================================================================

@tool(
    name="legifrance_lister_bodmr",
    description=(
        "Liste les Bulletins Officiels des Décorations, Médailles et Récompenses (BODMR). "
        "Filtrable par années et triable."
    ),
    parameters={
        "type": "object",
        "properties": {
            "annees": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Années à filtrer (optionnel, ex: [2023, 2024])",
            },
            "nb_resultats": {
                "type": "integer",
                "default": 20,
                "description": "Nombre de résultats (défaut: 20)",
            },
        },
    },
)
def legifrance_lister_bodmr(
    annees: Optional[List[int]] = None,
    nb_resultats: int = 20,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"pageNumber": 1, "pageSize": nb_resultats}
    if annees:
        body["years"] = annees
    data  = c._req("/list/bodmr", body=body)
    # BodmrListResponse → results (swagger), Bodmr : id, texts, refInjection
    items = data.get("results", [])
    if not items:
        return "Aucun BODMR trouvé."
    total = data.get("totalResultNumber", len(items))
    lines = [f"**{total} BODMR** — {len(items)} affiché(s)\n"]
    for b in items:
        rid   = b.get("id", "")
        nb_t  = len(b.get("texts", []))
        line  = f"- `{rid}`"
        if nb_t: line += f" ({nb_t} texte(s))"
        lines.append(line)
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Codes (compléments)
# ===========================================================================

@tool(
    name="legifrance_code_complet",
    description=(
        "Récupère le contenu complet d'un code juridique (articles inclus) à une date donnée. "
        "Contrairement à legifrance_consulter_code qui retourne uniquement la table des matières, "
        "cet outil retourne le texte intégral avec les articles. "
        "Attention : les codes volumineux peuvent retourner un résultat tronqué."
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Nom du code (civil, penal, travail, commerce…) "
                    "ou directement un ID Légifrance (LEGITEXT...)."
                ),
            },
            "date": {
                "type": "string",
                "description": "Date de consultation YYYY-MM-DD (défaut: aujourd'hui)",
            },
        },
        "required": ["code"],
    },
)
def legifrance_code_complet(code: str, date: Optional[str] = None) -> str:
    c = _get_client()
    try:
        tid = c.resolve_code(code)
    except ValueError as e:
        return str(e)
    data    = c._req("/consult/code", body={
        "textId": tid,
        "date":   date or globals()["date"].today().isoformat(),
    })
    # ConsultTextResponse → title (swagger)
    titre   = data.get("title", code)  # clé réelle : title
    lines   = [f"# {titre}\n"]
    articles = data.get("articles", data.get("sections", []))
    if articles:
        lines.append(f"**{len(articles)} article(s)/section(s)**\n")
        for a in articles[:30]:
            lines.append(_fmt_article(a))
            lines.append("")
        if len(articles) > 30:
            lines.append(f"*… {len(articles)-30} élément(s) supplémentaire(s) — utilisez legifrance_obtenir_article pour accéder aux articles individuels*")
    else:
        lines.append("*(contenu non disponible — utilisez legifrance_consulter_code pour la table des matières)*")
    return "\n".join(lines)


@tool(
    name="legifrance_code_par_ancien_id",
    description=(
        "Récupère le contenu d'un code juridique par son ancien identifiant Légifrance. "
        "Utile pour accéder à des codes référencés avec des identifiants obsolètes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ancien_id": {
                "type": "string",
                "description": "Ancien identifiant du code",
            },
        },
        "required": ["ancien_id"],
    },
)
def legifrance_code_par_ancien_id(ancien_id: str) -> str:
    c    = _get_client()
    data = c._req("/consult/getCodeWithAncienId", body={"ancienId": ancien_id})
    return _fmt_toc(data, ancien_id)


@tool(
    name="legifrance_article_par_eli",
    description=(
        "Récupère un article juridique par son identifiant ELI (European Legislation Identifier) "
        "ou son alias. "
        "Exemple d'ELI : '/eli/decret/2021/7/13/PRMD2117108D/jo/article_1'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id_eli_ou_alias": {
                "type": "string",
                "description": "Identifiant ELI ou alias de l'article",
            },
        },
        "required": ["id_eli_ou_alias"],
    },
)
def legifrance_article_par_eli(id_eli_ou_alias: str) -> str:
    c    = _get_client()
    data = c._req("/consult/getArticleWithIdEliOrAlias", body={"idEliOrAlias": id_eli_ou_alias})
    return _fmt_article(data)


@tool(
    name="legifrance_articles_meme_numero",
    description=(
        "Récupère la liste des articles qui ont eu le même numéro qu'un article donné "
        "au sein d'un texte. Utile pour retracer les renumérotations d'articles."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_cid": {
                "type": "string",
                "description": "CID de l'article de référence",
            },
            "article_num": {
                "type": "string",
                "description": "Numéro de l'article (ex: '1382', 'L1234-5')",
            },
            "text_cid": {
                "type": "string",
                "description": "CID du texte contenant l'article",
            },
            "date": {
                "type": "string",
                "description": "Date de référence au format YYYY-MM-DD",
            },
        },
        "required": ["article_cid", "article_num", "text_cid", "date"],
    },
)
def legifrance_articles_meme_numero(
    article_cid: str,
    article_num: str,
    text_cid: str,
    date: str,
) -> str:
    c    = _get_client()
    data = c._req("/consult/sameNumArticle", body={
        "articleCid": article_cid,
        "articleNum": article_num,
        "textCid":    text_cid,
        "date":       date,
    })
    # SectionsRevisionArticleResponse → newTexts, oldTexts (swagger)
    # ArticleDTO : name, cid, nature, dateDebut, dateFin, id, modifications
    new_texts = data.get("newTexts", [])
    old_texts = data.get("oldTexts", [])
    all_arts  = new_texts + old_texts
    if not all_arts:
        return f"Aucun autre article avec le numéro '{article_num}' trouvé."
    lines = [f"**{len(all_arts)} article(s)** : {len(new_texts)} nouveau(x), {len(old_texts)} ancien(s)\n"]
    for label, lst in [("Nouveau", new_texts), ("Ancien", old_texts)]:
        for a in lst:
            name  = a.get("name", "")
            cid   = a.get("cid", a.get("id", ""))
            debut = a.get("dateDebut", "")
            lines.append(f"- [{label}] **{name}**" + (f" `{cid}`" if cid else "") + (f" ({debut})" if debut else ""))
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Liens d'articles
# ===========================================================================

@tool(
    name="legifrance_liens_concordance",
    description=(
        "Récupère les liens de concordance d'un article juridique : "
        "autres textes ou articles qui font référence à cet article ou lui sont liés thématiquement."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_id": {
                "type": "string",
                "description": "Identifiant de l'article (ex: LEGIARTI000006436298)",
            },
        },
        "required": ["article_id"],
    },
)
def legifrance_liens_concordance(article_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/concordanceLinksArticle", body={"articleId": article_id})
    # SectionsRevisionArticleResponse → newTexts, oldTexts (swagger)
    new_texts = data.get("newTexts", [])
    old_texts = data.get("oldTexts", [])
    if not new_texts and not old_texts:
        return f"Aucun lien de concordance trouvé pour l'article `{article_id}`."
    lines = [f"**Concordances** : {len(new_texts)} nouveau(x), {len(old_texts)} ancien(s) pour `{article_id}`\n"]
    for label, lst in [("Nouveau", new_texts), ("Ancien", old_texts)]:
        for t in lst:
            name = t.get("name", "")
            nat  = t.get("nature", "")
            cid  = t.get("cid", t.get("id", ""))
            lines.append(f"- [{label}] **{name}**" + (f" ({nat})" if nat else "") + (f" — `{cid}`" if cid else ""))
    return "\n".join(lines)


@tool(
    name="legifrance_liens_relatifs",
    description=(
        "Récupère les liens relatifs d'un article juridique : "
        "textes modificateurs, textes modifiés, citations et références croisées."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_id": {
                "type": "string",
                "description": "Identifiant de l'article (ex: LEGIARTI000006436298)",
            },
        },
        "required": ["article_id"],
    },
)
def legifrance_liens_relatifs(article_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/relatedLinksArticle", body={"articleId": article_id})
    # RelatedLinksArticleResponse → liensCite, liensCitePar (swagger)
    # LiensRelatifsDTO : cidText, id, cidParent, dateVigeur, nature, name
    cites     = data.get("liensCite", [])
    cites_par = data.get("liensCitePar", [])
    if not cites and not cites_par:
        return f"Aucun lien relatif trouvé pour `{article_id}`."
    lines = [f"**Liens relatifs** : {len(cites)} cité(s), {len(cites_par)} cité par\n"]
    for label, lst in [("Cité", cites), ("Cité par", cites_par)]:
        for l in lst:
            name = l.get("name", "")
            nat  = l.get("nature", "")
            cid  = l.get("cidText", l.get("id", ""))
            lines.append(f"- [{label}] **{name}**" + (f" ({nat})" if nat else "") + (f" — `{cid}`" if cid else ""))
    return "\n".join(lines)


@tool(
    name="legifrance_liens_service_public",
    description=(
        "Récupère les liens vers service-public.fr associés à un article juridique. "
        "Permet de trouver les fiches pratiques correspondant à un article de loi."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_cid": {
                "type": "string",
                "description": "CID de l'article (optionnel)",
            },
            "fond": {
                "type": "string",
                "description": "Fond de consultation (optionnel, ex: 'JORF', 'CODE_DATE')",
            },
        },
    },
)
def legifrance_liens_service_public(
    article_cid: Optional[str] = None,
    fond: Optional[str] = None,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {}
    if article_cid:
        body["articleCid"] = article_cid
    if fond:
        body["fond"] = fond
    data  = c._req("/consult/servicePublicLinksArticle", body=body)
    # ServicePublicLinksArticleResponse → liensSP (object) (swagger)
    liens = data.get("liensSP", {})
    if not liens:
        return "Aucun lien service-public trouvé."
    lines = ["**Liens service-public.fr**\n"]
    if isinstance(liens, dict):
        for k, v in list(liens.items())[:20]:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


@tool(
    name="legifrance_a_liens_service_public",
    description=(
        "Vérifie quels articles parmi une liste possèdent des liens vers service-public.fr. "
        "Utile pour filtrer rapidement un ensemble d'articles avant d'appeler legifrance_liens_service_public."
    ),
    parameters={
        "type": "object",
        "properties": {
            "article_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste d'identifiants d'articles à vérifier",
            },
        },
        "required": ["article_ids"],
    },
)
def legifrance_a_liens_service_public(article_ids: List[str]) -> str:
    c    = _get_client()
    data = c._req("/consult/hasServicePublicLinksArticle", body={"ids": article_ids})
    avec = data.get("ids", data.get("results", data.get("articleIds", [])))
    if not avec:
        return "Aucun des articles fournis ne possède de liens service-public."
    lines = [f"**{len(avec)}/{len(article_ids)} article(s) avec liens service-public**\n"]
    for rid in avec:
        lines.append(f"- `{rid}`")
    sans = [i for i in article_ids if i not in avec]
    if sans:
        lines.append(f"\n*Sans lien : {', '.join(f'`{i}`' for i in sans)}*")
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — JORF (compléments)
# ===========================================================================

@tool(
    name="legifrance_jorf_part",
    description=(
        "Consulte la partie d'un texte publié au Journal Officiel (JORF) par son CID. "
        "Complémentaire de legifrance_jorf — retourne la structure en parties du texte."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_cid": {
                "type": "string",
                "description": "CID du texte JORF (ex: JORFTEXT000000000001)",
            },
        },
        "required": ["text_cid"],
    },
)
def legifrance_jorf_part(text_cid: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/jorfPart", body={"textCid": text_cid})
    # ConsultJorfResponse → title, dateParution, nor, sections, articles (swagger)
    titre  = data.get("title", text_cid)
    date_p = data.get("dateParution", "")
    nor    = data.get("nor", "")
    lines  = [f"# {titre}\n"]
    if date_p: lines.append(f"**Publication JO** : {date_p}")
    if nor:    lines.append(f"**NOR** : {nor}")
    sects = data.get("sections", [])
    arts  = data.get("articles", [])
    nb    = len(sects) + len(arts)
    if nb: lines.append(f"\n**{nb} section(s)/article(s)**\n")
    for s in (sects + arts)[:20]:
        t = s.get("title", s.get("titre", s.get("num", "")))
        if t: lines.append(f"- {t}")
    return "\n".join(lines)


@tool(
    name="legifrance_eli_alias_texte",
    description=(
        "Récupère un texte du Journal Officiel par son identifiant ELI "
        "(European Legislation Identifier) ou son alias. "
        "Exemple : '/eli/loi/2021/8/10/PRMD2117108L/jo/texte'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id_eli_ou_alias": {
                "type": "string",
                "description": "Identifiant ELI ou alias du texte",
            },
        },
        "required": ["id_eli_ou_alias"],
    },
)
def legifrance_eli_alias_texte(id_eli_ou_alias: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/eliAndAliasRedirectionTexte", body={"idEliOrAlias": id_eli_ou_alias})
    # ConsultJorfResponse → title, dateParution, nor, cid (swagger)
    titre  = data.get("title", id_eli_ou_alias)
    date_p = data.get("dateParution", "")
    nor    = data.get("nor", "")
    cid    = data.get("cid", "")
    lines  = [f"# {titre}\n"]
    if date_p: lines.append(f"**Publication JO** : {date_p}")
    if nor:    lines.append(f"**NOR** : {nor}")
    if cid:    lines.append(f"**CID** : `{cid}`")
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — KALI (compléments)
# ===========================================================================

@tool(
    name="legifrance_convention_cont",
    description=(
        "Consulte le conteneur principal d'une convention collective par son identifiant KALI "
        "(format KALICONT...). Différent de legifrance_convention_par_idcc qui utilise le numéro IDCC."
    ),
    parameters={
        "type": "object",
        "properties": {
            "cont_id": {
                "type": "string",
                "description": "Identifiant du conteneur KALI (ex: KALICONT000005635370)",
            },
        },
        "required": ["cont_id"],
    },
)
def legifrance_convention_cont(cont_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/kaliCont", body={"id": cont_id})
    # ConsultKaliContResponse → titre, id, num, nature, sections (swagger)
    titre   = data.get("titre", cont_id)  # clé réelle : titre (pas title)
    num     = data.get("num", "")
    nature  = data.get("nature", "")
    sections = data.get("sections", [])
    lines   = [f"# {titre}\n"]
    if num:    lines.append(f"**Numéro** : {num}")
    if nature: lines.append(f"**Nature** : {nature}")
    if sections:
        lines.append(f"\n**{len(sections)} section(s)**")
        for s in sections[:20]:
            t = s.get("titre", s.get("title", s.get("num", "")))
            rid = s.get("id", "")
            if t:
                lines.append(f"  - {t}" + (f" (`{rid}`)" if rid else ""))
        if len(sections) > 20:
            lines.append(f"  *… {len(sections)-20} élément(s) supplémentaire(s)*")
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Jurisprudence (compléments)
# ===========================================================================

@tool(
    name="legifrance_jurisprudence_ancien_id",
    description=(
        "Consulte une décision de jurisprudence par son ancien identifiant Légifrance. "
        "Utile pour accéder à des décisions référencées avec des identifiants obsolètes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ancien_id": {
                "type": "string",
                "description": "Ancien identifiant de la décision de jurisprudence",
            },
        },
        "required": ["ancien_id"],
    },
)
def legifrance_jurisprudence_ancien_id(ancien_id: str) -> str:
    c     = _get_client()
    data  = c._req("/consult/getJuriWithAncienId", body={"ancienId": ancien_id})
    # ConsultJuriTextResponse → text (list[TexteSimple]) (swagger)
    txt   = data.get("text") or [{}]
    txt   = txt[0] if isinstance(txt, list) else txt
    titre = txt.get("titre", ancien_id)
    juri  = txt.get("juridiction", "")
    dt    = txt.get("dateTexte", "")
    texte = _strip_html(txt.get("texteHtml", txt.get("texte", "")))
    lines = [f"# {titre}\n"]
    if juri:  lines.append(f"**Juridiction** : {juri}")
    if dt:    lines.append(f"**Date** : {dt}")
    if texte:
        lines.append(f"\n{texte[:5000]}")
        if len(texte) > 5000:
            lines.append("\n*[Texte tronqué]*")
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — CNIL (compléments)
# ===========================================================================

@tool(
    name="legifrance_cnil_ancien_id",
    description=(
        "Consulte une décision ou délibération de la CNIL par son ancien identifiant. "
        "Utile pour accéder à des décisions CNIL référencées avec des identifiants obsolètes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ancien_id": {
                "type": "string",
                "description": "Ancien identifiant de la décision CNIL",
            },
        },
        "required": ["ancien_id"],
    },
)
def legifrance_cnil_ancien_id(ancien_id: str) -> str:
    c     = _get_client()
    data   = c._req("/consult/getCnilWithAncienId", body={"ancienId": ancien_id})
    # ConsultCnilTextResponse → text (list[TexteSimple]) (swagger)
    txt    = data.get("text") or [{}]
    txt    = txt[0] if isinstance(txt, list) else txt
    titre  = txt.get("titre", ancien_id)
    date_d = txt.get("dateTexte", "")
    texte  = _strip_html(txt.get("texteHtml", txt.get("texte", "")))
    lines  = [f"# {titre}\n"]
    if date_d:
        lines.append(f"**Date** : {date_d}")
    if texte:
        lines.append(f"\n{texte[:5000]}")
        if len(texte) > 5000:
            lines.append("\n*[Texte tronqué]*")
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Fonds LEGI
# ===========================================================================

@tool(
    name="legifrance_legi_part",
    description=(
        "Consulte le contenu d'un texte du fonds LEGI (législation consolidée) par son identifiant. "
        "Retourne la partie du texte demandée avec ses articles."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text_id": {
                "type": "string",
                "description": "Identifiant du texte LEGI (ex: LEGITEXT000006070721)",
            },
            "date": {
                "type": "string",
                "description": "Date de consultation YYYY-MM-DD (défaut: aujourd'hui)",
            },
        },
        "required": ["text_id"],
    },
)
def legifrance_legi_part(text_id: str, date: Optional[str] = None) -> str:
    c    = _get_client()
    data = c._req("/consult/legiPart", body={
        "textId": text_id,
        "date":   date or globals()["date"].today().isoformat(),
    })
    # ConsultTextResponse → title, etat, dateParution, articles, sections (swagger)
    titre   = data.get("title", text_id)   # clé réelle : title (pas titre)
    lines   = [f"# {titre}\n"]
    etat    = data.get("etat", "")
    date_p  = data.get("dateParution", "")  # dateParution (pas dateDebut)
    if etat:
        lines.append(f"**État** : {etat}")
    if date_p:
        lines.append(f"**Date de parution** : {date_p}")
    articles = data.get("articles", data.get("sections", []))
    if articles:
        lines.append(f"\n**{len(articles)} article(s)/section(s)**\n")
        for a in articles[:30]:
            lines.append(_fmt_article(a))
            lines.append("")
        if len(articles) > 30:
            lines.append(f"*… {len(articles)-30} élément(s) supplémentaire(s)*")
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Tables annuelles
# ===========================================================================

@tool(
    name="legifrance_tables_annuelles",
    description=(
        "Récupère la liste des tables annuelles du Journal Officiel disponibles dans Légifrance. "
        "Les tables annuelles recensent tous les textes publiés au JO pour une période donnée. "
        "Utilisez legifrance_annees_sans_table pour connaître les années sans table disponible."
    ),
    parameters={
        "type": "object",
        "properties": {
            "annee_fin": {
                "type": "integer",
                "description": "Année de fin de la période (ex: 2024)",
            },
            "annee_debut": {
                "type": "integer",
                "description": "Année de début de la période (optionnel)",
            },
        },
        "required": ["annee_fin"],
    },
)
def legifrance_tables_annuelles(
    annee_fin: int,
    annee_debut: Optional[int] = None,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {"endYear": annee_fin}
    if annee_debut is not None:
        body["startYear"] = annee_debut
    data  = c._req("/consult/getTables", body=body)
    # GetTableResponse → tables, totalNbResult (swagger)
    items = data.get("tables", [])
    if not items:
        periode = f"{annee_debut}–{annee_fin}" if annee_debut else str(annee_fin)
        return f"Aucune table annuelle trouvée pour la période {periode}."
    lines = [f"**{len(items)} table(s) annuelle(s)**\n"]
    for t in items:
        annee = t.get("annee", t.get("year", ""))
        titre = t.get("titre", t.get("title", ""))
        rid   = t.get("id", "")
        line  = f"- **{annee}**"
        if titre:
            line += f" — {titre}"
        if rid:
            line += f" — `{rid}`"
        lines.append(line)
    return "\n".join(lines)


# ===========================================================================
# OUTILS CONSULT — Métadonnées BOCC
# ===========================================================================

@tool(
    name="legifrance_bocc_pdf_metadata",
    description=(
        "Récupère les métadonnées du PDF associé à un texte unitaire du BOCC "
        "(Bulletin Officiel des Conventions Collectives). "
        "Utile pour accéder au fichier PDF original d'un accord publié au BOCC."
    ),
    parameters={
        "type": "object",
        "properties": {
            "bocc_id": {
                "type": "string",
                "description": "Identifiant du texte BOCC (optionnel)",
            },
            "pour_bocc_global": {
                "type": "boolean",
                "description": "True pour cibler le BOCC global plutôt qu'un texte unitaire (optionnel)",
            },
        },
    },
)
def legifrance_bocc_pdf_metadata(
    bocc_id: Optional[str] = None,
    pour_bocc_global: Optional[bool] = None,
) -> str:
    c    = _get_client()
    body: Dict[str, Any] = {}
    if bocc_id:
        body["id"] = bocc_id
    if pour_bocc_global is not None:
        body["forGlobalBocc"] = pour_bocc_global
    data = c._req("/consult/getBoccTextPdfMetadata", body=body)
    if not data:
        return "Aucune métadonnée PDF BOCC trouvée."
    lines = ["**Métadonnées PDF BOCC**\n"]
    for k, v in data.items():
        if v:
            lines.append(f"- **{k}** : {v}")
    return "\n".join(lines) if len(lines) > 1 else "Aucune métadonnée disponible."


# ---------------------------------------------------------------------------
# Confirmation de chargement
# ---------------------------------------------------------------------------
_tools_count = sum(1 for name in [
    # Recherche
    "legifrance_rechercher", "legifrance_version_canonique_article",
    "legifrance_version_canonique", "legifrance_version_proche",
    # Consultation codes/lois
    "legifrance_consulter_code", "legifrance_obtenir_article",
    "legifrance_article_par_numero", "legifrance_versions_article",
    "legifrance_loi_decret", "legifrance_jorf",
    "legifrance_jo_par_nor", "legifrance_derniers_jo", "legifrance_sommaire_jorf",
    # KALI
    "legifrance_convention_par_idcc", "legifrance_convention_texte",
    "legifrance_convention_article", "legifrance_convention_section",
    # Jurisprudence
    "legifrance_jurisprudence", "legifrance_jurisprudence_plan_classement",
    # Divers
    "legifrance_cnil", "legifrance_acco", "legifrance_circulaire",
    "legifrance_debat", "legifrance_dossier_legislatif", "legifrance_section_par_cid",
    # Chrono
    "legifrance_historique_texte", "legifrance_versions_element", "legifrance_a_des_versions",
    # List
    "legifrance_lister_codes", "legifrance_conventions", "legifrance_lister_loda",
    "legifrance_lister_legislatures", "legifrance_lister_dossiers_legislatifs",
    "legifrance_lister_debats_parlementaires", "legifrance_lister_questions_parlementaires",
    "legifrance_lister_bocc", "legifrance_lister_bocc_textes",
    "legifrance_lister_boccs_et_textes", "legifrance_lister_docs_admins",
    # Suggest
    "legifrance_suggerer", "legifrance_suggerer_acco", "legifrance_suggerer_pdc",
    # Misc
    "legifrance_dates_sans_jo", "legifrance_annees_sans_table",
    "legifrance_commit_id",
    # List (nouveau)
    "legifrance_lister_bodmr",
    # Consult — codes (nouveaux)
    "legifrance_code_complet", "legifrance_code_par_ancien_id",
    "legifrance_article_par_eli", "legifrance_articles_meme_numero",
    # Consult — liens d'articles (nouveaux)
    "legifrance_liens_concordance", "legifrance_liens_relatifs",
    "legifrance_liens_service_public", "legifrance_a_liens_service_public",
    # Consult — JORF (nouveaux)
    "legifrance_jorf_part", "legifrance_eli_alias_texte",
    # Consult — KALI (nouveau)
    "legifrance_convention_cont",
    # Consult — JURI (nouveau)
    "legifrance_jurisprudence_ancien_id",
    # Consult — CNIL (nouveau)
    "legifrance_cnil_ancien_id",
    # Consult — LEGI (nouveau)
    "legifrance_legi_part",
    # Consult — tables annuelles (nouveau)
    "legifrance_tables_annuelles",
    # Consult — BOCC métadonnées (nouveau)
    "legifrance_bocc_pdf_metadata",
])
logger.info(f"✅ tools.legifrance_tools : {_tools_count} outils enregistrés dans Prométhée")
