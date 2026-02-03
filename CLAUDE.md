# Rereflect - Customer Feedback Analyzer

AI-powered customer feedback analysis platform for SaaS businesses.

## Project Overview

**Rereflect** transforms raw customer feedback into actionable insights using AI-powered sentiment analysis, pain point detection, and feature request extraction.

### Key Features
- Sentiment Analysis (positive/neutral/negative)
- Pain Point Detection with categorization
- Feature Request Extraction with prioritization
- Urgent Feedback Flagging (churn risk detection)
- Topic Clustering and tagging
- Multi-tenant organization support

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

## Tech Stack

### Frontend (`services/frontend-web`)
- **Framework**: Next.js 16 (App Router)
- **Language**: TypeScript 5.9
- **Styling**: TailwindCSS 3.4 with custom "Sunset Horizon" theme
- **UI Components**: shadcn/ui (Radix primitives)
- **Charts**: Recharts
- **Icons**: Lucide React

### Backend (`services/backend-api`)
- **Framework**: FastAPI 0.115
- **Database**: PostgreSQL with SQLAlchemy 2.0
- **Migrations**: Alembic
- **Auth**: JWT (python-jose) with bcrypt password hashing
- **Background Jobs**: Celery 5.3 with Redis broker

### Analysis Engine (`services/analysis-engine`)
- **Sentiment**: VADER sentiment analysis
- **NLP**: scikit-learn, BERTopic
- **Categorization**: Custom AI categorizer for pain points, features, urgency

## Development Setup

### Prerequisites
- Python 3.9+
- Node.js 18+
- PostgreSQL
- Redis

### Quick Start

```bash
# Start all services (recommended)
./start-all.sh

# Or start individually:
# Terminal 1: Redis
redis-server

# Terminal 2: Celery worker
cd services/worker-service && ./start.sh

# Terminal 3: Backend API
cd services/backend-api && ./start.sh

# Terminal 4: Frontend
cd services/frontend-web && npm run dev
```

### Service Ports
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Redis: localhost:6379

## Project Structure

```
rereflect/
├── services/
│   ├── frontend-web/          # Next.js frontend
│   │   ├── app/               # App Router pages
│   │   │   ├── (dashboard)/   # Protected dashboard routes
│   │   │   │   ├── dashboard/
│   │   │   │   ├── feedbacks/
│   │   │   │   ├── pain-points/
│   │   │   │   ├── feature-requests/
│   │   │   │   ├── urgent-feedbacks/
│   │   │   │   ├── categories/
│   │   │   │   └── settings/
│   │   │   ├── login/
│   │   │   └── signup/
│   │   ├── components/        # React components
│   │   │   ├── ui/            # shadcn/ui components
│   │   │   └── shared/        # Shared components (skeletons, etc.)
│   │   ├── contexts/          # React contexts (Theme, FeedbackPage)
│   │   ├── hooks/             # Custom React hooks
│   │   └── lib/               # Utilities and API client
│   │
│   ├── backend-api/           # FastAPI backend
│   │   ├── src/api/           # API routes
│   │   │   ├── routes/        # Endpoint handlers
│   │   │   └── main.py        # App entry point
│   │   ├── src/models/        # SQLAlchemy models
│   │   ├── src/database/      # DB session setup
│   │   ├── src/background/    # Celery scheduler
│   │   └── alembic/           # Database migrations
│   │
│   ├── analysis-engine/       # AI analysis service
│   │   └── src/analyzer/      # Core analysis logic
│   │
│   └── worker-service/        # Celery background workers
│       └── src/tasks/         # Async task definitions
│
├── shared/                    # Shared libraries
├── infrastructure/            # K8s, Terraform, Docker configs
├── docs/                      # Strategic documentation
└── start-all.sh               # Start all services script
```

## Key Files

### Frontend
- `app/(dashboard)/dashboard/page.tsx` - Main dashboard with charts and stats
- `app/(dashboard)/feedbacks/page.tsx` - Feedback list with DataTable
- `components/StatCard.tsx` - Stat card component with navigation
- `contexts/ThemeContext.tsx` - Dark/light theme management
- `contexts/FeedbackPageContext.tsx` - Feedback page state with URL sync
- `lib/api/` - API client functions

### Backend
- `src/api/main.py` - FastAPI app configuration
- `src/api/routes/` - API endpoint handlers
- `src/models/` - SQLAlchemy ORM models
- `src/background/scheduler.py` - Background job scheduler

## Theme System

The app uses a custom "Sunset Horizon" theme with CSS variables:

```css
/* Light mode palette */
--chart-1: oklch(0.65 0.18 25);   /* Primary coral */
--chart-2: oklch(0.72 0.14 65);   /* Warm amber/gold */
--chart-3: oklch(0.78 0.10 55);   /* Soft peach */
--destructive: oklch(0.55 0.22 25); /* Deep coral red */

/* Dark mode uses same hues with adjusted lightness */
```

Theme is applied via `data-theme` attribute and `.dark` class on `<html>`.

## API Patterns

### Authentication
All protected endpoints require JWT token:
```
Authorization: Bearer <token>
```

### Multi-tenancy
All data is scoped by `organization_id` extracted from JWT.

## Role-Based Access Control (RBAC)

### Role Hierarchy
```
Owner (level 3) > Admin (level 2) > Member (level 1)
```

### Permission Matrix

| Action | Owner | Admin | Member |
|--------|-------|-------|--------|
| View dashboard & analytics | ✅ | ✅ | ✅ |
| View feedback items | ✅ | ✅ | ✅ |
| Import feedback (CSV) | ✅ | ✅ | ✅ |
| View team list & invites | ✅ | ✅ | ✅ |
| Manage integrations | ✅ | ✅ | ❌ |
| Invite/remove members | ✅ | ✅ | ❌ |
| Change member roles | ✅ | ✅ | ❌ |
| Access billing | ✅ | ❌ | ❌ |
| Transfer ownership | ✅ | ❌ | ❌ |

### Backend Enforcement

Role checking dependencies in `src/api/dependencies.py`:
```python
require_admin_or_owner  # For admin/owner-only endpoints
require_owner           # For owner-only endpoints (billing, delete org)
```

Usage in routes:
```python
@router.post("/invite", dependencies=[Depends(require_admin_or_owner)])
@router.post("/billing/checkout", dependencies=[Depends(require_owner)])
```

### Frontend Enforcement

1. **Tab Visibility** (`components/SettingsTabs.tsx`):
   - Billing tab: owner only
   - Integrations tab: admin/owner only
   - Preferences & Team: all roles

2. **Route Protection** (in page components):
   - `/settings/billing` → redirects non-owners to `/settings/preferences`
   - `/settings/integrations` → redirects members to `/settings/preferences`

3. **Conditional UI** (buttons, actions):
   - `isOwner = user?.role === 'owner'`
   - `isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin'`

### Key RBAC Files
- `src/api/dependencies.py` - Backend role checking
- `src/api/routes/team.py` - Team management endpoints
- `components/SettingsTabs.tsx` - Tab visibility by role
- `contexts/AuthContext.tsx` - User role from JWT

## Billing & Subscription Tiers

Rereflect uses Stripe for billing with 4 subscription tiers:

| Tier | Price | Feedback/mo | Seats | Key Features |
|------|-------|-------------|-------|--------------|
| **Free** | $0 | 250 | 2 | Dashboard, CSV Import, Sentiment Analysis, Email Support |
| **Pro** | $29/mo | 2,500 | 10 | + Slack Integration, Webhooks, Data Export, Trends Analytics |
| **Business** | $99/mo | 25,000 | 25 | + API Access, Advanced Analytics, Custom Categories, Dedicated Support |
| **Enterprise** | Contact Sales | Unlimited | Unlimited | + SSO/SAML, Custom Integrations, SLA, Dedicated CSM, Audit Logs |

### Feature Gating

Features are gated by plan level using the `require_feature` dependency:

```python
@router.post("/slack/webhook", dependencies=[Depends(require_feature("slack_integration"))])
```

Feature IDs by tier:
- **Free**: `basic_dashboard`, `csv_import`, `sentiment_analysis`, `email_support`
- **Pro**: + `slack_integration`, `webhooks`, `data_export`, `trends_analytics`, `priority_support`
- **Business**: + `api_access`, `advanced_analytics`, `custom_categories`, `dedicated_support`
- **Enterprise**: + `sso_saml`, `custom_integrations`, `sla`, `dedicated_csm`, `audit_logs`, `custom_retention`

### Billing Enforcement

- **Feedback limits**: Checked in `POST /api/v1/feedback` via `check_feedback_limit` dependency
- **Feature access**: Checked via `require_feature(feature_id)` dependency
- **Overage tracking**: Pro/Business allow overage at $0.02/$0.01 per feedback
- **Enterprise**: Pay-as-you-go metered billing via Stripe Usage Records

### Key Billing Files
- `src/config/plans.py` - Plan definitions and feature mappings
- `src/api/routes/billing.py` - Billing API endpoints
- `src/api/dependencies.py` - Feature gating dependencies
- `src/services/stripe_service.py` - Stripe integration
- `src/models/subscription.py` - Subscription model
- `src/models/usage.py` - Usage tracking model
- `lib/api/billing.ts` - Frontend billing API

### Pagination
```
GET /api/v1/feedback?page=1&page_size=20&sort_by=created_at&sort_order=desc
```

### Filtering
```
GET /api/v1/feedback?sentiment=negative&is_urgent=true&search=payment
```

## Common Commands

```bash
# Frontend
cd services/frontend-web
npm run dev              # Start dev server
npm run build            # Production build
npm run lint             # Run ESLint

# Backend
cd services/backend-api
./start.sh               # Start with auto-reload
pytest tests/ -v         # Run tests

# Database
alembic upgrade head     # Apply migrations
alembic revision -m "description"  # Create migration

# All services
./start-all.sh           # Start all in tmux
./stop-all.sh            # Stop all services
```

## Development Guidelines

### Frontend
- Use TypeScript strict mode
- Follow shadcn/ui patterns for new components
- Use CSS variables for theming (never hardcode colors)
- Prefer `color-mix(in oklch, ...)` for color variations
- Use Skeleton components for loading states
- Keep components small and focused

### Backend
- All routes must validate organization_id
- Use Pydantic models for request/response validation
- Add appropriate error handling with HTTP status codes
- Write tests for new endpoints

### Git Workflow
- Feature branches from `master`
- Descriptive commit messages
- PR reviews before merge

## Troubleshooting

### FOUC (Flash of Unstyled Content)
Theme is initialized synchronously in `layout.tsx` via inline script before CSS loads.

### useSearchParams SSR Error
Wrap components using `useSearchParams` in `<Suspense>` boundary.

### 422 Validation Errors
- Check trailing slashes in API URLs
- Verify `page_size` doesn't exceed 100
- Ensure required fields are present

### Analysis Not Running
- Verify Redis is running: `redis-cli ping`
- Check Celery worker is active
- Look for errors in worker logs

## Resources

- [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) - Complete implementation guide
- [docs/PRD.md](docs/PRD.md) - Product requirements
- [docs/ROADMAP.md](docs/ROADMAP.md) - 12-month roadmap
- [Backend API Docs](http://localhost:8000/docs) - Swagger UI
