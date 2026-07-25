# PRD: Dashboard V2 — Customizable Analytics Grid

**Product**: Rereflect
**Author**: AI-assisted
**Date**: 2026-02-16
**Status**: Draft
**Priority**: High

---

## 1. Problem Statement

The current dashboard is a single long-scrolling page with ~10 sections that serves all user personas the same way. Key problems:

1. **Slow time-to-insight**: Users must scroll through 1200+ pixels of content to find what matters to them. A PM looking for feature request trends scrolls past churn risk data; a CS manager scrolls past pain point charts.
2. **Static snapshots, no trends**: Every metric shows a single point-in-time count (e.g., "42 total feedback") with no context on whether things are improving or worsening.
3. **No actionability**: Users see data but the dashboard doesn't guide them toward next steps. There are no recommended actions, no "compared to last period" context.
4. **One-size-fits-all**: A founder, PM, and CS manager all see the identical dashboard with no way to customize what they see first.

## 2. Goals & Success Metrics

### Goals
- Enable users to customize their dashboard layout per their role and priorities
- Add temporal context (trends, period comparisons) to every key metric
- Make the dashboard actionable with clear next-step guidance
- Reduce time-to-insight from "scroll and scan" to "glance and act"

### Success Metrics
| Metric | Current | Target |
|--------|---------|--------|
| Dashboard engagement (daily active views) | Baseline TBD | +30% |
| Time on dashboard page | ~45s (scroll-through) | ~90s (active engagement) |
| Click-through from dashboard to detail pages | ~15% | ~35% |
| User-customized layouts (% of users) | 0% | 40% within 30 days |

## 3. User Personas

| Persona | Primary Widgets | Secondary Widgets |
|---------|----------------|-------------------|
| **Product Manager** | Feature Requests, Pain Points by Category, Trend Lines, NPS Score | Sentiment Distribution, Top Categories |
| **Customer Success** | At-Risk Customers, Churn Risk, Urgent Feedback, Activity Feed | Sentiment Distribution, Team Activity |
| **Executive / Founder** | NPS Score, Sentiment Trend, Total Volume + Delta, Churn Summary | Pain Points (high-level), AI Insights |
| **Support Lead** | Urgent Feedback, Recent Activity Feed, Pain Points, Team Activity | Churn Risk, Sentiment |

Each persona will be able to configure their own layout via the drag-and-drop grid.

## 4. Feature Specification

### 4.1 Drag-and-Drop Customizable Grid

**Description**: Replace the current fixed-layout dashboard with a customizable widget grid system, inspired by Azure Dashboard tiles.

**Implementation**: `react-grid-layout` (battle-tested, used by Grafana, supports drag/resize/responsive breakpoints, built-in collision detection).

**Grid Specifications**:
- **Grid columns**: 12-column base grid
- **Row height**: 80px per grid unit
- **Widget sizes** (minimum → resizable):

| Widget Type | Min Size | Default Size | Max Size |
|-------------|----------|--------------|----------|
| Stat Card (single metric) | 2x2 | 3x2 | 4x2 |
| Donut/Pie Chart | 4x4 | 6x4 | 6x5 |
| Bar Chart | 4x4 | 6x4 | 12x5 |
| Trend Line Chart | 4x3 | 6x4 | 12x5 |
| List (Pain Points, etc.) | 4x3 | 6x4 | 6x8 |
| Activity Feed | 3x4 | 4x6 | 6x8 |
| NPS Score | 3x2 | 4x3 | 6x4 |
| Team Activity | 4x3 | 6x4 | 6x6 |
| AI Insights | 4x3 | 6x5 | 12x6 |

**Layout Persistence**:
- Stored **per-user** in a new `user_dashboard_layouts` table
- Schema: `{ user_id, layout_json, created_at, updated_at }`
- `layout_json` contains widget positions, sizes, and visibility state
- Falls back to a sensible default layout if no custom layout exists
- Save triggers: on drag-end, on resize-end (debounced 500ms)

**UI Controls**:
- **Edit mode toggle**: Button in top-right "Customize Dashboard" → enters edit mode with visible grid lines, drag handles, and resize handles
- **Add widget**: "+" button opens a widget catalog drawer/modal showing all available widgets with previews
- **Remove widget**: "X" button on each widget (only visible in edit mode)
- **Reset layout**: "Reset to Default" button in edit mode
- **Lock layout**: After customizing, user exits edit mode and layout is locked (no accidental drags)

**Responsive Breakpoints**:
- Desktop (≥1280px): 12 columns
- Tablet (≥768px): 6 columns (widgets reflow, maintain relative order)
- Mobile (<768px): 1 column stack (widgets full-width, ordered by priority)

### 4.2 Date Range Selector with Presets

**Description**: Replace the hardcoded "Last 30 days" with quick-select preset buttons.

**Presets**: `7d` | `14d` | `30d` | `90d` | `YTD`

**UI**: Pill/chip buttons in the dashboard header, next to the title. Active preset is highlighted with primary color.

**Backend Change**: The existing `days` query param already supports arbitrary values. For `YTD`, calculate days since Jan 1 of current year.

**State**: Stored in URL query param (`?range=30d`) and localStorage for persistence. Default: `30d`.

### 4.3 Period-over-Period Comparison (Delta Arrows)

**Description**: Every stat card shows a comparison against the equivalent previous period. If viewing "Last 30 days", compare to the 30 days before that.

**Display**:
```
Total Feedback    Positive          Negative
    42               16                12
  ↑ 12%           ↓ 5%             ↑ 23%
  vs prev 30d     vs prev 30d      vs prev 30d
```

- **Up arrow (green)**: Metric increased — green for positive metrics (total, positive), red for negative metrics (negative count, churn)
- **Down arrow (red/green)**: Context-aware coloring — a decrease in negative feedback is green (good), decrease in positive is red (bad)
- **Neutral (gray dash)**: No change or <1% difference

**Backend Change**: New endpoint or extend existing dashboard endpoint:
```
GET /api/v1/dashboard/?days=30&include_comparison=true
```

Returns additional `comparison` object:
```json
{
  "comparison": {
    "total_feedback_delta_pct": 12.5,
    "positive_delta_pct": -5.2,
    "neutral_delta_pct": 3.1,
    "negative_delta_pct": 23.0,
    "urgent_delta_pct": -10.0,
    "churn_high_delta_pct": 0.0,
    "pain_points_delta_pct": 8.3,
    "feature_requests_delta_pct": 15.0
  }
}
```

### 4.4 Trend Line Charts

**Description**: New widget showing metrics over time as line/area charts.

**Available Trends**:
1. **Feedback Volume Trend**: Total feedback count over time (area chart)
2. **Sentiment Trend**: Stacked area chart showing positive/neutral/negative over time
3. **Churn Risk Trend**: Average churn risk score over time (line chart)

**Granularity** (auto-adaptive):
| Date Range | Granularity |
|------------|-------------|
| 7d, 14d | Daily |
| 30d, 90d | Weekly |
| YTD | Monthly |

**Backend Change**: New endpoint:
```
GET /api/v1/dashboard/trends?days=30&metric=sentiment
```

Returns:
```json
{
  "metric": "sentiment",
  "granularity": "weekly",
  "data_points": [
    { "date": "2026-02-03", "positive": 5, "neutral": 3, "negative": 2 },
    { "date": "2026-02-10", "positive": 8, "neutral": 6, "negative": 4 },
    ...
  ]
}
```

Supported `metric` values: `volume`, `sentiment`, `churn_risk`

### 4.5 NPS / Satisfaction Score Widget

**Description**: A headline metric widget that provides a single "product health pulse" number.

**Important**: This is distinct from the existing Customer Health Score (which is per-customer). The NPS Score is a product-wide metric derived from feedback sentiment.

**Calculation** (simplified NPS-like score):
```
NPS = ((positive_count - negative_count) / total_count) * 100
```
- Range: -100 to +100
- Display: Large number with color coding
  - ≥ 50: Green (Excellent)
  - ≥ 20: Amber (Good)
  - ≥ 0: Orange (Needs Improvement)
  - < 0: Red (Critical)

**Widget Display**:
- Large NPS number centered
- Gauge/semicircle visual showing position on -100 to +100 scale
- Delta vs previous period
- Text label: "Excellent" / "Good" / "Needs Improvement" / "Critical"

**Note**: Full NPS implementation (with survey integration, 0-10 scale) is planned for a future milestone. This is a sentiment-derived proxy score.

**Backend Change**: Computed from existing sentiment data — no new endpoint needed. Frontend calculates from `sentiment` stats, or backend includes it in the dashboard response:
```json
{
  "nps_score": 42,
  "nps_label": "Good",
  "nps_delta_pct": 5.2
}
```

### 4.6 Recent Activity Feed Widget

**Description**: A real-time-ish feed of the latest activity in the organization.

**Feed Items** (in reverse chronological order):
- New feedback received (source: CSV import, Slack, API, manual)
- Feedback flagged as urgent
- Anomaly detected
- Churn risk spike for a customer
- Team member action (invited member, changed role)

**Polling**: Fetches new items every 30 seconds. Shows "Updated X seconds ago" badge.

**Display**:
- Scrollable list within the widget
- Each item: icon + description + relative timestamp ("2m ago", "1h ago")
- Max 20 items visible, "View All" links to a full activity log page (future)
- Color-coded left border by event type (red = urgent, amber = warning, green = positive, gray = info)

**Backend Change**: New endpoint:
```
GET /api/v1/activity-feed/?limit=20&since=<timestamp>
```

Returns:
```json
{
  "items": [
    {
      "id": 1,
      "type": "feedback_received",
      "title": "New feedback from john@acme.com",
      "subtitle": "Imported via CSV",
      "severity": "info",
      "created_at": "2026-02-16T02:30:00Z",
      "link": "/feedbacks/123"
    }
  ],
  "last_updated": "2026-02-16T02:38:00Z"
}
```

**Data Source**: Query from existing tables (feedback_items, anomalies, audit_logs, team_invites) ordered by created_at desc.

### 4.7 Team Activity Widget

**Description**: Shows which team members are most active and what they've been doing.

**Display**:
- List of team members with avatar/initials, name, last active
- Activity counts: feedbacks imported, feedback resolved, integrations configured
- Timeframe: matches the dashboard date range

**Backend Change**: New endpoint:
```
GET /api/v1/dashboard/team-activity?days=30
```

Aggregates from audit_logs and feedback import records.

### 4.8 Stat Card Improvements

**Description**: Enhance existing stat cards with delta indicators and mini sparklines.

**Changes**:
- Add delta percentage with directional arrow (from §4.3)
- Add tiny inline sparkline (last 7 data points) showing the trend direction
- Maintain clickability to filtered feedback list

### 4.9 Widget Catalog

**Description**: Full list of all available widgets that users can add to their dashboard.

| Widget ID | Name | Default Size | Category |
|-----------|------|--------------|----------|
| `stat-total-feedback` | Total Feedback | 3x2 | Overview |
| `stat-positive` | Positive Sentiment | 3x2 | Overview |
| `stat-neutral` | Neutral Sentiment | 3x2 | Overview |
| `stat-negative` | Negative Sentiment | 3x2 | Overview |
| `nps-score` | NPS Score | 4x3 | Overview |
| `sentiment-donut` | Sentiment Distribution | 6x4 | Charts |
| `pain-points-bar` | Pain Points by Category | 6x4 | Charts |
| `trend-volume` | Feedback Volume Trend | 6x4 | Charts |
| `trend-sentiment` | Sentiment Trend | 6x4 | Charts |
| `trend-churn` | Churn Risk Trend | 6x4 | Charts |
| `pain-points-list` | Pain Points List | 6x4 | Lists |
| `feature-requests-list` | Feature Requests List | 6x4 | Lists |
| `urgent-feedback` | Urgent Feedback | 6x4 | Lists |
| `top-categories` | Top Categories | 12x3 | Lists |
| `churn-risk-summary` | Churn Risk Overview | 6x4 | Risk |
| `at-risk-customers` | At-Risk Customers | 6x5 | Risk |
| `activity-feed` | Recent Activity | 4x6 | Activity |
| `team-activity` | Team Activity | 6x4 | Activity |
| `ai-insights` | AI Insights This Week | 6x5 | Intelligence |
| `anomaly-alerts` | Anomaly Alerts | 12x2 | Intelligence |

## 5. Default Layout

For new users (no saved layout), the default grid arrangement:

```
Row 1: [stat-total-feedback 3x2] [stat-positive 3x2] [stat-neutral 3x2] [stat-negative 3x2]
Row 2: [nps-score 4x3]           [sentiment-donut 4x3]                   [activity-feed 4x6 ↓]
Row 3: [trend-sentiment 8x4]                                             [activity-feed cont.]
Row 4: [pain-points-bar 6x4]     [feature-requests-list 6x4]
Row 5: [churn-risk-summary 6x4]  [urgent-feedback 6x4]
Row 6: [at-risk-customers 6x4]   [ai-insights 6x5]
Row 7: [top-categories 12x3]
Row 8: [team-activity 6x4]       [anomaly-alerts 6x2]
```

## 6. Technical Architecture

### Frontend

```
components/
  dashboard/
    DashboardGrid.tsx          # react-grid-layout wrapper + edit mode
    WidgetWrapper.tsx           # Generic widget container (header, resize handle, remove button)
    WidgetCatalog.tsx           # "Add Widget" drawer/modal
    DateRangeSelector.tsx       # Preset pill buttons
    widgets/
      StatCardWidget.tsx        # Enhanced stat card with delta + sparkline
      SentimentDonutWidget.tsx  # Existing donut, wrapped for grid
      PainPointsBarWidget.tsx   # Existing bar chart, wrapped
      TrendLineWidget.tsx       # New: line/area chart for trends
      NpsScoreWidget.tsx        # New: NPS gauge widget
      ActivityFeedWidget.tsx    # New: polling activity feed
      TeamActivityWidget.tsx    # New: team activity list
      PainPointsListWidget.tsx  # Existing pain points list, wrapped
      FeatureRequestsWidget.tsx # Existing feature requests, wrapped
      UrgentFeedbackWidget.tsx  # Existing urgent list, wrapped
      ChurnRiskWidget.tsx       # Existing churn risk, wrapped
      AtRiskCustomersWidget.tsx # Existing at-risk, wrapped
      AiInsightsWidget.tsx      # Existing AI insights, wrapped
      TopCategoriesWidget.tsx   # Existing top categories, wrapped
      AnomalyAlertsWidget.tsx   # Existing anomaly banners, wrapped
    hooks/
      useDashboardLayout.ts     # Layout persistence (save/load from API)
      useDateRange.ts           # Date range state + URL sync
      useDashboardData.ts       # React Query hooks for all dashboard data
      useActivityFeed.ts        # Polling hook for activity feed
    constants/
      widget-registry.ts        # Widget catalog: id, name, component, default size, min size
      default-layouts.ts        # Default layout configurations
```

### Backend (New Endpoints)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /api/v1/dashboard/` | GET | Existing — add `include_comparison` param |
| `GET /api/v1/dashboard/trends` | GET | New — time-series data for trend charts |
| `GET /api/v1/activity-feed/` | GET | New — recent activity feed |
| `GET /api/v1/dashboard/team-activity` | GET | New — team member activity stats |
| `GET /api/v1/user/dashboard-layout` | GET | New — fetch user's saved layout |
| `PUT /api/v1/user/dashboard-layout` | PUT | New — save user's layout |

### Database Changes

**New table: `user_dashboard_layouts`**
```sql
CREATE TABLE user_dashboard_layouts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    layout_json JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id)
);
```

**`layout_json` structure**:
```json
{
  "widgets": [
    { "id": "stat-total-feedback", "x": 0, "y": 0, "w": 3, "h": 2 },
    { "id": "nps-score", "x": 0, "y": 2, "w": 4, "h": 3 },
    ...
  ],
  "hidden_widgets": ["top-categories", "team-activity"],
  "version": 1
}
```

## 7. Implementation Phases

### Phase 1: Grid Infrastructure + Date Range (Week 1-2)
**Goal**: Dashboard renders in a customizable grid. All existing widgets work in the new layout.

- [ ] Install and configure `react-grid-layout`
- [ ] Create `DashboardGrid.tsx` with edit mode toggle
- [ ] Create `WidgetWrapper.tsx` (generic container with header/actions)
- [ ] Extract each existing dashboard section into its own widget component
- [ ] Create widget registry (`widget-registry.ts`) with size constraints
- [ ] Create default layout configuration
- [ ] Implement edit mode UI (grid lines, drag handles, resize handles, remove button)
- [ ] Implement `WidgetCatalog.tsx` (add widget drawer)
- [ ] Implement `DateRangeSelector.tsx` with preset buttons (7d, 14d, 30d, 90d, YTD)
- [ ] Create `user_dashboard_layouts` table + Alembic migration
- [ ] Create layout save/load API endpoints (`GET/PUT /api/v1/user/dashboard-layout`)
- [ ] Implement `useDashboardLayout.ts` hook (save on drag-end/resize-end, debounced)
- [ ] Wire date range to existing dashboard API `days` param
- [ ] Responsive breakpoints (12-col desktop, 6-col tablet, 1-col mobile)

**Deliverable**: Existing dashboard, same data, but now in a customizable drag-and-drop grid with date range presets.

### Phase 2: Period Comparison + Stat Card Enhancements (Week 3)
**Goal**: Every stat card shows delta vs previous period with directional arrows.

- [ ] Extend `GET /api/v1/dashboard/` with `include_comparison=true` param
- [ ] Backend: query previous period data and compute delta percentages
- [ ] Add `comparison` object to `DashboardResponse` schema
- [ ] Enhance `StatCardWidget.tsx` with delta arrow, percentage, and context-aware coloring
- [ ] Add mini sparkline to stat cards (last 7 data points from trend data)
- [ ] Frontend type updates for comparison data

**Deliverable**: Stat cards show "↑12% vs prev 30d" with smart color coding.

### Phase 3: Trend Line Charts (Week 4)
**Goal**: Users can see how metrics change over time.

- [ ] Create `GET /api/v1/dashboard/trends` endpoint
- [ ] Backend: aggregate feedback by day/week/month based on date range
- [ ] Support metrics: `volume`, `sentiment`, `churn_risk`
- [ ] Auto-adaptive granularity (daily for 7d/14d, weekly for 30d/90d, monthly for YTD)
- [ ] Create `TrendLineWidget.tsx` using Recharts area/line charts
- [ ] Three trend widgets: Feedback Volume, Sentiment Trend, Churn Risk Trend
- [ ] Register trend widgets in catalog with default sizes

**Deliverable**: Three new trend chart widgets available in the grid.

### Phase 4: NPS Score + Activity Feed + Team Activity (Week 5-6)
**Goal**: Complete the new widget set.

- [ ] Create `NpsScoreWidget.tsx` with gauge visual + delta
- [ ] Backend: compute NPS score from sentiment data, add to dashboard response
- [ ] Create `GET /api/v1/activity-feed/` endpoint (query from feedback_items, anomalies, audit_logs)
- [ ] Create `ActivityFeedWidget.tsx` with 30s polling via `useActivityFeed.ts`
- [ ] Activity feed items: new feedback, urgent flags, anomalies, team actions
- [ ] "Updated X seconds ago" badge
- [ ] Create `GET /api/v1/dashboard/team-activity` endpoint
- [ ] Create `TeamActivityWidget.tsx` with member list + activity counts
- [ ] Register all new widgets in catalog

**Deliverable**: NPS score, live activity feed, and team activity widgets available.

### Phase 5: Polish + Testing (Week 7)
**Goal**: Production-ready quality.

- [ ] Performance optimization (lazy-load widgets not in viewport)
- [ ] Loading skeletons for each widget type
- [ ] Error states per widget (one widget failing doesn't break the whole dashboard)
- [ ] Keyboard accessibility for grid editing
- [ ] Mobile layout testing and refinement
- [ ] Integration tests for new API endpoints
- [ ] Unit tests for NPS calculation, delta logic, granularity selection
- [ ] User acceptance testing

## 8. Dependencies & Risks

| Risk | Mitigation |
|------|-----------|
| `react-grid-layout` bundle size (~40KB gzipped) | Tree-shake, lazy-load grid only when edit mode is active |
| Layout migration if widget catalog changes | Version field in `layout_json`; migration script to handle schema changes |
| Polling activity feed at scale (many concurrent users) | 30s interval is conservative; Redis cache on the endpoint (5s TTL) |
| Complex responsive behavior with custom layouts | Separate layout configs per breakpoint stored in `layout_json` |
| Backend performance for comparison queries (double the queries) | Cache comparison data alongside main dashboard data (same 5min TTL) |

## 9. Out of Scope (Future Milestones)

- Full NPS survey integration (0-10 scale with Intercom/in-app surveys)
- TV / full-screen display mode
- Shared/team dashboard templates (preset layouts per role)
- Welcome/onboarding wizard for empty dashboards
- Custom date range picker (calendar UI)
- Real-time WebSocket updates (upgrade from polling)
- Dashboard export (PDF/PNG snapshot)
- Widget-level annotations/comments

## 10. Resolved Decisions

### Widget Plan Gating
**Decision**: Widgets follow their underlying feature's plan gate. If a user has access to the feature, they see the widget. If not, the widget shows a plan-upgrade prompt.

| Widget | Plan Gate | Rationale |
|--------|-----------|-----------|
| Stat Cards, Sentiment Donut, Pain Points, Feature Requests, Urgent, Top Categories, Anomaly Alerts | **All plans** | Core feedback analytics |
| NPS Score | **All plans** | Derived from sentiment (already available to all) |
| Trend Charts (volume, sentiment, churn) | **Pro+** | Maps to `trends_analytics` feature |
| At-Risk Customers | **Pro+** | Maps to `customer_health_scores` feature |
| AI Insights | **Pro+** | Maps to existing AI feature gate |
| Activity Feed | **All plans** | Core platform experience |
| Team Activity | **Pro+** | Maps to team management features |
| Churn Risk Summary | **Pro+** | Maps to `enhanced_churn_prediction` feature |

Widgets gated by plan show a locked state with "Upgrade to Pro to unlock" CTA instead of being hidden from the catalog.

### New Widget Discovery
**Decision**: Notification + manual add. When new widgets are released:
- A badge appears on the "Customize Dashboard" button: "2 new widgets available"
- The widget catalog drawer highlights new widgets with a "NEW" tag
- Users choose if and where to add them — existing layouts are never modified

### Mobile Edit Mode
**Decision**: Full edit mode on all devices. Touch-based drag and resize is supported:
- Drag: long-press to initiate (avoids accidental drags while scrolling)
- Resize: drag handle in bottom-right corner of each widget
- All the same controls as desktop (add, remove, reset layout)
- Widgets snap to single-column on mobile (<768px) but users can still reorder
