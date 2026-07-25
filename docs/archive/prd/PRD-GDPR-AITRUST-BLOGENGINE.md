# PRD: GDPR Compliance, AI Trust, & Blog Engine (M3.8)

**Status**: Planned
**Priority**: High
**Owner**: Full-stack
**Date**: 2026-03-18
**Estimated Effort**: 3 weeks (parallel tracks)
**Milestone**: M3.8

---

## Track A: GDPR Compliance (M3.7 partial)

### A.1 Problem Statement

Users cannot export or delete their personal data from Rereflect. GDPR (and similar regulations) require data portability (Art. 20) and right to erasure (Art. 17). Without these, enterprise-minded customers and EU-based users cannot adopt the product.

### A.2 Goals

1. Any user can export all their personal data as JSON + CSV from Settings
2. Any user can request account deletion with a 30-day grace period
3. Confirmation email on deletion request + reminder email 5 days before final purge
4. During grace period, account is deactivated (cannot login) but data is preserved
5. After 30 days, all user data is permanently purged
6. "GDPR compliant" badge on landing page

### A.3 Non-Goals

- No org-wide data export (only per-user)
- No admin-initiated deletion of other users (existing admin delete covers this)
- No data residency selection (deferred)
- No cookie consent banner (landing page is static, no tracking cookies)

### A.4 Data Export

**Endpoint**: `GET /api/v1/account/export`

Returns a ZIP file containing:

| File | Content |
|------|---------|
| `profile.json` | User email, role, org name, joined_at, plan |
| `feedbacks.csv` | All feedback items created by or assigned to this user |
| `feedbacks.json` | Same as above in JSON format |
| `conversations.json` | All Copilot conversations + messages |
| `notes.json` | All feedback notes authored by this user |
| `responses.json` | All feedback responses sent by this user |
| `reports.json` | All generated reports |
| `preferences.json` | Alert preferences, digest settings |

**Frontend**: Button in Settings > Preferences: "Export My Data" → downloads ZIP.

**Auth**: Any authenticated user. No role restriction.

### A.5 Data Deletion

**Endpoint**: `POST /api/v1/account/delete-request`

**Flow**:
1. User clicks "Delete My Account" in Settings > Preferences
2. Confirmation dialog: "This will permanently delete your account and all data after 30 days. You will be logged out immediately."
3. User confirms → API creates deletion request
4. Account is deactivated: `user.is_deactivated = True`, `user.deletion_requested_at = now()`
5. User is logged out
6. Confirmation email sent via Resend
7. Celery Beat task runs daily: checks for users where `deletion_requested_at + 30 days <= now()`
8. At day 25: reminder email sent ("Your account will be deleted in 5 days. Log in to cancel.")
9. At day 30: full data purge (all related records across 15+ tables)
10. If user logs in during grace period: `is_deactivated = False`, `deletion_requested_at = NULL` → cancels deletion

**Endpoint**: `POST /api/v1/account/cancel-deletion` (for grace period recovery)

**Database changes**:
- Add to `users` table: `is_deactivated` (Boolean, default false), `deletion_requested_at` (DateTime, nullable)
- Auth middleware: reject requests from deactivated users with 403 + message

### A.6 Plan Gating

None — GDPR compliance available to all plans.

---

## Track B: AI Trust — Human-in-the-Loop

### B.1 Problem Statement

Users cannot provide feedback on AI outputs (sentiment labels, categories, churn scores, copilot responses). Without human correction signals, the AI cannot improve over time, and users don't trust outputs they can't influence.

### B.2 Goals

1. Thumbs up/down on Copilot chat responses (optional text feedback on thumbs down)
2. Category/sentiment correction on feedback detail page (thumbs down → select correct value)
3. Churn risk flagging on customer health page
4. Response quality rating on AI-generated responses
5. Correction history visible in AI Settings page (count + accuracy stats)
6. All corrections stored in DB for future fine-tuning pipeline

### B.3 Non-Goals

- No automatic model retraining from corrections (stored for future use)
- No A/B testing of corrected vs uncorrected
- No correction review/approval workflow
- No bulk correction tools

### B.4 Database Schema

#### `ai_corrections` table

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| organization_id | Integer FK | |
| user_id | Integer FK | who made the correction |
| correction_type | String(50) | `copilot_response`, `sentiment`, `category`, `churn_risk`, `response_suggestion` |
| entity_type | String(50) | `conversation_message`, `feedback_item`, `customer_health`, `feedback_response` |
| entity_id | Integer | ID of the entity being corrected |
| signal | String(20) | `thumbs_up`, `thumbs_down`, `correction` |
| original_value | String(500) | What the AI said (e.g., "negative", "billing_issue") |
| corrected_value | String(500) | What the user says it should be (nullable for thumbs_up) |
| feedback_text | Text | Optional text feedback (thumbs_down only) |
| created_at | DateTime | |

Index: `(organization_id, correction_type)`, `(entity_type, entity_id)`

### B.5 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ai-corrections` | Submit a correction/rating |
| GET | `/api/v1/ai-corrections/stats` | Get correction stats for AI Settings page |
| GET | `/api/v1/ai-corrections` | List corrections (admin, paginated) |

### B.6 Correction Types

#### 1. Copilot Response Rating
- **Where**: Every AI message in Copilot chat
- **UI**: Thumbs up / thumbs down icons below each AI response (next to copy/regenerate)
- **Thumbs down flow**: Shows optional text input "What was wrong?" → submit
- **Stored as**: `correction_type=copilot_response`, `entity_type=conversation_message`, `entity_id=message.id`

#### 2. Feedback Categorization Correction
- **Where**: Feedback detail page, on sentiment/category/pain point/feature request badges
- **UI**: Small thumbs down icon next to each AI-assigned label. Click → dropdown to select correct value.
- **Sentiment**: Thumbs down → pick: positive, neutral, negative
- **Pain point category**: Thumbs down → pick from category list
- **Feature request category**: Thumbs down → pick from category list
- **Stored as**: `correction_type=sentiment|category`, `entity_type=feedback_item`, `original_value=negative`, `corrected_value=neutral`

#### 3. Churn Risk Flagging
- **Where**: Customer health page, on the health score
- **UI**: "Flag as inaccurate" link below the score → optional text "Why is this wrong?"
- **Stored as**: `correction_type=churn_risk`, `entity_type=customer_health`

#### 4. Response Suggestion Rating
- **Where**: ResponseModal after using a template or AI-generated response
- **UI**: Quick thumbs up/down after sending/copying a response
- **Stored as**: `correction_type=response_suggestion`, `entity_type=feedback_response`

### B.7 AI Settings — Correction Stats

New section in AI Settings page: "AI Accuracy"

Shows:
- Total corrections submitted (all time)
- Corrections this month
- Breakdown by type (pie chart: sentiment, category, churn, copilot, response)
- Most corrected categories (top 5 — which AI labels get corrected most)

### B.8 Plan Gating

Available to all plans. Corrections are a trust-building feature, not premium.

---

## Track C: Blog Scheduled Publishing + Content Batch

### C.1 Problem Statement

Blog posts in `blog.ts` currently show regardless of their date. Posts with future dates appear on the blog page before they should. There's no way to prepare posts in advance and have them auto-publish on their scheduled date. Additionally, there's no way to keep a post as a permanent draft.

### C.2 Goals

1. Add `status` field to blog posts: `draft`, `scheduled`, `published`
2. Frontend filters posts: only show where `status === 'published'` OR (`status === 'scheduled'` AND `date <= today`)
3. Draft posts never show publicly
4. Write all remaining planned blog posts (#8 through #24) with appropriate statuses and dates

### C.3 Implementation

#### Blog Post Type Update

```typescript
export interface BlogPost {
  slug: string;
  title: string;
  excerpt: string;
  date: string;
  status: 'draft' | 'scheduled' | 'published';  // NEW
  readTime: string;
  author: string;
  tags: string[];
  seoTitle: string;
  seoDescription: string;
  sections: BlogSection[];
}
```

#### Filter Logic

In the blog listing page and any component that renders posts:

```typescript
const visiblePosts = posts.filter(post => {
  if (post.status === 'published') return true;
  if (post.status === 'scheduled') return new Date(post.date) <= new Date();
  return false; // draft posts never shown
});
```

#### Existing Posts

All 7 published posts get `status: 'published'`.

#### New Posts (#8-#24)

Posts with dates before today get `status: 'published'`.
Posts with future dates get `status: 'scheduled'`.

### C.4 Blog Posts to Write

Write all remaining posts from BLOG-TRACKING.md:

| # | Title | Target Date | Status |
|---|-------|-------------|--------|
| 8 | Rereflect vs UserVoice | May 15 | scheduled |
| 9 | Support Tickets to Product Insights | Jun 1 | scheduled |
| 10 | Rereflect vs MonkeyLearn | Jun 15 | scheduled |
| 11 | Data-Driven Product Roadmap | Jul 1 | scheduled |
| 12 | Rereflect vs Thematic | Jul 15 | scheduled |
| 13 | NPS Is Not Enough | Aug 1 | scheduled |
| 14 | Rereflect vs Idiomatic | Aug 15 | scheduled |
| 15 | Voice-of-Customer Program | Sep 1 | scheduled |
| 16 | Best Customer Feedback Tools 2026 | Sep 15 | scheduled |
| 17 | Slack Messages to Product Strategy | Oct 1 | scheduled |
| 18 | Why SaaS Companies Ignore Feedback | Oct 15 | scheduled |
| 19 | Customer Feedback Categories Framework | Nov 1 | scheduled |
| 20 | AI Copilot Turns Questions Into Insights | Nov 15 | scheduled |
| 21 | Year-End Feedback Review | Dec 1 | scheduled |
| 22 | Real Cost of Not Analyzing Feedback | Dec 15 | scheduled |
| 23 | Custom Webhooks for Real-Time Alerts | Jan 1, 2027 | scheduled |
| 24 | AI Response Suggestions: Reply 10x Faster | Jan 15, 2027 | scheduled |

Each post follows the existing content structure and style from published posts. Comparison posts follow the template in BLOG-TRACKING.md.

---

## Implementation Phases

### Track A: GDPR (5 days)
1. Alembic migration: add `is_deactivated` + `deletion_requested_at` to users table
2. Data export endpoint (ZIP with JSON + CSV)
3. Deletion request endpoint + account deactivation
4. Cancel deletion endpoint
5. Auth middleware: block deactivated users
6. Celery Beat daily task: check grace periods, send reminder emails, execute purges
7. Frontend: Export + Delete buttons in Settings > Preferences
8. Resend email templates: deletion confirmation + 5-day reminder

### Track B: AI Trust (5 days)
1. Alembic migration: `ai_corrections` table
2. Corrections API (submit, stats, list)
3. Frontend: thumbs up/down on Copilot messages (MessageBubble component)
4. Frontend: category/sentiment correction on feedback detail page
5. Frontend: churn risk flagging on customer health page
6. Frontend: AI Settings correction stats section
7. Tests: correction submission, stats aggregation, plan access

### Track C: Blog Engine + Content (5 days)
1. Add `status` field to BlogPost interface + all existing posts
2. Filter logic in blog listing page
3. Write all 17 remaining blog posts (#8-#24)
4. Update BLOG-TRACKING.md with statuses

---

## Testing Strategy

- **GDPR**: Export endpoint returns correct ZIP structure, deletion flow (request → deactivate → cancel → reactivate), auth middleware blocks deactivated users, purge task cleans all tables
- **AI Trust**: Correction CRUD, stats aggregation, thumbs up/down UI rendering, correction type validation
- **Blog**: Filter logic (published shows, scheduled shows after date, draft hidden), status field validation
