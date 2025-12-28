# Implementation Guide
## Customer Feedback Analyzer - SaaS Transformation

**Created**: 2025-12-27
**Status**: Ready to Begin

---

## Table of Contents

1. [Project Structure Overview](#project-structure-overview)
2. [Folder Restructuring Plan](#folder-restructuring-plan)
3. [Implementation Steps](#implementation-steps)
4. [Service Development Order](#service-development-order)
5. [Month 1 Detailed Plan](#month-1-detailed-plan)

---

## Project Structure Overview

We're organizing the project as **independent microservices** with shared documentation at the root.

### Architecture Diagram

```
customer-feedback-analyzer/               (Root - Documentation Only)
│
├── docs/                                 (All documentation files)
│   ├── PRD.md
│   ├── ROADMAP.md
│   ├── API.md
│   ├── GETTING_STARTED.md
│   ├── USAGE.md
│   └── ...
│
├── services/                             (All microservices)
│   ├── analysis-engine/                  (Python - Core ML/AI engine)
│   ├── backend-api/                      (FastAPI - REST API)
│   ├── frontend-web/                     (Next.js - Dashboard UI)
│   ├── worker-service/                   (Python - Background jobs)
│   └── integration-service/              (Python - 3rd party integrations)
│
├── shared/                               (Shared libraries/utilities)
│   ├── models/                           (Shared data models)
│   └── utils/                            (Common utilities)
│
├── infrastructure/                       (DevOps & deployment)
│   ├── kubernetes/                       (K8s manifests)
│   ├── terraform/                        (Infrastructure as code)
│   └── docker/                           (Dockerfiles)
│
└── .claude/                              (Claude Code skills)
```

---

## Folder Restructuring Plan

### Phase 1: Preserve Current MVP

Before restructuring, we'll move the existing working code to `services/analysis-engine/` since it's production-ready.

**Current Structure**:
```
src/
├── analyzer/          → services/analysis-engine/src/analyzer/
├── api/               → services/backend-api/src/api/
tests/                 → services/analysis-engine/tests/
examples/              → services/analysis-engine/examples/
```

### Phase 2: Create Service Folders

Each service will be a standalone project:

#### 1. **services/analysis-engine/** (Existing MVP)
Python service with VADER sentiment + clustering

```
services/analysis-engine/
├── src/
│   └── analyzer/
│       ├── __init__.py
│       ├── core.py           # Main analyzer
│       ├── sentiment.py      # VADER sentiment
│       ├── extractors.py     # Pain points & features
│       └── models.py         # Data models
├── tests/
│   ├── test_analyzer.py
│   ├── test_sentiment.py
│   └── test_extractors.py
├── examples/
│   └── usage_example.py
├── requirements.txt
├── Dockerfile
└── README.md
```

**Purpose**: Core analysis engine (can be called by backend-api and worker-service)

---

#### 2. **services/backend-api/** (New - Month 1)
FastAPI REST API with multi-tenant architecture

```
services/backend-api/
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI app
│   │   ├── dependencies.py   # Auth, DB session
│   │   └── routes/
│   │       ├── auth.py       # Login, signup
│   │       ├── organizations.py
│   │       ├── feedback.py
│   │       ├── dashboard.py
│   │       └── integrations.py
│   ├── models/
│   │   ├── user.py
│   │   ├── organization.py
│   │   └── feedback.py
│   └── database/
│       ├── session.py
│       └── migrations/       # Alembic migrations
├── tests/
│   ├── test_auth.py
│   └── test_api.py
├── alembic.ini
├── requirements.txt
├── Dockerfile
└── README.md
```

**Purpose**: REST API for frontend, handles auth, multi-tenancy, CRUD

---

#### 3. **services/frontend-web/** (New - Month 1)
Next.js 14 dashboard with TypeScript + TailwindCSS

```
services/frontend-web/
├── app/
│   ├── (auth)/
│   │   ├── login/
│   │   └── signup/
│   ├── (dashboard)/
│   │   ├── dashboard/
│   │   ├── feedback/
│   │   ├── integrations/
│   │   └── settings/
│   └── layout.tsx
├── components/
│   ├── ui/               # shadcn/ui components
│   ├── dashboard/
│   └── feedback/
├── lib/
│   ├── api.ts           # API client
│   ├── auth.ts          # Authentication
│   └── utils.ts
├── public/
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.js
└── README.md
```

**Purpose**: User-facing dashboard, onboarding, settings

---

#### 4. **services/worker-service/** (New - Month 2)
Background job processing with Celery

```
services/worker-service/
├── src/
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── analysis.py       # Analyze feedback batches
│   │   ├── alerts.py         # Check urgent alerts
│   │   └── integrations.py   # Sync from 3rd parties
│   ├── celery_app.py
│   └── config.py
├── tests/
├── requirements.txt
├── Dockerfile
└── README.md
```

**Purpose**: Async jobs (analysis, alerts, syncs)

---

#### 5. **services/integration-service/** (New - Month 2)
Integration connectors for 3rd party APIs

```
services/integration-service/
├── src/
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py          # Base connector
│   │   ├── intercom.py
│   │   ├── zendesk.py
│   │   ├── slack.py
│   │   └── email.py
│   └── sync/
│       └── scheduler.py     # Sync scheduling
├── tests/
├── requirements.txt
├── Dockerfile
└── README.md
```

**Purpose**: Pull data from Intercom, Zendesk, etc.

---

### Phase 3: Shared Libraries

#### **shared/models/** (Pydantic models used across services)
```
shared/models/
├── __init__.py
├── feedback.py       # FeedbackItem model
├── organization.py
└── user.py
```

#### **shared/utils/** (Common utilities)
```
shared/utils/
├── __init__.py
├── validation.py
└── formatters.py
```

---

## Implementation Steps

### Step 1: Restructure Existing Code (This Week)

1. **Create new folder structure**:
```bash
mkdir -p services/{analysis-engine,backend-api,frontend-web,worker-service,integration-service}
mkdir -p shared/{models,utils}
mkdir -p infrastructure/{kubernetes,terraform,docker}
mkdir -p docs
```

2. **Move documentation to docs/**:
```bash
mv *.md docs/
# Keep README.md at root
mv docs/README.md ./
```

3. **Move existing code to analysis-engine**:
```bash
# Move analyzer code
mv src services/analysis-engine/
mv tests services/analysis-engine/
mv examples services/analysis-engine/
mv requirements.txt services/analysis-engine/
mv quickstart.sh services/analysis-engine/
```

4. **Create service READMEs**:
Each service gets a README explaining:
- Purpose
- Tech stack
- How to run locally
- How to test
- API endpoints (if applicable)

---

### Step 2: Month 1 Week 1-2 - Backend API Setup

**Goal**: Authentication + Multi-tenant database

1. **Set up backend-api project**:
```bash
cd services/backend-api
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary pydantic python-jose
```

2. **Create database schema** (PostgreSQL):
```sql
-- Organizations table
CREATE TABLE organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) NOT NULL,  -- free, starter, professional, business, enterprise
    stripe_customer_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    organization_id INT REFERENCES organizations(id),
    role VARCHAR(50) NOT NULL,  -- admin, member, viewer
    created_at TIMESTAMP DEFAULT NOW()
);

-- Feedback items table
CREATE TABLE feedback_items (
    id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organizations(id),
    text TEXT NOT NULL,
    source VARCHAR(100),  -- intercom, zendesk, manual, etc
    sentiment_score FLOAT,
    sentiment_label VARCHAR(20),
    extracted_issue TEXT,
    is_urgent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_feedback_org ON feedback_items(organization_id, created_at);
```

3. **Implement authentication** (JWT tokens):
- POST /api/v1/auth/signup
- POST /api/v1/auth/login
- GET /api/v1/auth/me

4. **Implement organization endpoints**:
- GET /api/v1/organizations/{org_id}
- PATCH /api/v1/organizations/{org_id}

---

### Step 3: Month 1 Week 3-4 - Frontend Dashboard

**Goal**: Users can sign up, login, see dashboard

1. **Set up Next.js project**:
```bash
cd services/frontend-web
npx create-next-app@latest . --typescript --tailwind --app --use-pnpm
pnpm install @tanstack/react-query react-hook-form zod @hookform/resolvers/zod
pnpm install -D @types/node
```

2. **Install shadcn/ui**:
```bash
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button input card table
```

3. **Create pages**:
- `/login` - Login form
- `/signup` - Signup form + create org
- `/dashboard` - Main dashboard (sentiment overview, top pain points)
- `/feedback` - Feedback list/detail

4. **Connect to backend API**:
```typescript
// lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function login(email: string, password: string) {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  })
  return res.json()
}
```

---

### Step 4: Month 2 Week 5-6 - File Upload & Analysis

**Goal**: Users can upload CSV and see analysis

1. **Backend API endpoints**:
- POST /api/v1/feedback/upload (multipart/form-data)
- GET /api/v1/feedback (list with pagination)
- GET /api/v1/feedback/{id}

2. **Worker service**:
- Set up Celery + Redis
- Task: `analyze_feedback_batch(org_id, feedback_ids)`
- Calls `analysis-engine` to analyze
- Saves results to database

3. **Frontend**:
- File upload component (drag-drop)
- Progress indicator
- Results table

---

### Step 5: Month 2 Week 7-8 - Integrations (Intercom, Zendesk)

**Goal**: Auto-sync feedback from customer support tools

1. **Integration service**:
- Create connectors for Intercom, Zendesk APIs
- OAuth flows
- Pull conversations/tickets

2. **Backend API**:
- POST /api/v1/integrations (save credentials)
- GET /api/v1/integrations (list connected)
- DELETE /api/v1/integrations/{id}

3. **Worker service**:
- Daily sync task
- Fetch new feedback from integrations
- Analyze and save

---

### Step 6: Month 3 Week 9-10 - Slack Alerts

**Goal**: Send urgent feedback to Slack

**Implementation**: Follow `.claude/skills/feature-implementation.md` Slack example

1. Add `integrations` table
2. API: POST /api/v1/integrations/slack
3. Worker task: Check urgent feedback every 5 min
4. Frontend: Integration settings page

---

### Step 7: Month 3 Week 11 - Billing (Stripe)

**Goal**: Users can subscribe and pay

1. **Backend API**:
- POST /api/v1/billing/checkout (create Stripe checkout session)
- POST /api/v1/billing/portal (customer portal link)
- Webhook: /api/v1/billing/webhook (Stripe events)

2. **Frontend**:
- Pricing page
- Upgrade flow
- Billing settings

---

### Step 8: Month 3 Week 12 - Launch Prep

**Goal**: Polish, test, launch

1. **Landing page** (marketing site)
2. **Onboarding flow** (first-time user tutorial)
3. **Help docs** (in-app help center)
4. **Performance optimization**
5. **Security audit**
6. **Beta testing** (5 companies)
7. **Product Hunt launch**

---

## Service Development Order

Follow this order for best results:

```
Week 1-2:  backend-api (auth, database)
Week 3-4:  frontend-web (login, dashboard)
Week 5-6:  worker-service + analysis-engine integration
Week 7-8:  integration-service (Intercom, Zendesk)
Week 9-10: worker-service (Slack alerts)
Week 11:   backend-api (Stripe billing)
Week 12:   frontend-web (polish, landing page)
```

**Dependencies**:
- Frontend depends on backend-api
- Worker-service depends on analysis-engine
- Integration-service is independent (can build anytime)

---

## Month 1 Detailed Plan

### Week 1: Backend API Foundation

**Day 1-2**: Database setup
- [ ] Install PostgreSQL locally
- [ ] Create database: `customer_feedback_saas`
- [ ] Set up Alembic migrations
- [ ] Create initial schema (organizations, users, feedback_items)

**Day 3-4**: Authentication
- [ ] Implement user model (SQLAlchemy)
- [ ] Password hashing (bcrypt)
- [ ] JWT token generation (python-jose)
- [ ] POST /api/v1/auth/signup endpoint
- [ ] POST /api/v1/auth/login endpoint
- [ ] Test with Postman/curl

**Day 5**: Multi-tenancy
- [ ] Implement organization model
- [ ] Add organization_id to all queries
- [ ] Dependency: `get_current_org()` (validates JWT, returns org)
- [ ] Test: Ensure users can't access other orgs' data

---

### Week 2: Organization & Feedback Endpoints

**Day 6-7**: Organization CRUD
- [ ] GET /api/v1/organizations/{org_id}
- [ ] PATCH /api/v1/organizations/{org_id}
- [ ] Invite user endpoint (optional)

**Day 8-9**: Feedback endpoints
- [ ] POST /api/v1/feedback (create single feedback)
- [ ] GET /api/v1/feedback (list with pagination)
- [ ] GET /api/v1/feedback/{id}
- [ ] DELETE /api/v1/feedback/{id}

**Day 10**: Testing
- [ ] Write integration tests for all endpoints
- [ ] Test multi-tenant isolation
- [ ] Document API (OpenAPI/Swagger)

---

### Week 3: Frontend Setup

**Day 11-12**: Project setup
- [ ] Create Next.js project
- [ ] Install dependencies (TanStack Query, React Hook Form, Zod)
- [ ] Set up shadcn/ui
- [ ] Create layout structure

**Day 13-14**: Auth pages
- [ ] Login page (form + validation)
- [ ] Signup page (email, password, org name)
- [ ] Auth context (store JWT token)
- [ ] Protected route middleware

**Day 15**: Testing
- [ ] Test login flow
- [ ] Test signup flow
- [ ] Test token refresh

---

### Week 4: Dashboard UI

**Day 16-17**: Dashboard layout
- [ ] Sidebar navigation
- [ ] Header (user menu, org switcher)
- [ ] Dashboard route structure

**Day 18-19**: Dashboard widgets
- [ ] Sentiment overview (pie chart or gauge)
- [ ] Top pain points list (table)
- [ ] Top feature requests list (table)
- [ ] Date range picker

**Day 20**: Polish
- [ ] Responsive design (mobile, tablet)
- [ ] Loading states (skeletons)
- [ ] Error states (retry buttons)
- [ ] Dark mode (optional)

---

## Quick Start Commands

### Backend API
```bash
cd services/backend-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn src.api.main:app --reload --port 8000
```

### Frontend Web
```bash
cd services/frontend-web
pnpm install
pnpm run dev
# Visit http://localhost:3000
```

### Analysis Engine
```bash
cd services/analysis-engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python examples/usage_example.py
```

### Worker Service
```bash
cd services/worker-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
celery -A src.celery_app worker --loglevel=info
```

---

## Resources

- **Strategic Docs**: [docs/PRD.md](docs/PRD.md), [docs/ROADMAP.md](docs/ROADMAP.md)
- **Development Guides**: [.claude/skills/saas-development.md](.claude/skills/saas-development.md)
- **Feature Implementation**: [.claude/skills/feature-implementation.md](.claude/skills/feature-implementation.md)
- **Current MVP**: [services/analysis-engine/](services/analysis-engine/)

---

## Next Steps

1. **This Week**: Restructure folders (Step 1)
2. **Next Week**: Start backend-api (auth + database)
3. **Week 3**: Build frontend dashboard
4. **Month 2**: File upload, integrations
5. **Month 3**: Alerts, billing, launch

---

**Let's build! 🚀**

**Created**: 2025-12-27
**Status**: Ready to Execute
**First Task**: Restructure project folders
