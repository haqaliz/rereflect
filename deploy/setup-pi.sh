#!/bin/bash
# One-time setup script for Raspberry Pi
# Run this on the Pi after cloning the repo

set -e

echo "=========================================="
echo "Rereflect Pi Setup"
echo "=========================================="

APP_DIR="/opt/rereflect"
REPO_URL="${1:-git@github.com:YOUR_USERNAME/rereflect.git}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./setup-pi.sh)"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
apt-get update
apt-get install -y git curl

# Clone or update repo
if [ -d "$APP_DIR/.git" ]; then
    echo "Repo already exists, pulling latest..."
    cd "$APP_DIR"
    git pull
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# Create .env file if it doesn't exist
if [ ! -f "$APP_DIR/.env.prod" ]; then
    echo "Creating .env.prod file..."
    cat > "$APP_DIR/.env.prod" << 'EOF'
# Database
POSTGRES_USER=rereflect
POSTGRES_PASSWORD=CHANGE_THIS_DB_PASSWORD
POSTGRES_DB=rereflect

# Security
JWT_SECRET=CHANGE_THIS_JWT_SECRET

# Admin user (created on first startup)
ADMIN_EMAIL=haqaliz@aol.com
ADMIN_PASSWORD=CHANGE_THIS_ADMIN_PASSWORD

# URLs - Update with your Pi's IP or domain
# For Tailscale: use 100.107.59.96
# For local network: use 192.168.1.160
PI_HOST=100.107.59.96
NEXT_PUBLIC_API_URL=http://${PI_HOST}:8000
CORS_ORIGINS=http://${PI_HOST}:3000,http://localhost:3000

# Webhook
WEBHOOK_SECRET=CHANGE_THIS_WEBHOOK_SECRET
EOF
    echo ""
    echo "IMPORTANT: Edit /opt/rereflect/.env.prod with your secrets!"
    echo ""
fi

# Create log files
touch /var/log/rereflect-webhook.log
touch /var/log/rereflect-deploy.log
chmod 644 /var/log/rereflect-*.log

# Make scripts executable
chmod +x "$APP_DIR/deploy/deploy.sh"
chmod +x "$APP_DIR/deploy/webhook-server.py"

# Install systemd service
echo "Installing webhook service..."
cp "$APP_DIR/deploy/rereflect-webhook.service" /etc/systemd/system/

# Update service with webhook secret from .env.prod
if [ -f "$APP_DIR/.env.prod" ]; then
    source "$APP_DIR/.env.prod"
    sed -i "s/CHANGE_THIS_SECRET/${WEBHOOK_SECRET:-CHANGE_THIS_SECRET}/" /etc/systemd/system/rereflect-webhook.service
fi

systemctl daemon-reload
systemctl enable rereflect-webhook
systemctl start rereflect-webhook

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit secrets in /opt/rereflect/.env.prod"
echo ""
echo "2. Start the app:"
echo "   cd /opt/rereflect"
echo "   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d"
echo ""
echo "3. Add webhook to GitHub repo:"
echo "   URL: http://YOUR_PI_IP:9000/webhook"
echo "   Secret: (same as WEBHOOK_SECRET in .env.prod)"
echo "   Events: Just the push event"
echo ""
echo "4. Check webhook service:"
echo "   systemctl status rereflect-webhook"
echo "   curl http://localhost:9000/health"
echo ""
