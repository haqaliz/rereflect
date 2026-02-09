#!/bin/sh
set -e

# Use Railway's PORT env var, default to 80 if not set
export PORT=${PORT:-80}

echo "Starting nginx on port $PORT..."

# Generate nginx config from template
envsubst '${PORT}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Test nginx configuration
nginx -t

# Start nginx in foreground
exec nginx -g 'daemon off;'
