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
tools/data_tools.py — Outils de manipulation de données et de dates
====================================================================

Outils exposés (18) :

  DATES & TEMPS
  - datetime_now            : date et heure actuelles, formatables
  - datetime_parse          : parser une date en format arbitraire / langage naturel
  - datetime_diff           : calculer l'écart entre deux dates
  - datetime_range          : générer une liste de dates entre deux bornes
  - datetime_convert_tz     : convertir un datetime entre fuseaux horaires

  TEXTE & CHAÎNES
  - text_regex              : recherche, extraction, remplacement par expression régulière
  - text_stats              : statistiques sur un texte (mots, phrases, fréquences…)
  - text_diff               : diff ligne à ligne entre deux textes
  - text_template           : rendu d'un template avec variables (mini-moteur)

  JSON & STRUCTURES
  - json_formatter          : validation, formatage et extraction dans un JSON
  - json_diff               : comparer deux JSONs et retourner les différences
  - json_schema_infer       : inférer le JSON Schema d'un objet JSON
  - json_flatten            : aplatir un JSON imbriqué en dictionnaire plat
  - json_transform          : filtrer / projeter / trier un JSON

  ENCODAGE / HASH
  - encode_decode           : base64, URL encoding, HTML entities, ROT13
  - hash_text               : MD5, SHA1, SHA256 d'une chaîne ou d'un fichier

  NOMBRES & STATISTIQUES
  - number_format           : formater un nombre (milliers, devises, notation…)
  - stats_describe          : statistiques descriptives sur une liste de nombres

Ce module s'enregistre automatiquement dans tools_engine au premier import.

Usage :
    import tools.data_tools   # suffit à enregistrer les outils
"""

import base64
import collections
import datetime
import difflib
import hashlib
import html
import json
import math
import re
import statistics
import string
import urllib.parse
import zoneinfo
from typing import Any, Optional

from core.tools_engine import tool, set_current_family, _TOOL_ICONS

set_current_family("data_tools", "Données", "📅")

# ── Icônes UI ──────────────────────────────────────────────────────────────
_TOOL_ICONS.update({
    "datetime_now":        "🕐",
    "datetime_parse":      "📆",
    "datetime_diff":       "⏱️",
    "datetime_range":      "📅",
    "datetime_convert_tz": "🌍",
    "text_regex":          "🔍",
    "text_stats":          "📊",
    "text_diff":           "↔️",
    "text_template":       "📝",
    "json_formatter":      "{}",
    "json_diff":           "🔀",
    "json_schema_infer":   "🗂️",
    "json_flatten":        "⬇️",
    "json_transform":      "⚙️",
    "encode_decode":       "🔐",
    "hash_text":           "#️⃣",
    "number_format":       "🔢",
    "stats_describe":      "📈",
})

# ── Helpers internes ───────────────────────────────────────────────────────

# Jours fériés français (liste fixe pour les calculs de jours ouvrés)
# Format : (mois, jour) — fêtes fixes uniquement (Pâques non inclus)
_JOURS_FERIES_FIXES = {
    (1,  1),  # Jour de l'an
    (5,  1),  # Fête du Travail
    (5,  8),  # Victoire 1945
    (7, 14),  # Fête Nationale
    (8, 15),  # Assomption
    (11, 1),  # Toussaint
    (11,11),  # Armistice
    (12,25),  # Noël
}


def _paques(annee: int) -> datetime.date:
    """Calcule la date de Pâques (algorithme de Butcher)."""
    a = annee % 19
    b, c = divmod(annee, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(114 + h + l - 7 * m, 31)
    return datetime.date(annee, mois, jour + 1)


def _jours_feries_annee(annee: int) -> set[datetime.date]:
    """Retourne l'ensemble des jours fériés français pour une année donnée."""
    feries = {datetime.date(annee, m, j) for m, j in _JOURS_FERIES_FIXES}
    paques = _paques(annee)
    feries.add(paques + datetime.timedelta(days=1))   # Lundi de Pâques
    feries.add(paques + datetime.timedelta(days=39))  # Ascension
    feries.add(paques + datetime.timedelta(days=50))  # Lundi de Pentecôte
    return feries


def _parse_date_flexible(s: str) -> datetime.datetime:
    """
    Tente de parser une date depuis un grand nombre de formats courants.
    Lève ValueError si aucun format ne correspond.
    """
    s = s.strip()

    # Formats classiques à tester dans l'ordre
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%m/%d/%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y %H:%M",
        "%d/%m/%y",
        "%Y%m%d",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue

    # Tentative avec les mois en français
    mois_fr = {
        "janvier": "01", "février": "02", "mars": "03", "avril": "04",
        "mai": "05", "juin": "06", "juillet": "07", "août": "08",
        "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12",
    }
    sl = s.lower()
    for nom, num in mois_fr.items():
        if nom in sl:
            sl2 = sl.replace(nom, num)
            for fmt in ("%d %m %Y", "%d %m %Y %H:%M"):
                try:
                    return datetime.datetime.strptime(sl2, fmt)
                except ValueError:
                    continue

    raise ValueError(f"Format de date non reconnu : '{s}'")


def _jours_ouvrés(d1: datetime.date, d2: datetime.date) -> int:
    """Compte les jours ouvrés (lun-ven hors fériés FR) entre deux dates incluses."""
    if d1 > d2:
        d1, d2 = d2, d1
    annees = range(d1.year, d2.year + 1)
    feries: set[datetime.date] = set()
    for a in annees:
        feries |= _jours_feries_annee(a)

    count = 0
    cur = d1
    while cur <= d2:
        if cur.weekday() < 5 and cur not in feries:
            count += 1
        cur += datetime.timedelta(days=1)
    return count


# ── SECTION 1 : DATES & TEMPS ───────────────────────────────────────────────

@tool(
    name="datetime_now",
    description=(
        "Retourne la date et l'heure actuelles du système. "
        "Le format de sortie peut être personnalisé via une chaîne strftime "
        "(ex: '%d/%m/%Y %H:%M'). Par défaut, retourne la date au format ISO 8601."
    ),
    parameters={
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": (
                    "Format strftime optionnel, ex: '%d/%m/%Y %H:%M:%S', "
                    "'%A %d %B %Y'. "
                    "Si absent, le format ISO 8601 est utilisé."
                ),
            },
        },
        "required": [],
    },
)
def datetime_now(format: Optional[str] = None) -> str:
    now = datetime.datetime.now()
    if format:
        try:
            return now.strftime(format)
        except Exception as e:
            return f"Format invalide : {e}"
    return now.isoformat(sep=" ", timespec="seconds")


@tool(
    name="datetime_parse",
    description=(
        "Parse une date exprimée dans un format arbitraire et la normalise. "
        "Supporte les formats ISO, DD/MM/YYYY, MM/DD/YYYY, avec heures, "
        "noms de mois en français et en anglais, etc. "
        "Retourne la date normalisée dans plusieurs formats utiles."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date_string": {
                "type": "string",
                "description": (
                    "Chaîne de date à parser, ex: '25/12/2024', '2024-12-25T14:30', "
                    "'25 décembre 2024', 'Dec 25, 2024'."
                ),
            },
            "format_entree": {
                "type": "string",
                "description": (
                    "Format strftime explicite si la détection automatique échoue, "
                    "ex: '%d/%m/%Y %H:%M'. Optionnel."
                ),
            },
        },
        "required": ["date_string"],
    },
)
def datetime_parse(date_string: str, format_entree: Optional[str] = None) -> dict:
    try:
        if format_entree:
            dt = datetime.datetime.strptime(date_string.strip(), format_entree)
        else:
            dt = _parse_date_flexible(date_string)

        jours_semaine_fr = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        mois_fr = [
            "", "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"
        ]

        return {
            "status": "success",
            "input": date_string,
            "iso":           dt.isoformat(sep="T", timespec="seconds"),
            "iso_date":      dt.strftime("%Y-%m-%d"),
            "fr_court":      dt.strftime("%d/%m/%Y"),
            "fr_long":       f"{jours_semaine_fr[dt.weekday()]} {dt.day} {mois_fr[dt.month]} {dt.year}",
            "fr_datetime":   dt.strftime("%d/%m/%Y %H:%M:%S") if dt.hour or dt.minute else dt.strftime("%d/%m/%Y"),
            "timestamp_unix": int(dt.timestamp()),
            "jour_semaine":  jours_semaine_fr[dt.weekday()],
            "numero_semaine": dt.isocalendar()[1],
            "trimestre":     f"T{((dt.month - 1) // 3) + 1} {dt.year}",
            "est_week_end":  dt.weekday() >= 5,
            "est_ferie_fr":  dt.date() in _jours_feries_annee(dt.year),
        }
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e),
            "formats_suggeres": [
                "YYYY-MM-DD", "DD/MM/YYYY", "DD/MM/YYYY HH:MM",
                "DD Month YYYY", "Month DD, YYYY",
            ],
        }
    except Exception as e:
        return {"status": "error", "error": f"Erreur inattendue : {e}"}


@tool(
    name="datetime_diff",
    description=(
        "Calcule l'écart entre deux dates. "
        "Retourne la différence en jours calendaires, jours ouvrés (France), "
        "semaines, mois et années. "
        "Utile pour calculer une durée, une ancienneté, un délai."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date_debut": {
                "type": "string",
                "description": "Date de début (tout format reconnu par datetime_parse).",
            },
            "date_fin": {
                "type": "string",
                "description": (
                    "Date de fin (tout format reconnu par datetime_parse). "
                    "Si absent, utilise la date du jour."
                ),
            },
            "inclure_jours_ouvrés": {
                "type": "boolean",
                "default": True,
                "description": "Calculer les jours ouvrés (lun-ven hors fériés FR). Défaut: true.",
            },
        },
        "required": ["date_debut"],
    },
)
def datetime_diff(
    date_debut: str,
    date_fin: Optional[str] = None,
    inclure_jours_ouvrés: bool = True,
) -> dict:
    try:
        dt1 = _parse_date_flexible(date_debut)
        dt2 = _parse_date_flexible(date_fin) if date_fin else datetime.datetime.now()

        delta = dt2 - dt1
        jours_total = delta.days
        signe = 1 if jours_total >= 0 else -1

        d1, d2 = dt1.date(), dt2.date()
        if d1 > d2:
            d1, d2 = d2, d1

        # Différence en mois / années
        annees = d2.year - d1.year
        mois_total = annees * 12 + (d2.month - d1.month)
        if d2.day < d1.day:
            mois_total -= 1
        annees_exactes = mois_total // 12
        mois_restants = mois_total % 12

        result = {
            "status": "success",
            "date_debut": dt1.strftime("%d/%m/%Y"),
            "date_fin":   dt2.strftime("%d/%m/%Y"),
            "jours_calendaires": jours_total,
            "semaines":          round(jours_total / 7, 2),
            "mois_approximatif": round(jours_total / 30.44, 2),
            "mois_exacts":       mois_total,
            "decomposition":     f"{annees_exactes} an(s) {mois_restants} mois",
            "sens":              "futur" if signe >= 0 else "passé",
        }

        if inclure_jours_ouvrés:
            result["jours_ouvres"] = _jours_ouvrés(d1, d2)

        return result

    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Erreur inattendue : {e}"}


@tool(
    name="datetime_range",
    description=(
        "Génère une liste de dates entre deux bornes. "
        "Utile pour créer des axes temporels, des séries de données, "
        "des plannings ou vérifier des continuités de dates."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date_debut": {
                "type": "string",
                "description": "Date de début (tout format reconnu).",
            },
            "date_fin": {
                "type": "string",
                "description": "Date de fin (incluse).",
            },
            "pas": {
                "type": "string",
                "enum": ["jour", "jour_ouvre", "semaine", "mois", "trimestre", "année"],
                "default": "jour",
                "description": (
                    "Incrément entre chaque date. "
                    "jour_ouvre exclut les week-ends et fériés FR. "
                    "Défaut: 'jour'."
                ),
            },
            "format_sortie": {
                "type": "string",
                "default": "%Y-%m-%d",
                "description": "Format strftime des dates en sortie. Défaut: '%Y-%m-%d'.",
            },
            "max_dates": {
                "type": "integer",
                "default": 500,
                "description": "Nombre maximum de dates à générer (défaut: 500, max: 2000).",
            },
        },
        "required": ["date_debut", "date_fin"],
    },
)
def datetime_range(
    date_debut: str,
    date_fin: str,
    pas: str = "jour",
    format_sortie: str = "%Y-%m-%d",
    max_dates: int = 500,
) -> dict:
    try:
        dt1 = _parse_date_flexible(date_debut).date()
        dt2 = _parse_date_flexible(date_fin).date()
        if dt1 > dt2:
            dt1, dt2 = dt2, dt1

        max_dates = min(max_dates, 2000)
        dates = []
        cur = dt1

        # Collecte des fériés pour toute la période
        feries: set[datetime.date] = set()
        if pas == "jour_ouvre":
            for a in range(dt1.year, dt2.year + 1):
                feries |= _jours_feries_annee(a)

        while cur <= dt2 and len(dates) < max_dates:
            if pas == "jour_ouvre":
                if cur.weekday() < 5 and cur not in feries:
                    dates.append(cur.strftime(format_sortie))
                cur += datetime.timedelta(days=1)
            elif pas == "jour":
                dates.append(cur.strftime(format_sortie))
                cur += datetime.timedelta(days=1)
            elif pas == "semaine":
                dates.append(cur.strftime(format_sortie))
                cur += datetime.timedelta(weeks=1)
            elif pas == "mois":
                dates.append(cur.strftime(format_sortie))
                # Avancer d'un mois
                mois = cur.month + 1
                annee = cur.year + (mois - 1) // 12
                mois = ((mois - 1) % 12) + 1
                jour = min(cur.day, [31,28+(1 if annee%4==0 and (annee%100!=0 or annee%400==0) else 0),31,30,31,30,31,31,30,31,30,31][mois-1])
                cur = datetime.date(annee, mois, jour)
            elif pas == "trimestre":
                dates.append(cur.strftime(format_sortie))
                mois = cur.month + 3
                annee = cur.year + (mois - 1) // 12
                mois = ((mois - 1) % 12) + 1
                jour = min(cur.day, [31,28+(1 if annee%4==0 and (annee%100!=0 or annee%400==0) else 0),31,30,31,30,31,31,30,31,30,31][mois-1])
                cur = datetime.date(annee, mois, jour)
            elif pas == "année":
                dates.append(cur.strftime(format_sortie))
                try:
                    cur = datetime.date(cur.year + 1, cur.month, cur.day)
                except ValueError:
                    cur = datetime.date(cur.year + 1, cur.month, 28)

        tronque = cur <= dt2 and len(dates) >= max_dates

        return {
            "status": "success",
            "nb_dates": len(dates),
            "dates": dates,
            "tronque": tronque,
            "message": f"Tronqué à {max_dates} dates (max_dates)" if tronque else None,
        }

    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"Erreur inattendue : {e}"}


@tool(
    name="datetime_convert_tz",
    description=(
        "Convertit un datetime d'un fuseau horaire vers un autre. "
        "Supporte tous les fuseaux IANA (Europe/Paris, America/New_York, UTC, Asia/Tokyo…). "
        "Si le datetime source n'a pas de fuseau, il est supposé dans le fuseau source."
    ),
    parameters={
        "type": "object",
        "properties": {
            "datetime_string": {
                "type": "string",
                "description": "Date et heure à convertir, ex: '2024-06-15 14:30:00'.",
            },
            "tz_source": {
                "type": "string",
                "default": "Europe/Paris",
                "description": (
                    "Fuseau horaire source (IANA), ex: 'Europe/Paris', 'UTC', "
                    "'America/New_York'. Défaut: 'Europe/Paris'."
                ),
            },
            "tz_cible": {
                "type": "string",
                "description": "Fuseau horaire cible (IANA), ex: 'America/Los_Angeles'.",
            },
        },
        "required": ["datetime_string", "tz_cible"],
    },
)
def datetime_convert_tz(
    datetime_string: str,
    tz_cible: str,
    tz_source: str = "Europe/Paris",
) -> dict:
    try:
        dt_naive = _parse_date_flexible(datetime_string)

        try:
            tz_src = zoneinfo.ZoneInfo(tz_source)
        except zoneinfo.ZoneInfoNotFoundError:
            return {"status": "error", "error": f"Fuseau source inconnu : '{tz_source}'"}

        try:
            tz_dst = zoneinfo.ZoneInfo(tz_cible)
        except zoneinfo.ZoneInfoNotFoundError:
            return {"status": "error", "error": f"Fuseau cible inconnu : '{tz_cible}'"}

        dt_src = dt_naive.replace(tzinfo=tz_src)
        dt_dst = dt_src.astimezone(tz_dst)

        # Décalage en heures
        offset_src = dt_src.utcoffset()
        offset_dst = dt_dst.utcoffset()
        diff_h = (offset_dst - offset_src).total_seconds() / 3600

        return {
            "status": "success",
            "source": {
                "datetime": dt_src.strftime("%d/%m/%Y %H:%M:%S"),
                "fuseau": tz_source,
                "offset_utc": str(offset_src),
            },
            "cible": {
                "datetime": dt_dst.strftime("%d/%m/%Y %H:%M:%S"),
                "iso": dt_dst.isoformat(timespec="seconds"),
                "fuseau": tz_cible,
                "offset_utc": str(offset_dst),
            },
            "difference_heures": diff_h,
            "description": f"{tz_cible} est {'+' if diff_h >= 0 else ''}{diff_h:.1f}h par rapport à {tz_source}",
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


# ── SECTION 2 : TEXTE & CHAÎNES ────────────────────────────────────────────

@tool(
    name="text_regex",
    description=(
        "Applique une expression régulière (regex) sur un texte. "
        "Modes disponibles : recherche (trouver toutes les occurrences), "
        "extraction (groupes capturants), remplacement, validation (booléen), "
        "split (découper). "
        "Supporte les flags : ignorer la casse, multiline, dotall."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texte": {
                "type": "string",
                "description": "Texte sur lequel appliquer la regex.",
            },
            "pattern": {
                "type": "string",
                "description": (
                    "Expression régulière Python, ex: r'\\d+', "
                    "r'(\\w+)@(\\w+\\.\\w+)', r'^[A-Z]'."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["chercher", "extraire", "remplacer", "valider", "split"],
                "default": "chercher",
                "description": (
                    "Mode d'opération : "
                    "chercher = toutes les occurrences, "
                    "extraire = groupes capturants nommés ou numérotés, "
                    "remplacer = substitution, "
                    "valider = true/false si le pattern correspond, "
                    "split = découper le texte. "
                    "Défaut: 'chercher'."
                ),
            },
            "remplacement": {
                "type": "string",
                "description": "Chaîne de remplacement (requis pour mode='remplacer').",
            },
            "ignorer_casse": {
                "type": "boolean",
                "default": False,
                "description": "Ignorer la casse (re.IGNORECASE). Défaut: false.",
            },
            "multiline": {
                "type": "boolean",
                "default": False,
                "description": "^ et $ correspondent à chaque ligne (re.MULTILINE). Défaut: false.",
            },
            "max_resultats": {
                "type": "integer",
                "default": 100,
                "description": "Nombre maximum de résultats retournés. Défaut: 100.",
            },
        },
        "required": ["texte", "pattern"],
    },
)
def text_regex(
    texte: str,
    pattern: str,
    mode: str = "chercher",
    remplacement: Optional[str] = None,
    ignorer_casse: bool = False,
    multiline: bool = False,
    max_resultats: int = 100,
) -> dict:
    try:
        flags = 0
        if ignorer_casse:
            flags |= re.IGNORECASE
        if multiline:
            flags |= re.MULTILINE

        compiled = re.compile(pattern, flags)

        if mode == "valider":
            match = compiled.search(texte)
            return {
                "status": "success",
                "valide": match is not None,
                "position": (match.start(), match.end()) if match else None,
            }

        elif mode == "chercher":
            matches = list(compiled.finditer(texte))[:max_resultats]
            resultats = [
                {
                    "texte": m.group(0),
                    "debut": m.start(),
                    "fin": m.end(),
                    "groupes": list(m.groups()) if m.groups() else None,
                }
                for m in matches
            ]
            return {
                "status": "success",
                "nb_occurrences": len(resultats),
                "resultats": resultats,
                "tronque": len(list(compiled.finditer(texte))) > max_resultats,
            }

        elif mode == "extraire":
            matches = list(compiled.finditer(texte))[:max_resultats]
            resultats = []
            for m in matches:
                entry: dict = {"match": m.group(0)}
                if compiled.groupindex:
                    # Groupes nommés
                    entry["groupes_nommes"] = m.groupdict()
                elif m.groups():
                    entry["groupes"] = list(m.groups())
                resultats.append(entry)
            return {
                "status": "success",
                "nb_occurrences": len(resultats),
                "resultats": resultats,
            }

        elif mode == "remplacer":
            if remplacement is None:
                return {"status": "error", "error": "Paramètre 'remplacement' requis pour le mode 'remplacer'."}
            resultat = compiled.sub(remplacement, texte)
            nb = len(compiled.findall(texte))
            return {
                "status": "success",
                "texte_original": texte,
                "texte_modifie": resultat,
                "nb_remplacements": nb,
            }

        elif mode == "split":
            parties = compiled.split(texte)[:max_resultats + 1]
            return {
                "status": "success",
                "nb_parties": len(parties),
                "parties": parties,
            }

        else:
            return {"status": "error", "error": f"Mode inconnu : '{mode}'"}

    except re.error as e:
        return {"status": "error", "error": f"Regex invalide : {e}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="text_stats",
    description=(
        "Calcule des statistiques sur un texte : "
        "nombre de caractères, mots, phrases, paragraphes, "
        "fréquence des mots (top N), temps de lecture estimé, "
        "score de lisibilité de Flesch (approximation)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texte": {
                "type": "string",
                "description": "Texte à analyser.",
            },
            "top_mots": {
                "type": "integer",
                "default": 10,
                "description": "Nombre de mots les plus fréquents à retourner. Défaut: 10.",
            },
            "langue": {
                "type": "string",
                "enum": ["fr", "en"],
                "default": "fr",
                "description": "Langue pour les mots vides (stop words). Défaut: 'fr'.",
            },
        },
        "required": ["texte"],
    },
)
def text_stats(texte: str, top_mots: int = 10, langue: str = "fr") -> dict:
    try:
        # ── Métriques de base ──
        nb_caract = len(texte)
        nb_caract_sans_espaces = len(texte.replace(" ", "").replace("\n", "").replace("\t", ""))
        mots = re.findall(r"\b\w+\b", texte)
        nb_mots = len(mots)

        # Phrases : terminées par . ! ?
        phrases = re.split(r"[.!?]+", texte)
        nb_phrases = len([p for p in phrases if p.strip()])

        # Paragraphes : séparés par une ligne vide
        paras = re.split(r"\n\s*\n", texte.strip())
        nb_paras = len([p for p in paras if p.strip()])

        # Syllabes (approximation : voyelles contiguës)
        def _syllabes(mot: str) -> int:
            return max(1, len(re.findall(r"[aeiouyàâéèêëîïôùûü]+", mot.lower())))

        nb_syllabes = sum(_syllabes(m) for m in mots)

        # ── Temps de lecture ──
        # Vitesse moyenne : 200 mots/min
        secondes_lecture = nb_mots / 200 * 60
        if secondes_lecture < 60:
            temps_lecture = f"{int(secondes_lecture)} secondes"
        else:
            mins = int(secondes_lecture // 60)
            secs = int(secondes_lecture % 60)
            temps_lecture = f"{mins} min {secs} s"

        # ── Score de Flesch (approximation française) ──
        moy_mots_phrase = nb_mots / max(nb_phrases, 1)
        moy_syllabes_mot = nb_syllabes / max(nb_mots, 1)
        flesch = 206.835 - 1.015 * moy_mots_phrase - 84.6 * moy_syllabes_mot
        flesch = max(0, min(100, round(flesch, 1)))

        if flesch >= 70:
            lisibilite = "Facile"
        elif flesch >= 50:
            lisibilite = "Moyen"
        elif flesch >= 30:
            lisibilite = "Difficile"
        else:
            lisibilite = "Très difficile"

        # ── Fréquence des mots ──
        stop_fr = {
            "le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
            "à", "au", "aux", "il", "elle", "ils", "elles", "je", "tu", "nous",
            "vous", "on", "se", "ce", "que", "qui", "ne", "pas", "plus",
            "par", "pour", "sur", "dans", "avec", "est", "son", "sa", "ses",
            "leur", "leurs", "y", "ou", "mais", "si", "car", "donc",
        }
        stop_en = {
            "the", "a", "an", "in", "on", "at", "to", "for", "of", "and",
            "or", "but", "is", "are", "was", "were", "be", "been", "have",
            "has", "had", "do", "does", "did", "it", "its", "i", "you",
            "he", "she", "we", "they", "this", "that", "with", "from", "by",
        }
        stop = stop_fr if langue == "fr" else stop_en

        freq = collections.Counter(
            m.lower() for m in mots
            if m.lower() not in stop and len(m) > 2
        )
        top = [{"mot": mot, "occurrences": n} for mot, n in freq.most_common(top_mots)]

        # ── Diversité lexicale ──
        mots_uniques = len(set(m.lower() for m in mots))
        ttr = round(mots_uniques / max(nb_mots, 1) * 100, 1)  # Type-Token Ratio

        return {
            "status": "success",
            "caracteres":              nb_caract,
            "caracteres_sans_espaces": nb_caract_sans_espaces,
            "mots":                    nb_mots,
            "mots_uniques":            mots_uniques,
            "diversite_lexicale_pct":  ttr,
            "phrases":                 nb_phrases,
            "paragraphes":             nb_paras,
            "syllabes":                nb_syllabes,
            "moy_mots_par_phrase":     round(moy_mots_phrase, 1),
            "moy_syllabes_par_mot":    round(moy_syllabes_mot, 2),
            "temps_lecture":           temps_lecture,
            "score_flesch":            flesch,
            "lisibilite":              lisibilite,
            "top_mots":                top,
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="text_diff",
    description=(
        "Compare deux textes ligne à ligne et retourne leurs différences "
        "(style git diff). "
        "Affiche les lignes ajoutées (+), supprimées (-) et inchangées. "
        "Utile pour comparer des versions de documents, du code, des configurations."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texte_a": {
                "type": "string",
                "description": "Texte original (version A).",
            },
            "texte_b": {
                "type": "string",
                "description": "Texte modifié (version B).",
            },
            "mode": {
                "type": "string",
                "enum": ["unifie", "cote_a_cote", "resume"],
                "default": "unifie",
                "description": (
                    "Format de sortie : "
                    "unifie = diff unifié (style git), "
                    "cote_a_cote = colonnes A/B, "
                    "resume = métriques uniquement. "
                    "Défaut: 'unifie'."
                ),
            },
            "contexte": {
                "type": "integer",
                "default": 3,
                "description": "Nombre de lignes de contexte autour des modifications. Défaut: 3.",
            },
            "ignorer_casse": {
                "type": "boolean",
                "default": False,
                "description": "Ignorer les différences de casse. Défaut: false.",
            },
            "ignorer_espaces": {
                "type": "boolean",
                "default": False,
                "description": "Ignorer les espaces en début/fin de ligne. Défaut: false.",
            },
        },
        "required": ["texte_a", "texte_b"],
    },
)
def text_diff(
    texte_a: str,
    texte_b: str,
    mode: str = "unifie",
    contexte: int = 3,
    ignorer_casse: bool = False,
    ignorer_espaces: bool = False,
) -> dict:
    try:
        def _preparer(t: str) -> list[str]:
            lignes = t.splitlines(keepends=True)
            if ignorer_espaces:
                lignes = [l.strip() + "\n" for l in lignes]
            if ignorer_casse:
                lignes = [l.lower() for l in lignes]
            return lignes

        lignes_a = _preparer(texte_a)
        lignes_b = _preparer(texte_b)

        # Métriques
        ajoutees   = sum(1 for l in difflib.ndiff(lignes_a, lignes_b) if l.startswith("+ "))
        supprimees = sum(1 for l in difflib.ndiff(lignes_a, lignes_b) if l.startswith("- "))
        identiques = len(lignes_a) + len(lignes_b) - ajoutees - supprimees
        similitude = difflib.SequenceMatcher(None, texte_a, texte_b).ratio()

        if mode == "resume":
            return {
                "status": "success",
                "lignes_a": len(lignes_a),
                "lignes_b": len(lignes_b),
                "lignes_ajoutees":   ajoutees,
                "lignes_supprimees": supprimees,
                "similitude_pct":    round(similitude * 100, 1),
                "identiques":        texte_a == texte_b,
            }

        elif mode == "unifie":
            diff_lines = list(difflib.unified_diff(
                lignes_a, lignes_b,
                fromfile="version_A",
                tofile="version_B",
                n=contexte,
            ))
            return {
                "status": "success",
                "diff_unifie": "".join(diff_lines),
                "lignes_ajoutees":   ajoutees,
                "lignes_supprimees": supprimees,
                "similitude_pct":    round(similitude * 100, 1),
                "nb_blocs": sum(1 for l in diff_lines if l.startswith("@@")),
            }

        elif mode == "cote_a_cote":
            matcher = difflib.SequenceMatcher(None, lignes_a, lignes_b)
            comparaison = []
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal":
                    for la, lb in zip(lignes_a[i1:i2], lignes_b[j1:j2]):
                        comparaison.append({"statut": "=", "a": la.rstrip(), "b": lb.rstrip()})
                elif tag == "replace":
                    for la in lignes_a[i1:i2]:
                        comparaison.append({"statut": "-", "a": la.rstrip(), "b": None})
                    for lb in lignes_b[j1:j2]:
                        comparaison.append({"statut": "+", "a": None, "b": lb.rstrip()})
                elif tag == "delete":
                    for la in lignes_a[i1:i2]:
                        comparaison.append({"statut": "-", "a": la.rstrip(), "b": None})
                elif tag == "insert":
                    for lb in lignes_b[j1:j2]:
                        comparaison.append({"statut": "+", "a": None, "b": lb.rstrip()})
            return {
                "status": "success",
                "comparaison": comparaison,
                "lignes_ajoutees":   ajoutees,
                "lignes_supprimees": supprimees,
                "similitude_pct":    round(similitude * 100, 1),
            }

        else:
            return {"status": "error", "error": f"Mode inconnu : '{mode}'"}

    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="text_template",
    description=(
        "Remplace des variables dans un template texte. "
        "Deux syntaxes supportées : "
        "simple ({{variable}} ou {variable}) et "
        "conditionnelle ({% if variable %}...{% endif %}). "
        "Utile pour générer des emails, des rapports, des messages personnalisés."
    ),
    parameters={
        "type": "object",
        "properties": {
            "template": {
                "type": "string",
                "description": (
                    "Template texte avec des marqueurs de variables. "
                    "Syntaxe : {{nom}}, {{prenom|majuscule}}, "
                    "{% if condition %}texte{% endif %}."
                ),
            },
            "variables": {
                "type": "object",
                "description": (
                    "Dictionnaire des variables à injecter, "
                    "ex: {\"nom\": \"Dupont\", \"montant\": 1500}."
                ),
            },
            "syntaxe": {
                "type": "string",
                "enum": ["double_accolades", "accolades_simples", "auto"],
                "default": "auto",
                "description": (
                    "Syntaxe de marqueurs : "
                    "double_accolades = {{var}}, "
                    "accolades_simples = {var} (style Python str.format), "
                    "auto = détecte automatiquement. "
                    "Défaut: 'auto'."
                ),
            },
        },
        "required": ["template", "variables"],
    },
)
def text_template(
    template: str,
    variables: dict,
    syntaxe: str = "auto",
) -> dict:
    try:
        # Convertir toutes les valeurs en str pour le rendu
        vars_str = {k: str(v) for k, v in variables.items()}

        # Détection automatique
        if syntaxe == "auto":
            if "{{" in template:
                syntaxe = "double_accolades"
            else:
                syntaxe = "accolades_simples"

        result = template

        # ── Traitements conditionnels {% if var %}...{% endif %} ──
        def _eval_if(m: re.Match) -> str:
            cond = m.group(1).strip()
            contenu = m.group(2)
            # Condition vraie si la variable existe et n'est pas vide/false
            val = variables.get(cond, "")
            return contenu if val and str(val).lower() not in ("false", "0", "") else ""

        result = re.sub(r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}", _eval_if, result, flags=re.DOTALL)

        # ── Filtres intégrés ──
        def _appliquer_filtre(val: str, filtre: str) -> str:
            filtres = {
                "majuscule": str.upper,
                "minuscule": str.lower,
                "titre":     str.title,
                "capitalise": str.capitalize,
                "strip":     str.strip,
            }
            f = filtres.get(filtre.strip())
            return f(val) if f else val

        if syntaxe == "double_accolades":
            def _remplacer(m: re.Match) -> str:
                expr = m.group(1).strip()
                if "|" in expr:
                    nom, filtre = expr.split("|", 1)
                    val = vars_str.get(nom.strip(), m.group(0))
                    return _appliquer_filtre(val, filtre)
                return vars_str.get(expr, m.group(0))

            result = re.sub(r"\{\{([^}]+)\}\}", _remplacer, result)

        else:  # accolades simples
            # Gestion des filtres dans {var|filtre}
            def _remplacer_simple(m: re.Match) -> str:
                expr = m.group(1).strip()
                if "|" in expr:
                    nom, filtre = expr.split("|", 1)
                    val = vars_str.get(nom.strip(), m.group(0))
                    return _appliquer_filtre(val, filtre)
                return vars_str.get(expr, m.group(0))

            result = re.sub(r"\{([^{}]+)\}", _remplacer_simple, result)

        # Variables non résolues
        non_resolues_dd = re.findall(r"\{\{(\w+)\}\}", result)
        non_resolues_s  = re.findall(r"\{(\w+)\}", result)
        non_resolues = list(set(non_resolues_dd + non_resolues_s))

        return {
            "status": "success",
            "resultat": result,
            "variables_utilisees": list(vars_str.keys()),
            "variables_non_resolues": non_resolues,
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


# ── SECTION 3 : JSON & STRUCTURES ──────────────────────────────────────────

@tool(
    name="json_formatter",
    description=(
        "Valide et formate une chaîne JSON en JSON indenté lisible. "
        "Peut également extraire une valeur imbriquée via un chemin de clés "
        "séparées par des points (ex: 'data.users.0.name' pour accéder à "
        "users[0].name dans l'objet data). "
        "Retourne une erreur descriptive si le JSON est invalide."
    ),
    parameters={
        "type": "object",
        "properties": {
            "json_string": {
                "type": "string",
                "description": "Chaîne JSON à analyser et formater.",
            },
            "key_path": {
                "type": "string",
                "description": (
                    "Chemin de clés séparé par '.', ex: 'data.users.0.name'. "
                    "Les indices de tableau sont exprimés en entiers. "
                    "Si absent, le JSON complet est retourné formaté."
                ),
            },
        },
        "required": ["json_string"],
    },
)
def json_formatter(json_string: str, key_path: Optional[str] = None) -> str:
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as e:
        line = getattr(e, "lineno", "?")
        col  = getattr(e, "colno",  "?")
        return f"JSON invalide (ligne {line}, col {col}) : {e.msg}"

    if not key_path:
        return json.dumps(data, ensure_ascii=False, indent=2)

    current = data
    parts   = key_path.split(".")
    for i, key in enumerate(parts):
        try:
            if isinstance(current, list):
                current = current[int(key)]
            elif isinstance(current, dict):
                current = current[key]
            else:
                traversed = ".".join(parts[:i])
                return (
                    f"Impossible de naviguer au-delà de '{traversed}' "
                    f"(type : {type(current).__name__})."
                )
        except (KeyError, IndexError, ValueError) as e:
            traversed = ".".join(parts[:i]) or "(racine)"
            return f"Clé/index introuvable à '{traversed}' : {e}"

    return json.dumps(current, ensure_ascii=False, indent=2)


@tool(
    name="json_diff",
    description=(
        "Compare deux objets JSON et retourne leurs différences structurelles. "
        "Identifie les clés ajoutées, supprimées, modifiées et inchangées "
        "à tous les niveaux d'imbrication. "
        "Retourne un résumé et le détail des changements."
    ),
    parameters={
        "type": "object",
        "properties": {
            "json_a": {
                "type": "string",
                "description": "Premier JSON (version A / originale).",
            },
            "json_b": {
                "type": "string",
                "description": "Second JSON (version B / modifiée).",
            },
            "ignorer_cles": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste de clés à ignorer dans la comparaison, ex: ['updated_at', 'id'].",
            },
        },
        "required": ["json_a", "json_b"],
    },
)
def json_diff(
    json_a: str,
    json_b: str,
    ignorer_cles: Optional[list] = None,
) -> dict:
    try:
        a = json.loads(json_a)
        b = json.loads(json_b)
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"JSON invalide : {e}"}

    ignorer = set(ignorer_cles or [])
    differences = []

    def _diff(obj_a: Any, obj_b: Any, chemin: str = "") -> None:
        if isinstance(obj_a, dict) and isinstance(obj_b, dict):
            cles_a = set(obj_a.keys()) - ignorer
            cles_b = set(obj_b.keys()) - ignorer
            for k in cles_a - cles_b:
                differences.append({
                    "type": "supprime",
                    "chemin": f"{chemin}.{k}".lstrip("."),
                    "valeur_a": obj_a[k],
                })
            for k in cles_b - cles_a:
                differences.append({
                    "type": "ajoute",
                    "chemin": f"{chemin}.{k}".lstrip("."),
                    "valeur_b": obj_b[k],
                })
            for k in cles_a & cles_b:
                _diff(obj_a[k], obj_b[k], f"{chemin}.{k}".lstrip("."))

        elif isinstance(obj_a, list) and isinstance(obj_b, list):
            max_len = max(len(obj_a), len(obj_b))
            for i in range(max_len):
                sous_chemin = f"{chemin}[{i}]"
                if i >= len(obj_a):
                    differences.append({"type": "ajoute", "chemin": sous_chemin, "valeur_b": obj_b[i]})
                elif i >= len(obj_b):
                    differences.append({"type": "supprime", "chemin": sous_chemin, "valeur_a": obj_a[i]})
                else:
                    _diff(obj_a[i], obj_b[i], sous_chemin)
        else:
            if obj_a != obj_b:
                differences.append({
                    "type": "modifie",
                    "chemin": chemin,
                    "valeur_a": obj_a,
                    "valeur_b": obj_b,
                })

    _diff(a, b)

    nb_ajouts    = sum(1 for d in differences if d["type"] == "ajoute")
    nb_supprime  = sum(1 for d in differences if d["type"] == "supprime")
    nb_modifie   = sum(1 for d in differences if d["type"] == "modifie")

    return {
        "status": "success",
        "identiques": len(differences) == 0,
        "resume": {
            "ajouts":       nb_ajouts,
            "suppressions": nb_supprime,
            "modifications": nb_modifie,
            "total_changements": len(differences),
        },
        "differences": differences,
    }


@tool(
    name="json_schema_infer",
    description=(
        "Infer le JSON Schema (draft-07) d'un objet JSON. "
        "Analyse la structure, les types, les valeurs optionnelles "
        "et génère un schéma de validation utilisable directement."
    ),
    parameters={
        "type": "object",
        "properties": {
            "json_string": {
                "type": "string",
                "description": "Objet JSON dont on veut inférer le schéma.",
            },
            "required_all": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Marquer toutes les clés comme required. "
                    "Si false, aucune clé n'est marquée required. "
                    "Défaut: true."
                ),
            },
            "titre": {
                "type": "string",
                "description": "Titre du schéma généré. Optionnel.",
            },
        },
        "required": ["json_string"],
    },
)
def json_schema_infer(
    json_string: str,
    required_all: bool = True,
    titre: Optional[str] = None,
) -> dict:
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"JSON invalide : {e}"}

    def _infer(val: Any) -> dict:
        if val is None:
            return {"type": "null"}
        elif isinstance(val, bool):
            return {"type": "boolean"}
        elif isinstance(val, int):
            return {"type": "integer"}
        elif isinstance(val, float):
            return {"type": "number"}
        elif isinstance(val, str):
            # Tentatives de détection de format
            schema: dict = {"type": "string"}
            if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                schema["format"] = "date"
            elif re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", val):
                schema["format"] = "date-time"
            elif re.match(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$", val):
                schema["format"] = "email"
            elif re.match(r"^https?://", val):
                schema["format"] = "uri"
            return schema
        elif isinstance(val, list):
            if not val:
                return {"type": "array", "items": {}}
            # Fusionner les types des éléments
            types_items = [_infer(item) for item in val]
            if all(t == types_items[0] for t in types_items):
                return {"type": "array", "items": types_items[0]}
            else:
                return {"type": "array", "items": {"oneOf": types_items}}
        elif isinstance(val, dict):
            props = {k: _infer(v) for k, v in val.items()}
            schema = {
                "type": "object",
                "properties": props,
            }
            if required_all and props:
                schema["required"] = list(props.keys())
            return schema
        else:
            return {}

    schema = _infer(data)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    if titre:
        schema["title"] = titre

    return {
        "status": "success",
        "schema": schema,
        "schema_json": json.dumps(schema, ensure_ascii=False, indent=2),
    }


@tool(
    name="json_flatten",
    description=(
        "Aplatit un JSON imbriqué en dictionnaire plat avec des clés composées. "
        "Ex: {a: {b: {c: 1}}} → {'a.b.c': 1}. "
        "Utile pour l'exploration, la conversion CSV, ou comparer deux JSON facilement."
    ),
    parameters={
        "type": "object",
        "properties": {
            "json_string": {
                "type": "string",
                "description": "JSON à aplatir.",
            },
            "separateur": {
                "type": "string",
                "default": ".",
                "description": "Séparateur entre les niveaux de clés. Défaut: '.'.",
            },
            "max_profondeur": {
                "type": "integer",
                "description": "Profondeur maximale d'aplatissement. Optionnel (sans limite par défaut).",
            },
            "inclure_listes": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Aplatir les listes avec des indices numériques "
                    "(ex: liste.0, liste.1). Défaut: true."
                ),
            },
        },
        "required": ["json_string"],
    },
)
def json_flatten(
    json_string: str,
    separateur: str = ".",
    max_profondeur: Optional[int] = None,
    inclure_listes: bool = True,
) -> dict:
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"JSON invalide : {e}"}

    result: dict = {}

    def _flatten(val: Any, prefix: str = "", profondeur: int = 0) -> None:
        if max_profondeur is not None and profondeur >= max_profondeur:
            result[prefix] = val
            return

        if isinstance(val, dict):
            if not val:
                result[prefix] = {}
                return
            for k, v in val.items():
                nouvelle_cle = f"{prefix}{separateur}{k}" if prefix else str(k)
                _flatten(v, nouvelle_cle, profondeur + 1)

        elif isinstance(val, list) and inclure_listes:
            if not val:
                result[prefix] = []
                return
            for i, v in enumerate(val):
                nouvelle_cle = f"{prefix}{separateur}{i}" if prefix else str(i)
                _flatten(v, nouvelle_cle, profondeur + 1)

        else:
            result[prefix] = val

    _flatten(data)

    return {
        "status": "success",
        "nb_cles": len(result),
        "aplati": result,
        "aplati_json": json.dumps(result, ensure_ascii=False, indent=2),
    }


@tool(
    name="json_transform",
    description=(
        "Applique des transformations sur un JSON : filtrer des éléments, "
        "projeter (garder certaines clés), trier un tableau, "
        "grouper par valeur, ou appliquer des renommages de clés. "
        "Utile pour préparer des données JSON avant traitement."
    ),
    parameters={
        "type": "object",
        "properties": {
            "json_string": {
                "type": "string",
                "description": "JSON à transformer (objet ou tableau).",
            },
            "operation": {
                "type": "string",
                "enum": ["projeter", "filtrer", "trier", "grouper", "renommer_cles"],
                "description": (
                    "Opération à effectuer : "
                    "projeter = garder seulement certaines clés, "
                    "filtrer = garder les éléments répondant à une condition, "
                    "trier = trier un tableau par une clé, "
                    "grouper = grouper un tableau par valeur d'une clé, "
                    "renommer_cles = renommer des clés dans un objet ou tableau."
                ),
            },
            "cles": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Clés à garder (pour 'projeter') ou clés source (pour 'renommer_cles').",
            },
            "condition": {
                "type": "object",
                "description": (
                    "Pour 'filtrer' : {\"cle\": \"valeur\"} ou "
                    "{\"cle\": {\"operateur\": \">\", \"valeur\": 100}}. "
                    "Opérateurs : =, !=, >, <, >=, <=, contient."
                ),
            },
            "cle_tri": {
                "type": "string",
                "description": "Clé sur laquelle trier (pour 'trier').",
            },
            "ordre_tri": {
                "type": "string",
                "enum": ["asc", "desc"],
                "default": "asc",
                "description": "Ordre de tri : asc ou desc. Défaut: 'asc'.",
            },
            "cle_groupe": {
                "type": "string",
                "description": "Clé sur laquelle grouper (pour 'grouper').",
            },
            "renommages": {
                "type": "object",
                "description": "Dict {ancien_nom: nouveau_nom} pour 'renommer_cles'.",
            },
        },
        "required": ["json_string", "operation"],
    },
)
def json_transform(
    json_string: str,
    operation: str,
    cles: Optional[list] = None,
    condition: Optional[dict] = None,
    cle_tri: Optional[str] = None,
    ordre_tri: str = "asc",
    cle_groupe: Optional[str] = None,
    renommages: Optional[dict] = None,
) -> dict:
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"JSON invalide : {e}"}

    try:
        if operation == "projeter":
            if not cles:
                return {"status": "error", "error": "Paramètre 'cles' requis pour 'projeter'."}
            if isinstance(data, list):
                resultat = [{k: item.get(k) for k in cles} for item in data if isinstance(item, dict)]
            elif isinstance(data, dict):
                resultat = {k: data.get(k) for k in cles}
            else:
                return {"status": "error", "error": "Opération 'projeter' nécessite un objet ou un tableau."}

        elif operation == "filtrer":
            if not condition:
                return {"status": "error", "error": "Paramètre 'condition' requis pour 'filtrer'."}
            if not isinstance(data, list):
                return {"status": "error", "error": "Opération 'filtrer' nécessite un tableau JSON."}

            def _satisfait(item: dict) -> bool:
                for cle, crit in condition.items():
                    val = item.get(cle)
                    if isinstance(crit, dict):
                        op = crit.get("operateur", "=")
                        ref = crit.get("valeur")
                        try:
                            if op == "=":      ok = val == ref
                            elif op == "!=":   ok = val != ref
                            elif op == ">":    ok = float(val) > float(ref)
                            elif op == "<":    ok = float(val) < float(ref)
                            elif op == ">=":   ok = float(val) >= float(ref)
                            elif op == "<=":   ok = float(val) <= float(ref)
                            elif op == "contient": ok = ref in str(val)
                            else:              ok = False
                        except (TypeError, ValueError):
                            ok = False
                        if not ok:
                            return False
                    else:
                        if val != crit:
                            return False
                return True

            avant = len(data)
            resultat = [item for item in data if isinstance(item, dict) and _satisfait(item)]
            return {
                "status": "success",
                "operation": "filtrer",
                "avant": avant,
                "apres": len(resultat),
                "resultat": resultat,
                "resultat_json": json.dumps(resultat, ensure_ascii=False, indent=2),
            }

        elif operation == "trier":
            if not cle_tri:
                return {"status": "error", "error": "Paramètre 'cle_tri' requis pour 'trier'."}
            if not isinstance(data, list):
                return {"status": "error", "error": "Opération 'trier' nécessite un tableau JSON."}
            try:
                resultat = sorted(data, key=lambda x: (x.get(cle_tri) is None, x.get(cle_tri)), reverse=(ordre_tri == "desc"))
            except TypeError:
                resultat = sorted(data, key=lambda x: str(x.get(cle_tri, "")), reverse=(ordre_tri == "desc"))

        elif operation == "grouper":
            if not cle_groupe:
                return {"status": "error", "error": "Paramètre 'cle_groupe' requis pour 'grouper'."}
            if not isinstance(data, list):
                return {"status": "error", "error": "Opération 'grouper' nécessite un tableau JSON."}
            groupes: dict = {}
            for item in data:
                if isinstance(item, dict):
                    cle_val = str(item.get(cle_groupe, "(null)"))
                    groupes.setdefault(cle_val, []).append(item)
            return {
                "status": "success",
                "operation": "grouper",
                "cle_groupe": cle_groupe,
                "nb_groupes": len(groupes),
                "tailles": {k: len(v) for k, v in groupes.items()},
                "resultat": groupes,
                "resultat_json": json.dumps(groupes, ensure_ascii=False, indent=2),
            }

        elif operation == "renommer_cles":
            if not renommages:
                return {"status": "error", "error": "Paramètre 'renommages' requis pour 'renommer_cles'."}

            def _renommer(obj: Any) -> Any:
                if isinstance(obj, dict):
                    return {renommages.get(k, k): _renommer(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_renommer(item) for item in obj]
                return obj

            resultat = _renommer(data)

        else:
            return {"status": "error", "error": f"Opération inconnue : '{operation}'"}

        return {
            "status": "success",
            "operation": operation,
            "resultat": resultat,
            "resultat_json": json.dumps(resultat, ensure_ascii=False, indent=2),
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


# ── SECTION 4 : ENCODAGE / HASH ────────────────────────────────────────────

@tool(
    name="encode_decode",
    description=(
        "Encode ou décode une chaîne dans différents formats : "
        "Base64, URL encoding, HTML entities, ROT13, hex, binaire. "
        "Utile pour préparer des données pour des API, nettoyer du HTML, "
        "ou comprendre des chaînes obfusquées."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texte": {
                "type": "string",
                "description": "Texte à encoder ou décoder.",
            },
            "format": {
                "type": "string",
                "enum": ["base64", "url", "html", "rot13", "hex", "binaire"],
                "description": (
                    "Format d'encodage/décodage : "
                    "base64 = encodage Base64, "
                    "url = URL percent-encoding, "
                    "html = entités HTML (&amp; &lt;…), "
                    "rot13 = rotation de 13 caractères, "
                    "hex = représentation hexadécimale, "
                    "binaire = représentation binaire."
                ),
            },
            "direction": {
                "type": "string",
                "enum": ["encoder", "decoder"],
                "default": "encoder",
                "description": "Encoder ou décoder. Défaut: 'encoder'.",
            },
        },
        "required": ["texte", "format"],
    },
)
def encode_decode(texte: str, format: str, direction: str = "encoder") -> dict:
    try:
        if format == "base64":
            if direction == "encoder":
                result = base64.b64encode(texte.encode("utf-8")).decode("ascii")
            else:
                # Ajouter le padding manquant
                padded = texte + "=" * (4 - len(texte) % 4) if len(texte) % 4 else texte
                result = base64.b64decode(padded).decode("utf-8")

        elif format == "url":
            if direction == "encoder":
                result = urllib.parse.quote(texte, safe="")
            else:
                result = urllib.parse.unquote(texte)

        elif format == "html":
            if direction == "encoder":
                result = html.escape(texte, quote=True)
            else:
                result = html.unescape(texte)

        elif format == "rot13":
            # ROT13 est son propre inverse
            result = texte.translate(str.maketrans(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
                "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm"
            ))

        elif format == "hex":
            if direction == "encoder":
                result = texte.encode("utf-8").hex()
            else:
                # Supprimer espaces et préfixe 0x éventuel
                hex_clean = texte.replace(" ", "").replace("0x", "")
                result = bytes.fromhex(hex_clean).decode("utf-8")

        elif format == "binaire":
            if direction == "encoder":
                result = " ".join(format(b, "08b") for b in texte.encode("utf-8"))
            else:
                bits = texte.replace(" ", "")
                octets = [int(bits[i:i+8], 2) for i in range(0, len(bits), 8)]
                result = bytes(octets).decode("utf-8")

        else:
            return {"status": "error", "error": f"Format inconnu : '{format}'"}

        return {
            "status": "success",
            "input": texte,
            "format": format,
            "direction": direction,
            "resultat": result,
            "longueur_entree": len(texte),
            "longueur_sortie": len(result),
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur lors du {direction} en {format} : {e}"}


@tool(
    name="hash_text",
    description=(
        "Calcule le hash cryptographique d'une chaîne de texte ou d'un fichier. "
        "Algorithmes supportés : MD5, SHA-1, SHA-256, SHA-512. "
        "Utile pour vérifier l'intégrité de données, comparer des valeurs "
        "ou générer des identifiants déterministes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "texte": {
                "type": "string",
                "description": "Texte dont calculer le hash.",
            },
            "algorithme": {
                "type": "string",
                "enum": ["md5", "sha1", "sha256", "sha512", "tous"],
                "default": "sha256",
                "description": (
                    "Algorithme de hachage. "
                    "'tous' retourne MD5, SHA1, SHA256 et SHA512 simultanément. "
                    "Défaut: 'sha256'."
                ),
            },
            "encodage": {
                "type": "string",
                "enum": ["hex", "base64"],
                "default": "hex",
                "description": "Format du hash en sortie : hex (défaut) ou base64.",
            },
            "fichier": {
                "type": "string",
                "description": (
                    "Chemin vers un fichier dont calculer le hash (au lieu du texte). "
                    "Si fourni, 'texte' est ignoré."
                ),
            },
        },
        "required": [],
    },
)
def hash_text(
    texte: str = "",
    algorithme: str = "sha256",
    encodage: str = "hex",
    fichier: Optional[str] = None,
) -> dict:
    try:
        # Source : fichier ou texte
        if fichier:
            p = Path(fichier).expanduser().resolve()
            if not p.exists():
                return {"status": "error", "error": f"Fichier introuvable : {fichier}"}
            data = p.read_bytes()
            source = f"fichier: {p.name}"
        else:
            if not texte:
                return {"status": "error", "error": "Fournissez 'texte' ou 'fichier'."}
            data = texte.encode("utf-8")
            source = f"texte ({len(texte)} car.)"

        from pathlib import Path as _Path

        def _hasher(algo: str) -> str:
            h = hashlib.new(algo, data)
            if encodage == "base64":
                return base64.b64encode(h.digest()).decode("ascii")
            return h.hexdigest()

        if algorithme == "tous":
            return {
                "status": "success",
                "source": source,
                "encodage": encodage,
                "md5":    _hasher("md5"),
                "sha1":   _hasher("sha1"),
                "sha256": _hasher("sha256"),
                "sha512": _hasher("sha512"),
            }
        else:
            algo_map = {"md5": "md5", "sha1": "sha1", "sha256": "sha256", "sha512": "sha512"}
            if algorithme not in algo_map:
                return {"status": "error", "error": f"Algorithme inconnu : '{algorithme}'"}
            return {
                "status": "success",
                "source": source,
                "algorithme": algorithme,
                "encodage": encodage,
                "hash": _hasher(algo_map[algorithme]),
                "longueur_bits": {"md5": 128, "sha1": 160, "sha256": 256, "sha512": 512}[algorithme],
            }

    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


# ── SECTION 5 : NOMBRES & STATISTIQUES ────────────────────────────────────

@tool(
    name="number_format",
    description=(
        "Formate un nombre selon différentes conventions : "
        "séparateurs de milliers, notation monétaire, pourcentage, "
        "notation scientifique, arrondi, conversion de bases (hex, octal, binaire)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "nombre": {
                "type": "number",
                "description": "Nombre à formater.",
            },
            "style": {
                "type": "string",
                "enum": ["milliers", "monnaie", "pourcentage", "scientifique", "ingenierie", "bases"],
                "default": "milliers",
                "description": (
                    "Style de formatage : "
                    "milliers = séparateurs de milliers, "
                    "monnaie = format monétaire, "
                    "pourcentage = valeur × 100 + %, "
                    "scientifique = notation 1.23e+06, "
                    "ingenierie = exposant multiple de 3, "
                    "bases = représentations hex/octal/binaire. "
                    "Défaut: 'milliers'."
                ),
            },
            "decimales": {
                "type": "integer",
                "default": 2,
                "description": "Nombre de décimales. Défaut: 2.",
            },
            "symbole_monnaie": {
                "type": "string",
                "default": "€",
                "description": "Symbole monétaire (pour style='monnaie'). Défaut: '€'.",
            },
            "separateur_milliers": {
                "type": "string",
                "default": " ",
                "description": "Séparateur des milliers. Défaut: espace insécable ' '.",
            },
            "separateur_decimal": {
                "type": "string",
                "default": ",",
                "description": "Séparateur décimal. Défaut: ','.",
            },
        },
        "required": ["nombre"],
    },
)
def number_format(
    nombre: float,
    style: str = "milliers",
    decimales: int = 2,
    symbole_monnaie: str = "€",
    separateur_milliers: str = "\u202f",
    separateur_decimal: str = ",",
) -> dict:
    try:
        n = float(nombre)

        def _fmt_base(val: float, dec: int) -> str:
            """Formate avec séparateurs FR."""
            fmt = f"{val:,.{dec}f}"
            # Remplacer séparateurs anglais par FR
            fmt = fmt.replace(",", "THOU").replace(".", "DEC")
            fmt = fmt.replace("THOU", separateur_milliers).replace("DEC", separateur_decimal)
            return fmt

        if style == "milliers":
            result = _fmt_base(n, decimales)
            return {"status": "success", "resultat": result, "nombre": n}

        elif style == "monnaie":
            result = f"{_fmt_base(n, decimales)} {symbole_monnaie}"
            return {"status": "success", "resultat": result, "nombre": n}

        elif style == "pourcentage":
            result = f"{_fmt_base(n * 100, decimales)} %"
            return {"status": "success", "resultat": result, "nombre": n, "note": "Multiplié × 100"}

        elif style == "scientifique":
            result = f"{n:.{decimales}e}"
            return {"status": "success", "resultat": result, "nombre": n}

        elif style == "ingenierie":
            if n == 0:
                result = "0"
            else:
                exp = int(math.floor(math.log10(abs(n)) / 3) * 3)
                mantisse = n / (10 ** exp)
                result = f"{mantisse:.{decimales}f}e{exp:+d}"
            return {"status": "success", "resultat": result, "nombre": n}

        elif style == "bases":
            ni = int(n)
            return {
                "status": "success",
                "nombre": ni,
                "decimal":    str(ni),
                "hexadecimal": hex(ni),
                "octal":       oct(ni),
                "binaire":     bin(ni),
                "note": "Valeur tronquée à l'entier" if n != ni else None,
            }

        else:
            return {"status": "error", "error": f"Style inconnu : '{style}'"}

    except (TypeError, ValueError) as e:
        return {"status": "error", "error": f"Nombre invalide : {e}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}


@tool(
    name="stats_describe",
    description=(
        "Calcule des statistiques descriptives complètes sur une liste de nombres. "
        "Sans nécessiter de fichier chargé : passez directement vos valeurs. "
        "Retourne : moyenne, médiane, écart-type, quartiles, mode, asymétrie, "
        "aplatissement (kurtosis), et un histogramme simplifié."
    ),
    parameters={
        "type": "object",
        "properties": {
            "valeurs": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Liste de nombres à analyser, ex: [10, 20, 15, 30, 25].",
            },
            "nb_classes_histo": {
                "type": "integer",
                "default": 5,
                "description": "Nombre de classes pour l'histogramme simplifié. Défaut: 5.",
            },
            "percentiles": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Percentiles supplémentaires à calculer, ex: [10, 90]. Optionnel.",
            },
        },
        "required": ["valeurs"],
    },
)
def stats_describe(
    valeurs: list,
    nb_classes_histo: int = 5,
    percentiles: Optional[list] = None,
) -> dict:
    try:
        nums = [float(v) for v in valeurs if v is not None]

        if not nums:
            return {"status": "error", "error": "Liste vide ou sans valeur numérique."}

        n = len(nums)
        nums_sorted = sorted(nums)

        # ── Statistiques de base ──
        mean = statistics.mean(nums)
        median = statistics.median(nums)
        minimum = nums_sorted[0]
        maximum = nums_sorted[-1]
        etendue = maximum - minimum

        std = statistics.stdev(nums) if n > 1 else 0.0
        variance = statistics.variance(nums) if n > 1 else 0.0
        cv = (std / mean * 100) if mean != 0 else None  # Coefficient de variation

        # ── Mode ──
        try:
            mode_val = statistics.mode(nums)
            mode_count = nums.count(mode_val)
        except statistics.StatisticsError:
            mode_val = None
            mode_count = None

        # ── Quartiles ──
        def _percentile(data: list, p: float) -> float:
            """Percentile par interpolation linéaire."""
            if len(data) == 1:
                return data[0]
            idx = (len(data) - 1) * p / 100
            lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
            return data[lo] + (data[hi] - data[lo]) * (idx - lo)

        q1 = _percentile(nums_sorted, 25)
        q3 = _percentile(nums_sorted, 75)
        iqr = q3 - q1

        # ── Asymétrie (skewness) et aplatissement (kurtosis) ──
        if n >= 3 and std > 0:
            skew = (n / ((n-1) * (n-2))) * sum((x - mean)**3 for x in nums) / std**3
        else:
            skew = None

        if n >= 4 and std > 0:
            kurt = (n*(n+1)/((n-1)*(n-2)*(n-3))) * sum((x-mean)**4 for x in nums) / std**4 \
                   - 3*(n-1)**2/((n-2)*(n-3))
        else:
            kurt = None

        # ── Percentiles supplémentaires ──
        perc_result = {}
        if percentiles:
            for p in percentiles:
                perc_result[f"p{int(p)}"] = round(_percentile(nums_sorted, float(p)), 4)

        # ── Histogramme simplifié ──
        nb_classes = max(2, min(nb_classes_histo, 20))
        if etendue == 0:
            histo = [{"classe": f"{minimum}", "min": minimum, "max": maximum, "count": n, "barre": "█" * min(n, 20)}]
        else:
            largeur = etendue / nb_classes
            classes_histo = []
            for i in range(nb_classes):
                borne_min = minimum + i * largeur
                borne_max = minimum + (i + 1) * largeur
                count = sum(1 for x in nums if (borne_min <= x < borne_max) or (i == nb_classes - 1 and x == borne_max))
                bar_len = int(count / n * 20)
                classes_histo.append({
                    "classe": f"[{round(borne_min,2)} – {round(borne_max,2)}[",
                    "min": round(borne_min, 4),
                    "max": round(borne_max, 4),
                    "count": count,
                    "pct": round(count / n * 100, 1),
                    "barre": "█" * bar_len,
                })
            histo = classes_histo

        # ── Valeurs aberrantes rapides (méthode IQR) ──
        borne_inf = q1 - 1.5 * iqr
        borne_sup = q3 + 1.5 * iqr
        outliers = [x for x in nums if x < borne_inf or x > borne_sup]

        return {
            "status": "success",
            "n": n,
            "min": round(minimum, 6),
            "max": round(maximum, 6),
            "etendue": round(etendue, 6),
            "moyenne": round(mean, 6),
            "mediane": round(median, 6),
            "mode": round(mode_val, 6) if mode_val is not None else None,
            "mode_occurrences": mode_count,
            "ecart_type": round(std, 6),
            "variance": round(variance, 6),
            "cv_pct": round(cv, 2) if cv is not None else None,
            "q1": round(q1, 6),
            "q3": round(q3, 6),
            "iqr": round(iqr, 6),
            "asymetrie": round(skew, 4) if skew is not None else None,
            "interpretation_asymetrie": (
                "symétrique" if skew is None or abs(skew) < 0.5
                else ("légèrement asymétrique" if abs(skew) < 1
                      else ("asymétrie droite" if skew > 0 else "asymétrie gauche"))
            ),
            "kurtosis": round(kurt, 4) if kurt is not None else None,
            "nb_outliers_iqr": len(outliers),
            "outliers": sorted(outliers),
            "percentiles": perc_result if perc_result else None,
            "histogramme": histo,
            "somme": round(sum(nums), 6),
        }

    except (TypeError, ValueError) as e:
        return {"status": "error", "error": f"Valeur non numérique : {e}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur : {e}"}
