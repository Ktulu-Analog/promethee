"""
main.py — Point d'entrée de l'application Prométhée AI (FastAPI)
"""
import logging
import logging.handlers
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Configuration centralisée du logging ──────────────────────────────────
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.handlers.RotatingFileHandler(
            _LOG_DIR / "promethee.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
# ──────────────────────────────────────────────────────────────────────────

from tools import register_all
register_all()

# ── Diagnostic au démarrage ───────────────────────────────────────────────
from core.config import Config
import logging as _logging
_logging.getLogger("promethee.startup").info(
    "[Config] QDRANT_URL=%s | LTM_ENABLED=%s | LOCAL=%s | MODEL=%s",
    Config.QDRANT_URL, Config.LTM_ENABLED, Config.LOCAL, Config.active_model(),
)
# Les collections Qdrant (QDRANT_COLLECTION, LTM_COLLECTION) sont propres à
# chaque utilisateur et calculées dynamiquement par UserConfig à partir du
# username — elles ne sont plus des attributs de Config.
# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    host = getattr(Config, "SERVER_HOST", "0.0.0.0")
    port = int(getattr(Config, "SERVER_PORT", 8000))

    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        reload=False,
    )
