# Architecture

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
│analysis│ │  worker-   │  Celery + Redis
│-engine │ │  service   │
└────────┘ └────────────┘
```

A Next.js frontend talks to a FastAPI backend over REST. Long-running analysis is
offloaded to a Celery worker (Redis broker), which uses the analysis engine — VADER /
scikit-learn / BERTopic locally, or an LLM provider when an organization has configured
a key.

## Services

| Service | Stack | Responsibility |
|---------|-------|----------------|
| `frontend-web` | Next.js 16 (App Router), TypeScript 5.9, TailwindCSS 3.4, shadcn/ui, Recharts | Dashboard SPA |
| `backend-api` | FastAPI 0.115, SQLAlchemy 2.0, Alembic, PostgreSQL, JWT | REST API, auth, persistence |
| `worker-service` | Celery 5.3, Redis | Async feedback analysis & background jobs |
| `analysis-engine` | VADER, scikit-learn, BERTopic | Sentiment, categorization, topic clustering |
| `landing-web` | Next.js | Marketing site (rereflect.ca) |

## Tech stack

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
- OpenAI / Anthropic / Google providers (BYOK) for LLM-grade analysis

## Project structure

```
rereflect/
├── services/
│   ├── frontend-web/          # Next.js dashboard
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
│   ├── worker-service/        # Celery background jobs
│   └── landing-web/           # Marketing site
│
├── packages/ui/               # Shared React component library
├── docs/                      # Documentation (this folder)
├── docker-compose.prod.yml    # Self-hosting stack
└── CLAUDE.md                  # Claude Code instructions
```

## Role-Based Access Control (RBAC)

### Role hierarchy

```
Owner (level 3) > Admin (level 2) > Member (level 1)
```

### Permission matrix

| Action | Owner | Admin | Member |
|--------|:-----:|:-----:|:------:|
| View dashboard & analytics | ✅ | ✅ | ✅ |
| View feedback items | ✅ | ✅ | ✅ |
| Import feedback (CSV) | ✅ | ✅ | ✅ |
| View team list & invites | ✅ | ✅ | ✅ |
| Manage integrations | ✅ | ✅ | ❌ |
| Invite/remove members | ✅ | ✅ | ❌ |
| Change member roles | ✅ | ✅ | ❌ |
| Transfer ownership | ✅ | ❌ | ❌ |

Roles are enforced on the backend via dependencies (`require_admin_or_owner`,
`require_owner`) and on the frontend via tab visibility and route guards. All data
access is additionally scoped by `organization_id` from the JWT.
