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
main.py — Point d'entrée FastAPI de Prométhée

Lancement :
    uvicorn server.main:app --reload --port 8000
    # ou directement :
    python main.py

Variables d'environnement :
    SERVER_HOST          Hôte d'écoute       (défaut : 0.0.0.0)
    SERVER_PORT          Port d'écoute        (défaut : 8000)
    ALLOWED_ORIGINS      CORS origins JSON    (défaut : ["http://localhost:5173"])
    DB_ENCRYPTION        ON/OFF               (hérité de .env)
"""

import json
import logging
import logging.handlers
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_DIR = Path(__file__).parent.parent / "logs"
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
        logging.StreamHandler(sys.stdout),
    ],
)

_log = logging.getLogger("promethee.server")

# ── Ajout du répertoire racine au sys.path ────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import json as _json
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from tools import register_all
from core import Config, HistoryDB
from core import crypto

from server.deps import set_db
from core import user_manager as _user_manager
from server.routers.auth import router as auth_router
from server.routers.conversations import router as conversations_router
from server.routers.ws_chat import router as ws_chat_router
from server.routers.rag import router as rag_router
from server.routers.settings import router as settings_router
from server.routers.monitoring import router as monitoring_router
from server.routers.tools_router import router as tools_router
from server.routers.profiles_skills import router as profiles_skills_router
from server.routers.upload import router as upload_router
from server.routers.vfs_router import router as vfs_router
from server.routers.admin import router as admin_router
from server.routers.ingest_admin import router as ingest_admin_router


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _log.info("=== Prométhée server starting up ===")

    _user_manager.init_db()
    _log.info("[startup] users.db initialisée")

    register_all()
    _log.info("[startup] Outils enregistrés")

    db = HistoryDB(db_path=Config.HISTORY_DB)
    set_db(db)
    _log.info("[startup] Static dir : %s (exists=%s)", _STATIC, _STATIC.exists())
    _log.info("[startup] HistoryDB ouverte : %s (chiffrement=%s)",
              Config.HISTORY_DB, Config.DB_ENCRYPTION)

    yield

    crypto.clear_key_cache()
    _log.info("=== Prométhée server shut down ===")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Prométhée API",
    version=Config.APP_VERSION or "3.0.0",
    description="API FastAPI pour l'assistant Prométhée — interface web React.",
    lifespan=lifespan,
)

# ── Healthcheck middleware ─────────────────────────────────────────────────────
# Problème : app.mount("/", StaticFiles(..., html=True)) est un catch-all
# Starlette qui intercepte TOUTES les requêtes, y compris /health, avant même
# que le routeur FastAPI ne soit consulté. Une route @app.get("/health")
# déclarée n'importe où dans le code sera toujours masquée par ce mount.
#
# Solution : middleware ASGI intercept GET /health avant le routing, donc
# avant le StaticFiles. Il court-circuite la chaîne et répond directement.

class HealthCheckMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "GET" and request.url.path == "/health":
            return Response(
                content=_json.dumps({"status": "ok", "version": Config.APP_VERSION}),
                media_type="application/json",
            )
        return await call_next(request)

app.add_middleware(HealthCheckMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
_raw_origins = os.getenv("ALLOWED_ORIGINS", '["http://localhost:5173"]')
try:
    _origins = json.loads(_raw_origins)
except json.JSONDecodeError:
    _origins = [_raw_origins]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router,             prefix="/auth",          tags=["auth"])
app.include_router(conversations_router,    prefix="/conversations",  tags=["conversations"])
app.include_router(ws_chat_router,                                   tags=["websocket"])
app.include_router(rag_router,              prefix="/rag",            tags=["rag"])
app.include_router(settings_router,         prefix="/settings",       tags=["settings"])
app.include_router(monitoring_router,       prefix="/monitoring",     tags=["monitoring"])
app.include_router(tools_router,            prefix="/tools",          tags=["tools"])
app.include_router(profiles_skills_router,                           tags=["profiles", "skills"])
app.include_router(upload_router,                                    tags=["upload"])
app.include_router(vfs_router,                                       tags=["vfs"])
app.include_router(admin_router,            prefix="/admin",          tags=["admin"])
app.include_router(ingest_admin_router,     prefix="/admin",          tags=["admin-ingest"])

# ── Fichiers statiques React (build de production) ────────────────────────────
# Ce mount DOIT rester en dernier : il capture toutes les routes non définies
# ci-dessus (SPA fallback sur index.html). /health est géré par le middleware
# ci-dessus et n'atteint jamais ce mount.
_STATIC = _ROOT / "frontend" / "dist"
if _STATIC.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")
