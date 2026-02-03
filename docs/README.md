# Rereflect Documentation

AI-powered customer feedback analysis SaaS platform.

## Quick Links

| Resource | Description |
|----------|-------------|
| [PLAN.md](./PLAN.md) | Development roadmap and task tracking |
| [Backend API Docs](https://api.rereflect.ca/docs) | Swagger UI |
| [Production App](https://app.rereflect.ca) | Live application |

---

## Product Overview

**Rereflect** transforms raw customer feedback into actionable insights using AI-powered sentiment analysis, pain point detection, and feature request extraction.

### Core Features
- **Sentiment Analysis** - Positive/neutral/negative classification
- **Pain Point Detection** - Categorized customer complaints
- **Feature Requests** - Extracted and prioritized suggestions
- **Urgent Flagging** - Churn risk detection
- **Multi-tenant** - Organization-based data isolation
- **Team Management** - RBAC with Owner/Admin/Member roles

---

## Subscription Tiers

| Tier | Price | Feedback/mo | Seats | Key Features |
|------|-------|-------------|-------|--------------|
| **Free** | $0 | 250 | 2 | Dashboard, CSV Import, Sentiment Analysis |
| **Pro** | $29/mo | 2,500 | 10 | + Slack Integration, Webhooks, Data Export |
| **Business** | $99/mo | 25,000 | 25 | + API Access, Advanced Analytics, Audit Logs |
| **Enterprise** | Custom | Unlimited | Unlimited | + SSO/SAML, Custom Integrations, SLA |

---

## Architecture

```
┌─────────────────┐
│  frontend-web   │  Next.js 16 + TypeScript + TailwindCSS
│  (app.rereflect)│
└────────┬────────┘
         │ REST API
         ▼
┌─────────────────┐
│   backend-api   │  FastAPI + PostgreSQL + SQLAlchemy
│ (api.rereflect) │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────────┐
│analysis│ │worker-     │  Celery + Redis
│-engine │ │service     │
└────────┘ └────────────┘
```

### Tech Stack

**Frontend**
- Next.js 16 (App Router)
- TypeScript 5.9
- TailwindCSS + shadcn/ui
- Recharts for analytics

**Backend**
- FastAPI 0.115
- PostgreSQL + SQLAlchemy 2.0
- Alembic migrations
- JWT authentication
- Celery + Redis

**Infrastructure**
- Railway (hosting)
- Stripe (billing)
- Resend (email)

---

## Role-Based Access Control (RBAC)

### Role Hierarchy
```
Owner (level 3) > Admin (level 2) > Member (level 1)
```

### Permission Matrix

| Action | Owner | Admin | Member |
|--------|-------|-------|--------|
| View dashboard & feedback | ✅ | ✅ | ✅ |
| Import feedback (CSV) | ✅ | ✅ | ✅ |
| View team list | ✅ | ✅ | ✅ |
| Manage integrations | ✅ | ✅ | ❌ |
| Invite/remove members | ✅ | ✅ | ❌ |
| Access billing | ✅ | ❌ | ❌ |
| Transfer ownership | ✅ | ❌ | ❌ |

---

## API Endpoints

### Authentication
```
POST /api/v1/auth/signup     # Create account
POST /api/v1/auth/login      # Get JWT token
GET  /api/v1/auth/me         # Current user info
```

### Feedback
```
GET  /api/v1/feedback        # List feedback (paginated)
POST /api/v1/feedback        # Create feedback
GET  /api/v1/feedback/:id    # Get single feedback
POST /api/v1/feedback/import # Import CSV
```

### Team Management
```
GET    /api/v1/team              # List members
POST   /api/v1/team/invite       # Send invite
GET    /api/v1/team/invites      # List pending invites
PATCH  /api/v1/team/:id/role     # Change role
DELETE /api/v1/team/:id          # Remove member
POST   /api/v1/team/transfer     # Transfer ownership
```

### Billing
```
GET  /api/v1/billing/plans        # List plans
GET  /api/v1/billing/subscription # Current subscription
POST /api/v1/billing/checkout     # Create Stripe checkout
POST /api/v1/billing/portal       # Stripe billing portal
GET  /api/v1/billing/usage        # Current usage
```

### Integrations
```
GET    /api/v1/integrations         # List integrations
POST   /api/v1/integrations         # Create integration
DELETE /api/v1/integrations/:id     # Delete integration
POST   /api/v1/integrations/:id/test # Test integration
```

---

## Development Setup

### Prerequisites
- Python 3.9+
- Node.js 18+
- PostgreSQL
- Redis

### Quick Start

```bash
# Clone and setup
git clone https://github.com/haqaliz/rereflect.git
cd rereflect

# Start all services
./start-all.sh

# Or individually:
# Backend: cd services/backend-api && ./start.sh
# Frontend: cd services/frontend-web && npm run dev
# Worker: cd services/worker-service && ./start.sh
```

### Local Ports
- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## Deployment

### Railway CLI
```bash
# Check status
railway status

# Deploy frontend
railway up --service frontend-web

# Deploy backend
railway up --service backend-api

# View logs
railway logs --service frontend-web --lines 50
```

### Environment Variables

**Backend**
```
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
JWT_SECRET_KEY=...
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
RESEND_API_KEY=re_...
```

**Frontend**
```
NEXT_PUBLIC_API_URL=https://api.rereflect.ca
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_...
```

---

## Key Files Reference

### Frontend
- `app/(dashboard)/` - Protected dashboard routes
- `components/SettingsTabs.tsx` - Tab visibility by role
- `contexts/AuthContext.tsx` - User authentication state
- `lib/api/` - API client functions

### Backend
- `src/api/routes/` - API endpoint handlers
- `src/api/dependencies.py` - Role checking middleware
- `src/models/` - SQLAlchemy ORM models
- `src/config/plans.py` - Subscription tier definitions

---

## Contact

- **Support**: support@rereflect.ca
- **Sales**: sales@rereflect.ca
