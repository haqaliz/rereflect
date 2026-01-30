# Railway Deployment Guide

Deploy Rereflect to Railway with PostgreSQL, Redis, and all application services.

## Prerequisites

- Railway account with payment info added
- GitHub repository connected to Railway
- This repository pushed to GitHub

## Architecture on Railway

```
┌─────────────────────────────────────────────────────────────┐
│                    Railway Project                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  PostgreSQL │  │    Redis    │  │   Backend API       │  │
│  │  (Plugin)   │  │  (Plugin)   │  │   (FastAPI)         │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │             │
│         └────────────────┼─────────────────────┘             │
│                          │                                   │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │                  Internal Network                      │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌─────────────────────┐ │ ┌─────────────────────────────┐  │
│  │   Worker Service    │◄┘ │   Frontend (Next.js)        │  │
│  │   (Celery)          │   │   Public Domain             │  │
│  └─────────────────────┘   └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Step-by-Step Deployment

### Step 1: Create Railway Project

1. Go to [railway.app](https://railway.app) and log in
2. Click **"New Project"**
3. Select **"Empty Project"**
4. Name it `rereflect` (or your preferred name)

### Step 2: Add PostgreSQL Database

1. In your project, click **"+ New"** → **"Database"** → **"PostgreSQL"**
2. Wait for it to provision (takes ~30 seconds)
3. Click on the PostgreSQL service
4. Go to **"Variables"** tab
5. Copy the `DATABASE_URL` value (you'll need this later)

### Step 3: Add Redis

1. Click **"+ New"** → **"Database"** → **"Redis"**
2. Wait for it to provision
3. Click on the Redis service
4. Go to **"Variables"** tab
5. Note the `REDIS_HOST` and `REDIS_PORT` values

### Step 4: Deploy Backend API

1. Click **"+ New"** → **"GitHub Repo"**
2. Select your `rereflect` repository
3. Railway will detect it as a monorepo - **click "Configure"**
4. Configure the service:
   - **Name**: `backend-api`
   - **Root Directory**: `services/backend-api`
   - **Config Path**: Leave empty (auto-detects `railway.toml`)
5. Click **"Deploy"**

6. After initial deploy, go to **"Settings"** tab:
   - Under **"Networking"**, click **"Generate Domain"**
   - Note this URL (e.g., `backend-api-production-xxxx.up.railway.app`)

7. Go to **"Variables"** tab and add:
   ```
   DATABASE_URL          = [Reference PostgreSQL → DATABASE_URL]
   REDIS_HOST            = [Reference Redis → REDISHOST]
   REDIS_PORT            = [Reference Redis → REDISPORT]
   JWT_SECRET            = [Generate: click "Generate" for 32+ char random string]
   CORS_ORIGINS          = https://your-frontend-domain.up.railway.app
   ADMIN_EMAIL           = admin@yourdomain.com
   ADMIN_PASSWORD        = [Your secure admin password]
   ```

   **To reference another service's variable:**
   - Click "Add Variable"
   - Click the "Reference" button
   - Select the service (PostgreSQL/Redis) and variable

### Step 5: Deploy Worker Service

1. Click **"+ New"** → **"GitHub Repo"**
2. Select your `rereflect` repository again
3. Configure the service:
   - **Name**: `worker-service`
   - **Root Directory**: `services` ⚠️ **Important: Set to `services/` not `services/worker-service/`**
   - **Config Path**: `services/worker-service/railway.toml`
4. Click **"Deploy"**

5. Go to **"Variables"** tab and add:
   ```
   DATABASE_URL          = [Reference PostgreSQL → DATABASE_URL]
   REDIS_HOST            = [Reference Redis → REDISHOST]
   REDIS_PORT            = [Reference Redis → REDISPORT]
   ```

### Step 6: Deploy Frontend

1. Click **"+ New"** → **"GitHub Repo"**
2. Select your `rereflect` repository again
3. Configure the service:
   - **Name**: `frontend-web`
   - **Root Directory**: `services/frontend-web`
4. Click **"Deploy"**

5. Go to **"Settings"** tab:
   - Under **"Networking"**, click **"Generate Domain"**
   - This is your public URL (e.g., `frontend-web-production-xxxx.up.railway.app`)

6. Go to **"Variables"** tab and add:
   ```
   NEXT_PUBLIC_API_URL   = https://[your-backend-domain].up.railway.app
   ```

7. **Important**: Go back to the Backend API service and update `CORS_ORIGINS` to include the frontend domain.

### Step 7: Run Database Migrations

1. Go to the **Backend API** service
2. Click **"Settings"** → **"Deploy"** section
3. Or use Railway CLI:
   ```bash
   # Install Railway CLI
   npm install -g @railway/cli

   # Login
   railway login

   # Link to project
   railway link

   # Run migrations on backend service
   railway run -s backend-api alembic upgrade head
   ```

### Step 8: Verify Deployment

1. **Backend Health Check**:
   ```
   https://[backend-domain].up.railway.app/health
   ```
   Should return: `{"status": "healthy"}`

2. **API Docs**:
   ```
   https://[backend-domain].up.railway.app/docs
   ```

3. **Frontend**:
   ```
   https://[frontend-domain].up.railway.app
   ```

4. **Login** with your admin credentials

## Environment Variables Reference

### Backend API
| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Reference from PostgreSQL |
| `REDIS_HOST` | Redis hostname | Reference from Redis |
| `REDIS_PORT` | Redis port | Reference from Redis |
| `JWT_SECRET` | Secret for JWT tokens | Generate 32+ chars |
| `CORS_ORIGINS` | Allowed origins (comma-separated) | `https://frontend.railway.app` |
| `ADMIN_EMAIL` | Default admin email | `admin@example.com` |
| `ADMIN_PASSWORD` | Default admin password | Secure password |

### Worker Service
| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Reference from PostgreSQL |
| `REDIS_HOST` | Redis hostname | Reference from Redis |
| `REDIS_PORT` | Redis port | Reference from Redis |

### Frontend
| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `https://backend.railway.app` |

## Custom Domain (Optional)

1. Go to the Frontend service → **"Settings"** → **"Networking"**
2. Click **"+ Custom Domain"**
3. Enter your domain (e.g., `app.rereflect.com`)
4. Add the CNAME record to your DNS:
   ```
   CNAME app.rereflect.com → [railway-provided-target]
   ```
5. Wait for SSL certificate provisioning

## Troubleshooting

### Build Failures

**Worker service can't find analysis-engine:**
- Ensure Root Directory is set to `services/` (not `services/worker-service/`)
- Ensure Config Path is `services/worker-service/railway.toml`

**Frontend build fails with API URL error:**
- Ensure `NEXT_PUBLIC_API_URL` is set BEFORE building
- If already built, trigger a redeploy after setting the variable

### Runtime Errors

**Database connection errors:**
- Check `DATABASE_URL` is correctly referenced
- Ensure PostgreSQL service is running

**Redis connection errors:**
- Check `REDIS_HOST` and `REDIS_PORT` are correctly referenced
- Ensure Redis service is running

**CORS errors:**
- Update `CORS_ORIGINS` in backend to include frontend URL
- Redeploy backend after updating

### Logs

View logs for any service:
1. Click on the service
2. Go to **"Deployments"** tab
3. Click on the latest deployment
4. View **"Build Logs"** or **"Deploy Logs"**

Or use CLI:
```bash
railway logs -s backend-api
railway logs -s worker-service
railway logs -s frontend-web
```

## Cost Estimation

With Railway's $5 free credit:

| Resource | Estimated Cost |
|----------|----------------|
| PostgreSQL | ~$0.05/day |
| Redis | ~$0.02/day |
| Backend API | ~$0.10/day (when active) |
| Worker Service | ~$0.10/day (always running) |
| Frontend | ~$0.05/day (when active) |
| **Total** | ~$10-15/month |

Services sleep when inactive, reducing costs. The $5 credit covers several weeks of light usage.

## Useful Commands

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Link to your project
railway link

# View all services
railway status

# View logs
railway logs -s [service-name]

# Run command on a service
railway run -s backend-api python -c "print('hello')"

# Open service in browser
railway open

# Deploy manually
railway up
```
