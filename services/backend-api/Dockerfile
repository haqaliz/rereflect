# Backend API Dockerfile
# Build context must be ./services (parent directory) -- see docker-compose.yml /
# docker-compose.prod.yml. Needed so this image can COPY the sibling analysis-engine
# package (see below); a Docker build context cannot COPY anything outside itself.
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY backend-api/requirements.txt .
# --extra-index-url resolves the CPU-only torch wheel (PyPI's default torch wheel on
# Linux pulls the multi-GB CUDA build; this repo is CPU-only by design). Non-torch
# packages still resolve from PyPI normally.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Copy application code
COPY backend-api/ .

# Copy analysis engine so the sync sentiment re-analyze path
# (src/api/routes/feedback.py's sys.path lookup: dirname(__file__) + "../../../analysis-engine",
# which resolves to /app/analysis-engine at runtime) finds a real 'analyzer' package.
# Pre-existing bug fix: this COPY + the build-context move above were both previously
# missing, so `analyzer` could never import in a real backend-api image.
COPY analysis-engine/src/analyzer ./analysis-engine/analyzer

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port (Railway uses PORT env var)
EXPOSE 8000

# Default port (Railway overrides with PORT env var)
ENV PORT=8000

# Health check disabled - Railway handles this
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run migrations then start server
CMD sh -c "python -m alembic upgrade head && python -m uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT}"
