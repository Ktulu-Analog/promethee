"""
main.py — Point d'entrée de l'application Prométhée AI
"""
import logging
import logging.handlers
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Configuration centralisée du logging ──────────────────────────────────
# Tous les loggers du projet (getLogger(__name__)) propagent vers la racine.
# Aucune sortie console — tout va dans logs/promethee.log.
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.handlers.RotatingFileHandler(
            _LOG_DIR / "promethee.log",
            maxBytes=5 * 1024 * 1024,   # 5 Mo
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
# ──────────────────────────────────────────────────────────────────────────

from tools import register_all
register_all()

# ── Diagnostic collections Qdrant ─────────────────────────────────────────
from core.config import Config
import logging as _logging
_logging.getLogger("promethee.startup").info(
    "[Config] QDRANT_COLLECTION=%s | LTM_COLLECTION=%s | LTM_ENABLED=%s | RAG_USER_ID=%r",
    Config.QDRANT_COLLECTION, Config.LTM_COLLECTION, Config.LTM_ENABLED, Config.RAG_USER_ID,
)
# ──────────────────────────────────────────────────────────────────────────

from ui import run

if __name__ == "__main__":
    run()
