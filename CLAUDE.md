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
├── TRACKING.md                # Development progress tracking
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

## Email Templates (Resend)

Rereflect uses [Resend](https://resend.com) for transactional emails with template-based rendering.

### Template Management Script

Use the management script to create, update, list, and delete templates:

```bash
cd services/backend-api

# List all templates
python scripts/manage_resend_templates.py list

# Get a specific template (view HTML content)
python scripts/manage_resend_templates.py get <template_id>

# Create a new template from HTML file
python scripts/manage_resend_templates.py create "template-name" "Subject Line" templates/email/template.html

# Update an existing template
python scripts/manage_resend_templates.py update <template_id> templates/email/template.html

# Delete a template (with confirmation)
python scripts/manage_resend_templates.py delete <template_id>
```

### Template Variable Syntax

Use triple curly braces for variables in HTML templates:
```html
<p>Hello, your role in {{{ORGANIZATION_NAME}}} has changed to {{{NEW_ROLE}}}.</p>
```

**Reserved variable names** (cannot be used): `FIRST_NAME`, `LAST_NAME`, `EMAIL`, `RESEND_UNSUBSCRIBE_URL`, `contact`, `this`

### Current Templates

| Template | Env Variable | Variables |
|----------|--------------|-----------|
| Team Invite | `RESEND_TEMPLATE_TEAM_INVITE` | `ORGANIZATION_NAME`, `INVITER_EMAIL`, `ROLE`, `INVITE_URL` |
| Welcome | `RESEND_TEMPLATE_WELCOME` | `ORGANIZATION_NAME`, `DASHBOARD_URL` |
| Password Reset | `RESEND_TEMPLATE_PASSWORD_RESET` | `RESET_URL` |
| Weekly Digest | `RESEND_TEMPLATE_WEEKLY_DIGEST` | `ORGANIZATION_NAME`, `WEEK_DATE`, `TOTAL_FEEDBACK`, `PAIN_POINTS`, `FEATURE_REQUESTS`, `POSITIVE_PERCENT`, `NEUTRAL_PERCENT`, `NEGATIVE_PERCENT`, `URGENT_COUNT`, `DASHBOARD_URL`, `UNSUBSCRIBE_URL` |
| Role Change | `RESEND_TEMPLATE_ROLE_CHANGE` | `ORGANIZATION_NAME`, `OLD_ROLE`, `NEW_ROLE`, `CHANGED_BY_EMAIL`, `DASHBOARD_URL` |
| Member Removed | `RESEND_TEMPLATE_MEMBER_REMOVED` | `ORGANIZATION_NAME`, `REMOVED_BY_EMAIL` |

### Adding a New Email Template

1. **Create HTML file** in `templates/email/`:
   ```bash
   # Use existing templates as reference for consistent styling
   cp templates/email/role_change.html templates/email/new_template.html
   ```

2. **Create template in Resend**:
   ```bash
   python scripts/manage_resend_templates.py create "new-template" "Subject with {{{VAR}}}" templates/email/new_template.html
   ```

3. **Add env variable** to `.env` and Railway:
   ```
   RESEND_TEMPLATE_NEW_TEMPLATE=<template_id_from_step_2>
   ```

4. **Add to email_service.py**:
   ```python
   TEMPLATE_NEW_TEMPLATE = os.getenv("RESEND_TEMPLATE_NEW_TEMPLATE")

   def send_new_template_email(to_email: str, var1: str) -> bool:
       return _send_with_template(
           to=to_email,
           template_id=TEMPLATE_NEW_TEMPLATE,
           variables={"VAR1": var1},
       )
   ```

5. **Call from route handler**:
   ```python
   from src.services.email_service import send_new_template_email
   send_new_template_email(user.email, some_value)
   ```

### Key Email Files
- `src/services/email_service.py` - Email sending functions
- `templates/email/` - HTML template source files
- `scripts/manage_resend_templates.py` - Template management CLI

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

## Agent Teams

Agent Teams coordinate multiple Claude Code sessions working in parallel. Use them for complex tasks where parallel work adds real value. Each teammate is an independent session with its own context window.

### When to Use Teams vs Subagents

| Scenario | Use |
|---|---|
| Quick focused task (search, single file edit) | **Subagent** |
| Complex cross-service feature (frontend + backend + worker) | **Agent Team** |
| Multi-angle code review (security + performance + architecture) | **Agent Team** |
| Bug investigation with competing hypotheses | **Agent Team** |
| Refactoring with test coverage | **Agent Team** |
| Simple code generation or single-file review | **Subagent** |

### Team Composition Patterns

When creating agent teams for Rereflect, use these compositions. Each references existing agent definitions from `~/.claude/agents/`.

#### 1. Full-Stack Feature Team

For implementing features that span frontend, backend, worker, and database layers.

**Teammates:**
- **frontend-dev** (`fe-react-specialist`): Next.js pages, React components, API client functions in `services/frontend-web/`
- **backend-dev** (`be-fastapi-specialist`): FastAPI routes, Pydantic schemas, SQLAlchemy models in `services/backend-api/`
- **worker-dev** (`be-fastapi-specialist`): Celery tasks, background jobs in `services/worker-service/`
- **db-architect** (`db-schema-designer`): Alembic migrations, schema design, index planning

**File ownership** (avoids conflicts):
- frontend-dev: `services/frontend-web/`
- backend-dev: `services/backend-api/src/api/`, `services/backend-api/src/models/`
- worker-dev: `services/worker-service/`
- db-architect: `services/backend-api/alembic/`

**Execution order:**
1. db-architect designs schema + creates migration
2. backend-dev implements models + API routes (depends on schema)
3. worker-dev implements background tasks (depends on models)
4. frontend-dev builds UI + API client (depends on API routes)

**Example prompt:**
```
Create an agent team to implement [FEATURE NAME]. Spawn 4 teammates:
- "frontend-dev" (fe-react-specialist): Build Next.js pages and components in services/frontend-web/
- "backend-dev" (be-fastapi-specialist): Implement FastAPI routes and Pydantic models in services/backend-api/
- "worker-dev" (be-fastapi-specialist): Build Celery tasks in services/worker-service/
- "db-architect" (db-schema-designer): Design schema and create Alembic migration

Require plan approval for db-architect before they create migrations.
Execution order: db-architect first, then backend-dev + worker-dev in parallel, then frontend-dev last.
Each teammate owns only their service directory — no cross-file edits.
```

#### 2. Code Review Squad

For thorough multi-angle review of PRs or significant changes.

**Teammates:**
- **security-reviewer** (`review-security`): OWASP vulnerabilities, auth issues, input validation, secrets
- **perf-reviewer** (`review-performance`): N+1 queries, re-renders, bundle size, API response size
- **arch-reviewer** (`review-architecture`): SOLID principles, separation of concerns, coupling, testability

**All teammates are read-only** — they review and report findings without making changes.

**Example prompt:**
```
Create an agent team to review the recent changes. Spawn 3 reviewers:
- "security-reviewer" (review-security): Check for OWASP vulnerabilities, auth issues, input validation
- "perf-reviewer" (review-performance): Check for N+1 queries, unnecessary re-renders, API payload size
- "arch-reviewer" (review-architecture): Check SOLID principles, coupling, testability

All reviewers are read-only — report findings only, do not edit code.
Focus on files changed in the current branch: [LIST FILES OR use `git diff --name-only master`]
Have each reviewer report findings with severity levels, then synthesize a combined review.
```

#### 3. Debug Investigation Team

For investigating bugs with multiple competing hypotheses in parallel.

**Teammates:**
- **detective-1** (`util-debug-detective`): Hypothesis A investigation
- **detective-2** (`util-debug-detective`): Hypothesis B investigation
- **backend-expert** (`be-fastapi-specialist`): FastAPI/SQLAlchemy-specific debugging
- **frontend-expert** (`fe-react-specialist`): React/Next.js-specific debugging

**Example prompt:**
```
Create an agent team to investigate [BUG DESCRIPTION]. Spawn teammates to test competing hypotheses:
- "detective-backend" (util-debug-detective): Investigate if the issue is in the FastAPI backend — check routes, models, DB queries in services/backend-api/
- "detective-frontend" (util-debug-detective): Investigate if the issue is in the Next.js frontend — check components, API calls, state in services/frontend-web/
- "detective-worker" (util-debug-detective): Investigate if the issue is in the Celery worker — check tasks, Redis connection in services/worker-service/

Have them share findings with each other and challenge each other's hypotheses.
The bug symptoms are: [DESCRIBE SYMPTOMS]
```

#### 4. Refactoring Team

For safe, well-tested refactoring of existing code.

**Teammates:**
- **architect** (`review-architecture`): Analyze current structure, design target architecture (read-only)
- **refactorer** (`util-refactoring-specialist`): Execute the refactoring changes
- **test-writer** (`qa-unit-test`): Write/update tests to maintain coverage through the refactoring

**Example prompt:**
```
Create an agent team to refactor [MODULE/AREA]. Spawn 3 teammates:
- "architect" (review-architecture): Analyze current structure and design the target architecture — read-only, plan approval required
- "refactorer" (util-refactoring-specialist): Execute refactoring changes following the architect's plan
- "test-writer" (qa-unit-test): Write tests before refactoring (characterization tests) and update after

Execution order: architect plans first (require approval), then test-writer writes characterization tests, then refactorer executes changes, then test-writer updates tests.
Focus area: [DESCRIBE WHAT TO REFACTOR]
```

### Team Usage Tips

- **Delegate mode**: Press `Shift+Tab` to restrict the lead to coordination only (no coding)
- **Direct messaging**: Use `Shift+Up/Down` to select and message individual teammates
- **Task list**: Press `Ctrl+T` to toggle the shared task list
- **Plan approval**: Add "Require plan approval" for risky changes (DB migrations, auth changes)
- **File ownership**: Always assign clear file boundaries to avoid edit conflicts
- **Cleanup**: Tell the lead to "shut down all teammates, then clean up the team" when done

### Rereflect-Specific Agent Mapping

| Layer | Primary Agent | Secondary Agent |
|---|---|---|
| Frontend (Next.js) | `fe-react-specialist` | `fe-ui-implementer` |
| Backend (FastAPI) | `be-fastapi-specialist` | `be-api-designer` |
| Database (PostgreSQL) | `db-schema-designer` | `db-migration-planner` |
| Worker (Celery) | `be-fastapi-specialist` | — |
| Security Review | `review-security` | — |
| Performance Review | `review-performance` | — |
| Architecture Review | `review-architecture` | — |
| Unit Tests | `qa-unit-test` | `qa-test-generator` |
| E2E Tests | `qa-e2e-playwright` | — |
| Bug Investigation | `util-debug-detective` | `qa-bug-hunter` |
| Refactoring | `util-refactoring-specialist` | — |

## Resources

- [README.md](README.md) - Project overview and setup
- [DEV-TRACKING.md](DEV-TRACKING.md) - Development progress and roadmap
- [SALES-TRACKING.md](SALES-TRACKING.md) - Sales strategy and growth tracking
- [Backend API Docs](http://localhost:8000/docs) - Swagger UI (when running)
