# Celery Worker Dockerfile
# Build context should be ./services (parent directory)
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
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY worker-service/requirements.txt .
# --extra-index-url resolves the CPU-only torch wheel (PyPI's default torch wheel on
# Linux pulls the multi-GB CUDA build; this repo is CPU-only by design). Non-torch
# packages still resolve from PyPI normally.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Download NLTK data for sentiment analysis
RUN python -c "import nltk; nltk.download('vader_lexicon', quiet=True); nltk.download('punkt', quiet=True)"

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

# Copy worker service code
COPY worker-service/src ./src

# Copy analysis engine (needed for sentiment analysis)
# Copy contents of src/ so 'analyzer' module is directly importable
COPY analysis-engine/src/analyzer ./analyzer

# Set PYTHONPATH to include /app for analyzer module
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Default: run worker with beat scheduler
CMD ["celery", "-A", "src.celery_app", "worker", "--beat", "--loglevel=info"]
