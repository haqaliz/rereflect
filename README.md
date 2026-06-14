# Rereflect

**AI-powered customer feedback analysis platform for SaaS businesses**

Transform customer feedback into actionable insights with sentiment analysis, pain point detection, feature request extraction, and churn risk identification.

---

## Features

- **Sentiment Analysis** - Track positive/neutral/negative trends
- **Pain Point Detection** - Auto-identify customer complaints
- **Feature Requests** - Detect and prioritize what customers want
- **Urgent Flagging** - Identify churn risks in real-time
- **Topic Clustering** - Group feedback by themes
- **Multi-tenant** - Organization isolation with RBAC

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+
- PostgreSQL 14+
- Redis

### Start All Services
```bash
./start-all.sh
```

### Or Start Individually

**Backend API:**
```bash
cd services/backend-api && ./start.sh
```

**Frontend:**
```bash
cd services/frontend-web && npm run dev
```

**Worker (Celery):**
```bash
cd services/worker-service && ./start.sh
```

### Access URLs
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

---

## Architecture

```
┌─────────────────┐
│  frontend-web   │  Next.js 16 + TypeScript + TailwindCSS
└────────┬────────┘
         │ REST API
         ▼
┌─────────────────┐
│   backend-api   │  FastAPI + PostgreSQL + SQLAlchemy
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────────┐
│analysis│ │worker-     │  Celery + Redis
│-engine │ │service     │
└────────┘ └────────────┘
```

---

## Tech Stack

### Frontend (`services/frontend-web`)
- Next.js 16 (App Router)
- TypeScript 5.9
- TailwindCSS 3.4 + shadcn/ui
- Recharts

### Backend (`services/backend-api`)
- FastAPI 0.115
- PostgreSQL + SQLAlchemy 2.0
- Alembic (migrations)
- JWT authentication
- Celery 5.3 + Redis

### AI/ML (`services/analysis-engine`)
- VADER sentiment analysis
- scikit-learn + BERTopic

---

## Project Structure

```
rereflect/
├── services/
│   ├── frontend-web/          # Next.js frontend
│   │   ├── app/               # App Router pages
│   │   │   └── (dashboard)/   # Protected routes
│   │   ├── components/        # React components
│   │   ├── contexts/          # Auth, Theme contexts
│   │   └── lib/               # API client, utilities
│   │
│   ├── backend-api/           # FastAPI backend
│   │   ├── src/api/routes/    # API endpoints
│   │   ├── src/models/        # SQLAlchemy models
│   │   └── alembic/           # Database migrations
│   │
│   ├── analysis-engine/       # AI analysis service
│   └── worker-service/        # Celery background jobs
│
├── infrastructure/            # K8s, Terraform, Docker
├── CLAUDE.md                  # Claude Code instructions
├── README.md                  # This file
└── TRACKING.md                # Development progress
```

---

## Role-Based Access Control (RBAC)

### Role Hierarchy
```
Owner (level 3) > Admin (level 2) > Member (level 1)
```

### Permission Matrix

| Action | Owner | Admin | Member |
|--------|-------|-------|--------|
| View dashboard & analytics | Yes | Yes | Yes |
| View feedback items | Yes | Yes | Yes |
| Import feedback (CSV) | Yes | Yes | Yes |
| View team list & invites | Yes | Yes | Yes |
| Manage integrations | Yes | Yes | No |
| Invite/remove members | Yes | Yes | No |
| Change member roles | Yes | Yes | No |
| Transfer ownership | Yes | No | No |

---

## Features & Limits

Rereflect is open source and self-hosted — **every feature is unlocked with no
limits**. There are no paid tiers, feedback quotas, or seat caps. The
`SELF_HOSTED=true` flag (the default) treats every instance as fully featured.

| Capability | Self-hosted |
|------------|-------------|
| Feedback / month | Unlimited |
| Team seats | Unlimited |
| Sentiment, pain points, feature requests, churn | Included |
| Advanced churn, cohorts, playbooks, analytics | Included |
| Integrations, webhooks, data export, API access | Included |
| AI copilot & LLM analysis (BYOK) | Included (bring your own key) |

---

## Development Setup

### Database Setup
```bash
createdb customer_feedback_saas
cd services/backend-api
source venv/bin/activate
alembic upgrade head
```

### Backend Environment (.env)
```
DATABASE_URL=postgresql:///customer_feedback_saas
JWT_SECRET=dev-secret-key-change-in-production
REDIS_HOST=localhost
REDIS_PORT=6379
```

### Frontend Environment (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Self-Hosting

Rereflect is open source (MIT) and designed to run entirely on your own
infrastructure. **All features are unlocked** on a self-hosted instance — there
are no paid tiers, seat limits, or feedback quotas.

### Prerequisites
- Docker + Docker Compose
- (Optional) Your own LLM API key for AI features — **not required**

### Quick Start (Docker Compose)

```bash
# 1. Copy and edit the production env template
cp .env.prod.example .env

# 2. Generate secrets and fill them into .env (see "Required env vars" below)

# 3. Build and start everything (Postgres, Redis, backend, worker, frontend)
docker compose -f docker-compose.prod.yml up -d --build
```

Then open the frontend at `http://localhost:3000` and log in with the
`ADMIN_EMAIL` / `ADMIN_PASSWORD` you set in `.env` (the first admin user is
seeded on startup).

### Required env vars

Set these in your `.env` (see `.env.prod.example` for the full annotated list):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | Secret for signing auth tokens (random 32+ chars) |
| `LLM_ENCRYPTION_KEY` | Fernet key used to encrypt stored BYOK LLM keys |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeds the first admin account |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `SELF_HOSTED` | Keep `true` — unlocks all features |
| `ai_analysis_enabled` | `false` by default — runs on free local VADER |

Generate `JWT_SECRET` and `LLM_ENCRYPTION_KEY`:

```bash
# JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"

# LLM_ENCRYPTION_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Running with no API key ($0, fully local)

Out of the box (`ai_analysis_enabled=false`, no LLM key), Rereflect runs the
**free local VADER + keyword analysis pipeline**. Sentiment, pain-point,
feature-request, and heuristic churn detection all work end-to-end with **no
external API and no cost**. This is the default and recommended starting point.

### Adding your own LLM key (BYOK)

To enable LLM-powered analysis and the AI copilot, bring your own key:

- **In-app (canonical):** Sign in, go to **Settings → AI**, and paste your
  OpenAI / Anthropic / Google key. Keys are encrypted at rest with
  `LLM_ENCRYPTION_KEY` (Fernet) and scoped per organization.
- **From env (single-tenant convenience):** You may also seed an operator key
  via `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_AI_API_KEY` in `.env`.
  This is treated as **your own key** for your own instance — Rereflect never
  provides or proxies a key.

There is no system/vendor key. If an organization has no key configured, AI
features degrade gracefully back to the free VADER pipeline rather than erroring.

### Notes

- **Frontend bakes its API URL at build time.** `NEXT_PUBLIC_API_URL` is
  embedded into the frontend image during `docker build`. If you deploy on a
  real host/domain, set `NEXT_PUBLIC_API_URL` to your backend's public URL and
  **rebuild** the frontend image (`docker compose -f docker-compose.prod.yml
  build frontend`).
- **No TLS in the bundled compose.** Services bind plain HTTP on `:3000`
  (frontend) and `:8000` (backend). For internet-facing deployments, put a
  reverse proxy (Caddy, nginx, Traefik) in front for TLS.

---

## API Reference

### Authentication
```
POST /api/v1/auth/signup
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

### Feedback
```
GET    /api/v1/feedback              # List with pagination
POST   /api/v1/feedback              # Create
GET    /api/v1/feedback/{id}         # Get one
PUT    /api/v1/feedback/{id}         # Update
DELETE /api/v1/feedback/{id}         # Delete
POST   /api/v1/feedback/import       # CSV import
```

### Dashboard
```
GET /api/v1/dashboard                # Analytics data
```

### Team Management
```
GET    /api/v1/team                  # List members
POST   /api/v1/team/invite           # Send invite
PATCH  /api/v1/team/{id}/role        # Change role
DELETE /api/v1/team/{id}             # Remove member
```

---

## Common Commands

```bash
# Start all services
./start-all.sh

# Stop all services
./stop-all.sh

# Run backend tests
cd services/backend-api && pytest tests/ -v

# Run database migrations
cd services/backend-api && alembic upgrade head

# Create new migration
alembic revision -m "description"

# Frontend build
cd services/frontend-web && npm run build
```

---

## Troubleshooting

### Port already in use
```bash
lsof -ti:8000 | xargs kill  # Backend
lsof -ti:3000 | xargs kill  # Frontend
```

### Database connection errors
```bash
# Check PostgreSQL is running
pg_isready

# Create database if missing
createdb customer_feedback_saas
```

### Redis connection errors
```bash
redis-cli ping  # Should return PONG
```

### Analysis not running
- Verify Redis: `redis-cli ping`
- Check Celery worker logs
- Ensure worker service is running

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup,
testing, and PR conventions.

---

## License

MIT — see [LICENSE](LICENSE). Third-party attributions are in [NOTICE](NOTICE).

---

**Rereflect is free and open source. Self-host it, hack on it, make it yours.**
