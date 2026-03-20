# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : IA‑Assistant
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
# Année   : 2026
# ============================================================================

"""
tools/open_meteo_tools.py — Interface Open‑Meteo
================================================

Outils exposés (2) :
  - météo_actuelle      : météo actuelle d’un point géographique
  - prévision_météo_7j : prévisions météo sur 7 jours (ou un nombre de jours)

Ce module interroge l’API publique **Open‑Meteo** (https://open-meteo.com/).
Il accepte soit des coordonnées latitude/longitude, soit un nom de lieu
qui sera résolu via le service de géocodage d’Open‑Meteo.

Usage :
    import tools.open_meteo_tools   # enregistre les outils
"""

# 1. Imports stdlib
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

# 2. Imports third‑party
import httpx  # httpx est installé dans l’environnement Prométhée

# 3. Imports locaux Prométhée
from core.tools_engine import tool, set_current_family, _TOOL_ICONS

# ---------------------------------------------------------------------------
# Configuration du logger interne
# ---------------------------------------------------------------------------
_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enregistrement de la famille d’outils
# ---------------------------------------------------------------------------
set_current_family("open_meteo_tools", "Météo Open‑Meteo", "🌦️")

# ── Icônes UI ─────────────────────────────────────────────────────────────────
_TOOL_ICONS.update({
    "météo_actuelle": "📍",
    "prévision_météo_7j": "🗓️",
})


# ---------------------------------------------------------------------------
# Table des codes météo WMO (Weather Interpretation Codes)
# Référence : https://open-meteo.com/en/docs#weathervariables
# ---------------------------------------------------------------------------
# Chaque entrée : code → (icône, description)
# Les codes pairs/impairs d'une même dizaine représentent parfois
# intensité légère (pair) vs modérée/forte (impair).

_WMO: dict[int, tuple[str, str]] = {
    # ── Ciel dégagé ──────────────────────────────────────────────────────
    0:  ("☀️",  "Ciel dégagé"),
    # ── Peu nuageux ──────────────────────────────────────────────────────
    1:  ("🌤️",  "Principalement dégagé"),
    2:  ("⛅",  "Partiellement nuageux"),
    3:  ("☁️",  "Couvert"),
    # ── Brouillard ───────────────────────────────────────────────────────
    45: ("🌫️",  "Brouillard"),
    48: ("🌫️",  "Brouillard givrant"),
    # ── Bruine ───────────────────────────────────────────────────────────
    51: ("🌦️",  "Bruine légère"),
    53: ("🌦️",  "Bruine modérée"),
    55: ("🌧️",  "Bruine forte"),
    56: ("🌨️",  "Bruine verglaçante légère"),
    57: ("🌨️",  "Bruine verglaçante forte"),
    # ── Pluie ────────────────────────────────────────────────────────────
    61: ("🌧️",  "Pluie légère"),
    63: ("🌧️",  "Pluie modérée"),
    65: ("🌧️",  "Pluie forte"),
    66: ("🌨️",  "Pluie verglaçante légère"),
    67: ("🌨️",  "Pluie verglaçante forte"),
    # ── Neige ────────────────────────────────────────────────────────────
    71: ("🌨️",  "Chutes de neige légères"),
    73: ("❄️",   "Chutes de neige modérées"),
    75: ("❄️",   "Chutes de neige fortes"),
    77: ("🌨️",  "Grains de neige"),
    # ── Averses de pluie ─────────────────────────────────────────────────
    80: ("🌦️",  "Averses légères"),
    81: ("🌧️",  "Averses modérées"),
    82: ("🌧️",  "Averses violentes"),
    # ── Averses de neige ─────────────────────────────────────────────────
    85: ("🌨️",  "Averses de neige légères"),
    86: ("❄️",   "Averses de neige fortes"),
    # ── Orage ────────────────────────────────────────────────────────────
    95: ("⛈️",  "Orage"),
    96: ("⛈️",  "Orage avec grêle légère"),
    99: ("⛈️",  "Orage avec grêle forte"),
}


def _wmo_icon(code: int | None) -> str:
    """Retourne l'icône emoji correspondant à un code météo WMO."""
    if code is None:
        return "🌡️"
    return _WMO.get(code, ("🌡️", ""))[0]


def _wmo_label(code: int | None) -> str:
    """Retourne la description textuelle d'un code météo WMO."""
    if code is None:
        return "Inconnu"
    return _WMO.get(code, ("", "Inconnu"))[1]


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _geocode(city: str) -> Optional[Dict[str, float]]:
    """
    Résout un nom de lieu via le géocodeur d’Open‑Meteo.

    Retourne un dictionnaire ``{'latitude': …, 'longitude': …}`` ou ``None`` si
    la résolution échoue.
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    try:
        resp = httpx.get(url, params={"name": city, "count": 1, "language": "fr"}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if data.get("results"):
            result = data["results"][0]
            return {"latitude": result["latitude"], "longitude": result["longitude"]}
        _log.warning("Aucun résultat de géocodage pour la ville : %s", city)
    except Exception as exc:  # pragma: no cover – on capture tout pour éviter la propagation
        _log.exception("Erreur lors du géocodage de %s", city)
    return None


def _call_open_meteo(endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Effectue un appel GET vers l’API Open‑Meteo et renvoie le JSON décodé.
    En cas d’erreur, loggue l’exception et renvoie ``None``.
    """
    base = "https://api.open-meteo.com/v1"
    url = f"{base}/{endpoint}"
    try:
        resp = httpx.get(url, params=params, timeout=15.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # pragma: no cover
        _log.exception("Erreur d’appel API Open‑Meteo : %s %s", url, params)
        return None


def _prepare_coordinates(
    latitude: Optional[float],
    longitude: Optional[float],
    city: Optional[str],
) -> Optional[Dict[str, float]]:
    """
    Normalise les coordonnées : si ``latitude``/``longitude`` sont fournis,
    ils sont retournés. Sinon, on tente de géocoder ``city``.
    Retourne ``None`` si aucune information géographique n’est disponible.
    """
    if latitude is not None and longitude is not None:
        return {"latitude": latitude, "longitude": longitude}
    if city:
        geo = _geocode(city)
        if geo:
            return geo
    return None

# ---------------------------------------------------------------------------
# Outils exposés
# ---------------------------------------------------------------------------

@tool(
    name="météo_actuelle",
    description=(
        "Renvoie la météo actuelle (température, vent, condition) d’un point géographique. "
        "Accepte latitude/longitude ou le nom d’une ville. "
        "Utilise l’API publique Open‑Meteo."
    ),
    parameters={
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number",
                "description": "Latitude décimale (ex : 43.2375)."
            },
            "longitude": {
                "type": "number",
                "description": "Longitude décimale (ex : 6.0718)."
            },
            "city": {
                "type": "string",
                "description": "Nom de la ville (ex : \"Cuers\"). Utilisé si latitude/longitude manquent."
            },
            "timezone": {
                "type": "string",
                "description": "Fuseau horaire (ex : \"Europe/Paris\"). Valeur par défaut : \"auto\"."
            },
        },
        "required": [],
    },
)
def météo_actuelle(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    timezone: str = "auto",
) -> dict:
    coords = _prepare_coordinates(latitude, longitude, city)
    if not coords:
        return {
            "status": "error",
            "error": "Impossible de déterminer les coordonnées. Fournissez latitude/longitude ou un nom de ville valide.",
        }

    params = {
        "latitude": coords["latitude"],
        "longitude": coords["longitude"],
        "current_weather": "true",
        "timezone": timezone,
    }
    data = _call_open_meteo("forecast", params)
    if not data or "current_weather" not in data:
        return {
            "status": "error",
            "error": "L’API Open‑Meteo n’a pas retourné de météo actuelle.",
        }

    cw   = data["current_weather"]
    code = cw.get("weathercode")
    return {
        "status": "success",
        "city": city or "",
        "latitude": coords["latitude"],
        "longitude": coords["longitude"],
        "temperature_c": cw.get("temperature"),
        "windspeed_kmh": cw.get("windspeed"),
        "winddirection_deg": cw.get("winddirection"),
        "weathercode": code,
        "weather_icon": _wmo_icon(code),
        "weather_label": _wmo_label(code),
        "time": cw.get("time"),
        "message": f"{_wmo_icon(code)} Météo actuelle récupérée avec succès.",
    }


@tool(
    name="prévision_météo_7j",
    description=(
        "Renvoie les prévisions météo journalières (température min/max, code météo) "
        "pour un nombre de jours (par défaut 7) à partir d’un point géographique. "
        "Accepte latitude/longitude ou le nom d’une ville."
    ),
    parameters={
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number",
                "description": "Latitude décimale."
            },
            "longitude": {
                "type": "number",
                "description": "Longitude décimale."
            },
            "city": {
                "type": "string",
                "description": "Nom de la ville à géocoder si latitude/longitude absents."
            },
            "days": {
                "type": "integer",
                "description": "Nombre de jours de prévision (max = 16). Valeur par défaut = 7.",
                "minimum": 1,
                "maximum": 16,
            },
            "timezone": {
                "type": "string",
                "description": "Fuseau horaire (ex : \"Europe/Paris\"). Valeur par défaut : \"auto\"."
            },
        },
        "required": [],
    },
)
def prévision_météo_7j(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    days: int = 7,
    timezone: str = "auto",
) -> dict:
    # Validation du nombre de jours (Open‑Meteo accepte jusqu’à 16 jours pour le daily)
    if not (1 <= days <= 16):
        return {
            "status": "error",
            "error": "Le paramètre `days` doit être compris entre 1 et 16.",
        }

    coords = _prepare_coordinates(latitude, longitude, city)
    if not coords:
        return {
            "status": "error",
            "error": "Impossible de déterminer les coordonnées. Fournissez latitude/longitude ou un nom de ville valide.",
        }

    params = {
        "latitude": coords["latitude"],
        "longitude": coords["longitude"],
        "daily": "weathercode,temperature_2m_max,temperature_2m_min",
        "timezone": timezone,
        "forecast_days": days,
    }
    data = _call_open_meteo("forecast", params)
    if not data or "daily" not in data:
        return {
            "status": "error",
            "error": "L’API Open‑Meteo n’a pas retourné de prévisions journalières.",
        }

    daily = data["daily"]
    forecast: List[Dict[str, Any]] = []
    for i, date in enumerate(daily.get("time", [])):
        code = daily["weathercode"][i]
        forecast.append({
            "date": date,
            "weathercode": code,
            "weather_icon": _wmo_icon(code),
            "weather_label": _wmo_label(code),
            "temp_min_c": daily["temperature_2m_min"][i],
            "temp_max_c": daily["temperature_2m_max"][i],
        })

    return {
        "status": "success",
        "city": city or "",
        "latitude": coords["latitude"],
        "longitude": coords["longitude"],
        "timezone": data.get("timezone", timezone),
        "forecast_days_requested": days,
        "forecast": forecast,
        "message": f"Prévisions météo sur {days} jours récupérées avec succès.",
    }
