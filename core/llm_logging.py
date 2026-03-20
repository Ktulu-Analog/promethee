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
llm_logging.py — Infrastructure de logs rotatifs et comptage de tokens.

Responsabilité unique
─────────────────────
Ce module fournit deux choses étroitement liées :

  1. L'infrastructure de logs rotatifs de l'application (répertoire, handlers).
  2. La classe TokenUsage — value object qui cumule la consommation de tokens
     sur une session (stream_chat ou agent_loop) et sait se logguer.

Pourquoi TokenUsage est ici et pas dans llm_service ?
──────────────────────────────────────────────────────
TokenUsage est une structure de données pure (comportement minimal, __slots__),
dont la seule dépendance externe est le logger de tokens défini dans ce même
module. La co-localiser avec l'infrastructure de logging évite un import
circulaire et rend les deux composants testables en isolation, sans avoir
besoin d'instancier un client LLM.

Fichiers de log
───────────────
Tous les logs sont écrits dans ~/.promethee/logs/ :

  tokens.log      Consommation de tokens par session + événements de compression.
                  Partagé par les loggers "promethee.tokens" et
                  "promethee.session_memory" pour garder un journal unifié.

Rotation automatique :
  - Taille max : 5 Mo par fichier
  - Archives   : 5 fichiers (.log.1 … .log.5)

Spécificités Albert
───────────────────
L'API Albert retourne deux chunks usage en mode streaming :
  - Chunk intermédiaire : tokens partiels, sans champs "requests" / "cost".
  - Chunk final         : tokens complets + cost (€) + carbon + requests >= 1.

TokenUsage.add() filtre les chunks intermédiaires via _is_final_chunk() pour
éviter le double comptage. Les champs cost et carbon sont spécifiques à Albert
et ignorés silencieusement sur les autres backends.
"""

import logging
import logging.handlers
from pathlib import Path

from .config import Config


# ── Répertoire de logs ────────────────────────────────────────────────────────

_LOG_DIR = Path.home() / ".promethee" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _make_rotating_handler(log_path: Path) -> logging.handlers.RotatingFileHandler:
    """
    Crée un RotatingFileHandler préconfiguré.

    Paramètres de rotation :
      - maxBytes   : 5 Mo par fichier
      - backupCount: 5 archives conservées (.log.1 … .log.5)

    Parameters
    ----------
    log_path : Path
        Chemin complet vers le fichier de log cible.

    Returns
    -------
    logging.handlers.RotatingFileHandler
        Handler prêt à être attaché à un logger.
    """
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    return handler


# ── Logger tokens ─────────────────────────────────────────────────────────────
#
# Reçoit les entrées de consommation de tokens (TokenUsage.log)
# et les événements de compression du contexte.

_token_log = logging.getLogger("promethee.tokens")
_token_log.setLevel(logging.DEBUG)
_token_log.propagate = False


def _setup_token_logger() -> None:
    """Configure le logger de tokens si ce n'est pas déjà fait (idempotent)."""
    if _token_log.handlers:
        return
    _token_log.addHandler(_make_rotating_handler(_LOG_DIR / "tokens.log"))


_setup_token_logger()


# ── Logger session_memory ────────────────────────────────────────────────────
#
# Écrit dans le même fichier que les tokens pour un journal unifié.
# Utilisé directement par session_memory.py via logging.getLogger().

_sm_log = logging.getLogger("promethee.session_memory")
_sm_log.setLevel(logging.DEBUG)
_sm_log.propagate = False


def _setup_sm_logger() -> None:
    """Configure le logger session_memory sur le même fichier que les tokens."""
    if _sm_log.handlers:
        return
    _sm_log.addHandler(_make_rotating_handler(_LOG_DIR / "tokens.log"))


_setup_sm_logger()


# ── TokenUsage ────────────────────────────────────────────────────────────────


class TokenUsage:
    """
    Cumul de tokens pour une requête LLM (stream_chat ou agent_loop).

    Value object léger (__slots__) qui agrège la consommation de tokens
    sur l'ensemble des appels LLM d'une même session, y compris les appels
    secondaires (consolidation SessionMemory, modèles de famille).

    Champs spécifiques à l'API Albert
    ──────────────────────────────────
    cost   : float — coût en euros de la session.
    carbon : dict  — empreinte carbone estimée :
                     {"kWh":     {"min": float, "max": float},
                      "kgCO2eq": {"min": float, "max": float}}

    Gestion du double comptage en streaming Albert
    ───────────────────────────────────────────────
    Albert retourne deux chunks avec usage en mode streaming :
      - Chunk intermédiaire : tokens partiels (prompt_tokens != 0),
        sans champ "requests" → ignoré par add() en mode streaming.
      - Chunk final         : tokens complets + cost + carbon + requests >= 1
        → pris en compte.
    Sur les autres backends (OpenAI standard, Ollama), un seul chunk final
    est retourné — _is_final_chunk() retourne True car "requests" est absent,
    ce qui revient à ne pas filtrer (comportement correct).
    """

    __slots__ = ("prompt", "completion", "calls", "cost", "carbon")

    def __init__(self) -> None:
        self.prompt:     int   = 0
        self.completion: int   = 0
        self.calls:      int   = 0
        self.cost:       float = 0.0
        self.carbon:     dict  = {}

    # ── Détection du chunk final Albert ──────────────────────────────────────

    @staticmethod
    def _is_final_chunk(usage) -> bool:
        """
        Détecte si un objet usage est le chunk final d'un stream Albert.

        Le chunk final Albert contient le champ ``requests`` (valeur >= 1).
        Le chunk intermédiaire ne l'a pas.
        Sur les backends non-Albert, ``requests`` est absent → retourne True
        (pas de filtrage, comportement identique à stream=False).

        Parameters
        ----------
        usage : objet usage retourné par l'API
            Peut être None — géré par l'appelant.

        Returns
        -------
        bool
            True si ce chunk doit être comptabilisé.
        """
        return getattr(usage, "requests", None) is not None

    # ── Accumulation ─────────────────────────────────────────────────────────

    def add(self, usage, streaming: bool = False) -> None:
        """
        Ajoute les tokens d'un objet usage retourné par l'API.

        Parameters
        ----------
        usage : objet usage de l'API (peut être None)
            Contient prompt_tokens, completion_tokens, et optionnellement
            cost, carbon (Albert), requests (Albert streaming).
        streaming : bool
            Si True, les chunks intermédiaires Albert sont ignorés pour
            éviter le double comptage (voir _is_final_chunk).
        """
        if usage is None:
            return
        if streaming and not self._is_final_chunk(usage):
            return  # chunk intermédiaire Albert — ignorer

        self.prompt     += getattr(usage, "prompt_tokens",     0) or 0
        self.completion += getattr(usage, "completion_tokens", 0) or 0
        self.calls      += 1
        self.cost       += getattr(usage, "cost", 0.0) or 0.0

        carbon = getattr(usage, "carbon", None)
        if carbon and isinstance(carbon, dict):
            for unit in ("kWh", "kgCO2eq"):
                if unit in carbon:
                    existing = self.carbon.setdefault(unit, {"min": 0.0, "max": 0.0})
                    existing["min"] += carbon[unit].get("min", 0.0)
                    existing["max"] += carbon[unit].get("max", 0.0)

    # ── Métriques ─────────────────────────────────────────────────────────────

    @property
    def total(self) -> int:
        """Total prompt + completion tokens."""
        return self.prompt + self.completion

    def pct(self, model_max: int = 0) -> float:
        """
        Pourcentage de la fenêtre du modèle consommé (basé sur prompt_tokens).

        Parameters
        ----------
        model_max : int
            Taille de la fenêtre du modèle en tokens. 0 = inconnu → retourne 0.0.

        Returns
        -------
        float
            Valeur entre 0.0 et 100.0.
        """
        if model_max <= 0:
            return 0.0
        return min(100.0, self.prompt * 100 / model_max)

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, context: str = "") -> None:
        """
        Écrit une ligne de bilan dans tokens.log.

        La ligne inclut prompt, completion, total, nombre d'appels,
        pourcentage de la fenêtre consommé, coût (€) et empreinte carbone
        (si disponibles via Albert).

        Parameters
        ----------
        context : str
            Étiquette libre décrivant le point de mesure
            (ex : "stream_chat", "agent_loop/final_stream").
        """
        co2_str = ""
        if self.carbon.get("kgCO2eq"):
            lo = self.carbon["kgCO2eq"]["min"]
            hi = self.carbon["kgCO2eq"]["max"]
            co2_str = f" co2=[{lo:.6f}-{hi:.6f}]kgCO2"
        _token_log.debug(
            "[%s] prompt=%d completion=%d total=%d calls=%d pct=%.1f%% cost=%.6f€%s",
            context or "?",
            self.prompt, self.completion, self.total, self.calls,
            self.pct(Config.CONTEXT_MODEL_MAX_TOKENS),
            self.cost,
            co2_str,
        )

    # ── Représentation ────────────────────────────────────────────────────────

    def __str__(self) -> str:
        return (
            f"{self.prompt:,} prompt + {self.completion:,} completion "
            f"= {self.total:,} tokens"
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"TokenUsage(prompt={self.prompt}, completion={self.completion}, "
            f"calls={self.calls}, cost={self.cost:.6f})"
        )


# ── Accès au logger de tokens (pour context_manager) ─────────────────────────

def get_token_logger() -> logging.Logger:
    """
    Retourne le logger de tokens de l'application.

    Destiné aux modules qui ont besoin de logguer des événements de
    compression sans importer TokenUsage (ex : context_manager.py).
    """
    return _token_log
