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
llm_clients.py — Fabrique de clients LLM.

Responsabilité unique
─────────────────────
Ce module est le **point d'entrée unique** pour tout code qui a besoin de
construire un client OpenAI/Ollama ou de résoudre le modèle actif.

Toute la logique de sélection backend / URL / clé API est ici. Aucun autre
module ne doit construire un ``OpenAI(...)`` directement.

Hiérarchie de résolution du modèle
────────────────────────────────────
Pour un appel LLM donné, la résolution suit cet ordre de priorité :

  1. **Modèle de famille** (build_family_client) — assigné dynamiquement
     depuis l'UI (onglet "Outils" des paramètres). Persisté dans
     ~/.promethee_family_models.json. Permet à chaque famille d'outils
     d'utiliser un modèle léger dédié pour sa réponse finale.

  2. **Modèle spécialisé par tâche** (build_specialist_client) — configuré
     dans .env (SPECIALIST_CODE_MODEL, SPECIALIST_SUMMARY_MODEL…).
     Prévu pour les tâches transversales (code, résumé) indépendantes des
     familles d'outils. Déprécié au profit de build_family_client.

  3. **Modèle principal** (build_client + Config.active_model()) — modèle
     de conversation par défaut, défini dans .env (OPENAI_MODEL).

Cas d'usage recommandé dans les outils
────────────────────────────────────────
    from core.llm_clients import build_family_client

    client, model = build_family_client("mon_outil_tools")
    resp = client.chat.completions.create(model=model, messages=[...])

build_family_client retourne transparentement (build_client(), active_model())
si aucun modèle n'est assigné — aucun test conditionnel n'est nécessaire
dans l'outil.
"""

import httpx
from openai import OpenAI

from .config import Config


# ── Cache de clients ──────────────────────────────────────────────────────────
#
# Chaque OpenAI(...) crée un pool de connexions httpx indépendant.
# Recréer un client à chaque appel force une nouvelle connexion TCP vers Albert,
# ce qui peut provoquer un GeneratorExit si la connexion est établie mais le
# stream commence pendant qu'Albert referme l'ancienne.
#
# Solution : un cache global (base_url, api_key) → OpenAI.
# Les paramètres de connexion étant stables au sein d'une session, le pool
# est réutilisé entre l'appel de décision et l'appel de synthèse finale.
#
# Thread-safety : le GIL protège les accès dict en lecture/écriture simple.
# En cas de concurrence (plusieurs requêtes simultanées), deux threads peuvent
# créer le client en parallèle — le dernier écrase le premier dans le dict,
# mais les deux clients sont valides. Le coût est au pire 2 connexions TCP
# sur le premier appel concurrent, jamais de corruption.

_CLIENT_CACHE: dict[tuple[str, str], OpenAI] = {}

# Timeouts httpx pour les appels vers Albert/vLLM.
#
# Le timeout par défaut httpx est 5s connect + 5s read. C'est insuffisant
# pour Albert qui peut mettre >5s à produire le premier token d'un stream
# de synthèse sur un contexte lourd (ex. 20 pages OCR).
#
#   connect : 10s — établissement TCP + TLS vers Albert
#   read    : 120s — attente du premier token (ou d'un chunk intermédiaire)
#   write   : 10s — envoi de la requête (corps JSON potentiellement volumineux)
#   pool    : 10s — attente d'une connexion libre dans le pool httpx
#
# Ces valeurs sont intentionnellement larges pour les LLM qui peuvent être
# lents à démarrer leur génération. Ajuster via Config si nécessaire.
_HTTPX_TIMEOUT = httpx.Timeout(
    connect=10.0,
    read=120.0,
    write=10.0,
    pool=10.0,
)


def _get_or_create_client(base_url: str, api_key: str) -> OpenAI:
    """
    Retourne un client OpenAI mis en cache pour (base_url, api_key).
    Crée et met en cache un nouveau client si nécessaire.
    Le client est configuré avec des timeouts httpx adaptés aux LLM lents.
    """
    key = (base_url, api_key)
    client = _CLIENT_CACHE.get(key)
    if client is None:
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=httpx.Client(timeout=_HTTPX_TIMEOUT),
        )
        _CLIENT_CACHE[key] = client
    return client


# ── Résolution du contexte utilisateur ───────────────────────────────────────

def _effective_config():
    """
    Retourne le UserConfig actif (mode multi-user, requête FastAPI)
    ou Config (mode Qt6 mono-user / hors requête).
    L'import est différé pour éviter les cycles d'import au démarrage.
    """
    try:
        from .request_context import get_user_config
        uc = get_user_config()
        return uc if uc is not None else Config
    except ImportError:
        return Config


# ── Client principal ──────────────────────────────────────────────────────────


def build_client(local: bool | None = None) -> OpenAI:
    """
    Construit un client OpenAI-compatible selon la configuration active.

    Returns
    -------
    OpenAI
        Client prêt à l'emploi.
    """
    cfg = _effective_config()
    return _get_or_create_client(
        cfg.OPENAI_API_BASE,
        cfg.OPENAI_API_KEY or "none",
    )


# ── Client spécialisé par tâche (déprécié) ───────────────────────────────────


def build_specialist_client(task: str) -> tuple[OpenAI, str]:
    """
    Construit un client et résout le modèle pour une tâche spécialisée.

    .. deprecated::
        Préférer ``build_family_client(family)`` qui utilise le registre
        dynamique géré depuis l'interface graphique.
        Cette fonction reste disponible pour rétrocompatibilité.

    Consulte ``Config.specialist_config(task)``. Si aucun modèle n'est
    configuré pour cette tâche, retourne le client et le modèle principaux.

    Parameters
    ----------
    task : str
        Identifiant de tâche en majuscules : "CODE", "SUMMARY"…

    Returns
    -------
    tuple[OpenAI, str]
        (client, nom_du_modèle)
    """
    spec = Config.specialist_config(task)

    if spec is None:
        return build_client(), Config.active_model()

    backend  = spec["backend"]
    model    = spec["model"]
    base_url = spec["base_url"]

    cfg = _effective_config()
    client = _get_or_create_client(
        base_url or cfg.OPENAI_API_BASE,
        cfg.OPENAI_API_KEY or "none",
    )

    return client, model


# ── Client par famille d'outils ───────────────────────────────────────────────


def build_family_client(family: str) -> tuple[OpenAI, str]:
    """
    Construit un client et résout le modèle assigné à une famille d'outils.

    Consulte le registre dynamique ``tools_engine._FAMILY_MODELS``, géré
    depuis l'interface graphique (onglet "Outils" des paramètres, colonne
    "Modèle"). Si aucun modèle n'est assigné à cette famille, retourne le
    client et le modèle principaux — comportement transparent pour l'appelant.

    L'import de ``tools_engine`` est différé (import local) pour éviter
    l'import circulaire core → tools_engine → core.

    Parameters
    ----------
    family : str
        Nom exact de la famille tel que déclaré dans ``set_current_family()``
        (ex : "tool_creator_tools", "imap_tools").

    Returns
    -------
    tuple[OpenAI, str]
        (client, nom_du_modèle).
        Retourne (build_client(), Config.active_model()) si aucune
        assignation n'est trouvée pour cette famille.

    Examples
    --------
    Utilisation dans un outil :

        from core.llm_clients import build_family_client

        client, model = build_family_client("tool_creator_tools")
        resp = client.chat.completions.create(model=model, messages=[...])
    """
    import core.tools_engine as _te  # import différé — évite le cycle core ↔ tools

    assigned = _te.get_family_model(family)

    if assigned is None:
        return build_client(), Config.active_model()

    backend  = assigned["backend"]
    model    = assigned["model"]
    base_url = assigned.get("base_url", "")

    cfg = _effective_config()
    client = _get_or_create_client(
        base_url or cfg.OPENAI_API_BASE,
        cfg.OPENAI_API_KEY or "none",
    )

    return client, model


# ── Découverte des modèles disponibles ───────────────────────────────────────


def list_remote_models() -> list[str]:
    """
    Liste les modèles disponibles sur le serveur OpenAI-compatible.

    Retourne ``[Config.OPENAI_MODEL]`` en cas d'erreur (réseau, auth…).

    Returns
    -------
    list[str]
        Noms des modèles triés alphabétiquement.
    """
    try:
        client = build_client()
        return sorted([m.id for m in client.models.list().data])
    except Exception:
        return [Config.OPENAI_MODEL]
