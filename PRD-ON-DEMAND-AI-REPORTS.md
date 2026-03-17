# PRD: On-Demand AI Reports (M2.4)

**Status**: Planned
**Priority**: High
**Owner**: Full-stack
**Date**: 2026-03-17
**Estimated Effort**: 2 weeks
**Milestone**: M2.4 (AI-TRACKING.md)

---

## 1. Problem Statement

Users who want to share feedback insights with stakeholders (executives, board members, investors, CS leads) must manually compile data from the dashboard, export PDFs of individual charts, and write summaries themselves. There's no way to generate a comprehensive, professional report with a single action.

**Impact**: Users spend 30-60 minutes compiling data for weekly/monthly reviews. Stakeholders without Rereflect access can't see insights at all. The lack of polished reports weakens the case for upgrading to paid plans.

---

## 2. Goals

1. Let users generate comprehensive reports via natural language in the AI Copilot
2. Support 4 report types: Executive Summary, Customer Health, Feature Request Prioritization, Churn Risk Analysis
3. Reports include AI-generated narrative sections (LLM-written summaries, key findings)
4. Render reports inline in Copilot chat with full preview
5. Export as branded PDF (Rereflect logo, colors, footer)
6. Include relevant charts based on report type (sentiment trend, volume bar, category distribution, churn risk)
7. Stream report sections progressively (same UX as Copilot chat streaming)
8. Save generated reports for future access (My Reports)
9. 3 predefined date ranges: 7 days, 30 days, 90 days
10. Plan gate: Business+ only

---

## 3. Non-Goals

- No scheduled/recurring reports (manual trigger only)
- No email delivery of reports
- No custom report builder (fixed 4 types)
- No actionable recommendations in reports (data + narrative only)
- No collaborative editing of reports
- No white-label/custom branding (Rereflect branded only)
- No custom date ranges (3 predefined only)

---

## 4. Report Types

### 4.1 Executive Summary

**Purpose**: High-level overview for leadership

**Sections**:
1. **Overview** — Total feedback count, date range, sources breakdown
2. **Sentiment Analysis** — Sentiment distribution (positive/neutral/negative), sentiment trend over time, notable shifts
3. **Top Pain Points** — Top 5 pain point categories by frequency, severity breakdown
4. **Feature Requests** — Top 5 feature requests by frequency, priority distribution
5. **Churn Risk Summary** — Customer count by risk level, new at-risk customers in period
6. **Urgent Items** — Count of urgent feedbacks, top urgent categories

**Charts**: Sentiment trend line, feedback volume bar chart, category distribution donut

---

### 4.2 Customer Health Report

**Purpose**: Per-cohort customer health for CS teams

**Sections**:
1. **Health Distribution** — Customers by risk level (healthy/moderate/at-risk/critical), change vs previous period
2. **At-Risk Customers** — Table of at-risk and critical customers (email, score, trend, top risk factors)
3. **Health Score Trends** — Average health score over time, direction indicator
4. **Sentiment by Customer Tier** — Sentiment breakdown for each risk level
5. **Top Risk Factors** — Most common factors driving health score decline

**Charts**: Churn risk distribution donut, health score trend line

---

### 4.3 Feature Request Prioritization

**Purpose**: Data-driven feature prioritization for product teams

**Sections**:
1. **Request Volume** — Total feature requests in period, trend vs previous period
2. **Top Requests by Frequency** — Ranked table of feature request categories with count, unique customers, avg sentiment
3. **Request by Source** — Which channels generate the most feature requests
4. **Customer Segment Analysis** — Feature requests broken down by customer health tier (are at-risk customers requesting the same things?)
5. **Priority Matrix** — Categorized by priority level (critical/high/medium/low)

**Charts**: Feature request volume bar chart, category distribution donut

---

### 4.4 Churn Risk Analysis

**Purpose**: Deep dive into churn signals for CS/leadership

**Sections**:
1. **Risk Overview** — Customers by risk level, new at-risk count, recovered count
2. **Churn Signal Breakdown** — Top churn factors across all at-risk customers (sentiment decline, complaint frequency, competitor mentions, etc.)
3. **High-Risk Customer Details** — Table of top 10 highest-risk customers with score, factors, recent feedback excerpts
4. **Churn Trends** — Average churn risk score over time, direction
5. **Category Correlation** — Which pain point categories correlate most with high churn risk

**Charts**: Churn risk trend line, risk distribution donut, churn factors bar chart

---

## 5. User Flow

### 5.1 Generate via Copilot

```
User opens AI Copilot (/conversations or Cmd+K)
  → Types "Generate an executive summary for the last 30 days"
  → OR clicks a report template chip in Cmd+K
  → Intent classifier detects "report" intent
  → System extracts: report_type + date_range
  → "Generating report..." status shown
  → Sections stream progressively into chat
  → Each section appears with its narrative + data
  → Charts render inline (Recharts)
  → "Download PDF" button appears at the bottom
  → Report is saved to My Reports
```

### 5.2 View Saved Reports

```
User navigates to /reports (or via sidebar)
  → Sees list of generated reports
  → Each row: report type, date range, generated date, download button
  → Click to view inline preview
  → Click "Download PDF" to get the branded PDF
```

### 5.3 Cmd+K Template Chips

4 new chips added to the existing 8:
- "Executive summary this month"
- "Customer health report"
- "Feature request priorities"
- "Churn risk analysis"

---

## 6. Intent Detection

### New Intent Type: `report`

Added to the intent classifier as a 4th type alongside `data`, `analysis`, `general`.

**Regex Patterns** (`_REPORT_PATTERNS`):
```python
r"\breport\b",
r"\bgenerate\b.*\breport\b",
r"\bcreate\b.*\breport\b",
r"\bexecutive\s+summary\b",
r"\bhealth\s+report\b",
r"\bchurn\s+(risk\s+)?analysis\b",
r"\bfeature\s+(request\s+)?prioriti",
r"\bmonthly\s+summary\b",
r"\bquarterly\s+review\b",
r"\bweekly\s+summary\b",
```

**Report Type Extraction**:
```python
# From the query, detect which report type
"executive" / "summary" / "overview" → executive_summary
"health" / "customer health" → customer_health
"feature" / "prioriti" / "request" → feature_prioritization
"churn" / "risk" / "attrition" → churn_risk
default (if just "report") → executive_summary
```

**Date Range Extraction** (reuse existing parameter extraction):
```python
"last 7 days" / "this week" → 7
"last 30 days" / "this month" → 30
"last 90 days" / "this quarter" / "quarterly" → 90
default → 30
```

---

## 7. Report Generation Pipeline

### Backend Service: `src/services/copilot/report_generator.py`

```python
class ReportGenerator:
    async def generate(
        self,
        org_id: int,
        report_type: str,      # executive_summary | customer_health | feature_prioritization | churn_risk
        date_range_days: int,   # 7 | 30 | 90
        db: Session,
        llm_client: LLMClient,
        stream_callback: Callable,  # sends streaming chunks
    ) -> Report:
```

**Pipeline**:
1. Query DB for relevant data based on report type + date range
2. For each section:
   a. Fetch section-specific data (SQL queries)
   b. Build LLM prompt with data context
   c. Stream LLM narrative generation → send chunks via `stream_callback`
   d. Generate chart data from SQL results
   e. Yield section as structured data
3. Assemble complete report
4. Save to DB (Report model)
5. Return report with all sections

### LLM Prompt Strategy

Each section gets its own focused prompt:

```
System: You are a data analyst writing a section of a feedback analysis report.
Write in a professional, concise tone. Use specific numbers from the data provided.
Do not make up data. If data is insufficient, say so.

User: Write the "{section_name}" section for an {report_type} report.
Date range: {start_date} to {end_date}
Organization: {org_name}

Data:
{formatted_data_tables}

Write 2-3 paragraphs summarizing the key findings.
Mention specific numbers, trends, and notable items.
```

---

## 8. Database Schema

### `reports` table

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| organization_id | Integer FK | organizations.id, CASCADE |
| created_by_user_id | Integer FK | users.id, SET NULL |
| conversation_id | Integer FK | conversations.id, SET NULL (if generated via copilot) |
| report_type | String(50) | executive_summary, customer_health, feature_prioritization, churn_risk |
| date_range_days | Integer | 7, 30, or 90 |
| title | String(500) | Auto-generated: "Executive Summary — Mar 1-17, 2026" |
| sections | JSON | Array of {heading, narrative, data, chart_type, chart_data} |
| metadata | JSON | {total_feedback, date_start, date_end, generated_at, model_used, tokens_used} |
| pdf_generated | Boolean | Default false, set true when PDF is generated |
| created_at | DateTime | |

Indexes: `(organization_id, created_at DESC)`, `(organization_id, report_type)`

### Section JSON Schema

```json
{
  "sections": [
    {
      "heading": "Sentiment Analysis",
      "narrative": "Over the past 30 days, sentiment has shifted notably...",
      "data": {
        "type": "table",
        "columns": ["Sentiment", "Count", "Percentage"],
        "rows": [["positive", 120, "40%"], ["neutral", 100, "33%"], ["negative", 80, "27%"]]
      },
      "chart": {
        "type": "line",
        "data": [{"date": "2026-03-01", "score": 0.45}, ...]
      }
    }
  ]
}
```

---

## 9. API Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/reports` | List org's saved reports | JWT, Business+ |
| GET | `/api/v1/reports/{id}` | Get report with sections | JWT, Business+ |
| DELETE | `/api/v1/reports/{id}` | Delete a report | JWT, Admin+ |
| GET | `/api/v1/reports/{id}/pdf` | Download report as PDF | JWT, Business+ |

Report generation itself happens via the Copilot WebSocket (not a REST endpoint).

---

## 10. WebSocket Integration

### New Message Type: `report`

**Server → Client**:

```json
{
  "type": "report_section",
  "message_id": "uuid",
  "report_id": 42,
  "section_index": 0,
  "section": {
    "heading": "Overview",
    "narrative": "Over the past 30 days...",
    "data": {...},
    "chart": {...}
  },
  "total_sections": 6,
  "done": false
}
```

Final message:
```json
{
  "type": "report_complete",
  "message_id": "uuid",
  "report_id": 42,
  "title": "Executive Summary — Feb 15 to Mar 17, 2026",
  "total_sections": 6,
  "pdf_available": true
}
```

---

## 11. PDF Generation

Reuse existing PDF export infrastructure (used for dashboard sharing).

**PDF Layout**:
- **Header**: Rereflect logo (top-left), report title (centered), date range (top-right)
- **Sections**: Each section as a block with heading, narrative paragraphs, data table, chart image
- **Charts**: Render Recharts to canvas → convert to image for PDF
- **Footer**: "Generated by Rereflect · {date} · Page X of Y"
- **Styling**: Match the Sunset Horizon theme colors for charts and accents

**Library**: Use existing PDF generation setup (check what's already used for dashboard PDF export).

---

## 12. Frontend Components

### Report Inline Preview (in Copilot chat)

When a report is streamed, it renders as a special message type in the ChatArea:

```tsx
<ReportPreview
  sections={sections}
  title={title}
  isStreaming={!done}
  reportId={reportId}
  onDownloadPDF={() => reportsAPI.downloadPDF(reportId)}
/>
```

Each section renders:
- Heading (h3)
- Narrative paragraphs (markdown)
- Data table (if present)
- Chart (Recharts component, if present)
- Divider between sections

"Download PDF" button fixed at the bottom of the report.

### My Reports Page (`/reports`)

- Table: Report Type (badge), Title, Date Range, Generated Date, Actions (View, Download PDF, Delete)
- Click row → expand inline preview (or navigate to detail page)
- Plan gate: Business+ only (show upgrade CTA for lower plans)

### Sidebar Navigation

Add "Reports" item under the existing Workspace collapsible section.

### Cmd+K Template Chips

Add 4 new static chips after the existing 8:
```typescript
{ label: "Executive summary this month", icon: FileBarChart },
{ label: "Customer health report", icon: HeartPulse },
{ label: "Feature request priorities", icon: Lightbulb },
{ label: "Churn risk analysis", icon: UserMinus },
```

---

## 13. Plan Gating

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| Report generation | - | - | Yes | Yes |
| Report types | - | - | All 4 | All 4 |
| Saved report history | - | - | Last 20 | Unlimited |
| PDF export | - | - | Yes | Yes |

Feature ID: `ai_reports`

When a non-Business user triggers a report intent in Copilot, respond with:
> "Report generation is available on the Business plan. Upgrade to generate comprehensive PDF reports from your feedback data."

---

## 14. Data Queries per Report Type

### Executive Summary Queries
1. `SELECT COUNT(*) FROM feedback_items WHERE org_id = :org AND created_at >= :start`
2. `SELECT sentiment_label, COUNT(*) FROM feedback_items WHERE ... GROUP BY sentiment_label`
3. `SELECT DATE(created_at), sentiment_label, COUNT(*) FROM ... GROUP BY 1, 2 ORDER BY 1` (trend)
4. `SELECT pain_point_category, COUNT(*) FROM ... WHERE pain_point_category IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 5`
5. `SELECT feature_request_category, COUNT(*) FROM ... WHERE feature_request_category IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 5`
6. `SELECT COUNT(*) FROM customer_health_scores WHERE org_id = :org AND risk_level IN ('at_risk', 'critical')`
7. `SELECT COUNT(*) FROM feedback_items WHERE org_id = :org AND is_urgent = true AND created_at >= :start`

### Customer Health Queries
1. `SELECT risk_level, COUNT(*) FROM customer_health_scores WHERE org_id = :org GROUP BY risk_level`
2. `SELECT email, health_score, risk_level, ... FROM customer_health_scores WHERE org_id = :org AND risk_level IN ('at_risk', 'critical') ORDER BY health_score ASC LIMIT 20`
3. `SELECT DATE(updated_at), AVG(health_score) FROM customer_health_scores WHERE ... GROUP BY 1 ORDER BY 1`

### Feature Prioritization Queries
1. `SELECT feature_request_category, COUNT(*), COUNT(DISTINCT customer_email) FROM feedback_items WHERE ... GROUP BY 1 ORDER BY 2 DESC`
2. `SELECT source, COUNT(*) FROM feedback_items WHERE feature_request_category IS NOT NULL AND ... GROUP BY 1`
3. `SELECT feature_request_priority, COUNT(*) FROM ... GROUP BY 1`

### Churn Risk Queries
1. `SELECT risk_level, COUNT(*) FROM customer_health_scores WHERE org_id = :org GROUP BY risk_level`
2. `SELECT email, health_score, churn_risk_score, ... FROM customer_health_scores WHERE org_id = :org ORDER BY health_score ASC LIMIT 10`
3. `SELECT DATE(updated_at), AVG(churn_risk_score) FROM ... GROUP BY 1`
4. `SELECT pain_point_category, AVG(churn_risk_score), COUNT(*) FROM feedback_items WHERE churn_risk_score > 50 AND ... GROUP BY 1 ORDER BY 2 DESC`

---

## 15. Implementation Phases

### Phase 1: Backend Report Generator (4-5 days)
- Alembic migration for `reports` table
- SQLAlchemy Report model
- `ReportGenerator` service with 4 report type implementations
- Data query functions per report type
- LLM prompt templates per section
- Report CRUD API endpoints (list, get, delete)
- Plan gating: `ai_reports` feature on Business+

### Phase 2: WebSocket Integration (2-3 days)
- Add `report` intent to intent classifier with regex patterns
- Report type + date range extraction from query
- Integrate `ReportGenerator` into WebSocket handler
- Stream sections progressively via `report_section` messages
- Send `report_complete` when done
- Save report to DB after generation
- Add 4 report system templates to template seeder

### Phase 3: Frontend (3-4 days)
- `ReportPreview` component for inline chat rendering
- Report section renderer (heading + narrative + table + chart)
- "Download PDF" button
- `/reports` page (My Reports list)
- Add 4 template chips to Cmd+K CommandBar
- Add "Reports" to sidebar navigation
- Plan gating UI (upgrade CTA for non-Business users)

### Phase 4: PDF Generation (1-2 days)
- PDF endpoint (`/api/v1/reports/{id}/pdf`)
- Branded PDF layout (logo, title, sections, charts, footer)
- Chart rendering to image (server-side or canvas-to-image)

---

## 16. Testing Strategy

- Backend: Report generator (data queries, section building, LLM prompts), CRUD endpoints, plan gating
- WebSocket: Report intent detection, section streaming, report completion
- Frontend: ReportPreview rendering, Cmd+K chips, My Reports page, PDF download
- Integration: End-to-end from Copilot query to saved report with PDF

---

## 17. Key Files (Expected)

### Backend
- `src/models/report.py` — SQLAlchemy model
- `src/services/copilot/report_generator.py` — Report generation logic
- `src/api/routes/reports.py` — CRUD + PDF endpoints
- `alembic/versions/xxx_add_reports_table.py` — Migration

### Frontend
- `components/copilot/ReportPreview.tsx` — Inline report renderer
- `app/(dashboard)/reports/page.tsx` — My Reports list
- `lib/api/reports.ts` — API client

### Modified Files
- `src/services/copilot/intent_classifier.py` — Add report intent
- `src/api/routes/copilot_ws.py` — Handle report generation
- `components/copilot/CommandBar.tsx` — Add 4 report chips
- `components/AppSidebar.tsx` — Add Reports nav item
- `src/config/plans.py` — Add `ai_reports` feature
