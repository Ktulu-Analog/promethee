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
     de conversation par défaut, défini dans .env (OPENAI_MODEL ou
     OLLAMA_MODEL selon LOCAL).

Cas d'usage recommandé dans les outils
────────────────────────────────────────
    from core.llm_clients import build_family_client

    client, model = build_family_client("mon_outil_tools")
    resp = client.chat.completions.create(model=model, messages=[...])

build_family_client retourne transparentement (build_client(), active_model())
si aucun modèle n'est assigné — aucun test conditionnel n'est nécessaire
dans l'outil.
"""

from openai import OpenAI

from .config import Config


# ── Client principal ──────────────────────────────────────────────────────────


def build_client(local: bool | None = None) -> OpenAI:
    """
    Construit un client OpenAI ou Ollama selon la configuration active.

    Parameters
    ----------
    local : bool | None
        Si None (défaut), utilise Config.LOCAL.
        Si True, construit un client Ollama.
        Si False, construit un client OpenAI-compatible.

    Returns
    -------
    OpenAI
        Client prêt à l'emploi.
    """
    use_local = Config.LOCAL if local is None else local
    if use_local:
        base_url = Config.OLLAMA_BASE_URL.rstrip("/") + "/v1"
        return OpenAI(base_url=base_url, api_key="ollama")
    return OpenAI(
        base_url=Config.OPENAI_API_BASE,
        api_key=Config.OPENAI_API_KEY or "none",
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

    if backend == "ollama":
        url    = (base_url or Config.OLLAMA_BASE_URL).rstrip("/") + "/v1"
        client = OpenAI(base_url=url, api_key="ollama")
    else:
        client = OpenAI(
            base_url=base_url or Config.OPENAI_API_BASE,
            api_key=Config.OPENAI_API_KEY or "none",
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

    if backend == "ollama":
        url    = (base_url or Config.OLLAMA_BASE_URL).rstrip("/") + "/v1"
        client = OpenAI(base_url=url, api_key="ollama")
    else:
        client = OpenAI(
            base_url=base_url or Config.OPENAI_API_BASE,
            api_key=Config.OPENAI_API_KEY or "none",
        )

    return client, model


# ── Découverte des modèles disponibles ───────────────────────────────────────


def list_local_models() -> list[str]:
    """
    Liste les modèles Ollama disponibles sur l'instance locale.

    Retourne une liste vide (ou ``[Config.OLLAMA_MODEL]``) en cas d'erreur
    (Ollama non démarré, package ollama non installé…).

    Returns
    -------
    list[str]
        Noms des modèles disponibles.
    """
    try:
        import ollama
        return [m["name"] for m in ollama.list().get("models", [])]
    except Exception:
        return [Config.OLLAMA_MODEL]


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
        client = build_client(local=False)
        return sorted([m.id for m in client.models.list().data])
    except Exception:
        return [Config.OPENAI_MODEL]
