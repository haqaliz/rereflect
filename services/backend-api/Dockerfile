# Backend API Dockerfile
# Build context must be ./services (parent directory) -- see docker-compose.yml /
# docker-compose.prod.yml. Needed so this image can COPY the sibling analysis-engine
# package (see below); a Docker build context cannot COPY anything outside itself.
FROM python:3.12-slim

WORKDIR /app

# Cache dir for any Hugging Face model download or pre-bake below. Always set --
# costs nothing unset and implies no network access on its own.
ENV HF_HOME=/app/models
# Off by default: pull-and-cache-on-first-use is the default path for the opt-in
# transformer sentiment provider (M5.1). Set to "true" at build time for air-gapped
# installs that need the weights baked into the image (see the RUN step below).
ARG BAKE_SENTIMENT_MODEL=false

# Install system dependencies
#  - libpq-dev, gcc: existing (psycopg2 + C ext builds)
#  - libxml2/libxmlsec1 (+ -dev, -openssl), pkg-config, build-essential: native deps for python3-saml's
#    xmlsec binding. Runtime libs (libxml2, libxmlsec1, libxmlsec1-openssl) are required to LOAD xmlsec;
#    the -dev headers + pkg-config + build-essential are required to BUILD the xmlsec wheel from sdist if
#    no compatible manylinux wheel resolves. Single-stage image keeps both (see saml-sso deps-and-docker
#    plan §6 for a multi-stage slimming follow-up, out of scope this slice).
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    build-essential \
    pkg-config \
    libxml2 \
    libxml2-dev \
    libxmlsec1 \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY backend-api/requirements.txt .
# --extra-index-url resolves the CPU-only torch wheel (PyPI's default torch wheel on
# Linux pulls the multi-GB CUDA build; this repo is CPU-only by design). Non-torch
# packages still resolve from PyPI normally.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Optional build-time pre-bake of the transformer sentiment model for air-gapped installs.
# Off by default (BAKE_SENTIMENT_MODEL=false) to keep the base image lean; the transformer
# provider is opt-in per-org and, when enabled without a pre-baked cache, downloads and
# caches the model into HF_HOME on first use instead (requires runtime network access once).
# TODO(model-packaging): replace revision='main' with sentiment-provider-core's pinned
# revision SHA (see transformer.py _MODEL_REVISION) before merge.
RUN if [ "$BAKE_SENTIMENT_MODEL" = "true" ]; then \
        python -c "from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
MODEL_ID='cardiffnlp/twitter-roberta-base-sentiment-latest'; REVISION='main'; \
AutoModelForSequenceClassification.from_pretrained(MODEL_ID, revision=REVISION); \
AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION)" ; \
    fi

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
