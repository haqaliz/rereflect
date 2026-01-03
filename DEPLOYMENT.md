# Rereflect Deployment Guide

## Render Deployment (Recommended)

Render provides a simple, scalable platform with managed PostgreSQL and Redis.

### Prerequisites

1. GitHub repository with your code
2. [Render account](https://render.com) (free to sign up)

### Step-by-Step Deployment

#### 1. Push to GitHub

```bash
git add .
git commit -m "Add deployment configuration"
git push origin main
```

#### 2. Connect to Render

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New"** > **"Blueprint"**
3. Connect your GitHub repository
4. Select the repo containing `render.yaml`
5. Click **"Apply"**

Render will automatically create:
- `rereflect-api` - Backend API (FastAPI)
- `rereflect-worker` - Celery background worker
- `rereflect-frontend` - Next.js frontend
- `rereflect-redis` - Redis instance
- `rereflect-db` - PostgreSQL database

#### 3. Configure Environment Variables

After initial deployment, update these in the Render dashboard:

**rereflect-api:**
```
CORS_ORIGINS=https://rereflect-frontend.onrender.com
```

**rereflect-frontend:**
```
NEXT_PUBLIC_API_URL=https://rereflect-api.onrender.com
```

#### 4. Run Database Migrations

SSH into the API service or use the Shell tab:

```bash
cd /opt/render/project/src
alembic upgrade head
```

#### 5. Verify Deployment

- Frontend: `https://rereflect-frontend.onrender.com`
- API: `https://rereflect-api.onrender.com/docs`
- Health: `https://rereflect-api.onrender.com/health`

---

## Estimated Costs (Render)

| Service | Plan | Cost/Month |
|---------|------|------------|
| API | Starter | $7 |
| Worker | Starter | $7 |
| Frontend | Starter | $7 |
| Redis | Starter (25MB) | $7 |
| PostgreSQL | Starter (1GB) | $7 |
| **Total** | | **$35/mo** |

For production workloads, upgrade to Standard plans (~$100/mo total).

---

## Local Docker Development

Test the full stack locally before deploying:

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Run migrations
docker compose exec backend alembic upgrade head

# Stop all services
docker compose down

# Stop and remove volumes (reset data)
docker compose down -v
```

### Service URLs (Local)

- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

---

## Scaling on Render

### Horizontal Scaling

1. Go to service settings
2. Increase instance count (API, Worker)
3. Render handles load balancing automatically

### Vertical Scaling

Upgrade plans for more resources:

| Plan | CPU | RAM | Best For |
|------|-----|-----|----------|
| Starter | 0.5 | 512MB | Development |
| Standard | 1 | 2GB | Production |
| Pro | 2 | 4GB | High traffic |

### Worker Scaling

For high feedback volume, scale workers:

1. Create additional worker services from the same Dockerfile
2. Remove `--beat` from extra workers (only one Beat scheduler needed)

---

## Custom Domain

1. Go to service settings > **Custom Domains**
2. Add your domain (e.g., `app.rereflect.io`)
3. Add DNS records as instructed
4. Render provides free SSL

Update `CORS_ORIGINS` and `NEXT_PUBLIC_API_URL` with custom domains.

---

## Environment Variables Reference

### Backend API

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://...` |
| `REDIS_HOST` | Redis hostname | `rereflect-redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `JWT_SECRET` | Secret for JWT tokens | (auto-generated) |
| `CORS_ORIGINS` | Allowed origins (comma-separated) | `https://app.rereflect.io` |

### Worker Service

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://...` |
| `REDIS_HOST` | Redis hostname | `rereflect-redis` |
| `REDIS_PORT` | Redis port | `6379` |

### Frontend

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `https://rereflect-api.onrender.com` |

---

## Troubleshooting

### API not responding

```bash
# Check health endpoint
curl https://rereflect-api.onrender.com/health

# View logs in Render dashboard
```

### Worker not processing tasks

1. Check Redis connection in worker logs
2. Verify `DATABASE_URL` is correct
3. Ensure Beat scheduler is running (check for `celery beat` in logs)

### CORS errors

1. Verify `CORS_ORIGINS` includes your frontend URL
2. Include protocol: `https://...` not just domain
3. Redeploy API after changing

### Database connection issues

1. Check `DATABASE_URL` format
2. Verify database is running (green status in Render)
3. Check IP allowlist if using external connections

---

## Monitoring

### Render Dashboard

- View logs, metrics, and alerts
- Set up notifications for failures

### Optional: Add Sentry

```bash
# Add to requirements.txt
sentry-sdk[fastapi]==1.x.x

# Add to main.py
import sentry_sdk
sentry_sdk.init(dsn="your-sentry-dsn")
```

---

## Backup & Recovery

### Database Backups

Render automatically backs up PostgreSQL daily (retained 7 days on Starter).

### Manual Backup

```bash
pg_dump $DATABASE_URL > backup.sql
```

### Restore

```bash
psql $DATABASE_URL < backup.sql
```
