# =============================================================================
#  Prométhée AI — Dockerfile multi-stage
# =============================================================================
#  Stage 1 : build du frontend React (Vite)
#  Stage 2 : image Python de production avec le frontend embarqué
# =============================================================================

# ─────────────────────────────────────────────
#  Stage 1 — Build React
# ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Copier uniquement les manifests pour profiter du cache Docker
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copier le reste du frontend et builder
COPY frontend/ ./
RUN npm run build
# Résultat dans /build/dist


# ─────────────────────────────────────────────
#  Stage 2 — Image Python de production
# ─────────────────────────────────────────────
FROM python:3.11-slim AS app

# ── Forcer apt à utiliser HTTPS (proxies transparents qui bloquent le port 80) ─
RUN echo 'Acquire::http::Pipeline-Depth "0";\nAcquire::https::Pipeline-Depth "0";' \
      > /etc/apt/apt.conf.d/99https \
 && sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/*.sources 2>/dev/null || true \
 && sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list 2>/dev/null || true \
 && sed -i 's|http://security.debian.org|https://security.debian.org|g' /etc/apt/sources.list.d/*.sources 2>/dev/null || true \
 && sed -i 's|http://security.debian.org|https://security.debian.org|g' /etc/apt/sources.list 2>/dev/null || true

# ── Dépendances système ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OCR
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    # PDF → images
    poppler-utils \
    # WeasyPrint (export PDF HTML→PDF)
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-xlib-2.0-0 \
    shared-mime-info \
    fonts-liberation \
    # LibreOffice (export odt/ods/odp)
    libreoffice-nogui \
    # Extraction .doc legacy
    antiword \
    # Utilitaires
    curl \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# ── Répertoire de travail ─────────────────────────────────────────────────────
WORKDIR /app

# ── Dépendances Python ────────────────────────────────────────────────────────
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── Code source ───────────────────────────────────────────────────────────────
COPY core/       ./core/
COPY tools/      ./tools/
COPY server/     ./server/
COPY skills/     ./skills/
COPY scripts/    ./scripts/
COPY prompts.yml ./
COPY main.py     ./

# ── Frontend buildé (copié depuis le stage 1) ─────────────────────────────────
COPY --from=frontend-builder /build/dist ./frontend/dist

# ── Assets JS locaux (Mermaid, KaTeX) ────────────────────────────────────────
# Téléchargés au build pour ne pas dépendre d'internet au runtime
RUN python scripts/download_mermaid.py && python scripts/download_katex.py

# ── Répertoires de données persistants ───────────────────────────────────────
RUN mkdir -p /app/data /app/logs

# ── Utilisateur non-root ──────────────────────────────────────────────────────
RUN useradd -m -u 1000 promethee \
 && chown -R promethee:promethee /app
USER promethee

# ── Exposition du port ────────────────────────────────────────────────────────
EXPOSE 8000

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Démarrage ─────────────────────────────────────────────────────────────────
CMD ["uvicorn", "server.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
