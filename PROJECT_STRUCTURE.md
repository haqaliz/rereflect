# Project Structure

**Clean microservices architecture for Customer Feedback Analyzer SaaS**

---

## Directory Layout

```
customer-feedback-analyzer/                 (Root - Organization only)
│
├── 📄 README.md                            Main project overview
├── 📄 IMPLEMENTATION_GUIDE.md              👈 Complete implementation guide
├── 📄 GETTING_STARTED_NOW.md               Quick start (5 steps)
├── 📄 RESTRUCTURE_COMPLETE.md              Restructure summary
├── 📄 LICENSE                              MIT License
│
├── 📁 docs/                                📚 All strategic documentation
│   ├── PRD.md                              Product Requirements (80+ pages)
│   ├── ROADMAP.md                          12-month development plan (50+ pages)
│   ├── SAAS_TRANSFORMATION_SUMMARY.md      How to use all docs
│   ├── API.md                              API reference
│   ├── USAGE.md                            Usage examples
│   ├── GETTING_STARTED.md                  Setup guide
│   ├── START_HERE.md                       New user intro
│   └── ...                                 Other docs
│
├── 📁 services/                            🎯 Independent microservices
│   │
│   ├── 📁 analysis-engine/                 ✅ PRODUCTION READY
│   │   ├── src/analyzer/                   Core AI engine
│   │   │   ├── core.py                     Main analyzer
│   │   │   ├── sentiment.py                VADER sentiment
│   │   │   ├── extractors.py               Pain points & features
│   │   │   └── models.py                   Data models
│   │   ├── src/api/                        FastAPI wrapper (optional)
│   │   │   └── main.py                     REST API
│   │   ├── tests/                          29 tests (100% passing)
│   │   ├── examples/                       Usage examples
│   │   ├── requirements.txt                Python dependencies
│   │   ├── quickstart.sh                   Quick start script
│   │   ├── .env.example                    Environment template
│   │   └── README.md                       Service documentation
│   │
│   ├── 📁 backend-api/                     🚧 Month 1 (Week 1-2)
│   │   ├── src/api/                        FastAPI REST API
│   │   │   ├── main.py                     App entry point
│   │   │   └── routes/                     API endpoints
│   │   │       ├── auth.py                 Authentication
│   │   │       ├── organizations.py        Organizations CRUD
│   │   │       ├── feedback.py             Feedback CRUD
│   │   │       ├── dashboard.py            Dashboard data
│   │   │       └── integrations.py         Integration management
│   │   ├── src/models/                     SQLAlchemy models
│   │   │   ├── user.py                     User model
│   │   │   ├── organization.py             Organization model
│   │   │   └── feedback.py                 Feedback model
│   │   ├── src/database/                   Database setup
│   │   │   ├── session.py                  DB connection
│   │   │   └── migrations/                 Alembic migrations
│   │   ├── tests/                          API tests
│   │   ├── requirements.txt                Python dependencies
│   │   ├── alembic.ini                     Migration config
│   │   └── README.md                       Service documentation
│   │
│   ├── 📁 frontend-web/                    🚧 Month 1 (Week 3-4)
│   │   ├── app/                            Next.js 14 App Router
│   │   │   ├── (auth)/                     Auth pages
│   │   │   │   ├── login/page.tsx          Login page
│   │   │   │   └── signup/page.tsx         Signup page
│   │   │   ├── (dashboard)/                Protected pages
│   │   │   │   ├── dashboard/page.tsx      Main dashboard
│   │   │   │   ├── feedback/page.tsx       Feedback list
│   │   │   │   ├── integrations/page.tsx   Integrations
│   │   │   │   └── settings/page.tsx       Settings
│   │   │   └── layout.tsx                  Root layout
│   │   ├── components/                     React components
│   │   │   ├── ui/                         shadcn/ui components
│   │   │   ├── dashboard/                  Dashboard widgets
│   │   │   └── feedback/                   Feedback components
│   │   ├── lib/                            Utilities
│   │   │   ├── api.ts                      API client
│   │   │   ├── auth.ts                     Auth utilities
│   │   │   └── utils.ts                    Common utils
│   │   ├── package.json                    Dependencies
│   │   ├── tsconfig.json                   TypeScript config
│   │   ├── tailwind.config.ts              Tailwind config
│   │   └── README.md                       Service documentation
│   │
│   ├── 📁 worker-service/                  🚧 Month 2 (Week 5-6)
│   │   ├── src/tasks/                      Celery tasks
│   │   │   ├── analysis.py                 Batch analysis
│   │   │   ├── alerts.py                   Urgent alerts
│   │   │   └── integrations.py             Sync tasks
│   │   ├── src/celery_app.py               Celery config
│   │   ├── requirements.txt                Python dependencies
│   │   └── README.md                       Service documentation
│   │
│   └── 📁 integration-service/             🚧 Month 2 (Week 7-8)
│       ├── src/connectors/                 API connectors
│       │   ├── base.py                     Base connector
│       │   ├── intercom.py                 Intercom API
│       │   ├── zendesk.py                  Zendesk API
│       │   ├── slack.py                    Slack webhooks
│       │   └── ...                         Other integrations
│       ├── requirements.txt                Python dependencies
│       └── README.md                       Service documentation
│
├── 📁 shared/                              🔧 Shared libraries
│   ├── models/                             Common data models
│   │   ├── __init__.py
│   │   ├── feedback.py                     Feedback model (Pydantic)
│   │   ├── organization.py                 Organization model
│   │   └── user.py                         User model
│   └── utils/                              Common utilities
│       ├── __init__.py
│       ├── validation.py                   Input validation
│       └── formatters.py                   Data formatters
│
├── 📁 infrastructure/                      ⚙️ DevOps & Deployment
│   ├── kubernetes/                         K8s manifests
│   │   ├── analysis-engine.yaml            Analysis engine deployment
│   │   ├── backend-api.yaml                Backend API deployment
│   │   ├── frontend-web.yaml               Frontend deployment
│   │   ├── worker-service.yaml             Worker deployment
│   │   └── redis.yaml                      Redis deployment
│   ├── terraform/                          Infrastructure as Code
│   │   ├── main.tf                         Main config
│   │   ├── database.tf                     PostgreSQL setup
│   │   └── kubernetes.tf                   K8s cluster
│   └── docker/                             Dockerfiles
│       ├── analysis-engine.Dockerfile
│       ├── backend-api.Dockerfile
│       ├── frontend-web.Dockerfile
│       └── worker-service.Dockerfile
│
└── 📁 .claude/                             🤖 Claude Code skills
    └── skills/                             Development guides
        ├── saas-development.md             Multi-tenancy, auth, API patterns
        └── feature-implementation.md       Step-by-step feature guide
```

---

## File Counts

**Documentation**: 15+ strategic documents
**Services**: 5 independent microservices
**Tests**: 29 tests (analysis-engine), more to be added
**Lines of Code**: ~3,000 (will grow to 50,000+)

---

## Service Dependencies

```
┌─────────────────┐
│  frontend-web   │ (Next.js dashboard)
└────────┬────────┘
         │ HTTP REST
         ▼
┌─────────────────┐
│   backend-api   │ (FastAPI + PostgreSQL)
└────────┬────────┘
         │
         ├─────────────┐
         │             │
         ▼             ▼
┌─────────────┐  ┌──────────────┐
│ analysis-   │  │ worker-      │ (Celery)
│ engine      │  │ service      │
└─────────────┘  └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │ integration- │
                 │ service      │
                 └──────────────┘
```

---

## Service Communication

| From | To | Method | Purpose |
|------|-----|---------|---------|
| frontend-web | backend-api | HTTP REST | All user actions |
| backend-api | analysis-engine | Direct import or HTTP | Analyze feedback |
| backend-api | worker-service | Redis (Celery) | Queue background jobs |
| worker-service | analysis-engine | Direct import | Batch analysis |
| worker-service | integration-service | Direct import | Sync 3rd party data |

---

## Shared Resources

**PostgreSQL** (Multi-tenant database):
- Organizations table
- Users table
- Feedback items table
- Integrations table

**Redis** (Single instance with logical databases):
- DB 0: Celery broker (task queue via Redis Streams)
- DB 1: Session storage
- DB 2: API response cache
- DB 3: Rate limiting

### Redis Scaling Strategy

**Current MVP Phase (10 customers, ~10K items)**:
- Single Redis instance handles both cache and queue
- Uses <1% of Redis capacity (Redis handles 100K+ ops/sec)
- Logical database separation provides isolation

**When to Split Redis Instances** (triggers for separation):
| Trigger | Threshold | Action |
|---------|-----------|--------|
| Memory pressure | Cache evictions affecting queue | Separate instances |
| Latency spikes | p99 > 10ms on cache reads | Separate instances |
| Scale | 500+ customers, 1M+ items | Redis Cluster or separate |
| Compliance | Different backup/persistence policies | Separate by concern |

**Growth Path**:
1. **Month 2-6**: Single Redis instance (handles 50 customers easily)
2. **Month 6+**: If advanced routing needed → consider RabbitMQ
3. **Month 12+**: If event streaming needed → add Kafka for analytics

---

## Development Workflow

### To work on a specific service:

```bash
# Analysis Engine (Python)
cd services/analysis-engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./quickstart.sh

# Backend API (Python)
cd services/backend-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8000

# Frontend Web (TypeScript/Next.js)
cd services/frontend-web
pnpm install
pnpm run dev
# Visit http://localhost:3000

# Worker Service (Python)
cd services/worker-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
celery -A src.celery_app worker --loglevel=info
```

---

## What Goes Where?

### Root Level
- ✅ Strategic documentation guides (IMPLEMENTATION_GUIDE.md, etc.)
- ✅ Project overview (README.md)
- ✅ License (LICENSE)
- ✅ Git ignore (.gitignore)
- ❌ No code files
- ❌ No dependencies (requirements.txt, package.json)

### /docs
- ✅ All strategic documentation (PRD, Roadmap, API docs)
- ✅ User guides
- ❌ No code

### /services/{service-name}
- ✅ Service-specific code
- ✅ Service-specific tests
- ✅ Service-specific dependencies
- ✅ Service-specific README
- ✅ Service-specific config (.env, etc.)

### /shared
- ✅ Code shared across multiple services
- ✅ Common data models
- ✅ Utility functions
- ❌ Service-specific logic

### /infrastructure
- ✅ Deployment configs (K8s, Terraform, Docker)
- ✅ CI/CD pipelines
- ❌ Application code

---

## Adding a New Service

1. Create folder: `mkdir services/new-service`
2. Add README: `touch services/new-service/README.md`
3. Add to this document
4. Add to root README.md
5. Create infrastructure configs (Dockerfile, K8s manifest)

---

## Resources

- **Main Guide**: [IMPLEMENTATION_GUIDE.md](../IMPLEMENTATION_GUIDE.md)
- **Quick Start**: [GETTING_STARTED_NOW.md](../GETTING_STARTED_NOW.md)
- **Service READMEs**: See each service's README.md for details
- **Development Patterns**: [.claude/skills/](./.claude/skills/)

---

**Last Updated**: 2025-12-27
**Status**: Clean microservices structure ready for development
**Next**: Start building (see [GETTING_STARTED_NOW.md](GETTING_STARTED_NOW.md))
