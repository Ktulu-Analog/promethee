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
tools/web_tools.py — Navigation, scraping et recherche web
===========================================================

Outils exposés (12) :

  Recherche (4) :
    - web_search        : recherche multi-moteurs (DDG ou SearXNG auto-hébergé)
                          avec résultats filtrables par date, domaine, langue
    - web_search_news   : recherche d'actualités récentes (dernières 24h/semaine/mois)
    - web_image_search  : recherche d'images (URLs directes + miniatures)
    - web_search_engine : retourne la configuration du moteur actif

  Lecture de pages (3) :
    - web_fetch         : télécharge une page et retourne son contenu texte/markdown
    - web_screenshot    : capture le HTML brut d'une URL (pour inspection de structure)
    - web_extract       : extraction ciblée via sélecteurs CSS

  Utilitaires (5) :
    - web_links         : liste tous les liens d'une page (filtrés par pattern)
    - web_tables        : extrait les tableaux HTML en JSON
    - web_rss           : lit un flux RSS/Atom et retourne les derniers articles
    - web_download_file : télécharge un fichier binaire (PDF, image, CSV…)

Configuration .env (optionnelle) :
  WEB_SEARCH_ENGINE=ddg          # "ddg" (défaut) ou "searxng"
  WEB_SEARCH_SEARXNG_URL=http://localhost:8080   # URL de votre instance SearXNG
  WEB_SEARCH_DEFAULT_LANG=fr-FR  # langue des résultats

Stratégie :
  - DuckDuckGo : aucune clé API, via POST HTML (https://html.duckduckgo.com/html/)
  - SearXNG    : instance auto-hébergée, API JSON native, aucune clé requise
  - Toutes les requêtes passent par httpx avec un User-Agent réaliste
  - Timeout configurable (défaut 15s)
  - Le contenu HTML est converti en Markdown via markdownify pour une lecture aisée
  - Les pages trop volumineuses sont tronquées avec un indicateur

Prérequis :
    pip install httpx beautifulsoup4 lxml markdownify
"""

import os
import re
import json
import time
import hashlib
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus, unquote

import httpx
from bs4 import BeautifulSoup

try:
    import markdownify as md_lib
    _HAS_MARKDOWNIFY = True
except ImportError:
    _HAS_MARKDOWNIFY = False

from core.config import Config
from core.tools_engine import tool, set_current_family, _TOOL_ICONS

set_current_family("web_tools", "Web", "🌐")

# ── Icônes UI ─────────────────────────────────────────────────────────────────
_TOOL_ICONS.update({
    "web_search":        "🔍",
    "web_search_news":   "📰",
    "web_image_search":  "🖼️",
    "web_search_engine": "⚙️",
    "web_fetch":         "🌐",
    "web_screenshot":    "📸",
    "web_extract":       "🎯",
    "web_links":         "🔗",
    "web_tables":        "📊",
    "web_rss":           "📡",
    "web_download_file": "⬇️",
})

# ── Constantes ────────────────────────────────────────────────────────────────
_DEFAULT_TIMEOUT   = 15
_MAX_RESULTS       = 25
_MAX_CONTENT_CHARS = 40_000

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers internes — HTTP
# ══════════════════════════════════════════════════════════════════════════════

def _get(url: str, timeout: int = _DEFAULT_TIMEOUT,
         extra_headers: dict = None) -> httpx.Response:
    """Effectue un GET avec les headers par défaut."""
    headers = dict(_DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# Helpers internes — HTML / texte
# ══════════════════════════════════════════════════════════════════════════════

def _html_to_markdown(html: str, base_url: str = "") -> str:
    """Convertit du HTML en Markdown lisible."""
    if not _HAS_MARKDOWNIFY:
        soup = BeautifulSoup(html, "lxml")
        return soup.get_text(separator="\n", strip=True)

    return md_lib.markdownify(
        html,
        heading_style="ATX",
        strip=["script", "style", "nav", "footer", "head", "noscript", "iframe"],
        newline_style="backslash",
    )


def _clean_text(text: str) -> str:
    """Supprime les lignes vides consécutives et les espaces superflus."""
    lines = text.splitlines()
    cleaned, prev_empty = [], False
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            if not prev_empty:
                cleaned.append("")
            prev_empty = True
        else:
            cleaned.append(stripped)
            prev_empty = False
    return "\n".join(cleaned).strip()


def _truncate(text: str, max_chars: int = _MAX_CONTENT_CHARS) -> tuple[str, bool]:
    """Tronque le texte si nécessaire. Retourne (texte, tronqué)."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _extract_main_content(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Tente d'isoler le contenu principal en supprimant les éléments
    de navigation, publicités, sidebars, etc.
    """
    for tag in soup.find_all([
        "nav", "header", "footer", "aside", "script", "style",
        "noscript", "iframe", "form", "button",
    ]):
        tag.decompose()

    for attr in ("class", "id", "role"):
        for pattern in ("nav", "menu", "sidebar", "footer", "header",
                        "cookie", "banner", "ad", "popup", "modal"):
            for el in soup.find_all(attrs={attr: re.compile(pattern, re.I)}):
                el.decompose()

    return soup


def _clean_snippet(raw: str) -> str:
    """Nettoie le HTML résiduel dans un snippet de résultat de recherche."""
    soup = BeautifulSoup(raw, "lxml")
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s{2,}", " ", text).strip()


# ══════════════════════════════════════════════════════════════════════════════
# Helpers internes — Moteurs de recherche
# ══════════════════════════════════════════════════════════════════════════════

def _get_engine() -> str:
    """Retourne le moteur configuré : 'ddg' ou 'searxng'."""
    return getattr(Config, "WEB_SEARCH_ENGINE", "ddg").lower().strip()


def _get_searxng_url() -> str:
    """Retourne l'URL de l'instance SearXNG configurée."""
    return getattr(Config, "WEB_SEARCH_SEARXNG_URL", "http://localhost:8080").rstrip("/")


def _get_default_lang() -> str:
    return getattr(Config, "WEB_SEARCH_DEFAULT_LANG", "fr-FR")


def _decode_ddg_url(href: str) -> str:
    """Décode l'URL DDG encapsulée dans /l/?uddg=..."""
    if "uddg=" in href:
        qs = parse_qs(urlparse(href).query)
        urls = qs.get("uddg", [])
        if urls:
            return unquote(urls[0])
    if href.startswith("/"):
        return "https://duckduckgo.com" + href
    return href


def _search_ddg(
    requete: str,
    limite: int = 10,
    region: str = "fr-fr",
    timeout: int = _DEFAULT_TIMEOUT,
    filtre_domaine: Optional[str] = None,
) -> list[dict]:
    """Recherche via DuckDuckGo HTML (sans API key)."""
    query = requete
    if filtre_domaine:
        query = f"site:{filtre_domaine} {query}"

    resp = httpx.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query, "kl": region},
        headers=_DEFAULT_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    resultats = []

    for result in soup.select(".result"):
        title_el   = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")
        url_el     = result.select_one(".result__url")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        href  = _decode_ddg_url(title_el.get("href", ""))

        if not href.startswith("http"):
            continue

        snippet     = _clean_snippet(snippet_el.decode_contents()) if snippet_el else ""
        display_url = url_el.get_text(strip=True) if url_el else href

        resultats.append({
            "titre":   title,
            "url":     href,
            "extrait": snippet,
            "domaine": display_url,
            "moteur":  "DuckDuckGo",
        })

        if len(resultats) >= limite:
            break

    return resultats


def _search_searxng(
    requete: str,
    limite: int = 10,
    lang: str = "fr-FR",
    timeout: int = _DEFAULT_TIMEOUT,
    categories: str = "general",
    time_range: Optional[str] = None,
    filtre_domaine: Optional[str] = None,
) -> list[dict]:
    """Recherche via instance SearXNG locale (API JSON)."""
    base_url = _get_searxng_url()

    query = requete
    if filtre_domaine:
        query = f"site:{filtre_domaine} {query}"

    params: dict = {
        "q":          query,
        "format":     "json",
        "categories": categories,
        "language":   lang,
    }
    if time_range:
        params["time_range"] = time_range  # "day", "week", "month", "year"

    resp = httpx.get(
        f"{base_url}/search",
        params=params,
        headers=_DEFAULT_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()

    data = resp.json()
    resultats = []

    for r in data.get("results", [])[:limite]:
        resultats.append({
            "titre":   r.get("title", ""),
            "url":     r.get("url", ""),
            "extrait": _clean_snippet(r.get("content", "")),
            "domaine": urlparse(r.get("url", "")).netloc,
            "moteur":  "SearXNG",
        })

    return resultats


def _search(
    requete: str,
    limite: int = 10,
    lang: str = "",
    timeout: int = _DEFAULT_TIMEOUT,
    filtre_domaine: Optional[str] = None,
    time_range: Optional[str] = None,
    categories: str = "general",
) -> list[dict]:
    """Dispatch vers le moteur configuré."""
    engine = _get_engine()
    lang   = lang or _get_default_lang()

    if engine == "searxng":
        return _search_searxng(
            requete,
            limite=limite,
            lang=lang,
            timeout=timeout,
            categories=categories,
            time_range=time_range,
            filtre_domaine=filtre_domaine,
        )
    else:
        region = lang.lower().replace("_", "-")
        return _search_ddg(
            requete,
            limite=limite,
            region=region,
            timeout=timeout,
            filtre_domaine=filtre_domaine,
        )


# ══════════════════════════════════════════════════════════════════════════════
# OUTILS — Recherche
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="web_search",
    description=(
        "Effectue une recherche web multi-moteurs (DuckDuckGo ou SearXNG auto-hébergé) "
        "et retourne les résultats (titre, URL, extrait). "
        "Pour lire le contenu complet d'un résultat, utiliser web_fetch avec l'URL. "
        "Exemples de requêtes : 'loi n° 2026-22 legifrance', "
        "'pandas read_csv documentation', 'actualité IA France 2026'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "requete": {
                "type": "string",
                "description": (
                    "Requête de recherche. Supporte les opérateurs avancés : "
                    "site:example.com, filetype:pdf, \"phrase exacte\", -mot_exclu."
                ),
            },
            "limite": {
                "type": "integer",
                "description": f"Nombre de résultats (défaut: 10, max: {_MAX_RESULTS}).",
            },
            "langue": {
                "type": "string",
                "description": (
                    "Langue/région des résultats : 'fr-FR' (défaut), 'en-US', 'de-DE', etc."
                ),
            },
            "filtre_domaine": {
                "type": "string",
                "description": (
                    "Restreindre les résultats à un domaine précis "
                    "(ex: 'legifrance.gouv.fr', 'wikipedia.org')."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["requete"],
    },
)
def web_search(
    requete: str,
    limite: int = 10,
    langue: str = "",
    filtre_domaine: Optional[str] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    limite = min(max(1, limite), _MAX_RESULTS)

    try:
        resultats = _search(
            requete,
            limite=limite,
            lang=langue,
            timeout=timeout,
            filtre_domaine=filtre_domaine,
        )

        if not resultats:
            return {
                "status":    "success",
                "requete":   requete,
                "nombre":    0,
                "resultats": [],
                "message":   "Aucun résultat trouvé. Essayez avec d'autres termes.",
            }

        return {
            "status":    "success",
            "requete":   requete,
            "moteur":    _get_engine(),
            "nombre":    len(resultats),
            "resultats": resultats,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s."}
    except httpx.ConnectError as e:
        return {"status": "error", "error": f"Connexion impossible : {e}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur de recherche : {e}"}


@tool(
    name="web_search_news",
    description=(
        "Recherche des actualités récentes sur le web. "
        "Filtre automatiquement les résultats sur une période récente "
        "(dernière journée, semaine ou mois). "
        "Idéal pour : suivi de l'actualité, veille réglementaire, "
        "nouvelles versions de logiciels, événements récents."
    ),
    parameters={
        "type": "object",
        "properties": {
            "requete": {
                "type": "string",
                "description": "Sujet à rechercher (ex: 'RGPD actualité 2026', 'Python 3.14 release').",
            },
            "periode": {
                "type": "string",
                "description": (
                    "Période de recherche : "
                    "'jour' (dernières 24h), "
                    "'semaine' (7 derniers jours, défaut), "
                    "'mois' (30 derniers jours), "
                    "'annee' (12 derniers mois)."
                ),
                "enum": ["jour", "semaine", "mois", "annee"],
            },
            "limite": {
                "type": "integer",
                "description": f"Nombre de résultats (défaut: 10, max: {_MAX_RESULTS}).",
            },
            "langue": {
                "type": "string",
                "description": "Langue des résultats (défaut: 'fr-FR').",
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["requete"],
    },
)
def web_search_news(
    requete: str,
    periode: str = "semaine",
    limite: int = 10,
    langue: str = "",
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    limite = min(max(1, limite), _MAX_RESULTS)

    _periodes = {
        "jour":    "day",
        "semaine": "week",
        "mois":    "month",
        "annee":   "year",
    }
    time_range = _periodes.get(periode, "week")

    try:
        engine = _get_engine()

        if engine == "searxng":
            resultats = _search_searxng(
                requete,
                limite=limite,
                lang=langue or _get_default_lang(),
                timeout=timeout,
                categories="news,general",
                time_range=time_range,
            )
        else:
            # DDG n'expose pas de filtre date natif dans l'API HTML ;
            # on ajoute une indication temporelle dans la requête pour biaiser les résultats.
            _ddg_time = {"jour": " site:* après 24h", "semaine": "", "mois": "", "annee": ""}
            requete_ddg = requete + _ddg_time.get(periode, "")
            region = (langue or _get_default_lang()).lower().replace("_", "-")
            resultats = _search_ddg(
                requete_ddg,
                limite=limite,
                region=region,
                timeout=timeout,
            )

        if not resultats:
            return {
                "status":    "success",
                "requete":   requete,
                "periode":   periode,
                "nombre":    0,
                "resultats": [],
                "message":   "Aucune actualité trouvée pour cette période.",
            }

        return {
            "status":    "success",
            "requete":   requete,
            "periode":   periode,
            "moteur":    engine,
            "nombre":    len(resultats),
            "resultats": resultats,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s."}
    except httpx.ConnectError as e:
        return {"status": "error", "error": f"Connexion impossible : {e}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur recherche actualités : {e}"}


@tool(
    name="web_image_search",
    description=(
        "Recherche des images sur le web et retourne leurs URLs directes. "
        "Retourne pour chaque image : l'URL directe (img_url), une miniature (thumbnail), "
        "le titre, la page source et le format. "
        "Avec SearXNG : résultats natifs de la catégorie 'images' (tous sujets). "
        "Sans SearXNG : repli sur Wikimedia Commons (images libres de droits). "
        "Pour télécharger une image trouvée, utiliser web_download_file avec son img_url."
    ),
    parameters={
        "type": "object",
        "properties": {
            "requete": {
                "type": "string",
                "description": (
                    "Description de l'image recherchée. "
                    "Ex: 'logo Python', 'carte France régions', 'Charmander Pokémon'."
                ),
            },
            "limite": {
                "type": "integer",
                "description": f"Nombre de résultats (défaut: 10, max: {_MAX_RESULTS}).",
            },
            "langue": {
                "type": "string",
                "description": "Langue des résultats (défaut: 'fr-FR').",
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["requete"],
    },
)
def web_image_search(
    requete: str,
    limite: int = 10,
    langue: str = "",
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    limite = min(max(1, limite), _MAX_RESULTS)
    engine = _get_engine()
    lang   = langue or _get_default_lang()

    try:
        if engine == "searxng":
            # ── SearXNG : catégorie images native ─────────────────────────
            base_url = _get_searxng_url()
            params: dict = {
                "q":          requete,
                "format":     "json",
                "categories": "images",
                "language":   lang,
            }
            resp = httpx.get(
                f"{base_url}/search",
                params=params,
                headers=_DEFAULT_HEADERS,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            resultats = []
            for r in data.get("results", [])[:limite]:
                img_url = r.get("img_src") or r.get("url", "")
                if not img_url:
                    continue
                resultats.append({
                    "titre":     r.get("title", ""),
                    "img_url":   img_url,
                    "thumbnail": r.get("thumbnail_src") or r.get("thumbnail", ""),
                    "source":    r.get("url", ""),
                    "domaine":   urlparse(r.get("url", "")).netloc,
                    "format":    r.get("img_format", ""),
                    "moteur":    "SearXNG",
                })

        else:
            # ── Repli Wikimedia Commons : API publique, images libres ──────
            # DDG HTML ne retourne pas d'URLs d'images directes ; Wikimedia
            # Commons offre une API JSON fiable sans clé ni authentification.
            params_wm: dict = {
                "action":      "query",
                "generator":   "search",
                "gsrsearch":   f"filetype:bitmap|drawing {requete}",
                "gsrnamespace": "6",          # NS 6 = File:
                "gsrlimit":    str(limite),
                "prop":        "imageinfo",
                "iiprop":      "url|mime|size|extmetadata",
                "iiurlwidth":  "400",          # miniature 400px
                "format":      "json",
                "origin":      "*",
            }
            resp = httpx.get(
                "https://commons.wikimedia.org/w/api.php",
                params=params_wm,
                headers=_DEFAULT_HEADERS,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            pages = data.get("query", {}).get("pages", {})
            resultats = []
            for page in pages.values():
                ii = page.get("imageinfo", [{}])[0]
                img_url = ii.get("url", "")
                if not img_url:
                    continue
                # Titre sans le préfixe "File:"
                titre = page.get("title", "").removeprefix("File:").rsplit(".", 1)[0]
                # Description depuis les métadonnées EXIF/XMP si disponible
                extmeta = ii.get("extmetadata", {})
                desc = (
                    extmeta.get("ImageDescription", {}).get("value", "")
                    or extmeta.get("ObjectName", {}).get("value", "")
                )
                # Nettoyer le HTML éventuel dans la description
                if desc:
                    desc = BeautifulSoup(desc, "lxml").get_text(strip=True)[:200]
                mime = ii.get("mime", "")
                resultats.append({
                    "titre":     titre,
                    "img_url":   img_url,
                    "thumbnail": ii.get("thumburl", ""),
                    "source":    f"https://commons.wikimedia.org/wiki/{quote_plus(page.get('title', ''))}",
                    "domaine":   "commons.wikimedia.org",
                    "format":    mime.split("/")[-1] if mime else "",
                    "description": desc,
                    "moteur":    "Wikimedia Commons",
                })
                if len(resultats) >= limite:
                    break

        if not resultats:
            msg = (
                "Aucune image trouvée."
                if engine == "searxng"
                else (
                    "Aucune image trouvée sur Wikimedia Commons pour cette requête. "
                    "Essayez avec des termes en anglais, ou configurez SearXNG "
                    "(WEB_SEARCH_ENGINE=searxng) pour une recherche plus large."
                )
            )
            return {
                "status":    "success",
                "requete":   requete,
                "nombre":    0,
                "resultats": [],
                "message":   msg,
            }

        return {
            "status":    "success",
            "requete":   requete,
            "moteur":    engine if engine == "searxng" else "Wikimedia Commons",
            "nombre":    len(resultats),
            "resultats": resultats,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s."}
    except httpx.ConnectError as e:
        return {"status": "error", "error": f"Connexion impossible : {e}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur recherche images : {e}"}


@tool(
    name="web_search_engine",
    description=(
        "Retourne la configuration du moteur de recherche actif "
        "(DuckDuckGo ou SearXNG) et ses paramètres. "
        "Utile pour savoir quel moteur est configuré avant d'effectuer une recherche."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def web_search_engine() -> dict:
    engine = _get_engine()

    info: dict = {
        "status":       "success",
        "moteur_actif": engine,
    }

    if engine == "searxng":
        searxng_url = _get_searxng_url()
        try:
            resp = httpx.get(
                f"{searxng_url}/config",
                headers=_DEFAULT_HEADERS,
                timeout=5,
            )
            if resp.status_code == 200:
                cfg = resp.json()
                info["searxng_url"]     = searxng_url
                info["searxng_version"] = cfg.get("version", "inconnue")
                info["searxng_statut"]  = "disponible"
            else:
                info["searxng_url"]    = searxng_url
                info["searxng_statut"] = f"erreur HTTP {resp.status_code}"
        except Exception as e:
            info["searxng_url"]    = searxng_url
            info["searxng_statut"] = f"inaccessible ({e})"
    else:
        info["description"] = (
            "DuckDuckGo HTML (sans clé API). "
            "Pour utiliser SearXNG, définissez WEB_SEARCH_ENGINE=searxng "
            "et WEB_SEARCH_SEARXNG_URL dans le fichier .env."
        )

    info["langue_defaut"] = _get_default_lang()
    return info


# ══════════════════════════════════════════════════════════════════════════════
# OUTILS — Lecture de pages
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="web_fetch",
    description=(
        "Télécharge une page web et retourne son contenu en Markdown lisible. "
        "Idéal pour lire un article, une documentation, une page Wikipedia, etc. "
        "Le contenu est nettoyé (navigation, publicités supprimées) et converti en texte. "
        "Pour du scraping ciblé, préférer web_extract avec des sélecteurs CSS."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL complète de la page à télécharger (ex: https://example.com/article).",
            },
            "nettoyer": {
                "type": "boolean",
                "description": (
                    "Si true (défaut), supprime navigation/sidebar/footer pour ne garder "
                    "que le contenu principal."
                ),
            },
            "max_caracteres": {
                "type": "integer",
                "description": f"Limite de caractères retournés (défaut: {_MAX_CONTENT_CHARS}).",
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["url"],
    },
)
def web_fetch(
    url: str,
    nettoyer: bool = True,
    max_caracteres: int = _MAX_CONTENT_CHARS,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    try:
        resp = _get(url, timeout=timeout)
        content_type = resp.headers.get("Content-Type", "")

        if "html" not in content_type and "xml" not in content_type:
            return {
                "status": "error",
                "error": (
                    f"La page retourne un contenu non-HTML : {content_type}. "
                    "Utilisez web_download_file pour les fichiers binaires."
                ),
            }

        soup = BeautifulSoup(resp.text, "lxml")

        # Titre
        title = soup.title.string.strip() if soup.title else ""

        # Meta description
        meta_desc = ""
        meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        if meta and meta.get("content"):
            meta_desc = meta["content"].strip()

        if nettoyer:
            soup = _extract_main_content(soup)

        main = (
            soup.find("main") or
            soup.find("article") or
            soup.find(attrs={"id": re.compile(r"content|main|article", re.I)}) or
            soup.find("body") or
            soup
        )

        markdown = _html_to_markdown(str(main), base_url=url)
        text = _clean_text(markdown)
        text, truncated = _truncate(text, max_caracteres)

        return {
            "status":           "success",
            "url":              resp.url,
            "titre":            title,
            "description":      meta_desc,
            "contenu":          text,
            "tronque":          truncated,
            "taille_originale": len(markdown),
            "code_http":        resp.status_code,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s : {url}"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"Erreur HTTP {e.response.status_code} : {url}"}
    except httpx.ConnectError:
        return {"status": "error", "error": f"Impossible de se connecter à : {url}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur inattendue : {e}"}


@tool(
    name="web_screenshot",
    description=(
        "Retourne le HTML brut d'une URL pour inspecter la structure d'une page. "
        "Utile pour comprendre la structure DOM avant d'écrire des sélecteurs CSS "
        "pour web_extract. Retourne les balises et attributs principaux."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL de la page à inspecter.",
            },
            "profondeur": {
                "type": "integer",
                "description": "Profondeur de l'arbre DOM à afficher (défaut: 3, max: 6).",
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["url"],
    },
)
def web_screenshot(
    url: str,
    profondeur: int = 3,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    profondeur = min(max(1, profondeur), 6)

    def _dump(tag, depth: int, max_depth: int) -> str:
        if depth > max_depth or not hasattr(tag, "name") or not tag.name:
            return ""
        indent = "  " * (depth - 1)
        attrs = ""
        for attr in ("id", "class", "href", "src", "name", "role", "aria-label"):
            val = tag.get(attr)
            if val:
                if isinstance(val, list):
                    val = " ".join(val)
                attrs += f' {attr}="{val[:60]}"'
        text_preview = ""
        if depth == max_depth:
            text = tag.get_text(strip=True)[:80]
            if text:
                text_preview = f"  → \"{text}\""
        children = [_dump(c, depth + 1, max_depth) for c in tag.children]
        children_str = "".join(c for c in children if c)
        return f"{indent}<{tag.name}{attrs}>{text_preview}\n{children_str}"

    try:
        resp = _get(url, timeout=timeout)
        soup = BeautifulSoup(resp.text, "lxml")
        body = soup.find("body") or soup
        structure = _dump(body, 1, profondeur)
        structure, truncated = _truncate(structure, 20_000)

        return {
            "status":       "success",
            "url":          resp.url,
            "titre":        soup.title.string.strip() if soup.title else "",
            "structure_dom": structure,
            "tronque":      truncated,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"Erreur HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="web_extract",
    description=(
        "Extrait des éléments précis d'une page web via des sélecteurs CSS. "
        "Permet de cibler exactement ce qu'on cherche (titre, prix, tableau, liste…). "
        "Exemples de sélecteurs : 'h1', '.price', '#content p', 'table.data tr'. "
        "Utiliser web_screenshot d'abord pour inspecter la structure si nécessaire."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL de la page.",
            },
            "selecteur": {
                "type": "string",
                "description": "Sélecteur CSS (ex: 'article h2', '.price', '#main p').",
            },
            "attribut": {
                "type": "string",
                "description": (
                    "Si fourni, extrait cet attribut plutôt que le texte "
                    "(ex: 'href' pour les liens, 'src' pour les images)."
                ),
            },
            "limite": {
                "type": "integer",
                "description": "Nombre max d'éléments à retourner (défaut: 50).",
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["url", "selecteur"],
    },
)
def web_extract(
    url: str,
    selecteur: str,
    attribut: Optional[str] = None,
    limite: int = 50,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    limite = min(max(1, limite), 500)

    try:
        resp = _get(url, timeout=timeout)
        soup = BeautifulSoup(resp.text, "lxml")
        elements = soup.select(selecteur)

        if not elements:
            return {
                "status":    "success",
                "url":       resp.url,
                "selecteur": selecteur,
                "nombre":    0,
                "resultats": [],
                "message":   f"Aucun élément trouvé pour le sélecteur '{selecteur}'.",
            }

        resultats = []
        for el in elements[:limite]:
            if attribut:
                val = el.get(attribut, "")
                if val and attribut in ("href", "src", "action"):
                    val = urljoin(url, val)
                resultats.append({"attribut": attribut, "valeur": val})
            else:
                text = el.get_text(separator=" ", strip=True)
                html_inner = str(el)[:500] if len(str(el)) > 200 else str(el)
                resultats.append({"texte": text, "html": html_inner})

        return {
            "status":           "success",
            "url":              resp.url,
            "selecteur":        selecteur,
            "nombre":           len(elements),
            "nombre_retournes": len(resultats),
            "resultats":        resultats,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"Erreur HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


# ══════════════════════════════════════════════════════════════════════════════
# OUTILS — Utilitaires
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="web_links",
    description=(
        "Extrait tous les liens d'une page web. "
        "Peut filtrer par pattern (ex: ne retenir que les PDF, ou les liens internes). "
        "Utile pour cartographier un site ou trouver des fichiers à télécharger."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL de la page à analyser.",
            },
            "filtre": {
                "type": "string",
                "description": (
                    "Regex pour filtrer les URLs (ex: '\\.pdf$', 'legifrance', '^https://example')."
                ),
            },
            "internes_seulement": {
                "type": "boolean",
                "description": "Si true, retourne uniquement les liens vers le même domaine.",
            },
            "limite": {
                "type": "integer",
                "description": "Nombre max de liens (défaut: 100).",
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["url"],
    },
)
def web_links(
    url: str,
    filtre: Optional[str] = None,
    internes_seulement: bool = False,
    limite: int = 100,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    limite = min(max(1, limite), 1000)
    base_domain = urlparse(url).netloc

    try:
        resp = _get(url, timeout=timeout)
        soup = BeautifulSoup(resp.text, "lxml")

        liens = []
        seen = set()

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            absolute = urljoin(resp.url, href)
            parsed = urlparse(absolute)

            if parsed.scheme not in ("http", "https"):
                continue

            if internes_seulement and parsed.netloc != base_domain:
                continue

            if filtre:
                try:
                    if not re.search(filtre, absolute, re.I):
                        continue
                except re.error:
                    pass

            if absolute in seen:
                continue
            seen.add(absolute)

            text = tag.get_text(strip=True)[:100]
            liens.append({
                "url":     absolute,
                "texte":   text,
                "domaine": parsed.netloc,
            })

            if len(liens) >= limite:
                break

        return {
            "status":          "success",
            "url":             resp.url,
            "nombre":          len(liens),
            "filtre_applique": filtre,
            "liens":           liens,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"Erreur HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="web_tables",
    description=(
        "Extrait les tableaux HTML d'une page et les retourne en JSON structuré. "
        "Très utile pour récupérer des données tabulaires (cours de bourse, "
        "statistiques, comparatifs, horaires, résultats sportifs…)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL de la page contenant des tableaux.",
            },
            "index": {
                "type": "integer",
                "description": (
                    "Index du tableau à extraire (0 = premier). "
                    "Si absent, retourne tous les tableaux."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["url"],
    },
)
def web_tables(
    url: str,
    index: Optional[int] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    try:
        resp = _get(url, timeout=timeout)
        soup = BeautifulSoup(resp.text, "lxml")
        tables_html = soup.find_all("table")

        if not tables_html:
            return {
                "status":          "success",
                "url":             resp.url,
                "nombre_tableaux": 0,
                "tableaux":        [],
                "message":         "Aucun tableau HTML trouvé sur cette page.",
            }

        def _parse_table(table) -> dict:
            headers = []
            rows = []

            header_row = table.find("thead")
            if header_row:
                headers = [
                    th.get_text(strip=True)
                    for th in header_row.find_all(["th", "td"])
                ]

            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if not headers and cells:
                    if not rows:
                        headers = cells
                        continue
                if cells:
                    if headers and len(cells) == len(headers):
                        rows.append(dict(zip(headers, cells)))
                    else:
                        rows.append(cells)

            caption = table.find("caption")
            return {
                "legende":  caption.get_text(strip=True) if caption else "",
                "colonnes": headers,
                "nb_lignes": len(rows),
                "donnees":  rows[:200],
            }

        if index is not None:
            if index >= len(tables_html):
                return {
                    "status": "error",
                    "error": f"Index {index} invalide — la page contient {len(tables_html)} tableau(x).",
                }
            return {
                "status":  "success",
                "url":     resp.url,
                "index":   index,
                "tableau": _parse_table(tables_html[index]),
            }

        return {
            "status":          "success",
            "url":             resp.url,
            "nombre_tableaux": len(tables_html),
            "tableaux":        [_parse_table(t) for t in tables_html],
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"Erreur HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="web_rss",
    description=(
        "Lit un flux RSS ou Atom et retourne les derniers articles "
        "(titre, date, lien, résumé). "
        "Utile pour suivre l'actualité, les blogs, les sites d'information. "
        "Beaucoup de sites exposent leur flux RSS à /feed, /rss, /atom ou /feed.xml."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL du flux RSS/Atom.",
            },
            "limite": {
                "type": "integer",
                "description": "Nombre d'articles à retourner (défaut: 10, max: 50).",
            },
            "timeout": {
                "type": "integer",
                "description": f"Délai max en secondes (défaut: {_DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["url"],
    },
)
def web_rss(
    url: str,
    limite: int = 10,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    limite = min(max(1, limite), 50)

    try:
        resp = _get(url, timeout=timeout,
                    extra_headers={"Accept": "application/rss+xml,application/atom+xml,text/xml,*/*"})
        soup = BeautifulSoup(resp.content, "xml")

        articles = []

        is_atom = bool(soup.find("feed"))
        items = soup.find_all("entry") if is_atom else soup.find_all("item")

        channel = soup.find("channel") or soup.find("feed")
        feed_title = ""
        if channel:
            t = channel.find("title", recursive=False)
            feed_title = t.get_text(strip=True) if t else ""

        for item in items[:limite]:
            t = item.find("title")
            title = t.get_text(strip=True) if t else ""

            if is_atom:
                link_tag = item.find("link", rel=lambda r: r != "enclosure")
                link = link_tag.get("href", "") if link_tag else ""
            else:
                link_tag = item.find("link")
                link = link_tag.get_text(strip=True) if link_tag else ""
                if not link and link_tag:
                    link = link_tag.next_sibling or ""

            pub_date = ""
            for date_tag in ("pubDate", "published", "updated", "dc:date"):
                d = item.find(date_tag)
                if d:
                    pub_date = d.get_text(strip=True)
                    break

            summary = ""
            for summary_tag in ("description", "summary", "content", "content:encoded"):
                s = item.find(summary_tag)
                if s:
                    raw = s.get_text(strip=True)
                    sub_soup = BeautifulSoup(raw, "lxml")
                    summary = sub_soup.get_text(separator=" ", strip=True)[:500]
                    break

            articles.append({
                "titre":  title,
                "lien":   link,
                "date":   pub_date,
                "resume": summary,
            })

        return {
            "status":     "success",
            "url":        resp.url,
            "flux_titre": feed_title,
            "format":     "Atom" if is_atom else "RSS",
            "nombre":     len(articles),
            "articles":   articles,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"Erreur HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur lecture flux RSS : {e}"}


@tool(
    name="web_download_file",
    description=(
        "Télécharge un fichier depuis une URL et le sauvegarde localement. "
        "Supporte tous les types : PDF, CSV, images, archives ZIP, etc. "
        "Retourne le chemin local du fichier téléchargé."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL du fichier à télécharger.",
            },
            "destination": {
                "type": "string",
                "description": (
                    "Chemin VFS de destination (ex: /documents/rapport.pdf). "
                    "Si c'est un dossier (sans extension), le nom de fichier est déduit de l'URL. "
                    "Défaut : /downloads/<nom_fichier>"
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Délai max en secondes (défaut: 60 pour les gros fichiers).",
            },
            "taille_max_mo": {
                "type": "integer",
                "description": "Taille maximum autorisée en Mo (défaut: 100).",
            },
        },
        "required": ["url"],
    },
)
def web_download_file(
    url: str,
    destination: Optional[str] = None,
    timeout: int = 60,
    taille_max_mo: int = 100,
) -> dict:
    import io as _io
    from core.virtual_fs import get_vfs

    taille_max = taille_max_mo * 1024 * 1024

    try:
        # ── Vérification optionnelle de la taille via HEAD ─────────────────
        try:
            head = httpx.head(url, headers=_DEFAULT_HEADERS,
                              timeout=10, follow_redirects=True)
            content_length = int(head.headers.get("Content-Length", 0))
            if content_length > taille_max:
                return {
                    "status": "error",
                    "error": (
                        f"Fichier trop volumineux : {content_length / 1024 / 1024:.1f} Mo "
                        f"(limite : {taille_max_mo} Mo)."
                    ),
                }
        except Exception:
            pass  # HEAD non supporté ou timeout → on tente quand même

        # ── Télécharger en streaming avec contrôle de taille ──────────────
        buf = _io.BytesIO()
        total = 0
        final_url = url
        resp_headers: dict = {}

        with httpx.stream("GET", url, headers=_DEFAULT_HEADERS,
                          timeout=timeout, follow_redirects=True) as resp:
            resp.raise_for_status()
            final_url = str(resp.url)
            resp_headers = dict(resp.headers)

            for chunk in resp.iter_bytes(chunk_size=8192):
                total += len(chunk)
                if total > taille_max:
                    return {
                        "status": "error",
                        "error": f"Fichier trop volumineux (dépasse {taille_max_mo} Mo pendant le téléchargement).",
                    }
                buf.write(chunk)

        # ── Déduire le nom de fichier ──────────────────────────────────────
        filename = ""
        cd = resp_headers.get("content-disposition", "")
        if "filename=" in cd:
            m = re.search(r'filename[^;=\n]*=[\'\"]?([^\'\"\n;]+)', cd)
            if m:
                filename = m.group(1).strip()

        if not filename:
            parsed = urlparse(final_url)
            filename = Path(parsed.path).name or "fichier_telecharge"
            if "." not in filename:
                ct = resp_headers.get("content-type", "").split(";")[0].strip()
                ext = mimetypes.guess_extension(ct) or ""
                filename += ext

        # ── Déterminer le chemin VFS de destination ────────────────────────
        if destination:
            vfs_dest = destination if destination.startswith("/") else f"/{destination}"
            # Si la destination est un dossier (pas d'extension), y ajouter le nom
            if not Path(vfs_dest).suffix:
                vfs_dest = f"{vfs_dest.rstrip('/')}/{filename}"
        else:
            vfs_dest = f"/downloads/{filename}"

        # ── Ingérer dans le VFS ────────────────────────────────────────────
        data = buf.getvalue()
        mime_type = resp_headers.get("content-type", "").split(";")[0].strip()
        if not mime_type or mime_type == "*/*":
            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or "application/octet-stream"

        vfs = get_vfs()
        vfs.write_bytes(vfs_dest, data, mime_type=mime_type, overwrite=True)

        taille_str = (
            f"{total / 1024:.1f} Ko" if total < 1024 * 1024
            else f"{total / 1024 / 1024:.2f} Mo"
        )

        return {
            "status":    "success",
            "url":       final_url,
            "fichier":   vfs_dest,
            "vfs":       True,
            "nom":       filename,
            "taille":    taille_str,
            "type_mime": mime_type,
        }

    except httpx.TimeoutException:
        return {"status": "error", "error": f"Timeout après {timeout}s"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"Erreur HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur téléchargement : {e}"}
