# PRD: Predictive Analytics — Churn Prediction & Customer Health Score

**Product**: Rereflect
**Author**: Rereflect Team
**Date**: 2026-02-15
**Timeline**: 2-3 weeks (Feb 17 - Mar 7, 2026)
**Status**: Draft

---

## 1. Overview

Enhance Rereflect's AI capabilities with two interconnected features:

1. **Improved Churn Prediction** — Upgrade the existing 4-factor heuristic churn_risk_score to a multi-factor scoring engine using 9 signals
2. **Customer Health Score** — New aggregate metric that groups feedback by customer email and computes a 0-100 health score

Both features use a **hybrid approach**: algorithmic scoring for real-time updates + weekly GPT-4 deep-dive analysis for high-risk customers.

### Current State
- Churn risk scoring: 4 factors only (sentiment score, urgency flag, churn keywords, frustration keywords)
- No customer-level aggregation — all scoring is per-feedback-item
- No sentiment trend tracking (point-in-time only)
- No resolution time tracking for scoring

### Success Criteria
- Churn risk score uses 9 factors (up from 4)
- Customer health scores computed for all customers with email addresses
- Dashboard widget shows top 5 at-risk customers with health scores
- Weekly LLM analysis generates natural language churn insights for customers scoring < 40
- Plan gating enforced: Pro+ for full suite, Free keeps basic churn only
- Zero regressions on existing 472 backend tests

---

## 2. Phase 1: Enhanced Churn Risk Scoring (Week 1)

### 2.1 New Scoring Factors

Upgrade `_compute_heuristic_churn_risk()` in `services/worker-service/src/tasks/analysis.py` from 4 factors to 9:

| Factor | Weight | Signal | Source |
|--------|--------|--------|--------|
| Sentiment score | 15 pts | Negative sentiment (compound score) | `sentiment_score` on current item |
| Urgency flag | 10 pts | Item flagged as urgent | `is_urgent` on current item |
| Churn keywords | 15 pts | "cancel", "switch", "leave", "refund", "downgrade" | Text analysis on current item |
| Frustration keywords | 10 pts | "terrible", "awful", "disappointed", "worst" | Text analysis on current item |
| **Sentiment trend** | **15 pts** | Declining sentiment over last 5 feedbacks from same customer | Query by `customer_email` |
| **Feedback frequency** | **10 pts** | Increasing complaint frequency (more feedbacks in last 7d vs prior 30d average) | Query by `customer_email` |
| **Resolution time** | **10 pts** | Avg days from "new" to "resolved" for customer's recent feedbacks | `FeedbackWorkflowEvent` timestamps |
| **Pain point severity** | **10 pts** | Critical/major pain points in recent feedbacks | `pain_point_severity` |
| **Feature request density** | **5 pts** | High ratio of feature requests to total feedbacks (frustrated power user) | `feature_request_category` count |
| **Total** | **100 pts** | | |

### 2.2 Add customer_email to FeedbackItem

**File**: `services/backend-api/src/models/feedback.py`

Add a dedicated field for customer email extraction:
```python
customer_email = Column(String(255), nullable=True, index=True)
```

**File**: New Alembic migration

Add the column + index:
```python
op.add_column('feedback_items', sa.Column('customer_email', sa.String(255), nullable=True))
op.create_index('ix_feedback_customer_email', 'feedback_items', ['customer_email'])
```

### 2.3 Populate customer_email on Ingest

Extract email from `source_metadata` during feedback creation/analysis:

**Files to modify**:
- `services/backend-api/src/api/routes/feedback.py` — CSV import: extract email from row if column exists
- `services/worker-service/src/tasks/analysis.py` — After analysis: extract from `source_metadata.author_email`
- `services/worker-service/src/adapters/slack_adapter.py` — Slack: user email from profile
- `services/worker-service/src/adapters/intercom_adapter.py` — Intercom: contact email
- `services/worker-service/src/adapters/email_adapter.py` — Email: sender address

Extraction logic (in analysis task):
```python
def _extract_customer_email(feedback_item):
    """Extract customer email from source_metadata."""
    if feedback_item.customer_email:
        return feedback_item.customer_email
    meta = feedback_item.source_metadata or {}
    # Try common metadata fields
    for key in ['author_email', 'email', 'sender_email', 'from_email', 'user_email']:
        if meta.get(key):
            return meta[key].lower().strip()
    return None
```

### 2.4 Backfill Existing Data

One-time migration script or Celery task to backfill `customer_email` from `source_metadata` on existing feedback items.

**File**: `services/backend-api/scripts/backfill_customer_email.py`

```python
# Iterate all feedback items with source_metadata, extract email, update
```

### 2.5 Enhanced Scoring Function

**File**: `services/worker-service/src/tasks/analysis.py`

Replace `_compute_heuristic_churn_risk()` with `_compute_churn_risk_score()`:

```python
def _compute_churn_risk_score(feedback_item, db_session):
    score = 0

    # --- Original 4 factors (50 pts) ---
    # Sentiment (15 pts)
    if feedback_item.sentiment_score is not None:
        if feedback_item.sentiment_score < -0.5:
            score += 15
        elif feedback_item.sentiment_score < -0.2:
            score += 10
        elif feedback_item.sentiment_score < 0:
            score += 5

    # Urgency (10 pts)
    if feedback_item.is_urgent:
        score += 10

    # Churn keywords (15 pts)
    churn_keywords = ["cancel", "switch", "leave", "refund", "downgrade", "alternative"]
    text_lower = feedback_item.text.lower()
    matches = sum(1 for kw in churn_keywords if kw in text_lower)
    score += min(matches * 5, 15)

    # Frustration keywords (10 pts)
    frustration_keywords = ["terrible", "awful", "disappointed", "worst", "unacceptable", "furious"]
    frust_matches = sum(1 for kw in frustration_keywords if kw in text_lower)
    score += min(frust_matches * 5, 10)

    # --- New 5 factors (50 pts) — require customer_email ---
    customer_email = feedback_item.customer_email
    if not customer_email:
        return score  # Return basic score if no email

    # Sentiment trend (15 pts) — declining over last 5 feedbacks
    recent = db_session.query(FeedbackItem.sentiment_score).filter(
        FeedbackItem.organization_id == feedback_item.organization_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.sentiment_score.isnot(None),
        FeedbackItem.id != feedback_item.id,
    ).order_by(FeedbackItem.created_at.desc()).limit(5).all()

    if len(recent) >= 2:
        scores = [r.sentiment_score for r in recent]
        # Check if trend is declining (later items more negative)
        if scores[0] < scores[-1]:  # Most recent worse than oldest
            decline = scores[-1] - scores[0]
            if decline > 0.5:
                score += 15
            elif decline > 0.3:
                score += 10
            elif decline > 0.1:
                score += 5

    # Feedback frequency (10 pts) — more complaints recently
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    last_7d = db_session.query(func.count(FeedbackItem.id)).filter(
        FeedbackItem.organization_id == feedback_item.organization_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.created_at >= now - timedelta(days=7),
    ).scalar() or 0

    last_30d = db_session.query(func.count(FeedbackItem.id)).filter(
        FeedbackItem.organization_id == feedback_item.organization_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.created_at >= now - timedelta(days=30),
    ).scalar() or 0

    avg_weekly = (last_30d / 4.0) if last_30d > 0 else 0
    if avg_weekly > 0 and last_7d > avg_weekly * 2:
        score += 10
    elif avg_weekly > 0 and last_7d > avg_weekly * 1.5:
        score += 5

    # Resolution time (10 pts) — slow resolution
    from src.models.feedback import FeedbackWorkflowEvent
    avg_resolution = _get_avg_resolution_days(db_session, feedback_item.organization_id, customer_email)
    if avg_resolution is not None:
        if avg_resolution > 7:
            score += 10
        elif avg_resolution > 3:
            score += 5

    # Pain point severity (10 pts)
    critical_count = db_session.query(func.count(FeedbackItem.id)).filter(
        FeedbackItem.organization_id == feedback_item.organization_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.pain_point_severity.in_(["critical", "major"]),
        FeedbackItem.created_at >= now - timedelta(days=30),
    ).scalar() or 0
    if critical_count >= 3:
        score += 10
    elif critical_count >= 1:
        score += 5

    # Feature request density (5 pts) — high ratio = frustrated power user
    total_recent = last_30d
    feature_count = db_session.query(func.count(FeedbackItem.id)).filter(
        FeedbackItem.organization_id == feedback_item.organization_id,
        FeedbackItem.customer_email == customer_email,
        FeedbackItem.feature_request_category.isnot(None),
        FeedbackItem.created_at >= now - timedelta(days=30),
    ).scalar() or 0
    if total_recent > 0 and (feature_count / total_recent) > 0.5:
        score += 5

    return min(score, 100)
```

### Phase 1 Deliverables
- [ ] Alembic migration: add `customer_email` column + index
- [ ] Email extraction logic in analysis task + all adapters
- [ ] Backfill script for existing feedback items
- [ ] 9-factor churn risk scoring function
- [ ] Helper: `_get_avg_resolution_days()`
- [ ] All existing tests pass + new scoring tests

---

## 3. Phase 2: Customer Health Score (Week 1-2)

### 3.1 Customer Health Model

**New file**: `services/backend-api/src/models/customer_health.py`

```python
class CustomerHealth(Base):
    __tablename__ = "customer_health_scores"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_name = Column(String(255), nullable=True)

    # Health score (0-100, higher = healthier)
    health_score = Column(Integer, nullable=False, default=50)

    # Component scores (0-100 each, weighted into health_score)
    churn_risk_component = Column(Integer, default=50)      # 35% weight (inverted: low churn = high health)
    sentiment_component = Column(Integer, default=50)        # 25% weight
    resolution_component = Column(Integer, default=50)       # 25% weight
    frequency_component = Column(Integer, default=50)        # 15% weight

    # Metadata
    feedback_count = Column(Integer, default=0)
    last_feedback_at = Column(DateTime, nullable=True)
    risk_level = Column(String(20), default="unknown")  # healthy, moderate, at_risk, critical

    # LLM analysis (weekly, for at-risk customers)
    llm_analysis = Column(Text, nullable=True)           # GPT-generated insight text
    llm_analyzed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_customer_health_org_email', 'organization_id', 'customer_email', unique=True),
        Index('ix_customer_health_org_score', 'organization_id', 'health_score'),
        Index('ix_customer_health_risk', 'organization_id', 'risk_level'),
    )
```

### 3.2 Health Score Computation

**New file**: `services/backend-api/src/services/health_score_service.py`

Computes health score per customer using churn-heavy weights:

```python
WEIGHTS = {
    "churn_risk": 0.35,     # Most important signal
    "sentiment": 0.25,
    "resolution": 0.25,
    "frequency": 0.15,
}

def compute_health_score(org_id, customer_email, db):
    """Compute 0-100 health score (higher = healthier)."""
    # Churn risk component (35%): inverted avg churn_risk_score
    avg_churn = _avg_churn_risk(db, org_id, customer_email, days=30)
    churn_component = max(0, 100 - (avg_churn or 0))

    # Sentiment component (25%): avg sentiment mapped to 0-100
    avg_sentiment = _avg_sentiment(db, org_id, customer_email, days=30)
    sentiment_component = _sentiment_to_score(avg_sentiment)

    # Resolution component (25%): faster resolution = higher score
    avg_resolution_days = _avg_resolution_days(db, org_id, customer_email)
    resolution_component = _resolution_to_score(avg_resolution_days)

    # Frequency component (15%): stable/declining frequency = healthy
    freq_trend = _feedback_frequency_trend(db, org_id, customer_email)
    frequency_component = _frequency_to_score(freq_trend)

    # Weighted sum
    health_score = int(
        churn_component * WEIGHTS["churn_risk"] +
        sentiment_component * WEIGHTS["sentiment"] +
        resolution_component * WEIGHTS["resolution"] +
        frequency_component * WEIGHTS["frequency"]
    )

    # Risk level
    if health_score >= 70:
        risk_level = "healthy"
    elif health_score >= 50:
        risk_level = "moderate"
    elif health_score >= 30:
        risk_level = "at_risk"
    else:
        risk_level = "critical"

    return {
        "health_score": health_score,
        "churn_risk_component": churn_component,
        "sentiment_component": sentiment_component,
        "resolution_component": resolution_component,
        "frequency_component": frequency_component,
        "risk_level": risk_level,
    }
```

### 3.3 Health Score Recomputation

**File**: `services/worker-service/src/tasks/analysis.py`

After each feedback item is analyzed, recompute the customer's health score:

```python
# At end of analyze_feedback task:
if feedback_item.customer_email:
    _update_customer_health(db, feedback_item.organization_id, feedback_item.customer_email)
```

### 3.4 Health Score API Endpoint

**File**: `services/backend-api/src/api/routes/dashboard.py`

Add customer health data to dashboard response:

```python
class CustomerHealthSummary(BaseModel):
    customer_email: str
    customer_name: Optional[str]
    health_score: int
    risk_level: str
    feedback_count: int
    last_feedback_at: Optional[datetime]
    churn_risk_component: int
    sentiment_component: int
    resolution_component: int
    frequency_component: int

# Add to DashboardResponse:
at_risk_customers: List[CustomerHealthSummary]  # Top 5 lowest health scores
```

Query: Top 5 customers with lowest health_score for the org:
```python
at_risk = db.query(CustomerHealth).filter(
    CustomerHealth.organization_id == current_org.id,
    CustomerHealth.health_score < 50,
).order_by(CustomerHealth.health_score.asc()).limit(5).all()
```

### 3.5 Dashboard Widget (Frontend)

**File**: `services/frontend-web/app/(dashboard)/dashboard/page.tsx`

Add "Customer Health" section to dashboard:
- Card titled "At-Risk Customers"
- Table: Customer (email/name), Health Score (color-coded badge), Risk Level, Last Feedback
- Health score badge colors: green (70+), yellow (50-69), orange (30-49), red (<30)
- Empty state: "No at-risk customers detected"
- Click row → navigate to feedbacks filtered by customer_email

### Phase 2 Deliverables
- [ ] Alembic migration: `customer_health_scores` table
- [ ] `CustomerHealth` model with indexes
- [ ] `health_score_service.py` with weighted scoring
- [ ] Health recomputation after each analysis
- [ ] Dashboard API returns `at_risk_customers`
- [ ] Dashboard widget showing top 5 at-risk customers
- [ ] Cache invalidation on health score update
- [ ] All tests pass

---

## 4. Phase 3: Weekly LLM Deep-Dive for At-Risk Customers (Week 2)

### 4.1 Weekly Churn Analysis Task

**File**: `services/worker-service/src/tasks/insights.py`

Add to existing weekly insights Celery Beat schedule (Monday 8:30 AM UTC):

```python
@celery.task(name="generate_churn_insights")
def generate_churn_insights():
    """Weekly LLM analysis for at-risk customers (health_score < 40)."""
    for org in get_ai_enabled_orgs():
        at_risk = db.query(CustomerHealth).filter(
            CustomerHealth.organization_id == org.id,
            CustomerHealth.health_score < 40,
        ).all()

        for customer in at_risk:
            # Get last 10 feedbacks for this customer
            feedbacks = db.query(FeedbackItem).filter(
                FeedbackItem.organization_id == org.id,
                FeedbackItem.customer_email == customer.customer_email,
            ).order_by(FeedbackItem.created_at.desc()).limit(10).all()

            # Generate LLM analysis
            analysis = _generate_churn_analysis(customer, feedbacks)
            customer.llm_analysis = analysis
            customer.llm_analyzed_at = datetime.utcnow()
            db.commit()
```

### 4.2 LLM Prompt

```python
def _generate_churn_analysis(customer, feedbacks):
    prompt = f"""Analyze this customer's feedback history and assess churn risk.

Customer: {customer.customer_email}
Health Score: {customer.health_score}/100 (Risk: {customer.risk_level})
Total Feedbacks: {customer.feedback_count}

Recent Feedbacks (newest first):
{_format_feedbacks(feedbacks)}

Provide a concise analysis (3-5 sentences):
1. What is driving this customer's dissatisfaction?
2. What is the most likely churn trigger?
3. What specific action should the team take to retain this customer?

Be specific and actionable. Reference actual feedback content."""
    return call_openai(prompt)
```

### 4.3 Display LLM Insights

Add `llm_analysis` to `CustomerHealthSummary` response and show in the dashboard widget as an expandable detail below at-risk customers that have LLM analysis available.

### Phase 3 Deliverables
- [ ] `generate_churn_insights` Celery task
- [ ] Celery Beat schedule entry (Monday 8:30 AM, after weekly insights)
- [ ] LLM prompt for churn analysis
- [ ] `llm_analysis` + `llm_analyzed_at` in API response
- [ ] Dashboard widget shows LLM insight with expand/collapse
- [ ] Redis lock to prevent duplicate runs

---

## 5. Phase 4: Plan Gating & Feedbacks Integration (Week 2-3)

### 5.1 Feature Gating

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| Basic churn risk (4-factor, per-item) | Yes | Yes | Yes | Yes |
| Enhanced churn risk (9-factor) | No | Yes | Yes | Yes |
| Customer health scores | No | Yes | Yes | Yes |
| Dashboard at-risk widget | No | Yes | Yes | Yes |
| Weekly LLM churn insights | No | Yes | Yes | Yes |

**File**: `services/backend-api/src/config/plans.py`

Add feature IDs:
- `enhanced_churn_prediction` — Pro+
- `customer_health_scores` — Pro+
- `churn_llm_insights` — Pro+

### 5.2 Feedbacks List: Filter by Customer

**File**: `services/backend-api/src/api/routes/feedback.py`

Add `customer_email` filter parameter:
```python
customer_email: Optional[str] = Query(None)
# Add to query:
if customer_email:
    query = query.filter(FeedbackItem.customer_email == customer_email)
```

**File**: `services/frontend-web/app/(dashboard)/feedbacks/page.tsx`

Support `?customer_email=` URL parameter for navigating from dashboard widget.

### 5.3 Feedback Detail: Show Customer Health

**File**: `services/frontend-web/app/(dashboard)/feedbacks/[id]/page.tsx`

If the feedback has `customer_email`, show a small health score badge in the header area (score + risk level color).

### Phase 4 Deliverables
- [ ] Feature IDs added to plans.py
- [ ] `require_feature` guards on health score endpoints
- [ ] Feedbacks list filterable by `customer_email`
- [ ] Feedback detail shows customer health badge
- [ ] Free tier graceful degradation (shows basic churn only)
- [ ] All tests pass

---

## 6. Out of Scope

| Item | Reason |
|------|--------|
| Dedicated /customers page | Dashboard widget is enough for now, add page when customers request it |
| Customer lifetime value | Requires Stripe customer-to-org mapping, defer until more billing data |
| Feature impact prediction | Requires longitudinal data (track which features shipped, measure impact) |
| Revenue impact scoring | Depends on CLV, defer |
| Real-time LLM triggers | Weekly batch is cost-effective, real-time deferred |
| Customer segmentation | Nice-to-have, build when enough customer data exists |

---

## 7. Implementation Schedule

| Week | Phase | Key Deliverables |
|------|-------|--------------------|
| **Week 1** (Feb 17-21) | Enhanced Churn Scoring | customer_email field, 9-factor scoring, email extraction, backfill |
| **Week 1-2** (Feb 21-28) | Customer Health Score | CustomerHealth model, health_score_service, dashboard API + widget |
| **Week 2** (Feb 24-28) | LLM Deep-Dive | Weekly churn insights task, LLM prompt, dashboard integration |
| **Week 2-3** (Feb 28 - Mar 7) | Plan Gating & Integration | Feature gating, feedbacks filter, health badge |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| customer_email not available on many items | Health scores only for subset of customers | Graceful fallback: items without email get basic 4-factor scoring only |
| LLM cost for large orgs with many at-risk customers | High OpenAI API costs | Cap at 20 customers per org per weekly run, skip if BYOK key not set on Free tier |
| Health score recomputation slow | Slows down feedback analysis | Async: queue health recomputation as separate Celery task, don't block analysis |
| Score instability (fluctuates with each feedback) | Confusing for users | Use 30-day rolling window for all component calculations |
| email extraction wrong / inconsistent | Incorrect customer grouping | Normalize all emails to lowercase, strip whitespace, validate format |

---

## 9. Related Documents

- [DEV-TRACKING.md](DEV-TRACKING.md) - Development roadmap
- [PRD-TECHNICAL-DEBT.md](PRD-TECHNICAL-DEBT.md) - Technical debt resolution (completed)
- [CLAUDE.md](CLAUDE.md) - Technical documentation
