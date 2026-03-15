---
name: Créateur d'outils Prométhée
description: Protocole complet pour générer un fichier tools/*.py valide — structure, patterns, validation, variables .env et documentation utilisateur
tags: [outils, tools, python, génération, promethee, code]
version: 1.0
---

# Créateur d'outils Prométhée

Ce skill décrit le protocole exact à suivre pour générer un outil Prométhée de qualité production.
Il est destiné à être lu par le LLM **avant** toute génération de code d'outil.

---

## 1. Structure obligatoire d'un fichier `tools/*.py`

Chaque fichier d'outils suit impérativement cette structure, dans cet ordre :

```python
# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : <auteur>
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
# Année   : 2026
# ============================================================================

"""
tools/<nom>_tools.py — <titre court>
=====================================

Outils exposés (N) :
  - nom_outil_1  : description courte
  - nom_outil_2  : description courte

<Explications sur la stratégie d'accès, les dépendances, les prérequis.>

Usage :
    import tools.<nom>_tools   # suffit à enregistrer les outils
"""

# 1. Imports stdlib
# 2. Imports third-party
# 3. Imports locaux Prométhée

from core.tools_engine import tool, set_current_family, _TOOL_ICONS

set_current_family("<nom>_tools", "<Label UI>", "<emoji>")

# ── Icônes UI ─────────────────────────────────────────────────────────────────
_TOOL_ICONS.update({
    "nom_outil_1": "🔧",
    "nom_outil_2": "🔧",
})

# ══════════════════════════════════════════════════════════════════════════════
# Helpers internes (fonctions préfixées _ , non exposées comme outils)
# ══════════════════════════════════════════════════════════════════════════════

# ... helpers ...

# ══════════════════════════════════════════════════════════════════════════════
# Outils exposés
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="nom_outil_1",
    description="...",
    parameters={ ... }
)
def nom_outil_1(...) -> dict:
    ...
```

---

## 2. Le décorateur `@tool`

```python
@tool(
    name="nom_de_l_outil",          # snake_case, unique dans tout le projet
    description=(
        "Description claire de ce que fait l'outil. "
        "Indiquer quand l'utiliser, ce qu'il retourne, "
        "et les prérequis éventuels (autres outils à appeler avant, config nécessaire)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "param_obligatoire": {
                "type": "string",           # string | integer | number | boolean | array | object
                "description": "Rôle du paramètre, format attendu, exemples si utile.",
            },
            "param_optionnel": {
                "type": "integer",
                "description": "Description. Défaut : 20.",
            },
            "param_enum": {
                "type": "string",
                "enum": ["valeur_a", "valeur_b", "valeur_c"],
                "description": "Choisir parmi les valeurs listées.",
            },
            "param_array": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste de chaînes.",
            },
        },
        "required": ["param_obligatoire"],   # liste des paramètres sans valeur par défaut
    },
)
def nom_de_l_outil(
    param_obligatoire: str,
    param_optionnel: int = 20,
    param_enum: str = "valeur_a",
    param_array: list | None = None,
) -> dict:
    ...
```

**Règles impératives sur le décorateur :**
- `name` doit correspondre exactement au nom de la fonction Python.
- `required` ne liste QUE les paramètres sans valeur par défaut.
- Les paramètres optionnels ont TOUJOURS une valeur par défaut en Python ET sont absents de `required`.
- `description` doit guider le LLM sur QUAND appeler cet outil, pas seulement CE qu'il fait.

---

## 3. Format de retour des fonctions

**Toujours retourner un `dict`**, jamais une chaîne brute ou `None`.

### Succès
```python
return {
    "status": "success",
    # ... champs spécifiques au résultat ...
    "message": "Description humaine du résultat (optionnel mais recommandé).",
}
```

### Erreur
```python
return {
    "status": "error",
    "error": "Message d'erreur précis, actionnable par l'utilisateur.",
}
```

### Annulation (opérations destructives)
```python
return {
    "status": "cancelled",
    "message": "Opération annulée. Passez confirmer=true pour confirmer.",
}
```

**Règles sur les retours :**
- Les opérations destructives (suppression, écriture irréversible) DOIVENT avoir un paramètre `confirmer: bool` et retourner `cancelled` si `confirmer=False`.
- Ne jamais faire `raise` dans un outil — capturer toutes les exceptions et retourner `{"status": "error", ...}`.
- Les champs du dict de retour doivent être en français (snake_case) pour cohérence avec le reste du projet.

---

## 4. Gestion de la configuration

Lire la configuration depuis `Config` (jamais `os.getenv` directement dans un outil Prométhée principal) :

```python
from core.config import Config

host = Config.MON_SERVICE_HOST
api_key = Config.MON_SERVICE_API_KEY
```

**Exception :** pour les outils standalone (comme `imap_tools.py`) qui peuvent être utilisés hors Prométhée, lire `os.getenv` directement est acceptable — mais documenter clairement ce choix.

---

## 5. Helpers internes

Toute logique réutilisée entre plusieurs outils du même fichier doit être extraite en helper privé :

```python
def _connect_service(host: str, api_key: str) -> tuple[bool, "Client | str"]:
    """
    Ouvre une connexion au service.
    Returns (success, client | error_message)
    """
    try:
        client = ServiceClient(host, api_key)
        client.ping()
        return True, client
    except Exception as e:
        return False, f"Impossible de se connecter à {host} : {e}"
```

**Pattern recommandé pour les connexions :**
```python
ok, result = _connect_service(host, api_key)
if not ok:
    return {"status": "error", "error": result}
client = result
```

---

## 6. Dépendances externes

- **Stdlib uniquement** : aucune modification de `requirements.txt` nécessaire.
- **Third-party** : ajouter dans `requirements.txt` avec version minimale. Documenter dans le docstring du module.
- **Import optionnel** : si la dépendance est optionnelle, utiliser le pattern :

```python
try:
    import some_lib
    SOME_LIB_OK = True
except ImportError:
    SOME_LIB_OK = False

# Dans l'outil :
if not SOME_LIB_OK:
    return {"status": "error", "error": "some_lib non installé. pip install some_lib"}
```

---

## 7. Variables `.env` à générer

Pour chaque variable de configuration nécessaire à l'outil, produire les informations suivantes dans un fichier <nom>_tools.md au format markdown:

```env
# ── <Nom du service> ──────────────────────────────────────────────────────────
# <Description de l'outil, URL de la doc API si applicable>
MON_SERVICE_HOST=https://api.monservice.fr    # URL de base (sans slash final)
MON_SERVICE_API_KEY=                          # Clé API (obligatoire)
MON_SERVICE_TIMEOUT=30                        # Timeout en secondes (optionnel)
```

Et dans `core/config.py`, ajouter dans la classe `Config` :

```python
# ── <Nom du service> ─────────────────────────────────────────────────────────
MON_SERVICE_HOST:    str = os.getenv("MON_SERVICE_HOST", "https://api.monservice.fr")
MON_SERVICE_API_KEY: str = os.getenv("MON_SERVICE_API_KEY", "")
MON_SERVICE_TIMEOUT: int = int(os.getenv("MON_SERVICE_TIMEOUT", "30"))
```

---

## 8. Activation de l'outil dans le projet

Ajouter dans `tools/__init__.py` la ligne d'import :

```python
import tools.mon_service_tools
```

C'est le seul fichier à modifier en dehors du nouveau fichier d'outils.

---

## 9. Checklist de qualité avant livraison

Avant de retourner le code généré, vérifier mentalement chaque point :

- [ ] `set_current_family(...)` appelé avant tout `@tool`
- [ ] `_TOOL_ICONS.update({...})` présent pour chaque outil
- [ ] Chaque `@tool` : `name` == nom de fonction Python
- [ ] Chaque `@tool` : `required` ne contient que les params sans défaut
- [ ] Chaque fonction retourne `dict` (jamais `str`, `None`, `raise`)
- [ ] Toutes les exceptions capturées → `{"status": "error", "error": "..."}`
- [ ] Opérations destructives protégées par `confirmer: bool`
- [ ] Helpers internes préfixés `_`
- [ ] Variables d'env documentées (bloc `.env` + lignes `config.py`)
- [ ] Ligne `import tools.<nom>_tools` pour `__init__.py`
- [ ] Syntaxe Python valide (ast.parse)

---

## 10. Exemple complet minimal

```python
# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
# Année   : 2026
# ============================================================================

"""
tools/meteo_tools.py — Consultation météo via OpenMeteo (API publique)
=======================================================================

Outils exposés (2) :
  - meteo_actuelle  : température et conditions météo pour une ville
  - meteo_previsions : prévisions sur N jours

Aucune clé API requise (OpenMeteo est gratuit et ouvert).

Usage :
    import tools.meteo_tools
"""

import json
import urllib.request
from typing import Optional

from core.tools_engine import tool, set_current_family, _TOOL_ICONS

set_current_family("meteo_tools", "Météo", "🌤️")

_TOOL_ICONS.update({
    "meteo_actuelle":    "🌡️",
    "meteo_previsions":  "📅",
})


# ══════════════════════════════════════════════════════════════════════════════
# Helpers internes
# ══════════════════════════════════════════════════════════════════════════════

def _geocode(ville: str) -> tuple[bool, dict | str]:
    """Convertit un nom de ville en coordonnées GPS via OpenMeteo Geocoding."""
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.request.quote(ville)}&count=1&language=fr"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        if not results:
            return False, f"Ville '{ville}' introuvable."
        r = results[0]
        return True, {"lat": r["latitude"], "lon": r["longitude"], "nom": r["name"], "pays": r.get("country", "")}
    except Exception as e:
        return False, f"Erreur géocodage : {e}"


# ══════════════════════════════════════════════════════════════════════════════
# Outils exposés
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="meteo_actuelle",
    description=(
        "Retourne la météo actuelle pour une ville : température, ressenti, "
        "humidité, vent et description des conditions. "
        "Utiliser pour répondre à 'quel temps fait-il à X', 'météo de X aujourd'hui'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ville": {
                "type": "string",
                "description": "Nom de la ville (ex: Paris, Lyon, Marseille).",
            },
        },
        "required": ["ville"],
    },
)
def meteo_actuelle(ville: str) -> dict:
    ok, geo = _geocode(ville)
    if not ok:
        return {"status": "error", "error": geo}

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={geo['lat']}&longitude={geo['lon']}"
            f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m"
            f"&timezone=auto"
        )
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())

        cur = data["current"]
        return {
            "status":       "success",
            "ville":        f"{geo['nom']}, {geo['pays']}",
            "temperature":  f"{cur['temperature_2m']}°C",
            "ressenti":     f"{cur['apparent_temperature']}°C",
            "humidite":     f"{cur['relative_humidity_2m']}%",
            "vent":         f"{cur['wind_speed_10m']} km/h",
        }
    except Exception as e:
        return {"status": "error", "error": f"Erreur météo : {e}"}
```

---

## 11. Points d'attention spécifiques par type d'outil

### Outils qui appellent une API HTTP externe
- Toujours définir un `timeout` (10–30 s selon le service).
- Toujours capturer `urllib.error.HTTPError` séparément pour extraire le code HTTP.
- Retourner le code HTTP dans l'erreur pour que l'utilisateur puisse diagnostiquer (401, 403, 429…).

### Outils qui lisent/écrivent des fichiers
- Utiliser `pathlib.Path`, jamais `os.path`.
- Valider l'existence du fichier avant d'opérer et retourner une erreur claire.
- Les opérations d'écriture irréversibles (suppression, écrasement) → paramètre `confirmer: bool`.

### Outils qui appellent une base de données
- Toujours fermer la connexion dans un `finally`.
- Utiliser des requêtes paramétrées (jamais de f-string dans le SQL).
- Ouvrir en lecture seule (`mode=ro`) si l'outil ne fait que lire.

### Outils qui lancent des sous-processus
- Utiliser `subprocess.run(..., capture_output=True, text=True, timeout=30)`.
- Ne jamais utiliser `shell=True` sauf nécessité absolue documentée.
- Vérifier `returncode` et inclure `stderr` dans les erreurs.
