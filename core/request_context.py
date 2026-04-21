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
request_context.py — Contexte par requête via contextvars.

Mécanisme
─────────
Python 3.7+ permet d'attacher des valeurs à l'exécution courante via
contextvars.ContextVar. asyncio.to_thread() propage automatiquement le
contexte asyncio vers le thread worker — ce qui permet aux tools exécutés
dans agent_loop() (dans un thread) de lire le UserConfig de l'utilisateur
qui a déclenché la requête.

Usage dans les tools et llm_clients
────────────────────────────────────
    from core.request_context import get_user_config

    ucfg = get_user_config()
    api_key = ucfg.OPENAI_API_KEY if ucfg else Config.OPENAI_API_KEY

Usage dans les routes FastAPI (ws_chat.py, etc.)
─────────────────────────────────────────────────
    from core.request_context import set_user_config

    set_user_config(user_config)           # avant to_thread()
    result = await asyncio.to_thread(...)  # le contexte est propagé

Rétrocompatibilité Qt6
───────────────────────
Quand le serveur FastAPI n'est pas utilisé, _USER_CONFIG_VAR n'est jamais
défini — get_user_config() retourne None et les tools tombent sur Config.
"""

import contextvars
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .user_config import UserConfig

_USER_CONFIG_VAR: contextvars.ContextVar[Optional["UserConfig"]] = (
    contextvars.ContextVar("user_config", default=None)
)


def set_user_config(user_config: Optional["UserConfig"]) -> None:
    """Positionne le UserConfig pour la requête courante (à appeler depuis la coroutine FastAPI)."""
    _USER_CONFIG_VAR.set(user_config)


def get_user_config() -> Optional["UserConfig"]:
    """Retourne le UserConfig de la requête courante, ou None (mode Qt6 / hors requête)."""
    return _USER_CONFIG_VAR.get()
