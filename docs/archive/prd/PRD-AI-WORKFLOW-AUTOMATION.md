# PRD: AI Workflow Automation (M4.4)

**Status**: Planned
**Priority**: High
**Owner**: Full-stack
**Date**: 2026-03-18
**Estimated Effort**: 3 weeks
**Milestone**: M4.4 (AI-TRACKING.md)

---

## 1. Problem Statement

Teams using Rereflect identify churn risks, critical bugs, and urgent feedback — but then must manually assign, escalate, and respond to each one. A CS lead seeing a customer's health score drop from 60 to 25 has to manually assign a team member, change the status, draft a response, and notify the team. This multi-step process is slow, inconsistent, and prone to human error.

**Impact**: At-risk customers don't get timely outreach. Critical bugs sit unassigned for hours. Response time varies wildly depending on who's online. Teams that could automate 80% of their triage workflow are stuck doing it manually.

---

## 2. Goals

1. Let orgs create IF/THEN automation rules: IF [trigger condition] THEN [action(s)]
2. Support 4 trigger types: health score threshold, sentiment pattern, churn risk level change, feedback category match
3. Support 4 action types: auto-assign, change status, send notification, draft AI response
4. Rules support multiple actions per trigger (e.g., assign + notify + draft response)
5. Real-time execution — triggers fire immediately when conditions are met (event-driven)
6. Configurable cooldown per rule (default 24h, adjustable 1h-7d) to prevent spam
7. 5 pre-built starter templates (Churn Prevention, Critical Bug Escalation, etc.)
8. Execution audit log — every automation run is logged with trigger, actions, and outcome
9. Plan-gated: Pro=5 rules, Business=20, Enterprise=unlimited
10. Settings > Automations page with form-based rule builder

---

## 3. Non-Goals

- No visual flow builder (drag-and-drop node editor)
- No multi-step conditional chains (IF → THEN → IF → THEN)
- No time-delayed actions ("wait 2 hours, then send")
- No external integrations as actions (no Slack message, no JIRA issue — use webhooks for that)
- No AND/OR compound triggers (one trigger type per rule)
- No automation analytics/metrics dashboard

---

## 4. Trigger Types

### 4.1 Health Score Threshold

**Fires when**: A customer's health score crosses below a configured threshold.

**Configuration**:
- `threshold`: number (1-99, default 30)
- `direction`: `below` (fires when score drops below threshold)

**Example**: "When health score drops below 30" → assign to CS lead + send notification

**Event source**: Health score recomputation (after feedback analysis)

### 4.2 Sentiment Pattern

**Fires when**: A customer sends N negative feedbacks within X days.

**Configuration**:
- `count`: number (1-20, default 3)
- `days`: number (1-30, default 7)
- `sentiment`: `negative` (could extend to `neutral` later)

**Example**: "When a customer sends 3 negative feedbacks in 7 days" → escalate + draft response

**Event source**: After feedback analysis (sentiment assigned)

### 4.3 Churn Risk Level Change

**Fires when**: A customer's risk level changes to a specified level.

**Configuration**:
- `target_level`: `at_risk` | `critical` (which level triggers the rule)
- `from_levels`: optional array of source levels (e.g., only fire when going from `moderate` → `at_risk`, not `healthy` → `at_risk`)

**Example**: "When risk level becomes critical" → assign to CS lead + notify + draft outreach

**Event source**: Health score recomputation (risk level change)

### 4.4 Feedback Category Match

**Fires when**: New feedback matches specific categories + optional conditions.

**Configuration**:
- `categories`: string[] (e.g., `["critical_bug", "security_breach"]`)
- `is_urgent`: optional boolean (only fire if urgent)
- `severity`: optional string (e.g., `critical`, `high`)

**Example**: "When feedback is critical_bug + urgent" → assign to engineering lead + change status to In Review

**Event source**: After feedback analysis (categories assigned)

---

## 5. Action Types

### 5.1 Auto-Assign

Assign the feedback item to a team member.

**Configuration**:
- `assign_to`: `user:{user_id}` | `role:owner` | `role:admin` | `round_robin`
- `round_robin` selects the team member with fewest open items (reuses existing auto-assignment logic)

### 5.2 Change Workflow Status

Move the feedback item to a specific workflow status.

**Configuration**:
- `status`: `new` | `in_review` | `resolved` | `closed`

### 5.3 Send Notification

Create a notification for specified recipients.

**Configuration**:
- `recipients`: `assignee` | `admins` | `owner` | `user:{user_id}`
- `channels`: `dashboard` | `email` | `slack` (uses existing notification dispatch)
- `message_template`: optional custom message (default: "Automation '{rule_name}' triggered for feedback #{id}")

### 5.4 Draft AI Response

Generate an AI response suggestion and save it as a draft on the feedback item.

**Configuration**:
- `tone`: `professional` | `empathetic` | `friendly` | `concise` (default: org's `default_tone`)
- `template_id`: optional — use a specific response template as base

**Implementation**: Calls the existing response generation endpoint, saves the result as a draft `FeedbackResponse` with `status=draft`, and notifies the assignee.

---

## 6. Rule Structure

```json
{
  "id": 1,
  "organization_id": 1,
  "name": "Churn Risk Escalation",
  "description": "Escalate when customer health drops critically",
  "is_active": true,
  "trigger": {
    "type": "health_score_threshold",
    "config": {
      "threshold": 30,
      "direction": "below"
    }
  },
  "actions": [
    {
      "type": "auto_assign",
      "config": { "assign_to": "role:admin" }
    },
    {
      "type": "change_status",
      "config": { "status": "in_review" }
    },
    {
      "type": "send_notification",
      "config": {
        "recipients": "admins",
        "channels": ["dashboard", "email"]
      }
    },
    {
      "type": "draft_response",
      "config": { "tone": "empathetic" }
    }
  ],
  "cooldown_hours": 24,
  "execution_count": 15,
  "last_executed_at": "2026-03-18T10:00:00Z",
  "created_at": "2026-03-01T00:00:00Z"
}
```

---

## 7. Pre-Built Templates

5 starter templates users can enable and customize:

### 7.1 Churn Prevention
- **Trigger**: Health score drops below 30
- **Actions**: Assign to admin (round-robin), notify via dashboard + email, draft empathetic response
- **Cooldown**: 48h

### 7.2 Critical Bug Escalation
- **Trigger**: Category match = `critical_bug` or `security_breach`, urgent = true
- **Actions**: Assign to admin, change status to `in_review`, notify via all channels
- **Cooldown**: 1h

### 7.3 Feature Request Triage
- **Trigger**: Category match = any feature request category
- **Actions**: Change status to `in_review`, assign to round-robin
- **Cooldown**: 24h

### 7.4 Negative Sentiment Alert
- **Trigger**: Sentiment pattern = 3 negative in 7 days
- **Actions**: Notify admins via dashboard + email, draft empathetic response
- **Cooldown**: 48h

### 7.5 Positive Feedback Follow-up
- **Trigger**: Category match = `positive` sentiment feedback
- **Actions**: Draft friendly thank-you response
- **Cooldown**: 168h (1 week)

---

## 8. Execution Engine

### Event-Driven Architecture

Automation rules evaluate in real-time when specific events occur:

```
Event occurs (feedback analyzed, health score updated)
  → AutomationEngine.evaluate(org_id, event_type, context)
  → Query active rules matching event_type for this org
  → For each matching rule:
     → Check trigger condition against context data
     → Check cooldown (last_executed_at + cooldown_hours > now? skip)
     → If condition met + not in cooldown:
        → Execute all actions sequentially
        → Log execution to audit table
        → Update rule's last_executed_at + execution_count
```

### Dispatch Points

| Event | Where it fires | Triggers evaluated |
|-------|----------------|-------------------|
| Feedback analyzed | Worker: after `analyze_single_feedback` | `feedback_category_match`, `sentiment_pattern` |
| Health score updated | Worker: after `recompute_health_score` | `health_score_threshold`, `churn_risk_level_change` |

### Cooldown

Each rule has a `cooldown_hours` (default 24). Cooldown is per-customer per-rule:
- Key: `automation_cooldown:{rule_id}:{customer_email}`
- Storage: Redis (same DB as other cooldowns)
- TTL: cooldown_hours * 3600

---

## 9. Database Schema

### `automation_rules` table

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| organization_id | Integer FK | organizations.id, CASCADE |
| name | String(200) | User-friendly label |
| description | Text | Optional description |
| is_active | Boolean | Default true. Pause/resume toggle. |
| trigger_type | String(50) | health_score_threshold, sentiment_pattern, churn_risk_level_change, feedback_category_match |
| trigger_config | JSON | Type-specific configuration |
| actions | JSON | Array of {type, config} objects |
| cooldown_hours | Integer | Default 24. Min 1, max 168 (7 days). |
| execution_count | Integer | Total times this rule has fired |
| last_executed_at | DateTime | Nullable |
| is_template | Boolean | Default false. True for pre-built templates. |
| template_id | String(50) | Nullable. Template identifier (e.g., "churn_prevention") |
| created_at | DateTime | |
| updated_at | DateTime | |

Indexes: `(organization_id, is_active)`, `(organization_id, trigger_type)`

### `automation_executions` table (audit log)

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| rule_id | Integer FK | automation_rules.id, CASCADE |
| organization_id | Integer FK | |
| feedback_id | Integer | FK to feedback_items.id (nullable) |
| customer_email | String | The customer that triggered the rule (nullable) |
| trigger_snapshot | JSON | The condition values at time of trigger |
| actions_executed | JSON | Array of {type, result, error} |
| status | String(20) | `success`, `partial_failure`, `failed` |
| executed_at | DateTime | |

Index: `(rule_id, executed_at DESC)`, `(organization_id, executed_at DESC)`

Retention: 90 days (Celery Beat weekly purge)

---

## 10. API Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/automations` | List org's automation rules | JWT |
| POST | `/api/v1/automations` | Create rule | JWT, Admin+ |
| GET | `/api/v1/automations/{id}` | Get rule details | JWT |
| PUT | `/api/v1/automations/{id}` | Update rule | JWT, Admin+ |
| DELETE | `/api/v1/automations/{id}` | Delete rule | JWT, Admin+ |
| PATCH | `/api/v1/automations/{id}/toggle` | Pause/resume rule | JWT, Admin+ |
| GET | `/api/v1/automations/{id}/executions` | Get execution log (last 50) | JWT |
| GET | `/api/v1/automations/templates` | List available templates | JWT |
| POST | `/api/v1/automations/templates/{template_id}/enable` | Enable a template (creates a rule from template) | JWT, Admin+ |

---

## 11. Frontend

### Settings > Automations Page

**List view**:
- Table: Name, Trigger type (badge), Actions (icon chips), Status (active/paused toggle), Executions count, Last fired
- "Add Rule" button (disabled at plan limit)
- Plan limit indicator: "3/5 rules used"
- "Browse Templates" button → opens template picker

**Create/Edit Rule Form** (form-based):
```
Rule Name: [____________]
Description: [____________] (optional)

TRIGGER
  Type: [dropdown: Health Score / Sentiment Pattern / Risk Level Change / Category Match]
  
  (dynamic config based on type)
  Health Score: "When score drops below [__30__]"
  Sentiment: "When customer sends [__3__] negative feedbacks in [__7__] days"
  Risk Level: "When risk level becomes [dropdown: at_risk / critical]"
  Category: "When category is [multi-select tags] and urgent is [toggle]"

ACTIONS (add multiple)
  [+ Add Action]
  1. [dropdown: Auto-assign / Change Status / Notify / Draft Response]
     (dynamic config per type)
  2. ...

COOLDOWN
  "Don't re-trigger for same customer within [__24__] hours"

[Cancel] [Save Rule]
```

**Execution Log** (on rule detail page):
- Table: Timestamp, Customer, Feedback #, Actions taken, Status (success/failed)
- Last 50 executions

**Template Picker** (modal/drawer):
- 5 cards: name, description, trigger summary, action summary
- "Enable" button → creates rule with template defaults → redirects to edit page for customization

### Sidebar Navigation

Add "Automations" to Settings section in `AppSidebar.tsx`.

---

## 12. Plan Gating

| Plan | Max Rules | Templates | Trigger Types | Actions |
|------|-----------|-----------|---------------|---------|
| Free | 0 | - | - | - |
| Pro | 5 | All 5 | All 4 | All 4 |
| Business | 20 | All 5 | All 4 | All 4 |
| Enterprise | Unlimited | All 5 | All 4 | All 4 |

Feature ID: `workflow_automation`

---

## 13. Implementation Phases

### Phase 1: Database + Backend API (4-5 days)
- Alembic migration for `automation_rules` + `automation_executions` tables
- SQLAlchemy models
- CRUD API endpoints + toggle + templates + execution log
- Plan gating: `workflow_automation` feature, rule count limits per plan
- 5 pre-built template definitions
- Trigger config + action config validation (Pydantic schemas)

### Phase 2: Execution Engine (3-4 days)
- `AutomationEngine` service: evaluate(), execute_rule(), check_cooldown()
- Action executors: assign, change_status, notify, draft_response
- Redis cooldown tracking
- Wire into dispatch points: feedback analysis task, health score recomputation
- Execution logging to `automation_executions` table
- Celery Beat weekly purge for executions > 90 days

### Phase 3: Frontend (3-4 days)
- Settings > Automations list page
- Rule create/edit form with dynamic trigger/action config
- Execution log view
- Template picker modal
- Active/paused toggle
- Plan limit indicator + upgrade CTA
- Sidebar navigation entry
- API client (`lib/api/automations.ts`)

---

## 14. Testing Strategy

- Backend: CRUD endpoints, plan limits, trigger validation, action validation, template enable
- Engine: trigger evaluation (each type), cooldown check, action execution, multi-action rules, execution logging
- Frontend: rule list, create form, toggle, template picker, execution log
- Integration: end-to-end from feedback analysis → trigger match → action execution → audit log

---

## 15. Key Files (Expected)

### Backend
- `src/models/automation_rule.py` — SQLAlchemy model
- `src/models/automation_execution.py` — Audit log model
- `src/api/routes/automations.py` — CRUD + toggle + templates endpoints
- `src/services/automation_engine.py` — Evaluation + execution logic
- `src/config/automation_templates.py` — 5 pre-built template definitions
- `alembic/versions/xxx_add_automation_tables.py` — Migration

### Worker
- Wire dispatch in `src/tasks/analysis.py` (after feedback analysis)
- Wire dispatch in health score recomputation

### Frontend
- `app/(dashboard)/settings/automations/page.tsx` — List + template picker
- `app/(dashboard)/settings/automations/[id]/page.tsx` — Edit rule + execution log
- `app/(dashboard)/settings/automations/new/page.tsx` — Create rule
- `lib/api/automations.ts` — API client
- `components/automations/RuleForm.tsx` — Reusable form component
