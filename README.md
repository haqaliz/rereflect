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
| Access billing | Yes | No | No |
| Transfer ownership | Yes | No | No |

---

## Billing Tiers

| Tier | Price | Feedback/mo | Seats |
|------|-------|-------------|-------|
| Free | $0 | 250 | 2 |
| Pro | $29/mo | 2,500 | 10 |
| Business | $99/mo | 25,000 | 25 |
| Enterprise | Contact | Unlimited | Unlimited |

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

## Railway Deployment

### Services to Deploy
1. PostgreSQL (Database plugin)
2. Redis (Database plugin)
3. Backend API (Root: `services/backend-api`)
4. Worker Service (Root: `services/`, Config: `services/worker-service/railway.toml`)
5. Frontend (Root: `services/frontend-web`)

### Key Environment Variables

**Backend:**
```
DATABASE_URL=[Reference PostgreSQL]
REDIS_HOST=[Reference Redis]
REDIS_PORT=[Reference Redis]
JWT_SECRET=[Generate random 32+ chars]
CORS_ORIGINS=https://your-frontend.up.railway.app
```

**Frontend:**
```
NEXT_PUBLIC_API_URL=https://your-backend.up.railway.app
```

### Useful Commands
```bash
railway login
railway link
railway logs -s backend-api
railway up --service backend-api --detach
```

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

### Billing (Owner only)
```
GET  /api/v1/billing/subscription    # Current plan
POST /api/v1/billing/checkout        # Stripe checkout
POST /api/v1/billing/portal          # Billing portal
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

## License

MIT

---

**Goal**: $50K MRR SaaS Platform
