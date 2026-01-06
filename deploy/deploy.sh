#!/bin/bash
# Rereflect Auto-Deployment Script
# Triggered by GitHub webhook on push to master

set -e

# Configuration
DEPLOY_DIR="/opt/rereflect"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
LOG_FILE="/opt/rereflect/deploy/deploy.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting deployment"
log "=========================================="

cd "$DEPLOY_DIR"

# Pull latest changes
log "Pulling latest changes from git..."
git fetch origin master
git reset --hard origin/master

# Build and deploy with docker compose
log "Building and deploying containers..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build

log "Stopping existing containers..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down --remove-orphans

log "Starting containers..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# Wait for postgres to be healthy
log "Waiting for PostgreSQL to be healthy..."
for i in {1..30}; do
    if docker exec rereflect-postgres pg_isready -U rereflect > /dev/null 2>&1; then
        log "PostgreSQL is ready"
        break
    fi
    sleep 2
done

# Wait for backend to start
log "Waiting for backend to start..."
sleep 10

# Run database migrations
log "Running database migrations..."
docker exec rereflect-backend python -m alembic upgrade head || {
    log "WARNING: Migration failed, but continuing..."
}

# Health check
log "Running health checks..."
sleep 5

BACKEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "000")
FRONTEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/ || echo "000")

if [ "$BACKEND_HEALTH" = "200" ]; then
    log "Backend health check: PASSED"
else
    log "Backend health check: FAILED (HTTP $BACKEND_HEALTH)"
fi

if [ "$FRONTEND_HEALTH" = "200" ]; then
    log "Frontend health check: PASSED"
else
    log "Frontend health check: FAILED (HTTP $FRONTEND_HEALTH)"
fi

# Cleanup old images
log "Cleaning up old Docker images..."
docker image prune -f

log "=========================================="
log "Deployment completed"
log "=========================================="

# Show container status
docker compose -f "$COMPOSE_FILE" ps
