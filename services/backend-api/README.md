# Backend API

**Multi-tenant REST API for Customer Feedback Analyzer SaaS**

---

## Purpose

FastAPI backend that provides:
- Authentication (JWT tokens, OAuth)
- Multi-tenant data isolation (organization-based)
- CRUD operations for feedback, organizations, users
- Integration with analysis-engine service
- Billing integration (Stripe)
- Rate limiting and usage tracking

---

## Tech Stack

- **Framework**: FastAPI 0.115+
- **Database**: PostgreSQL (multi-tenant schema)
- **ORM**: SQLAlchemy 2.0
- **Auth**: JWT (python-jose), OAuth (Google)
- **Validation**: Pydantic 2.0
- **Migrations**: Alembic
- **Cache**: Redis (sessions, rate limits)
- **Billing**: Stripe API

---

## Quick Start

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up database
createdb customer_feedback_saas
alembic upgrade head

# Run server
uvicorn src.api.main:app --reload --port 8000

# Visit API docs
open http://localhost:8000/docs
```

---

## API Endpoints

### Authentication
- `POST /api/v1/auth/signup` - Create account + organization
- `POST /api/v1/auth/login` - Login with email/password
- `POST /api/v1/auth/google` - OAuth with Google
- `GET /api/v1/auth/me` - Get current user

### Organizations
- `GET /api/v1/organizations/{org_id}` - Get org details
- `PATCH /api/v1/organizations/{org_id}` - Update org settings
- `POST /api/v1/organizations/{org_id}/invite` - Invite team member

### Feedback
- `POST /api/v1/feedback` - Create single feedback
- `POST /api/v1/feedback/upload` - Upload CSV/JSON file
- `GET /api/v1/feedback` - List feedback (paginated)
- `GET /api/v1/feedback/{id}` - Get single feedback
- `DELETE /api/v1/feedback/{id}` - Delete feedback

### Dashboard
- `GET /api/v1/dashboard` - Get dashboard metrics
- `GET /api/v1/dashboard/trends` - Get sentiment trends

### Integrations
- `POST /api/v1/integrations/slack` - Connect Slack
- `POST /api/v1/integrations/intercom` - Connect Intercom
- `GET /api/v1/integrations` - List connected integrations
- `DELETE /api/v1/integrations/{id}` - Disconnect integration

### Billing (Month 3)
- `POST /api/v1/billing/checkout` - Create Stripe checkout session
- `POST /api/v1/billing/portal` - Customer portal link
- `POST /api/v1/billing/webhook` - Stripe webhook handler

---

## Database Schema

```sql
-- Core tables
organizations (id, name, plan, stripe_customer_id, created_at)
users (id, email, password_hash, organization_id, role, created_at)
feedback_items (id, organization_id, text, source, sentiment_score, ...)
integrations (id, organization_id, type, config, is_active, created_at)
usage_logs (id, organization_id, event, metadata, created_at)

-- Indexes for performance
CREATE INDEX idx_feedback_org ON feedback_items(organization_id, created_at);
CREATE INDEX idx_users_org ON users(organization_id);
```

---

## Multi-Tenancy

**Row-Level Security**: All queries include `organization_id` filter

```python
# Dependency injection
async def get_current_org(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Organization:
    user = verify_token(token)
    org = db.query(Organization).filter(
        Organization.id == user.organization_id
    ).first()
    return org

# Usage in endpoints
@app.get("/api/v1/feedback")
async def list_feedback(
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    # Automatically scoped to org
    feedback = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == org.id
    ).all()
    return feedback
```

---

## Authentication Flow

1. User signs up → `POST /auth/signup`
2. Create user + organization in database
3. Return JWT token (expires in 7 days)
4. Frontend stores token in cookie/localStorage
5. All subsequent requests include: `Authorization: Bearer {token}`
6. Backend validates token and extracts `organization_id`

**JWT Payload**:
```json
{
  "user_id": 123,
  "organization_id": 45,
  "role": "admin",
  "exp": 1234567890
}
```

---

## Rate Limiting

**Per Plan Limits**:
- Free: 100 requests/hour
- Starter: 1,000 requests/hour
- Professional: 10,000 requests/hour
- Business: 50,000 requests/hour
- Enterprise: Unlimited

**Implementation**:
```python
from slowapi import Limiter

limiter = Limiter(key_func=get_organization_id)

@app.post("/api/v1/feedback")
@limiter.limit("100/hour")  # Free tier
async def create_feedback(...):
    pass
```

---

## Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@localhost/customer_feedback_saas
REDIS_URL=redis://localhost:6379
JWT_SECRET=your-secret-key-here
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
ANALYSIS_ENGINE_URL=http://localhost:8001
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Test specific module
pytest tests/test_auth.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Test multi-tenancy isolation
pytest tests/test_multitenant.py -v
```

---

## Migrations

```bash
# Create new migration
alembic revision -m "Add integrations table"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1

# Check current version
alembic current
```

---

## Development Workflow

1. Create feature branch: `git checkout -b feature/slack-integration`
2. Add database models: `src/models/integration.py`
3. Create migration: `alembic revision -m "Add integrations"`
4. Add API routes: `src/api/routes/integrations.py`
5. Write tests: `tests/test_integrations.py`
6. Run tests: `pytest tests/ -v`
7. Create PR for review

---

## Deployment

**Docker**:
```bash
docker build -t backend-api .
docker run -p 8000:8000 \
  -e DATABASE_URL=... \
  -e REDIS_URL=... \
  backend-api
```

**Kubernetes**: See `/infrastructure/kubernetes/backend-api.yaml`

---

## Performance

- **Response time**: < 100ms (95th percentile)
- **Throughput**: 1,000 requests/second
- **Database connections**: Pool of 20
- **Cache hit rate**: 80%+ (Redis)

---

## Security

- ✅ JWT token validation on all protected routes
- ✅ Password hashing (bcrypt)
- ✅ Row-level security (organization isolation)
- ✅ Input validation (Pydantic)
- ✅ SQL injection prevention (SQLAlchemy ORM)
- ✅ Rate limiting (slowapi)
- ✅ CORS configuration
- ✅ HTTPS only (production)

---

## Support

- **API Docs**: http://localhost:8000/docs (Swagger)
- **Development Guide**: [/.claude/skills/saas-development.md](/.claude/skills/saas-development.md)
- **Feature Implementation**: [/.claude/skills/feature-implementation.md](/.claude/skills/feature-implementation.md)

---

**Status**: In Development (Month 1)
**Version**: 0.1.0
**Maintained**: Yes
