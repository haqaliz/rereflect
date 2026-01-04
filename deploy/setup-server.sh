#!/bin/bash
# Rereflect Server Setup Script
# Run this on your Pi4b to set up the complete deployment infrastructure

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (sudo ./setup-server.sh)"
    exit 1
fi

# Configuration
DOMAIN="${1:-}"
WEBHOOK_SECRET="${2:-$(openssl rand -hex 32)}"
DEPLOY_DIR="/opt/rereflect"

if [ -z "$DOMAIN" ]; then
    echo ""
    echo "Usage: ./setup-server.sh <domain> [webhook_secret]"
    echo ""
    echo "Example: ./setup-server.sh rereflect.example.com"
    echo ""
    exit 1
fi

log_info "Setting up Rereflect deployment for domain: $DOMAIN"
echo ""

# Update system
log_info "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install required packages
log_info "Installing required packages..."
apt-get install -y \
    nginx \
    certbot \
    python3-certbot-nginx \
    curl \
    git

# Create certbot webroot directory
mkdir -p /var/www/certbot

# Configure Nginx for initial certificate request
log_info "Configuring Nginx for certificate request..."
cat > /etc/nginx/sites-available/rereflect << NGINX_INITIAL
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'Rereflect - Waiting for SSL setup';
        add_header Content-Type text/plain;
    }
}
NGINX_INITIAL

# Enable the site
ln -sf /etc/nginx/sites-available/rereflect /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and reload nginx
nginx -t
systemctl reload nginx

log_info "Nginx configured for HTTP. Ready for certificate request."
echo ""

# Request SSL certificate
log_info "Requesting SSL certificate from Let's Encrypt..."
echo ""
echo "IMPORTANT: Make sure your domain $DOMAIN points to this server's IP!"
echo ""
read -p "Press Enter to continue with certificate request (Ctrl+C to cancel)..."

certbot certonly --webroot \
    -w /var/www/certbot \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "admin@$DOMAIN" \
    || {
        log_warn "Certbot failed. You may need to run it manually:"
        log_warn "  certbot certonly --webroot -w /var/www/certbot -d $DOMAIN"
        log_warn "Continuing with setup..."
    }

# Configure full Nginx with SSL
log_info "Configuring Nginx with SSL..."
sed "s/YOUR_DOMAIN/$DOMAIN/g" "$DEPLOY_DIR/deploy/nginx.conf" > /etc/nginx/sites-available/rereflect

# Test and reload nginx
if nginx -t; then
    systemctl reload nginx
    log_info "Nginx configured with SSL"
else
    log_warn "Nginx config test failed. Check /etc/nginx/sites-available/rereflect"
fi

# Update .env.prod with webhook secret
log_info "Updating environment configuration..."
if grep -q "^WEBHOOK_SECRET=" "$DEPLOY_DIR/.env.prod"; then
    sed -i "s/^WEBHOOK_SECRET=.*/WEBHOOK_SECRET=$WEBHOOK_SECRET/" "$DEPLOY_DIR/.env.prod"
else
    echo "WEBHOOK_SECRET=$WEBHOOK_SECRET" >> "$DEPLOY_DIR/.env.prod"
fi

# Update CORS and API URLs for the domain
sed -i "s|NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://$DOMAIN|" "$DEPLOY_DIR/.env.prod"
sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=https://$DOMAIN|" "$DEPLOY_DIR/.env.prod"

# Install webhook service
log_info "Installing webhook service..."
sed "s/^Environment=WEBHOOK_SECRET=$/Environment=WEBHOOK_SECRET=$WEBHOOK_SECRET/" \
    "$DEPLOY_DIR/deploy/rereflect-webhook.service" > /etc/systemd/system/rereflect-webhook.service

systemctl daemon-reload
systemctl enable rereflect-webhook
systemctl start rereflect-webhook

# Set up certbot auto-renewal
log_info "Setting up SSL certificate auto-renewal..."
(crontab -l 2>/dev/null | grep -v certbot; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -

# Final status
echo ""
echo "=========================================="
echo "  SETUP COMPLETE"
echo "=========================================="
echo ""
echo "Domain: https://$DOMAIN"
echo ""
echo "Webhook URL for GitHub:"
echo "  https://$DOMAIN/webhook"
echo ""
echo "Webhook Secret (save this!):"
echo "  $WEBHOOK_SECRET"
echo ""
echo "Services status:"
systemctl status rereflect-webhook --no-pager -l || true
echo ""
echo "Next steps:"
echo "1. Configure GitHub webhook at:"
echo "   https://github.com/YOUR_USER/rereflect/settings/hooks"
echo ""
echo "2. Set Payload URL to: https://$DOMAIN/webhook"
echo "3. Set Content type to: application/json"
echo "4. Set Secret to: $WEBHOOK_SECRET"
echo "5. Select 'Just the push event'"
echo ""
echo "6. Rebuild containers with new domain:"
echo "   cd $DEPLOY_DIR && ./deploy/deploy.sh"
echo ""
