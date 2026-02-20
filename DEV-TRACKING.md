# Development Tracking

**Vision**: AI-powered feedback analysis SaaS
**Target**: $50K MRR in 12 months
**Last Updated**: 2026-02-20

---

## Current Status

| Milestone | Status | MRR Target |
|-----------|--------|------------|
| Phase 1: MVP SaaS | 100% Complete | $500 |
| Phase 2: Growth | Next | $5,000 |
| Phase 3: Enterprise | Planned | $50,000 |

---

## Phase 1: MVP SaaS (Months 1-3)

### Authentication & Multi-tenancy - COMPLETE
- [x] User authentication (email/password)
- [x] JWT token management
- [x] Organization model (tenant isolation)
- [x] Multi-tenant data scoping

### Dashboard & Analytics - COMPLETE
- [x] Main dashboard with charts
- [x] Sentiment overview widgets
- [x] Pain points list
- [x] Feature requests list
- [x] Urgent feedback alerts
- [x] Responsive design
- [x] Dashboard v2: Drag-and-drop widget grid (react-grid-layout v2)

### Feedback Management - COMPLETE
- [x] CSV import with parsing
- [x] Feedback list with pagination
- [x] Feedback detail view
- [x] Search and filtering
- [x] Category management

### Integrations - COMPLETE
- [x] Slack OAuth integration
- [x] Webhook support
- [x] Feedback sources management
- [x] Auto-refresh polling

### Team Management (RBAC) - COMPLETE
- [x] Role system (Owner/Admin/Member)
- [x] Team invitations with email (Resend)
- [x] Invite acceptance flow
- [x] Role changes
- [x] Member removal
- [x] Ownership transfer
- [x] Audit logging
- [x] Frontend tab visibility by role
- [x] Route protection
- [x] Conditional UI rendering

### Billing (Stripe) - COMPLETE
- [x] Subscription model
- [x] 4 tiers (Free/Pro/Business/Enterprise)
- [x] Stripe Checkout integration
- [x] Stripe Billing Portal
- [x] Usage tracking
- [x] Feature gating
- [x] Trial support (14 days)

### Quick Wins - COMPLETE
- [x] Email notifications for role changes
- [x] Email notifications for member removal
- [x] OAuth signup (Google Sign-In)

---

## Phase 2: Growth Features (Months 4-6)

**Goal**: 50 paying customers, $5K MRR

### Priority Order & Reasoning

| Priority | Feature Area | Why |
|----------|--------------|-----|
| **1st** | AI Enhancements | Core differentiator - why customers pay for Rereflect over spreadsheets |
| **2nd** | Notifications | Drives daily engagement and retention, surfaces urgent insights |
| **3rd** | Enhanced Analytics | Proves ROI to customers, enables data-driven decisions |
| **4th** | Feedback Workflow | Completes the feedback loop (analyze → act), focused scope |
| **5th** | Additional Integrations | Expands data sources, but not urgent for existing customers |

---

### 1. AI Enhancements (Priority: HIGH) - COMPLETE
> *Our differentiator - this is why customers choose Rereflect*

- [x] Auto-categorization (LLM-powered with custom categories)
- [x] Impact scoring / churn risk detection (displayed on feedback detail)
- [x] Anomaly detection (unusual spikes in negative sentiment)
- [x] Suggested actions (AI-generated weekly insights with actions)

### 2. Notifications (Priority: HIGH) - COMPLETE
> *Keeps users engaged and surfaces critical insights proactively*

- [x] Urgent feedback Slack alerts (outbound notifications)
- [x] Email digest (daily + weekly with configurable schedule)
- [x] Alert configuration UI (per-type thresholds, channels, retention)
- [x] In-app notification center (header bell popover + full page)
- [x] Notification detail page with metadata display
- [x] Dismiss/restore workflow
- [x] Per-type retention billing (30–365 days with Stripe metering)
- [x] Slack brand icon for channel settings
- [x] Replace all native HTML selects with shadcn components

### 3. Enhanced Analytics (Priority: MEDIUM) - COMPLETE
> *Proves ROI and enables data-driven product decisions*

- [x] Trends over time (sentiment/volume charts with date ranges)
- [x] Saved views and filters (quick access to common queries)
- [x] Export dashboard as PDF (for stakeholder reports)
- [x] Dashboard sharing (public link for read-only access)

### 4. Feedback Workflow (Priority: MEDIUM) - COMPLETE
> *Completes the feedback loop: collect → analyze → ACT. Focused scope, not project management.*

- [x] Status tracking (New → In Review → Resolved → Closed) with free-form transitions
- [x] Feedback assignment (route to team member) with bulk assign/unassign
- [x] Internal notes (markdown, author-only edit/delete)
- [x] Workflow overview page (`/workflow`) with kanban (drag-and-drop) and table views
- [x] Timeline log on feedback detail page (status changes, assignments, notes)
- [x] Bulk actions (multi-select for status change + assign)
- [x] Auto-assignment engine (category-based rules + round-robin fallback)
- [x] Assignment rules management (`/settings/workflow`)
- [x] 3 new notification types (feedback_assigned, status_changed, note_added)
- [x] Status + Assignee columns on feedbacks list with filters

**Deliberately excluded** (not aligned with core value):
- ~~Comments on feedback items~~ (turns app into Slack)
- ~~@mentions~~ (not a project management tool)
- ~~Activity feed~~ (nice-to-have, not essential)

### 5. Additional Integrations (Priority: LOW)
> *Expands feedback sources, but existing customers can use CSV/Slack*

- [x] Intercom API (pull support conversations)
- [x] Email forwarding (receive feedback via email)
- [ ] Zendesk API (pull support tickets)
- [ ] HubSpot integration (sync with CRM)

---

## Phase 3: Enterprise (Months 7-12)

**Goal**: 10 enterprise customers, $50K MRR

### Security & Compliance
- [ ] SSO/SAML (Okta, Azure AD, Google Workspace)
- [ ] Advanced RBAC (custom roles)
- [ ] Data residency (US/EU/APAC)
- [ ] SOC 2 Type II certification
- [ ] GDPR compliance tools
- [ ] IP whitelisting

### Enterprise Features
- [ ] Custom AI models (train on your data)
- [ ] White-labeling (custom domain, branding)
- [ ] Custom data retention policies
- [ ] SLA guarantees (99.99% uptime)
- [ ] Dedicated support

### Workflow Automation
- [ ] JIRA integration
- [ ] Linear integration
- [ ] Asana integration
- [ ] Custom webhooks (trigger on events)
- [ ] Auto-routing rules

### Predictive Analytics — COMPLETE
- [x] Improved churn prediction (9-factor: sentiment, urgency, churn keywords, frustration keywords, sentiment trend, feedback frequency, resolution time, pain severity, feature request density)
- [x] Customer health score (weighted aggregate: churn_risk 35%, sentiment 25%, resolution 25%, frequency 15%)
- [x] Customer health dashboard widget (top 5 at-risk, expandable with LLM analysis)
- [x] Weekly LLM churn insights (GPT-4 deep-dive for customers with health_score < 40, Celery Beat Mondays 7AM)
- [x] Plan gating (enhanced_churn_prediction, customer_health_scores, churn_llm_insights → Pro+)
- [x] Feedbacks filterable by customer_email (from dashboard widget click-through)
- [x] Cache invalidation on all feedback mutation paths (create, delete, update, CSV import, approve pending, integration sync, source events)
- [x] Customer 360 page (`/customers` list + `/customers/[email]` profile)
- [x] Enhanced AI Analysis System (structured JSON storage, 3-tier analysis, interactive action items)
- [ ] Feature impact prediction — deferred (requires longitudinal data)
- [ ] Customer lifetime value estimation — deferred (requires Stripe customer mapping)
- [ ] Revenue impact scoring — deferred (depends on CLV)

---

## Technical Debt

- [x] Add comprehensive test coverage (billing/Stripe tests + Vitest frontend setup)
- [x] Performance optimization (Redis server-side caching + React Query client-side caching)
- [x] Database query optimization (4 indexes, eager loading, SQL tag aggregation)
- [ ] Error tracking (Sentry) — deferred (cost)
- [ ] Monitoring dashboard (DataDog) — deferred (cost)

---

## Success Metrics

### Phase 1 Targets
- [x] 100 signups
- [x] 10 paying customers
- [x] < 3s page load
- [x] 99%+ uptime

### Phase 2 Targets
- [ ] 500 signups
- [ ] 50 paying customers
- [ ] $5,000 MRR
- [ ] < 5% monthly churn
- [ ] NPS > 40

### Phase 3 Targets
- [ ] 5,000 signups
- [ ] 500 paying customers
- [ ] 10 enterprise customers
- [ ] $50,000 MRR
- [ ] SOC 2 certified

---

### 0. Public Changelog - COMPLETE
> *Transparency and trust — show customers what's shipping*

- [x] Public changelog page (`/changelog`) with category + date range filters
- [x] Auto-sync from git commits via GitHub API on every deploy (idempotent)
- [x] Admin management UI (`/system/changelog`) for system admins
- [x] Server-side pagination (20 per batch, "Load more")
- [x] Conventional commit parsing (feat/fix/chore/refactor/breaking)

---

## Recent Completions (Feb 2026)

- **Predictive Analytics** (4 phases, PRD-PREDICTIVE-ANALYTICS.md):
  - Phase 1 — Enhanced Churn Scoring: `customer_email` column + index on feedback_items, email extraction from source_metadata + CSV import + all adapters, 9-factor churn risk scoring (up from 4), backfill script for existing data
  - Phase 2 — Customer Health Score: `CustomerHealth` model with 3 indexes, `health_score_service.py` (4-component weighted scoring), health recomputation after each analysis, dashboard API returns top 5 at-risk customers, expandable dashboard widget with score badges + component breakdown + LLM analysis
  - Phase 3 — Weekly LLM Deep-Dive: `generate_churn_insights` Celery task, `CHURN_ANALYSIS_PROMPT` for GPT-4, Celery Beat schedule (Mondays 7AM UTC), stores `llm_analysis` on CustomerHealth records
  - Phase 4 — Plan Gating & Integration: 3 feature IDs (enhanced_churn_prediction, customer_health_scores, churn_llm_insights) gated to Pro+, `customer_email` filter on feedbacks list endpoint, dashboard widget click-through to filtered feedbacks
  - Comprehensive cache invalidation audit: all 11 feedback mutation points now invalidate `dashboard:*` + `analytics:*` cache keys (backend routes + worker tasks)
  - Diverse sample CSV: 1000 rows, 50 unique customers across 4 risk profiles, all categories represented
  - Alembic migrations: customer_email column, customer_health_scores table
- **Feedback Workflow** (6 phases):
  - DB schema: workflow_status + assigned_to on feedback_items, FeedbackNote, FeedbackWorkflowEvent, AssignmentRule models
  - 14+ workflow API endpoints (status change, assign, overview, timeline, notes CRUD, assignment rules, auto-assign)
  - Feedback detail page workflow section with status dropdown, assignee selector, notes, timeline
  - Workflow overview page (`/workflow`) with kanban drag-and-drop + table view toggle
  - Bulk actions bar for multi-select status change and assignment
  - Auto-assignment engine: category-based rules (priority ordered) + round-robin fallback (fewest open items)
  - Assignment rules settings page (`/settings/workflow`) with auto-assignment toggle
  - 3 new notification types: feedback_assigned, status_changed, note_added (targeted per-user)
  - Status + Assignee columns on feedbacks list with filter dropdowns
  - Sidebar navigation: Workflow page + Workflow settings
- **Enhanced Analytics** (5 phases):
  - Analytics trends API with 7d/30d/90d date ranges and auto granularity (daily/weekly)
  - Analytics page with Metric Trends (line chart, dropdown metric selector), Feedback Volume (bar chart), Distribution (donut with Sentiment/Source tabs), Top Insights (table with column-aligned headers)
  - Saved views (org-wide tab bar, plan-gated limits)
  - PDF export with theme-aware colors (oklch support via browser color resolution)
  - Dashboard sharing: token-based public links with optional password, expiration (24h/7d/30d/never), view counts
  - Public shared view page (`/shared/[token]`) mirroring full analytics layout
  - Shared links management page (`/shared-links`) with pagination, status filters, deactivation
  - Plan gating: Free=7d only, Pro+ gets 30d/90d/export/sharing
  - Volume spike notification deduplication (24h cooldown, re-alert only on >20% count increase)
- **Full notification system** (10 phases):
  - DB models, migrations, and alert preferences
  - Notification API (list, detail, mark read, dismiss, restore, preferences, retention)
  - Alert dispatch engine (urgent feedback, sentiment spike, churn risk, volume spike)
  - Daily + weekly email digests with per-user scheduling (hourly Celery Beat)
  - Per-type retention billing with Stripe metered usage
  - Alert preferences UI (per-type thresholds, email/Slack/in-app channels)
  - Header bell popover (5 recent, 30s polling for unread count)
  - Full notifications page (`/notifications`) with type filters, pagination, dismissed view
  - Notification detail page (`/notifications/[id]`) with metadata, dismiss/restore
  - Slack brand SVG icon for channel settings
  - Replaced all native `<select>` elements with shadcn Select components
  - Hidden number input spinners globally via CSS
  - Sidebar restructured: Settings as nested group, System section moved to end
- Public changelog with auto-sync from GitHub API on deploy
- Admin changelog management (edit/hide/delete entries)
- AI enhancements: auto-categorization, anomaly detection, suggested actions, churn risk
- Weekly email digest with opt-in/out preferences
- Redis distributed lock for worker deduplication
- Churn risk display on feedback detail page
- Full RBAC implementation with frontend/backend enforcement
- Tab visibility filtering by role
- Route protection for billing/integrations pages
- Ownership transfer with confirmation
- Audit logging for team actions
- Documentation consolidation
- Google Sign-In OAuth integration
- Email notifications for role changes
- Email notifications for member removal
- Resend template management script
- **Landing Page Separation** (pnpm workspaces monorepo):
  - Decoupled SEO-optimized landing page from authenticated dashboard
  - Created `packages/ui` shared UI package with Logo, Select, theme, utilities
  - New `services/landing-web` with Next.js 15 static export + nginx serving
  - Updated `services/frontend-web` for standalone builds with workspace dependencies
  - Railway deployment configuration with dynamic port handling
  - Local dev: landing on port 3001, app on port 3000
- **System Admin Management** (Users + Organizations):
  - Admin Users page (`/system/users`): list/search/filter by org, edit (org transfer, role, system admin toggle), delete with full FK cleanup (12+ related tables)
  - Admin Organizations page (`/system/organizations`): list/search, detail dialog with member list, delete empty orgs (cleans up 20 related tables)
  - Shared `user_service.py` for user deletion cleanup (used by both team.py and admin_users.py)
  - FK constraint migration: 5 columns made nullable, ondelete SET NULL/CASCADE added across 11 models
  - Dynamic FK constraint name lookup via `information_schema` (handles mixed naming conventions)
  - Auto-migration on deploy: Dockerfile runs `alembic upgrade head` before uvicorn
- **Auto-refresh polling** added to workflow page and feedback detail page (30s interval)
- **Email Forwarding Integration**:
  - Resend inbound webhook endpoint (`/api/v1/webhooks/email/inbound`) with signature verification
  - Email parser: strips forwarding headers (Apple Mail, Gmail, Outlook, Thunderbird), extracts original sender/subject/body
  - Lazy body fetching from Resend API (webhook only sends metadata)
  - EmailAdapter in worker-service: check_triggers (all_emails, specific_senders, keyword_match), extract_content (HTML→text), fetch_context
  - Feedback source type: `email` with `all_emails` trigger
  - Frontend: email source type in feedback sources wizard (new, detail, list pages)
  - Redis connection fix for webhook → Celery task queuing (REDIS_HOST/PORT/PASSWORD env vars)
  - Comprehensive tests: email parser (Apple Mail, Gmail, Outlook headers), webhook endpoint, adapter
- **Changelog Sync Fix**: Fixed GITHUB_TOKEN env var (had literal `"` prefix breaking all GitHub API calls), added `.strip()` resilience for quoted env vars
- **Intercom Integration** (TDD, 50 tests):
  - OAuth flow: connect + callback endpoints with state management
  - Webhook receiver: HMAC-SHA1 signature verification, 3 topics (conversation.user.created, conversation.user.replied, conversation.rating.added)
  - IntercomAdapter: check_triggers (all_conversations, new_conversations, replies, ratings, keywords), extract_content (HTML stripping), get_external_ids, fetch_context
  - Write-back service: add_note_to_conversation, close_conversation (two-way sync)
  - Plan gating: `intercom_integration` feature on Pro+ (same as Slack)
  - Frontend: Intercom in Available Integrations, OAuth connect flow, integration type icons
  - 23 backend tests + 27 worker adapter tests (all passing)
  - **Feedback Sources**: Intercom as selectable source type in feedback sources wizard
    - Backend: `/types` endpoint, valid_types, feature gating, integration validation, workspace_id/workspace_name copying
    - Frontend: Intercom icon/color across all 4 feedback source pages (list, new, detail, pending)
    - Frontend: Dynamic integration selection step (no longer hardcoded to Slack)
    - Worker: Source matching by workspace_id via Integration (same pattern as Slack's team_id)
    - Webhook: Extract app_id from Intercom payload as workspace_id for source matching
- **Dashboard v2 — Customizable Widget Grid**:
  - Drag-and-drop grid layout with react-grid-layout v2 (12/6/1-col responsive breakpoints)
  - 20 widgets across 6 categories: Overview (stat cards, NPS gauge), Charts (sentiment donut, pain points bar, 3 trend lines), Lists (pain points, feature requests, urgent feedback, top categories), Risk (churn summary, at-risk customers), Activity (activity feed, team activity), Intelligence (AI insights, anomaly alerts)
  - Widget registry with definitions (min/max/default sizes, plan gating, icons)
  - Widget catalog drawer for add/remove in edit mode
  - Per-user layout persistence (all 3 breakpoints saved to server via `UserDashboardLayout` model)
  - Debounced save with flush-on-exit (500ms debounce, immediate flush when clicking "Done")
  - Layout reset to defaults (DELETE endpoint)
  - v2 server format: saves lg/md/sm layouts (fixes breakpoint-aware persistence)
  - Activity feed backend endpoint (synthesized from recent feedback by severity)
  - Fixed sentiment trend data (backend `data` field aligned with frontend)
  - Empty state placeholders on all widgets (icons + descriptive messages)
  - NPS gauge widget with semicircle SVG, score color coding, delta badge, description
  - Anomaly alerts as read-only history widget with relative timestamps
  - Top categories with CSS grid auto-fill (responsive card layout, min 180px)
  - Alembic migration: `user_dashboard_layouts` table
- **Customer 360 — Customer List & Profile Pages** (PRD-CUSTOMER-360.md):
  - Customer list page (`/customers`): sortable DataTable with health score, risk level, confidence, trend, feedback count, last active; server-side pagination/search/filter; risk distribution bar; stat cards; free plan blur gating
  - Customer profile page (`/customers/[email]`): health score overview, 4-component progress bars (churn risk, sentiment, resolution, frequency) with shadcn tooltips, health score history chart, activity timeline, recent feedbacks list, AI analysis section
  - Health score history: `CustomerHealthHistory` model with daily snapshots, backfill script, Recharts line chart with time range selector (7d/30d/90d)
  - Activity timeline: synthesized from feedback creation, status changes, health score changes, LLM analysis, action completions
  - Customer link on feedback detail page (clickable email → customer profile)
  - Sidebar navigation: Customers page with Users icon
  - Backend: full customers API (`/api/v1/customers/`) with list, profile, activity, analyze, batch-analyze endpoints
  - Alembic migrations: customer_health_scores new columns, customer_health_history table
  - 11 backend tests + 8 frontend tests (Vitest + React Testing Library)
- **Enhanced AI Analysis System** (PRD plan, 5 phases):
  - Phase 1 — Schema: `llm_analysis_data` (JSON) + `llm_raw_response` (JSON) columns on customer_health_scores, `customer_analysis_actions` table with audit trail, data migration from pipe-separated text to structured JSON
  - Phase 2 — Worker: 3-tier analysis prompts (churn_risk for <40, retention for 40-69, growth_opportunity for 70+), structured JSON storage, action item creation, immediate urgency alert dispatch
  - Phase 3 — Tiered Schedule: at-risk weekly (Mon 7AM), moderate bi-weekly (Mon 7:15AM), healthy monthly (Mon 7:30AM)
  - Phase 4 — API: structured response fields, `PATCH /actions/{id}` endpoint for action CRUD, 24h re-analyze cooldown, system admin gated batch-analyze, activity timeline includes action completions
  - Phase 5 — Frontend: risk-adaptive AI card styling (red/amber/green by analysis type), interactive action checklist (Business+), read-only analysis (Pro), risk driver badges, urgency indicator, "Re-analyze All" button (system admin), dashboard widget updated for structured display
  - Plan gating: `ai_analysis_actions` feature on Business+ plans
  - Breadcrumb fix: layout handles `/customers/*` routes, removed duplicate page-level breadcrumb
- **Technical Debt Resolution** (4 phases):
  - Phase 1 — DB Query Optimization: 4 compound indexes (org+sentiment, org+urgent, org+pain_cat, org+feature_cat), SQLAlchemy relationships for eager loading (feedback_source, assigned_user), SQL-level tag aggregation with json_array_elements_text (Python fallback for SQLite), SQL_ECHO env var
  - Phase 2 — Server Caching: Redis cache service (DB 2, lazy init, graceful fallback), dashboard caching (5min TTL), analytics caching (10min TTL), cache invalidation on feedback create/analyze/status-change, HTTP Cache-Control headers on read endpoints
  - Phase 3 — Client Caching: React Query (TanStack Query v5) with QueryProvider, dashboard/feedbacks/workflow pages migrated to useQuery, refetchInterval replaces setInterval polling, refetchIntervalInBackground: false
  - Phase 4 — Test Coverage: Billing/Stripe test suite (test_billing.py, 15+ test cases covering checkout, webhooks, portal, usage limits, feature gating), Vitest configured with jsdom + @testing-library/react, StatCard + ThemeContext tests, frontend test scripts (npm run test/test:watch/test:coverage)
  - Alembic migration: 9232cfa0634d_add_critical_feedback_indexes
  - PRD: PRD-TECHNICAL-DEBT.md
- **Customer Sentiment Alerts** (M1.3, PRD-CUSTOMER-SENTIMENT-ALERTS.md):
  - New alert type `customer_health_drop` with 3 trigger conditions: threshold crossing (score < 50), point drop (≥ 15pts), risk level downgrade
  - Recovery alerts on risk level upgrades (green positive notifications)
  - `dispatch_health_drop_alert()` in worker-service with Redis 24h dedup per customer, risk level changes bypass cooldown
  - Auto-triggers LLM analysis when health drop detected and analysis is stale (>24h)
  - Preferences API: dual thresholds (`threshold_value` + `drop_threshold`) per user, validation (1-99 / 5-50)
  - Slack Block Kit card with score change, risk level badge, top risk drivers, Customer 360 CTA button
  - Email via existing daily digest pipeline (no new Resend template)
  - Frontend: alert preferences row with dual threshold inputs, notification list/bell/detail with red (drop) / green (recovery) styling, score change display, risk badges, component breakdown
  - Plan gated to Pro+ (reuses `customer_health_scores` feature)
  - 90 TDD tests across 5 test files (backend alerts, preferences API, worker dispatch, frontend preferences UI, notification display)

---

## Decisions Made

- Using Resend for transactional emails (with template management script)
- Stripe for all billing
- Railway for hosting
- Google OAuth via access token flow (full-width custom button)
- Phase 2 prioritizes AI/Notifications over Integrations (differentiator focus)
- Collaboration features scoped down to "Feedback Workflow" (status, assignment, notes only)
- Excluded @mentions, comments, activity feed (avoids becoming project management tool)
- Changelog auto-syncs via GitHub API at startup (idempotent, strips quoted env vars for resilience)
- `is_system_admin` boolean on User model for system-level access (separate from org roles)
- Notification bell in header (not sidebar) with Radix popover for quick access
- Per-type retention billing: each alert type has independent retention days, Stripe billed on total extra days
- Digest scheduling: hourly Celery Beat, tasks filter users by preferred hour/day (no per-user cron)
- Workflow notifications: direct DB insert from backend-api (no Celery round-trip for simple notification creation)
- Workflow permissions: all roles (Owner/Admin/Member) can do everything; all plans have access
- Auto-assignment: category rules checked first (by priority desc), round-robin fallback (member with fewest open items)
- Landing page separated into standalone service for independent SEO optimization and deployment
- Monorepo architecture with pnpm workspaces for shared UI components and dependencies
- Auto-refresh polling (30s) on workflow and feedback detail pages for real-time collaboration
- Intercom integration follows same pattern as Slack: OAuth flow, adapter, webhook receiver, Pro+ gating, HMAC-SHA1 verification, two-way sync (notes + close)
- Email forwarding: Resend inbound webhooks, lazy body fetch from API, parser strips forwarding headers from all major mail clients
- Technical debt: Sentry skipped due to $29/mo cost, deferred until paying customers cover it
- Predictive analytics: hybrid approach — algorithmic scoring for real-time + weekly GPT-4 for at-risk customers (cost-effective)
- Customer health score: churn-heavy weights (35% churn, 25% sentiment, 25% resolution, 15% frequency)
- Health score recomputation: inline after each analysis task (not a separate Celery task — fast enough)
- LLM churn insights: capped at customers with health_score < 40, Monday 7AM UTC (before weekly digest at 8:30AM)
- Customer 360: separate list page + profile page (not inline dashboard expansion), server-side pagination for scalability
- Enhanced AI Analysis: structured JSON column (not separate table) for analysis data, legacy `llm_analysis` kept during transition period
- Three-tier analysis: different prompts per health tier (churn_risk/retention/growth_opportunity), tiered scheduling to balance API costs
- Action items: reset on re-analysis (archive old pending, create new), Business+ only for interactivity
- On-demand analysis: 1 feedback minimum (batch/scheduled requires 2), 24h cooldown on re-analyze
- Feature impact prediction / CLV / revenue scoring deferred — insufficient data currently
- Worker-service cache invalidation: lightweight cache.py utility connecting to Redis DB 2 (same as backend-api cache_service)
- Redis cache uses DB 2 (DB 0=Celery, DB 1=sessions, DB 2=cache, DB 3=rate limiting)
- React Query (TanStack Query v5) with staleTime 5min, gcTime 30min for client-side caching
- Vitest + @testing-library/react for frontend unit tests
- Customer sentiment alerts: 3 trigger conditions (threshold + drop + risk change), recovery alerts on risk upgrade, 24h Redis dedup bypassed for risk transitions
- Health drop email: daily digest pipeline (no dedicated template), consistent with existing alert email pattern
- Health drop dedup: Redis DB 2 key `health_alert_cooldown:{org_id}:{email}` with 86400s TTL, re-alerts only if score dropped further

---

## Related

- [SALES-TRACKING.md](SALES-TRACKING.md) - Sales strategy and growth metrics
