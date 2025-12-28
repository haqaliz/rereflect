# SaaS Development Skill

Use this skill when working on SaaS-specific features for the Customer Feedback Analyzer platform.

## Context

This project is transforming from an open-source tool into a professional SaaS platform. Key documents:
- [PRD.md](../../PRD.md) - Product requirements
- [ROADMAP.md](../../ROADMAP.md) - Development roadmap

## Tech Stack

### Current (MVP)
- **Backend**: FastAPI + Python
- **Analysis**: VADER sentiment + scikit-learn + BERTopic
- **Database**: PostgreSQL (multi-tenant)
- **Cache**: Redis
- **Queue**: Celery
- **Auth**: NextAuth / Auth0
- **Billing**: Stripe
- **Deploy**: Docker + Kubernetes

### Planned (Frontend)
- **Framework**: Next.js 14+ with App Router
- **Language**: TypeScript 5.0+
- **Styling**: TailwindCSS 3.4+
- **Components**: shadcn/ui (Radix UI)
- **State**: React Context + TanStack Query
- **Forms**: React Hook Form + Zod

## Architecture Patterns

### Multi-Tenancy
All database tables must include `organization_id` for tenant isolation:

```python
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

class FeedbackItem(Base):
    __tablename__ = "feedback_items"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    text = Column(String, nullable=False)
    # ... other fields

    # Add index for tenant queries
    __table_args__ = (
        Index('ix_feedback_org_date', 'organization_id', 'created_at'),
    )
```

### API Design

**RESTful endpoints**:
```
POST   /api/v1/auth/signup
POST   /api/v1/auth/login
GET    /api/v1/organizations/{org_id}
POST   /api/v1/organizations/{org_id}/feedback
GET    /api/v1/organizations/{org_id}/dashboard
POST   /api/v1/organizations/{org_id}/integrations
GET    /api/v1/organizations/{org_id}/reports
```

**Always include**:
- Authentication (JWT tokens)
- Rate limiting
- Error handling (consistent JSON error format)
- Pagination (limit, offset)
- Filtering (query parameters)

### Security Best Practices

**1. Row-Level Security**
```python
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

async def get_current_org(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Organization:
    user = verify_token(token)
    org = db.query(Organization).filter(
        Organization.id == user.organization_id
    ).first()
    if not org:
        raise HTTPException(status_code=403, detail="Forbidden")
    return org

# Use in endpoints
@app.get("/api/v1/dashboard")
async def get_dashboard(
    org: Organization = Depends(get_current_org)
):
    # org is guaranteed to be the user's organization
    return analyze_feedback(org.id)
```

**2. Input Validation**
```python
from pydantic import BaseModel, validator

class FeedbackCreate(BaseModel):
    text: str
    source: str
    date: str

    @validator('text')
    def text_not_empty(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Text cannot be empty')
        if len(v) > 10000:
            raise ValueError('Text too long (max 10000 chars)')
        return v.strip()

    @validator('source')
    def valid_source(cls, v):
        allowed = ['zendesk', 'intercom', 'email', 'manual']
        if v not in allowed:
            raise ValueError(f'Invalid source. Must be one of: {allowed}')
        return v
```

## Common SaaS Features

### 1. Usage Tracking

```python
from datetime import datetime

async def track_usage(org_id: int, event: str, metadata: dict = None):
    """Track feature usage for billing and analytics."""
    usage = UsageLog(
        organization_id=org_id,
        event=event,
        metadata=metadata or {},
        created_at=datetime.utcnow()
    )
    db.add(usage)
    await db.commit()

# Use it
await track_usage(org.id, "feedback_analyzed", {"count": 100})
```

### 2. Feature Flags

```python
from enum import Enum

class Feature(str, Enum):
    ADVANCED_ANALYTICS = "advanced_analytics"
    CUSTOM_MODELS = "custom_models"
    SSO = "sso"
    WHITE_LABEL = "white_label"

def has_feature(org: Organization, feature: Feature) -> bool:
    """Check if organization has access to feature."""
    plan_features = {
        "free": [],
        "starter": [],
        "professional": [Feature.ADVANCED_ANALYTICS],
        "business": [Feature.ADVANCED_ANALYTICS, Feature.SSO],
        "enterprise": [Feature.ADVANCED_ANALYTICS, Feature.SSO,
                      Feature.CUSTOM_MODELS, Feature.WHITE_LABEL]
    }
    return feature in plan_features.get(org.plan, [])

# Use in endpoints
@app.get("/api/v1/advanced-analytics")
async def get_advanced_analytics(org: Organization = Depends(get_current_org)):
    if not has_feature(org, Feature.ADVANCED_ANALYTICS):
        raise HTTPException(status_code=403, detail="Upgrade to access this feature")
    # ...
```

### 3. Rate Limiting

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to endpoints
@app.post("/api/v1/feedback")
@limiter.limit("100/hour")  # 100 requests per hour
async def create_feedback(
    request: Request,
    data: FeedbackCreate,
    org: Organization = Depends(get_current_org)
):
    # ...
```

### 4. Background Jobs

```python
from celery import Celery

celery_app = Celery('tasks', broker='redis://localhost:6379')

@celery_app.task
def analyze_feedback_batch(org_id: int, feedback_ids: List[int]):
    """Analyze feedback in background."""
    from src.analyzer import FeedbackAnalyzer

    # Get feedback from database
    feedback_items = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.id.in_(feedback_ids)
    ).all()

    # Analyze
    analyzer = FeedbackAnalyzer()
    result = analyzer.analyze(feedback_items)

    # Save results
    save_analysis_results(org_id, result)

    # Send notification
    send_slack_notification(org_id, "Analysis complete!")

# Trigger from API
@app.post("/api/v1/feedback/batch")
async def upload_feedback_batch(file: UploadFile):
    # Parse file, save to database
    feedback_ids = save_feedback_items(org.id, items)

    # Queue background job
    analyze_feedback_batch.delay(org.id, feedback_ids)

    return {"status": "processing", "job_id": "..."}
```

## Frontend Patterns

### 1. Data Fetching (TanStack Query)

```typescript
// hooks/useDashboard.ts
import { useQuery } from '@tanstack/react-query'

export function useDashboard(orgId: string, dateRange: DateRange) {
  return useQuery({
    queryKey: ['dashboard', orgId, dateRange],
    queryFn: async () => {
      const res = await fetch(
        `/api/v1/organizations/${orgId}/dashboard?${new URLSearchParams({
          start_date: dateRange.start,
          end_date: dateRange.end
        })}`
      )
      if (!res.ok) throw new Error('Failed to fetch dashboard')
      return res.json()
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    retry: 3
  })
}

// Usage in component
function Dashboard() {
  const { data, isLoading, error } = useDashboard(orgId, dateRange)

  if (isLoading) return <Skeleton />
  if (error) return <ErrorState error={error} />

  return <DashboardView data={data} />
}
```

### 2. Forms (React Hook Form + Zod)

```typescript
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const integrationSchema = z.object({
  type: z.enum(['zendesk', 'intercom', 'slack']),
  api_key: z.string().min(10, 'API key must be at least 10 characters'),
  subdomain: z.string().optional()
})

type IntegrationForm = z.infer<typeof integrationSchema>

function IntegrationSetup() {
  const { register, handleSubmit, formState: { errors } } = useForm<IntegrationForm>({
    resolver: zodResolver(integrationSchema)
  })

  const onSubmit = async (data: IntegrationForm) => {
    await fetch('/api/v1/integrations', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <input {...register('type')} />
      {errors.type && <span>{errors.type.message}</span>}

      <input {...register('api_key')} />
      {errors.api_key && <span>{errors.api_key.message}</span>}

      <button type="submit">Connect</button>
    </form>
  )
}
```

### 3. Authentication Flow

```typescript
// lib/auth.ts
import { SignJWT, jwtVerify } from 'jose'

export async function createToken(user: User) {
  const token = await new SignJWT({
    userId: user.id,
    orgId: user.organization_id
  })
    .setProtectedHeader({ alg: 'HS256' })
    .setExpirationTime('7d')
    .sign(new TextEncoder().encode(process.env.JWT_SECRET!))

  return token
}

export async function verifyToken(token: string) {
  try {
    const { payload } = await jwtVerify(
      token,
      new TextEncoder().encode(process.env.JWT_SECRET!)
    )
    return payload as { userId: number; orgId: number }
  } catch {
    return null
  }
}

// middleware.ts
export async function middleware(request: NextRequest) {
  const token = request.cookies.get('token')?.value

  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  const payload = await verifyToken(token)
  if (!payload) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  return NextResponse.next()
}
```

## Database Migrations

### Using Alembic (SQLAlchemy)

```python
# migrations/versions/001_add_organizations.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('plan', sa.String(), nullable=False),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Add organization_id to existing feedback_items
    op.add_column('feedback_items',
        sa.Column('organization_id', sa.Integer(), nullable=True))

    # Add foreign key
    op.create_foreign_key(
        'fk_feedback_organization',
        'feedback_items', 'organizations',
        ['organization_id'], ['id']
    )

    # Create index
    op.create_index(
        'ix_feedback_org',
        'feedback_items',
        ['organization_id', 'created_at']
    )

def downgrade():
    op.drop_index('ix_feedback_org', 'feedback_items')
    op.drop_constraint('fk_feedback_organization', 'feedback_items')
    op.drop_column('feedback_items', 'organization_id')
    op.drop_table('organizations')
```

## Testing SaaS Features

```python
import pytest
from fastapi.testclient import TestClient

def test_multi_tenant_isolation():
    """Ensure organizations can't access each other's data."""
    # Create two organizations
    org1 = create_organization("Org 1")
    org2 = create_organization("Org 2")

    # Create feedback for org1
    feedback1 = create_feedback(org1.id, "Test feedback 1")

    # Try to access as org2 user
    client = TestClient(app)
    token = create_auth_token(org2.id)

    response = client.get(
        f"/api/v1/feedback/{feedback1.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Should return 404 (not 403 to avoid leaking existence)
    assert response.status_code == 404

def test_usage_limits():
    """Test that free tier respects usage limits."""
    org = create_organization("Free Org", plan="free")

    # Free tier: 100 feedback items/month
    for i in range(100):
        create_feedback(org.id, f"Feedback {i}")

    # 101st should fail
    response = client.post(
        "/api/v1/feedback",
        json={"text": "Over limit"},
        headers=auth_headers(org.id)
    )

    assert response.status_code == 402  # Payment Required
    assert "upgrade" in response.json()["detail"].lower()
```

## Deployment Checklist

When deploying new SaaS features:

- [ ] Environment variables documented in .env.example
- [ ] Database migrations tested (up and down)
- [ ] Feature flags configured
- [ ] Rate limits set appropriately
- [ ] Billing integration tested (Stripe test mode)
- [ ] Multi-tenant isolation verified
- [ ] Performance tested with realistic data
- [ ] Monitoring/alerts configured
- [ ] Documentation updated
- [ ] Changelog entry added

## Common Commands

```bash
# Run migrations
alembic upgrade head

# Create new migration
alembic revision -m "Add feature X"

# Run background workers
celery -A src.worker worker --loglevel=info

# Run with hot reload
uvicorn src.api.main:app --reload --port 8000

# Run tests
pytest tests/ -v

# Type checking
mypy src/

# Database console
psql postgresql://user:pass@localhost/dbname
```

## Resources

- [PRD.md](../../PRD.md) - Full product requirements
- [ROADMAP.md](../../ROADMAP.md) - Development roadmap
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [Next.js App Router](https://nextjs.org/docs/app)
- [Stripe Billing](https://stripe.com/docs/billing)

## When to Use This Skill

Use this skill when:
- Implementing authentication/authorization
- Building multi-tenant features
- Adding billing/subscription logic
- Creating API endpoints
- Setting up integrations
- Implementing background jobs
- Building frontend dashboards
- Database schema changes
- Security-related features
