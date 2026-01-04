# Rereflect Deployment Guide

Complete guide for deploying Rereflect to a Raspberry Pi 4b with automated CI/CD, SSL, and domain setup.

## Architecture Overview

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    Raspberry Pi 4b                       │
                    │                                                          │
 GitHub ──webhook──▶│  ┌─────────┐    ┌─────────┐    ┌─────────────────────┐  │
                    │  │ Nginx   │───▶│ Webhook │───▶│ Deploy Script       │  │
                    │  │ :80/443 │    │ :9000   │    │ (pull/build/migrate)│  │
                    │  └────┬────┘    └─────────┘    └─────────────────────┘  │
                    │       │                                                  │
 Users ────HTTPS───▶│       ▼                                                  │
                    │  ┌─────────┐    ┌─────────┐    ┌─────────┐              │
                    │  │Frontend │    │ Backend │    │ Worker  │              │
                    │  │ :3000   │    │ :8000   │    │ Celery  │              │
                    │  └─────────┘    └────┬────┘    └────┬────┘              │
                    │                      │              │                    │
                    │                 ┌────┴────┐   ┌────┴────┐               │
                    │                 │Postgres │   │  Redis  │               │
                    │                 │  :5432  │   │  :6379  │               │
                    │                 └─────────┘   └─────────┘               │
                    └─────────────────────────────────────────────────────────┘
```

## Prerequisites

### On Your Pi4b
- Raspberry Pi 4b with 4GB+ RAM
- Raspberry Pi OS (64-bit) or Ubuntu Server
- Docker and Docker Compose installed
- Git installed
- SSH access configured

### Domain & Network
- A domain name (e.g., `rereflect.yourdomain.com`)
- DNS A record pointing to your Pi's public IP
- Ports 80 and 443 forwarded to Pi (if behind NAT)
- Or: Use Tailscale for private access

---

## Initial Server Setup

### 1. Install Docker on Pi4b

```bash
# SSH into your Pi
ssh root@pi4b

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group (if not root)
usermod -aG docker $USER

# Install Docker Compose plugin
apt-get update
apt-get install -y docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### 2. Clone the Repository

```bash
# Create deployment directory
mkdir -p /opt/rereflect
cd /opt

# Clone the repository
git clone https://github.com/haqaliz/rereflect.git
cd rereflect
```

### 3. Create Environment File

```bash
cat > /opt/rereflect/.env.prod << 'ENVEOF'
# Database
POSTGRES_USER=rereflect
POSTGRES_PASSWORD=YOUR_SECURE_DB_PASSWORD
POSTGRES_DB=rereflect

# Security
JWT_SECRET=YOUR_SECURE_JWT_SECRET_MIN_32_CHARS

# Admin user (created on first startup)
ADMIN_EMAIL=your@email.com
ADMIN_PASSWORD=your_secure_admin_password

# URLs - Update with your domain
NEXT_PUBLIC_API_URL=https://yourdomain.com
CORS_ORIGINS=https://yourdomain.com

# Webhook (will be set by setup script)
WEBHOOK_SECRET=
ENVEOF

# Secure the file
chmod 600 /opt/rereflect/.env.prod
```

---

## Domain & SSL Setup

### Option A: Public Domain with Let's Encrypt

#### 1. Configure DNS

Add an A record in your DNS provider:
```
Type: A
Name: rereflect (or @ for root domain)
Value: YOUR_PI_PUBLIC_IP
TTL: 300
```

#### 2. Port Forwarding (if behind NAT)

Forward these ports to your Pi's local IP:
- Port 80 → Pi:80 (HTTP, for Let's Encrypt)
- Port 443 → Pi:443 (HTTPS)

#### 3. Run Setup Script

```bash
cd /opt/rereflect
./deploy/setup-server.sh yourdomain.com
```

The script will:
- Install Nginx and Certbot
- Request SSL certificate from Let's Encrypt
- Configure Nginx as reverse proxy
- Start the webhook listener service
- Set up SSL auto-renewal

**Save the webhook secret displayed at the end!**

### Option B: Tailscale (Private Access)

If using Tailscale for private access without public domain:

```bash
# Install Tailscale on Pi
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up

# Get Tailscale IP
tailscale ip -4  # e.g., 100.107.59.96

# Update .env.prod with Tailscale IP
sed -i 's|NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://100.107.59.96:8000|' /opt/rereflect/.env.prod
sed -i 's|CORS_ORIGINS=.*|CORS_ORIGINS=http://100.107.59.96:3000|' /opt/rereflect/.env.prod
```

For Tailscale, you can skip Nginx/SSL and access directly:
- Frontend: `http://TAILSCALE_IP:3000`
- Backend: `http://TAILSCALE_IP:8000`

---

## GitHub Webhook Configuration

### 1. Get Your Webhook Secret

If you used the setup script, it displayed the secret. Otherwise, generate one:

```bash
# Generate a new secret
WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "Webhook Secret: $WEBHOOK_SECRET"

# Add to .env.prod
echo "WEBHOOK_SECRET=$WEBHOOK_SECRET" >> /opt/rereflect/.env.prod
```

### 2. Configure GitHub Webhook

Go to: `https://github.com/YOUR_USERNAME/rereflect/settings/hooks/new`

| Setting | Value |
|---------|-------|
| **Payload URL** | `https://yourdomain.com/webhook` |
| **Content type** | `application/json` |
| **Secret** | Your webhook secret from step 1 |
| **SSL verification** | Enable (if using SSL) |
| **Events** | ☑ Just the push event |
| **Active** | ☑ Checked |

Click **Add webhook**

### 3. Test the Webhook

GitHub will send a ping event. Check:
```bash
# View webhook logs
tail -f /opt/rereflect/deploy/webhook.log

# Or check systemd service
journalctl -u rereflect-webhook -f
```

---

## Manual Deployment

If you need to deploy manually (without webhook):

```bash
ssh root@pi4b
cd /opt/rereflect

# Pull latest changes
git pull origin master

# Run deployment
./deploy/deploy.sh
```

Or step by step:

```bash
# Pull changes
git fetch origin master
git reset --hard origin/master

# Rebuild and restart
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod down
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

# Run migrations
docker exec rereflect-backend python -m alembic upgrade head

# Check status
docker compose -f docker-compose.prod.yml ps
```

---

## Service Management

### Webhook Service

```bash
# Status
systemctl status rereflect-webhook

# Restart
systemctl restart rereflect-webhook

# View logs
journalctl -u rereflect-webhook -f

# Stop/Start
systemctl stop rereflect-webhook
systemctl start rereflect-webhook
```

### Docker Containers

```bash
cd /opt/rereflect

# View status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend

# Restart all
docker compose -f docker-compose.prod.yml restart

# Restart specific service
docker compose -f docker-compose.prod.yml restart backend

# Stop all
docker compose -f docker-compose.prod.yml down

# Start all
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### Nginx

```bash
# Test config
nginx -t

# Reload
systemctl reload nginx

# View logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

---

## SSL Certificate Management

### Check Certificate Status

```bash
certbot certificates
```

### Manual Renewal

```bash
certbot renew
systemctl reload nginx
```

### Auto-Renewal (set up by setup script)

```bash
# View cron job
crontab -l | grep certbot

# Should show:
# 0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'
```

---

## Troubleshooting

### Webhook Not Triggering

1. Check webhook service is running:
   ```bash
   systemctl status rereflect-webhook
   ```

2. Check webhook logs:
   ```bash
   tail -100 /opt/rereflect/deploy/webhook.log
   ```

3. Verify GitHub webhook delivery:
   - Go to GitHub repo → Settings → Webhooks → Recent Deliveries
   - Check for errors

4. Test webhook manually:
   ```bash
   curl -X POST http://localhost:9000/webhook \
     -H "Content-Type: application/json" \
     -H "X-GitHub-Event: ping" \
     -d '{"zen": "test"}'
   ```

### Container Issues

1. Check container status:
   ```bash
   docker compose -f docker-compose.prod.yml ps -a
   ```

2. View container logs:
   ```bash
   docker logs rereflect-backend
   docker logs rereflect-frontend
   docker logs rereflect-worker
   ```

3. Restart unhealthy container:
   ```bash
   docker compose -f docker-compose.prod.yml restart backend
   ```

### Database Issues

1. Check PostgreSQL:
   ```bash
   docker exec rereflect-postgres pg_isready -U rereflect
   ```

2. Connect to database:
   ```bash
   docker exec -it rereflect-postgres psql -U rereflect -d rereflect
   ```

3. Run migrations manually:
   ```bash
   docker exec rereflect-backend python -m alembic upgrade head
   ```

### SSL Issues

1. Check Nginx config:
   ```bash
   nginx -t
   ```

2. Check certificate:
   ```bash
   certbot certificates
   ```

3. Force renewal:
   ```bash
   certbot renew --force-renewal
   systemctl reload nginx
   ```

---

## Backup & Restore

### Backup Database

```bash
# Create backup
docker exec rereflect-postgres pg_dump -U rereflect rereflect > backup_$(date +%Y%m%d).sql

# Compress
gzip backup_$(date +%Y%m%d).sql
```

### Restore Database

```bash
# Stop backend and worker
docker compose -f docker-compose.prod.yml stop backend worker

# Restore
gunzip backup_YYYYMMDD.sql.gz
docker exec -i rereflect-postgres psql -U rereflect -d rereflect < backup_YYYYMMDD.sql

# Start services
docker compose -f docker-compose.prod.yml start backend worker
```

### Backup Volumes

```bash
# Create backup directory
mkdir -p /opt/backups

# Backup PostgreSQL data
docker run --rm -v rereflect_postgres_data:/data -v /opt/backups:/backup alpine \
  tar czf /backup/postgres_data_$(date +%Y%m%d).tar.gz /data

# Backup Redis data
docker run --rm -v rereflect_redis_data:/data -v /opt/backups:/backup alpine \
  tar czf /backup/redis_data_$(date +%Y%m%d).tar.gz /data
```

---

## URLs Reference

| Service | URL |
|---------|-----|
| Frontend | `https://yourdomain.com` |
| Backend API | `https://yourdomain.com/api/` |
| API Documentation | `https://yourdomain.com/docs` |
| Health Check | `https://yourdomain.com/health` |
| Webhook Endpoint | `https://yourdomain.com/webhook` |

---

## File Locations on Pi4b

| Path | Description |
|------|-------------|
| `/opt/rereflect/` | Main application directory |
| `/opt/rereflect/.env.prod` | Environment variables |
| `/opt/rereflect/deploy/` | Deployment scripts |
| `/opt/rereflect/deploy/deploy.log` | Deployment logs |
| `/opt/rereflect/deploy/webhook.log` | Webhook service logs |
| `/etc/nginx/sites-available/rereflect` | Nginx configuration |
| `/etc/letsencrypt/live/yourdomain.com/` | SSL certificates |
| `/etc/systemd/system/rereflect-webhook.service` | Webhook systemd service |

---

## Quick Reference Commands

```bash
# Deploy manually
cd /opt/rereflect && ./deploy/deploy.sh

# View all logs
docker compose -f docker-compose.prod.yml logs -f

# Restart everything
docker compose -f docker-compose.prod.yml restart

# Check webhook
systemctl status rereflect-webhook

# Run migrations
docker exec rereflect-backend python -m alembic upgrade head

# Check SSL
certbot certificates
```
