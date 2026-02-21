# PRD: Churn Prediction Accuracy

**Product**: Rereflect
**Author**: Rereflect Team
**Date**: 2026-02-21
**Timeline**: 1 week (Feb 21 - Feb 28, 2026)
**Status**: Draft
**Milestone**: AI-TRACKING M1.4

---

## 1. Overview

Make churn predictions transparent, trustworthy, and measurable. Today, users see a single churn risk score (0-100) with no explanation of why it's high or low, no indication of how reliable it is, and no way to validate accuracy. This milestone adds three capabilities: factor-level explainability, confidence scoring, and backtest validation.

### Current State
- 9-factor churn risk scoring computed per feedback item (`_compute_heuristic_churn_risk()` in analysis.py)
- **Factor breakdown is discarded** — only the final composite score (0-100) is stored on `FeedbackItem.churn_risk_score`
- Customer health scores have `confidence_level` field (low/medium/high) but it's **not exposed in API or displayed on frontend**
- No backtest infrastructure to evaluate prediction accuracy
- Churn risk card on feedback detail shows score + risk level + progress bar — no factor breakdown

### Success Criteria
- Users can see which of the 9 factors drove a high churn risk score (expandable breakdown)
- Customer 360 shows aggregated factor patterns across all customer feedbacks (last 30 days)
- Confidence indicator (0-100%) displayed on Customer 360, feedback detail, and feedbacks list
- Backtest script produces precision/recall/F1 metrics + CSV export for both churn risk and health score
- Backfill script populates factor breakdown for all existing feedback items
- Zero regressions on existing tests

---

## 2. Data Model Changes

### 2.1 FeedbackItem: Add `churn_risk_factors` Column

**File**: `services/backend-api/src/models/feedback.py`

Add a JSON column to store the per-factor breakdown:

```python
churn_risk_factors = Column(JSON, nullable=True)
```

**Stored format**:
```json
{
    "sentiment": {"score": 15, "max": 15, "label": "Very negative sentiment"},
    "churn_keywords": {"score": 10, "max": 15, "label": "2 churn keywords found"},
    "frustration_keywords": {"score": 5, "max": 10, "label": "1 frustration keyword"},
    "urgency": {"score": 10, "max": 10, "label": "Marked as urgent"},
    "sentiment_trend": {"score": 15, "max": 15, "label": "Sentiment declining sharply"},
    "feedback_frequency": {"score": 5, "max": 10, "label": "Complaint frequency increasing"},
    "resolution_time": {"score": 10, "max": 10, "label": "Average resolution > 7 days"},
    "pain_severity": {"score": 5, "max": 10, "label": "1 critical pain point"},
    "feature_density": {"score": 0, "max": 5, "label": "Low feature request ratio"}
}
```

Each factor stores:
- `score`: Points contributed (0 to max)
- `max`: Maximum possible points for this factor
- `label`: Human-readable explanation of why this score was given

### 2.2 CustomerHealth: Add `confidence_score` Column

**File**: `services/backend-api/src/models/customer_health.py`

Add a numeric confidence score alongside the existing `confidence_level`:

```python
confidence_score = Column(Integer, default=0)  # 0-100 percentage
```

The existing `confidence_level` (low/medium/high string) is kept for backward compatibility. The new `confidence_score` provides granular 0-100% confidence.

### 2.3 Alembic Migration

Single migration adding:
- `churn_risk_factors` (JSON, nullable) to `feedback_items`
- `confidence_score` (Integer, default 0) to `customer_health_scores`

---

## 3. Churn Risk Explainability

### 3.1 Factor Computation Changes

**File**: `services/worker-service/src/tasks/analysis.py`

Modify `_compute_heuristic_churn_risk()` to return both the score and factor breakdown:

```python
def _compute_heuristic_churn_risk(feedback, db=None) -> Tuple[int, Dict]:
    """Returns (composite_score, factors_dict)"""
```

**Current flow** (lines 491-668):
1. Compute each factor's contribution
2. Sum all contributions → return single int

**New flow**:
1. Compute each factor's contribution
2. Build factors dict with score/max/label for each
3. Sum all contributions
4. Return (total_score, factors_dict)

**Factor labels** (generated during computation):
| Factor | Label Examples |
|--------|---------------|
| sentiment | "Very negative sentiment", "Slightly negative", "Neutral/positive" |
| churn_keywords | "3 churn keywords found: cancel, switching, refund", "No churn keywords" |
| frustration_keywords | "2 frustration keywords: frustrated, terrible", "No frustration keywords" |
| urgency | "Marked as urgent", "Not urgent" |
| sentiment_trend | "Sentiment declining sharply (-0.6)", "Stable sentiment trend" |
| feedback_frequency | "Complaint frequency spiking (3x average)", "Normal frequency" |
| resolution_time | "Average resolution > 7 days", "Resolved within 1 day" |
| pain_severity | "3 critical pain points in 30 days", "No critical issues" |
| feature_density | "High feature request ratio (60%)", "Low feature request ratio" |

### 3.2 Store Factors on Analysis

**File**: `services/worker-service/src/tasks/analysis.py`

After computing churn risk, store factors on the feedback item:

```python
score, factors = _compute_heuristic_churn_risk(feedback, db)
feedback.churn_risk_score = score
feedback.churn_risk_factors = factors  # NEW
```

For LLM-computed churn risk (when LLM is available), generate a simplified factor breakdown from the LLM result + text analysis:
- Sentiment factor from `feedback.sentiment_score`
- Urgency from `feedback.is_urgent`
- Keyword factors from text analysis (always available)
- Customer-level factors (trend, frequency, resolution, pain, features) from DB queries

### 3.3 API Changes

**File**: `services/backend-api/src/api/routes/feedbacks.py`

Include `churn_risk_factors` in the feedback detail response:

```python
# In FeedbackDetailResponse schema
churn_risk_factors: Optional[Dict] = None
```

**File**: `services/backend-api/src/api/routes/customer_health.py`

Add aggregated factors endpoint:

```
GET /api/v1/customers/{email}/churn-factors
```

Response:
```json
{
    "customer_email": "john@acme.com",
    "period_days": 30,
    "feedback_count": 12,
    "aggregated_factors": {
        "sentiment": {"avg_score": 12.5, "max": 15, "description": "Consistently negative sentiment"},
        "churn_keywords": {"avg_score": 8.3, "max": 15, "description": "Frequent churn language"},
        ...
    },
    "top_risk_drivers": ["sentiment", "churn_keywords", "sentiment_trend"]
}
```

Plan gated: `enhanced_churn_prediction` (Pro+)

### 3.4 Frontend: Feedback Detail

**File**: `services/frontend-web/app/(dashboard)/feedbacks/[id]/page.tsx`

Add expandable factor breakdown below the existing churn risk card:

**Collapsed state** (default):
- Existing churn risk card (score, risk level, progress bar)
- "View factor breakdown" toggle button (ChevronDown icon)

**Expanded state**:
- Each factor as a row: label, score/max, filled progress bar
- Sorted by score descending (highest contributors first)
- Color coding: red (>75% of max), orange (40-75%), green (<40%)
- Factors with 0 score shown in muted style

**Plan gating**: Factor breakdown section hidden for Free plan users. Show "Upgrade to Pro to see factor breakdown" CTA.

### 3.5 Frontend: Customer 360

**File**: `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx`

Add "Churn Risk Drivers" section to the customer profile:

- Fetches aggregated factors from `GET /api/v1/customers/{email}/churn-factors`
- Shows average factor scores across last 30 days as horizontal bar chart
- Top 3 risk drivers highlighted with badges
- "Based on {n} feedbacks in the last 30 days" subtitle

Plan gated: Pro+ (same as Customer 360 page)

---

## 4. Confidence Scoring

### 4.1 Enhanced Confidence Computation

**File**: `services/backend-api/src/services/health_score_service.py`

Replace the simple feedback-count-based confidence with a 3-factor formula:

```python
def compute_confidence_score(feedback_count: int, last_feedback_at: datetime, unique_categories: int) -> int:
    """Returns 0-100 confidence percentage."""

    # Factor 1: Data volume (0-40 points)
    if feedback_count >= 20:
        volume_score = 40
    elif feedback_count >= 10:
        volume_score = 30
    elif feedback_count >= 5:
        volume_score = 20
    elif feedback_count >= 3:
        volume_score = 10
    else:
        volume_score = feedback_count * 3  # 0, 3, 6

    # Factor 2: Data recency (0-35 points)
    if last_feedback_at is None:
        recency_score = 0
    else:
        days_since = (datetime.utcnow() - last_feedback_at).days
        if days_since <= 7:
            recency_score = 35
        elif days_since <= 14:
            recency_score = 28
        elif days_since <= 30:
            recency_score = 20
        elif days_since <= 60:
            recency_score = 10
        else:
            recency_score = 5

    # Factor 3: Topic diversity (0-25 points)
    # unique_categories = count of distinct pain_point_category + feature_request_category
    if unique_categories >= 5:
        diversity_score = 25
    elif unique_categories >= 3:
        diversity_score = 18
    elif unique_categories >= 2:
        diversity_score = 10
    else:
        diversity_score = 5

    return min(volume_score + recency_score + diversity_score, 100)
```

**Confidence levels** (derived from score):
| Score | Level | Display |
|-------|-------|---------|
| 0-30 | low | "Low confidence" badge (red) |
| 31-60 | medium | "Medium confidence" badge (yellow) |
| 61-100 | high | No badge or "High confidence" (green) |

### 4.2 Update Health Score Recomputation

**File**: `services/backend-api/src/services/health_score_service.py` → `update_customer_health()`

After computing health score, also compute confidence:

```python
# Query unique categories for this customer
unique_cats = db.query(func.count(func.distinct(FeedbackItem.pain_point_category))).filter(
    FeedbackItem.organization_id == org_id,
    FeedbackItem.customer_email == customer_email,
    FeedbackItem.pain_point_category.isnot(None),
).scalar() or 0

unique_feature_cats = db.query(func.count(func.distinct(FeedbackItem.feature_request_category))).filter(
    FeedbackItem.organization_id == org_id,
    FeedbackItem.customer_email == customer_email,
    FeedbackItem.feature_request_category.isnot(None),
).scalar() or 0

confidence = compute_confidence_score(
    feedback_count=feedback_count,
    last_feedback_at=existing_record.last_feedback_at,
    unique_categories=unique_cats + unique_feature_cats,
)
existing_record.confidence_score = confidence
existing_record.confidence_level = (
    "low" if confidence <= 30 else "medium" if confidence <= 60 else "high"
)
```

### 4.3 API Changes

**File**: `services/backend-api/src/api/routes/customer_health.py`

Add `confidence_score` to the customer health response schema:

```python
confidence_score: int  # 0-100
confidence_level: str  # low/medium/high
```

**File**: `services/backend-api/src/api/routes/feedbacks.py`

Include confidence data when feedback has a `customer_email`:
- Fetch `CustomerHealth.confidence_score` for the customer
- Return in feedback detail response as `customer_confidence_score`

### 4.4 Frontend: Customer 360

**File**: `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx`

Add confidence indicator to the health score overview section:

- Circular badge or pill showing "{confidence_score}% confidence"
- Color: red (<30), yellow (30-60), green (>60)
- Tooltip explaining the 3 factors: "Based on {n} feedbacks, last feedback {x} days ago, {y} topic categories"

### 4.5 Frontend: Feedback Detail

**File**: `services/frontend-web/app/(dashboard)/feedbacks/[id]/page.tsx`

Add confidence indicator to the churn risk card (when `customer_email` exists):

- Small badge below the score: "87% confidence" or "Low confidence (23%)"
- Tooltip: "Based on data volume, recency, and topic diversity for this customer"

### 4.6 Frontend: Feedbacks List

**File**: `services/frontend-web/app/(dashboard)/feedbacks/page.tsx`

Add subtle confidence indicator on low-confidence items:

- When `customer_confidence_score < 30`: show a small warning icon (AlertTriangle) next to the churn risk column
- Tooltip: "Low confidence — limited data for this customer"
- No indicator for medium/high confidence (avoid clutter)

---

## 5. Backtest Validation

### 5.1 CLI Script

**File**: `scripts/backtest_churn.py`

Standalone script that evaluates churn prediction accuracy:

```bash
# Usage
python scripts/backtest_churn.py --days 30 --output results.csv
python scripts/backtest_churn.py --days 60 --output results_60d.csv --db-url postgresql://...
```

**Algorithm**:
1. Query all customers with `CustomerHealth` records
2. Define "churned" = no feedback in last `--days` days (default 30)
3. For each customer:
   - Get their most recent `churn_risk_score` (from their last feedback before the evaluation window)
   - Get their `health_score` at the time
   - Determine actual churn status (did they submit feedback after that point?)
4. Compute metrics:
   - **Churn risk score evaluation**: threshold at 50 → predicted churn if score > 50
   - **Health score evaluation**: threshold at 50 → predicted churn if score < 50
5. Output:
   - Precision, recall, F1-score, accuracy for both metrics
   - Optimal threshold analysis (test thresholds 20-80 in steps of 5)
   - ROC-AUC if enough data

**CSV output columns**:
```
customer_email, feedback_count, last_churn_risk_score, last_health_score,
predicted_churn_by_risk, predicted_churn_by_health, actual_churned,
days_since_last_feedback, correct_risk, correct_health
```

**Terminal output**:
```
=== Churn Prediction Backtest Results ===
Period: 30 days | Customers evaluated: 150 | Churned: 23 (15.3%)

--- Churn Risk Score (threshold: 50) ---
Precision: 0.72 | Recall: 0.65 | F1: 0.68 | Accuracy: 0.81

--- Health Score (threshold: 50) ---
Precision: 0.78 | Recall: 0.70 | F1: 0.74 | Accuracy: 0.85

--- Optimal Thresholds ---
Best churn risk threshold: 45 (F1: 0.71)
Best health score threshold: 55 (F1: 0.76)

Results exported to: results.csv
```

### 5.2 Admin API Endpoint

**File**: `services/backend-api/src/api/routes/admin.py` (or new `admin_backtest.py`)

```
POST /api/v1/admin/backtest
```

Request:
```json
{
    "churn_days": 30,
    "organization_id": null  // null = all orgs, specific id = single org
}
```

Response:
```json
{
    "period_days": 30,
    "customers_evaluated": 150,
    "churned_count": 23,
    "churn_rate": 15.3,
    "churn_risk_metrics": {
        "threshold": 50,
        "precision": 0.72,
        "recall": 0.65,
        "f1": 0.68,
        "accuracy": 0.81,
        "optimal_threshold": 45,
        "optimal_f1": 0.71
    },
    "health_score_metrics": {
        "threshold": 50,
        "precision": 0.78,
        "recall": 0.70,
        "f1": 0.74,
        "accuracy": 0.85,
        "optimal_threshold": 55,
        "optimal_f1": 0.76
    }
}
```

Gated to `is_system_admin` only.

---

## 6. Backfill Script

**File**: `scripts/backfill_churn_factors.py`

Recomputes `churn_risk_factors` for all existing feedback items:

```bash
python scripts/backfill_churn_factors.py --batch-size 100
python scripts/backfill_churn_factors.py --org-id 5  # single org
python scripts/backfill_churn_factors.py --dry-run    # preview only
```

**Logic**:
1. Query feedback items where `churn_risk_factors IS NULL` and `churn_risk_score IS NOT NULL`
2. For each item, run `_compute_heuristic_churn_risk(feedback, db)` to get factor breakdown
3. Store factors on the item
4. Batch commit every `--batch-size` items
5. Also recompute `confidence_score` on all `CustomerHealth` records

**Output**:
```
Backfilling churn_risk_factors...
Processed: 1000/2500 feedback items (40%)
Processed: 2000/2500 feedback items (80%)
Done: 2500 items updated, 0 errors

Recomputing confidence scores...
Updated: 150 customer health records
Done.
```

---

## 7. Plan Gating

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| Churn risk score (existing) | Yes | Yes | Yes | Yes |
| Factor breakdown (expandable) | - | Yes | Yes | Yes |
| Aggregated factors on Customer 360 | - | Yes | Yes | Yes |
| Confidence score display | - | Yes | Yes | Yes |
| Low-confidence warning on feedbacks list | - | Yes | Yes | Yes |
| Backtest endpoint | - | - | - | System admin |

**Feature IDs used**: `enhanced_churn_prediction` (existing Pro+ gate)

---

## 8. Implementation Phases

### Phase 1: Data Model + Migration (0.5 day)

**Files**:
- `services/backend-api/src/models/feedback.py` — Add `churn_risk_factors` JSON column
- `services/backend-api/src/models/customer_health.py` — Add `confidence_score` Integer column
- `services/backend-api/alembic/versions/` — New migration

**Tasks**:
1. Add columns to models
2. Create Alembic migration
3. Test migration applies cleanly

### Phase 2: Factor Computation + Storage (1 day)

**Files**:
- `services/worker-service/src/tasks/analysis.py` — Modify `_compute_heuristic_churn_risk()` to return factors dict, store on feedback

**TDD tests**:
1. `_compute_heuristic_churn_risk()` returns tuple (score, factors)
2. Factors dict has all 9 keys with score/max/label
3. Factor scores sum to composite score
4. Labels are descriptive (include keyword matches, trend values)
5. Customer-level factors return defaults when no `customer_email`/`db`
6. Factors stored on `feedback.churn_risk_factors` after analysis

### Phase 3: Confidence Scoring (1 day)

**Files**:
- `services/backend-api/src/services/health_score_service.py` — Add `compute_confidence_score()`, integrate into `update_customer_health()`

**TDD tests**:
1. `compute_confidence_score()` returns 0-100
2. High feedback count (20+) = high volume score (40)
3. Recent feedback (≤7 days) = high recency score (35)
4. Diverse categories (5+) = high diversity score (25)
5. Maximum confidence = 100 (40+35+25)
6. Low confidence: 1 feedback, 60+ days old, 1 category
7. `confidence_level` derived correctly (low ≤30, medium ≤60, high >60)
8. Confidence updated in `update_customer_health()`

### Phase 4: API Extensions (0.5 day)

**Files**:
- `services/backend-api/src/api/routes/feedbacks.py` — Include `churn_risk_factors` in detail response
- `services/backend-api/src/api/routes/customer_health.py` — Add `confidence_score` to response, add `/churn-factors` endpoint
- `services/backend-api/src/api/routes/admin.py` — Add backtest endpoint

**TDD tests**:
1. Feedback detail response includes `churn_risk_factors` when present
2. Customer health response includes `confidence_score` and `confidence_level`
3. `/churn-factors` returns aggregated factors for last 30 days
4. `/churn-factors` plan-gated to Pro+
5. Backtest endpoint requires `is_system_admin`
6. Backtest returns metrics structure with precision/recall/F1

### Phase 5: Frontend — Factor Breakdown (1 day)

**Files**:
- `services/frontend-web/app/(dashboard)/feedbacks/[id]/page.tsx` — Expandable factor breakdown
- `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx` — Aggregated factors section

**TDD tests**:
1. Factor breakdown section renders when `churn_risk_factors` exists
2. Collapsed by default, expands on click
3. Factors sorted by score descending
4. Each factor shows label, score/max, progress bar
5. Color coding: red (>75% of max), orange (40-75%), green (<40%)
6. Hidden for Free plan users with upgrade CTA
7. Customer 360 shows aggregated factors
8. Top 3 risk drivers highlighted

### Phase 6: Frontend — Confidence Display (0.5 day)

**Files**:
- `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx` — Confidence badge
- `services/frontend-web/app/(dashboard)/feedbacks/[id]/page.tsx` — Confidence on churn card
- `services/frontend-web/app/(dashboard)/feedbacks/page.tsx` — Low-confidence warning icon

**TDD tests**:
1. Customer 360 shows confidence score badge with correct color
2. Feedback detail shows confidence badge on churn risk card
3. Feedbacks list shows warning icon when confidence < 30
4. No warning icon for medium/high confidence
5. Tooltip shows explanation text

### Phase 7: Backtest + Backfill Scripts (1 day)

**Files**:
- `scripts/backtest_churn.py` — CLI backtest script
- `scripts/backfill_churn_factors.py` — Backfill script

**TDD tests** (for backtest logic, not the CLI wrapper):
1. Churn detection: customer with no feedback in 30+ days = churned
2. Churn detection: customer with recent feedback = not churned
3. Metrics computation: precision, recall, F1, accuracy from confusion matrix
4. Optimal threshold search finds best F1
5. CSV output has correct columns
6. Backfill updates items with NULL `churn_risk_factors`
7. Backfill skips items with existing factors

---

## 9. Risk & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Backfill is slow for large datasets | Medium — could take minutes for 10K+ items | Batch processing with progress output, `--batch-size` flag |
| Factor labels are noisy/unhelpful | Low — labels hardcoded in analysis code | Keep labels concise, test readability with real data |
| Confidence score formula needs tuning | Medium — weights may not match intuition | Start with simple additive weights, adjust after backtest |
| Backtest produces misleading results with small data | High — precision/recall unreliable with few customers | Show "Insufficient data" warning if <20 customers evaluated |
| Customer-level factors unavailable for feedbacks without customer_email | Low — ~30% of feedback may lack email | Show "4 of 9 factors available" when customer-level data missing |

---

## 10. Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `services/backend-api/src/models/feedback.py` | Modify | Add `churn_risk_factors` JSON column |
| `services/backend-api/src/models/customer_health.py` | Modify | Add `confidence_score` column |
| `services/backend-api/alembic/versions/` | New | Migration for new columns |
| `services/worker-service/src/tasks/analysis.py` | Modify | Return + store factor breakdown |
| `services/backend-api/src/services/health_score_service.py` | Modify | Add `compute_confidence_score()` |
| `services/backend-api/src/api/routes/feedbacks.py` | Modify | Include factors in detail response |
| `services/backend-api/src/api/routes/customer_health.py` | Modify | Add confidence + churn-factors endpoint |
| `services/backend-api/src/api/routes/admin.py` | Modify | Add backtest endpoint |
| `services/frontend-web/app/(dashboard)/feedbacks/[id]/page.tsx` | Modify | Factor breakdown + confidence badge |
| `services/frontend-web/app/(dashboard)/feedbacks/page.tsx` | Modify | Low-confidence warning icon |
| `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx` | Modify | Aggregated factors + confidence badge |
| `scripts/backtest_churn.py` | New | CLI backtest script |
| `scripts/backfill_churn_factors.py` | New | Backfill script for existing data |

---

## 11. Success Metrics

| Metric | Target |
|--------|--------|
| Factor breakdown click-through rate | > 30% of users viewing feedback detail expand factors |
| Confidence score coverage | 100% of CustomerHealth records have confidence_score |
| Backfill completion | 100% of existing feedback items with churn_risk_score have factors populated |
| Backtest baseline established | Precision/recall/F1 metrics recorded for current model |
| Churn risk accuracy (F1) | Baseline measurement (target: > 0.60 with current 9-factor model) |

---

## Related

- [AI-TRACKING.md](AI-TRACKING.md) — M1.4 milestone
- [PRD-PREDICTIVE-ANALYTICS.md](PRD-PREDICTIVE-ANALYTICS.md) — Original churn scoring implementation
- [PRD-CUSTOMER-360.md](PRD-CUSTOMER-360.md) — Customer 360 page (dependency, completed)
- [PRD-CUSTOMER-SENTIMENT-ALERTS.md](PRD-CUSTOMER-SENTIMENT-ALERTS.md) — M1.3 (dependency, completed)
