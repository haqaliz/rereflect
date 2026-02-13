# Backend API Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (git needed for changelog export during build)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Export changelog from git history during build (JSON file used on startup)
RUN python scripts/sync_changelog.py --export changelog_commits.json --all || echo "Changelog export skipped (no git history)"

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

# Run with uvicorn - uses PORT env var for Railway compatibility
CMD sh -c "python -m uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT}"
