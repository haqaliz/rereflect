#!/bin/bash
# Deployment script for Rereflect on Raspberry Pi
# Called by webhook server when code is pushed

set -e

BRANCH=${1:-master}
APP_DIR="/opt/rereflect"
LOG_FILE="/var/log/rereflect-deploy.log"
COMPOSE_FILE="docker-compose.prod.yml"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting deployment of branch: $BRANCH"
log "=========================================="

cd "$APP_DIR"

# Pull latest code
log "Pulling latest code..."
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"

# Build and deploy with docker compose
log "Building containers..."
docker compose -f "$COMPOSE_FILE" build --parallel

log "Stopping old containers..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans

log "Starting new containers..."
docker compose -f "$COMPOSE_FILE" up -d

# Wait for services to be healthy
log "Waiting for services to be healthy..."
sleep 10

# Check health
if docker compose -f "$COMPOSE_FILE" ps | grep -q "unhealthy"; then
    log "ERROR: Some services are unhealthy!"
    docker compose -f "$COMPOSE_FILE" ps
    exit 1
fi

# Clean up old images
log "Cleaning up old images..."
docker image prune -f

log "=========================================="
log "Deployment completed successfully!"
log "=========================================="

# Show running services
docker compose -f "$COMPOSE_FILE" ps
