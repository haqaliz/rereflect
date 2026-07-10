# Celery Worker Dockerfile
# Build context should be ./services (parent directory)
FROM python:3.12-slim

WORKDIR /app

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
