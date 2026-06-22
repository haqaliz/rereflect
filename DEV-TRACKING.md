# Development Tracking

**Vision**: AI-powered feedback analysis SaaS
**Target**: $50K MRR in 12 months
**Last Updated**: 2026-05-21

---

## Current Status

| Milestone | Status | MRR Target |
|-----------|--------|------------|
| Phase 1: MVP SaaS | 100% Complete | $500 |
| Phase 2: Growth | Next | $5,000 |
| Phase 3: Enterprise | Planned | $50,000 |

---

## ⚠️ Open-Source Self-Hosted Pivot (2026-06)

Rereflect pivoted to **free, open-source, self-hosted (MIT, BYOK)**. The SaaS/MRR framing and plan-gating below are **stale** — every feature is unlocked. See `PRD-OSS-SELF-HOSTED-PIVOT.md`.

**Open-Source Feature Batch — shipped 2026-06-22** (`PRD-LOCAL-LLM-CUSTOM-AI-PUBLIC-API.md`):
- ✅ **Local / Offline LLM** — Ollama / any OpenAI-compatible endpoint, keyless; VADER fallback with no model.
- ✅ **Custom AI** — custom pain-point/feature-request/urgency taxonomies + configurable health-score weights.
- ✅ **Public REST API** — API keys (read/ingest), reads + feedback ingestion + webhooks + OpenAPI docs.

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
- [x] Linear integration (OAuth, webhooks, feedback sources, issue management)
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
- [x] GDPR compliance tools
- [ ] IP whitelisting

### Enterprise Features
- [ ] Custom AI models (train on your data)
- [ ] White-labeling (custom domain, branding)
- [ ] Custom data retention policies
- [ ] SLA guarantees (99.99% uptime)
- [ ] Dedicated support

### Workflow Automation
- [ ] JIRA integration
- [x] Linear integration
- [ ] Asana integration
- [x] Custom webhooks (trigger on events)
- [x] Auto-routing rules

### M3.2 — JIRA Integration (2-3 weeks)
- [ ] JIRA OAuth flow (connect/disconnect via Atlassian OAuth 2.0)
- [ ] JIRA API client: projects, issue types, priorities, labels, users
- [ ] Create issue from feedback: team/project/priority selection (reuse Create Issue page)
- [ ] Webhook receiver: issue status sync back to Rereflect
- [ ] Feedback source type: `jira` (pull comments from JIRA issues)
- [ ] Plan gate: Pro+ (same as Linear)

### M3.3 — Asana Integration (2 weeks)
- [ ] Asana OAuth flow
- [ ] Asana API client: workspaces, projects, tasks
- [ ] Create task from feedback: workspace/project selection
- [ ] Plan gate: Pro+

### M3.4 — Zendesk Integration (2 weeks)
- [ ] Zendesk OAuth flow
- [ ] Zendesk API client: tickets, comments, users
- [ ] Feedback source type: `zendesk` (pull ticket data as feedback)
- [ ] Plan gate: Pro+

### M3.5 — HubSpot CRM Integration (3 weeks)
- [ ] HubSpot OAuth flow
- [ ] Sync contacts: company, deal stage, ARR, renewal date
- [ ] Match by email: link HubSpot contacts to Rereflect customers
- [ ] Customer 360 enrichment: CRM data on customer profile
- [ ] Plan gate: Business+

### M3.6 — SSO/SAML (3 weeks)
- [ ] SAML 2.0 SSP integration (Okta, Azure AD, Google Workspace)
- [ ] Auto-provisioning: create users on first SSO login
- [ ] Settings page: SSO configuration (Entity ID, ACS URL, certificate)
- [ ] Plan gate: Enterprise only

### M3.7 — Advanced RBAC & GDPR (2 weeks) — GDPR COMPLETE
- [ ] Custom roles with granular permissions
- [x] GDPR data export: user can export all their data as ZIP (JSON+CSV)
- [x] GDPR data deletion: user can request full account + data deletion (30-day grace period, deactivation, cancel flow)
- [x] Auth middleware blocks deactivated users
- [x] GDPR purge background task
- [x] Settings > Preferences: Export/Delete buttons with shadcn Dialog
- [x] Landing page: GDPR badge, Privacy Policy update, 2 FAQ entries, Bento card
- [x] 7 backend tests
- [ ] Plan gate: Enterprise (RBAC), all plans (GDPR)

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
- [x] Error tracking (Sentry) — COMPLETE (free tier across all 3 services)
- [x] Monitoring dashboard — COMPLETE (health endpoint: /health/detailed)

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

## Recent Completions (Feb–May 2026)

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
- **Churn Prediction Accuracy** (M1.4):
  - Factor breakdown component (`ChurnFactorBreakdown.tsx`): shadcn Collapsible with 9 factors sorted by score, color-coded progress bars (red >75%, orange 40-75%, green <40%), Pro+ plan gating with upgrade CTA
  - Confidence score on customer health scores: `confidence_score` column on `customer_health_scores`, computed from feedback count + data recency + analysis coverage
  - Backtest validation script (`scripts/backtest_churn.py`): evaluates prediction accuracy against historical churn data
  - `churn_risk_factors` JSON column on `feedback_items`: 9-factor breakdown (sentiment, churn_keywords, frustration_keywords, urgency, sentiment_trend, feedback_frequency, resolution_time, pain_severity, feature_density)
  - Worker-service model fix: added missing `churn_risk_factors` column to worker's `FeedbackItem` model (was silently not persisting)
  - Backfill script for 1000 existing analyzed feedback items
  - Alembic migration: `6e4501930bf0` (confidence_score + churn_risk_factors columns)
  - 11 frontend tests (ChurnFactorBreakdown: collapse/expand, sorting, colors, plan gating, null state)
  - Feedback detail page: URL-synced tabs (`?tab=overview|analysis|timeline`), manual refresh button replacing 30s polling
  - Deployed to production (Railway): backend-api + worker-service
- **Multi-Model Support** (M2.1, PRD-MULTI-MODEL-SUPPORT.md):
  - LLM abstraction layer: unified `LLMClient` with provider factory (OpenAI, Anthropic, Google)
  - Per-org model selection: configurable default provider + model per task type (categorization, analysis, insights)
  - BYOK key management: Fernet-encrypted API key storage per provider, add/remove/validate endpoints
  - Fallback chain: primary → retry → system OpenAI fallback with automatic provider rotation
  - Plan gating: Free = GPT-4o-mini only, Pro = all OpenAI models, Business+ = all providers (Anthropic, Google)
  - Budget tracking: per-org monthly usage limits with provider-level cost breakdown
  - Model registry: admin-managed model catalog with tier badges (cheap/mid/premium), pricing, availability
  - Backend: 8 new API endpoints (keys CRUD, model list, model test, usage, budget), 4 new DB models (OrgAIConfig, OrgAPIKey, LLMModelPrice, LLMUsageLog), Alembic migration
  - Worker: LLM factory with provider-specific clients, org config resolver, usage logging, pricing calculation
  - Frontend: AI Settings page (3 tabs: General, Providers, Usage), model selector with tier badges, BYOK key management UI, usage charts, budget banner
  - Admin: AI Models registry page (`/system/ai-models`) with pricing sync, availability toggles
  - SVG tier badge icons replacing emoji indicators, legend labels on model selection
  - 94 worker TDD tests + 8 backend tests + 54 frontend tests (all passing)
- **AI Copilot: Command Bar** (M2.2, PRD-AI-COPILOT.md):
  - Cmd+K spotlight modal: search input, 8 static template chips, dynamic AI suggestions, keyboard navigation, plan gating display
  - Conversations page (`/conversations`): ChatGPT-style layout with auto-collapsing sidebar, folder organization, persistent history
  - Chat UI: WebSocket streaming (token-by-token), markdown rendering (react-markdown + remark-gfm), SQL syntax highlighting, Recharts chart rendering, deep links, @mention autocomplete
  - Intent classifier: rule-based regex patterns + LLM fallback for data/analysis/general classification with confidence scores
  - SQL generation engine: LLM-based SQL generation → schema whitelist validation → org-scope injection → parameterized execution (5s timeout)
  - SQL safety guardrails: read-only, schema whitelist, 3-join max, no subqueries, row limits by query type × plan tier
  - Self-learning query templates: cosine similarity matching (OpenAI embeddings, 0.85 threshold), idempotent saving, 15 pre-built system templates
  - Context resolver: @mention parsing (6 types: @customer:, @feedback:#, @period:, @tag:, @source:, @category:), conversation history assembly, 15K char context limit
  - Response formatter: table/chart/deep link formatting, markdown XSS sanitization
  - WebSocket endpoint: JWT auth via query param, streaming protocol, rate limiting, connection management
  - REST API: conversations CRUD, folders CRUD (Pro+), template starters, usage endpoint
  - Frontend API client: 12 API functions with full TypeScript interfaces
  - Admin templates page (`/system/query-templates`): DataTable with search, usage stats, active toggle, delete
  - Plan gating UI: remaining queries display (Free tier), upgrade CTAs (inline/banner/modal), token budget exceeded banner, usage section in AI Settings
  - Backend: 6 new DB models, Alembic migration, 10 service modules, 4 route modules
  - UUID `public_id` on conversations: all API routes, WS handler, and frontend use UUID strings instead of sequential numeric IDs for URLs and external references
  - Alembic migration (`n3o4p5q6r7s8`): adds `public_id` column with backfill + unique index
  - 334 backend TDD tests + 187 frontend TDD tests = 521 total tests (all passing)
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
- **AI Response Suggestions** (M2.3, PRD-AI-RESPONSE-SUGGESTIONS.md):
  - Response modal on feedback detail page: template suggestion, browse templates, AI generation, tone selector, copy/send actions
  - 8 system response templates seeded on startup (Bug Report, Feature Request, Churn Risk, Positive, Complaint, Urgent, Follow-up, Onboarding)
  - Template CRUD: system templates (read-only) + custom org templates, scoring algorithm for best-match suggestion
  - Template browser component with search, system/custom sections
  - Response settings per org: brand_voice, default_tone, product_name_display, support_email_display
  - Feedback response history: tracks all responses sent per feedback item (channel, source, tone, status)
  - AI response generation endpoint with tone selection and token tracking
  - Send response endpoint supporting clipboard, Slack, Intercom, Linear, email channels
  - Response usage tracking: ai_responses_generated counter, monthly limits by plan
  - Actions dropdown: consolidated Delete, Re-analyze, Respond, Create Issue into single dropdown menu
  - Removed standalone refresh button (realtime events via useRealtimeEvents handle auto-refresh)
  - Create Issue stepped page (`/feedbacks/[id]/create-issue`): 3-step wizard (Select Integration → Configure → Done) matching feedback source wizard style
  - Create Issue page: Linear form with AI-prefilled title/description, team/priority/project selectors, duplicate warning, success summary
  - Plan gating: `response_suggestions` feature on Pro+
  - Alembic migration (`o4p5q6r7s8t9`): Organization response columns + response_templates + feedback_responses tables
  - Backend: 3 new route modules (response_templates, response_settings, feedback_responses), 2 new DB models, system template seeder
  - Frontend: ResponseModal, TemplateBrowser components, responses API client, Actions dropdown, Create Issue page
  - 10 TDD tests (FeedbackDetailActions: refresh removed, actions dropdown, create issue navigation)
- **Linear Integration** (full-stack, Mar 2026):
  - OAuth flow: connect + callback + disconnect endpoints with state management
  - Linear API client: organizations, teams, issues, comments, labels, statuses, webhooks
  - Webhook receiver: signature verification, issue/comment event processing
  - Team mapping + status mapping configuration (per-org)
  - Issue templates with variable substitution (sentiment, category, source, etc.)
  - Test connection endpoint (validates access token against Linear API)
  - Feedback source type: `linear` with triggers (all_messages, labels, keywords)
  - Frontend: Linear settings page (header with test/delete, status toggle, mapping tabs, template editor, sticky save bar)
  - Frontend: CreateIssueDialog, LinkedIssuesCard, LinearIcon components
  - Frontend: Linear in feedback sources wizard with OAuth check
  - Frontend: "Requires OAuth" badge on Linear across all feedback source pages
  - Landing page: Linear integration detail page, added to integrations overview + IntegrationBar
  - Plan gating: `linear_integration` feature on Pro+
  - Alembic migration: linear_integration tables (linear_integrations, linear_team_mappings, linear_status_mappings, linear_issue_templates)
  - Backend tests: 7 test files (client, config, issues, models, OAuth, plan gating, webhook)
  - Frontend tests: 4 test files (CreateIssueButton, CreateIssueDialog, LinearSettings, LinkedIssuesCard)
- **On-Demand AI Reports** (M2.4):
  - 4 report types via Copilot: Executive Summary, Customer Health, Feature Prioritization, Churn Risk
  - Report model + Alembic migration, ReportGenerator service, CRUD API (Business+)
  - Intent classifier: 'report' as 4th intent type
  - WebSocket streaming via regular chat messages
  - Frontend: My Reports page, ReportPreview component, 4 Cmd+K template chips
  - Reports in sidebar under Workspace
  - 105 backend + 36 WS + 10 frontend tests
- **GDPR + AI Trust + Blog Engine** (M3.8):
  - GDPR (Track A): Data export endpoint (ZIP with JSON+CSV), account deletion with 30-day grace period, deactivation, cancel flow, auth middleware blocks deactivated users, GDPR purge background task, Settings > Preferences: Export/Delete buttons, landing page GDPR badge + Privacy Policy update + FAQ entries + Bento card, 7 backend tests
  - AI Trust — Human-in-the-Loop (Track B): ai_corrections model + CRUD API (submit, stats, list), thumbs up/down on Copilot responses with feedback Dialog, category/sentiment correction on feedback detail page, health score flag icon on customer profile, AI Accuracy stats tab in AI Settings, 9 backend + 7 frontend tests
  - Blog Engine (Track C): Status field (draft/scheduled/published) on BlogPost, date-based filter (scheduled posts auto-show after date), wrote all 17 remaining posts (#8-#24) with scheduled dates (Apr 1 - Dec 1)
- **AI Workflow Automation** (M4.4, Apr 2026):
  - 4 trigger types: health score threshold, sentiment pattern, churn risk level change, feedback category match
  - 4 action types: auto-assign (user/role/round-robin), change status, send notification, draft AI response
  - Multiple actions per rule, configurable cooldown (1h-7d), active/paused toggle
  - 5 pre-built templates (Churn Prevention, Critical Bug Escalation, Feature Request Triage, Negative Sentiment Alert, Positive Feedback Follow-up)
  - Real-time event-driven execution (fires on feedback analysis + health score update)
  - Redis cooldown per customer per rule
  - Execution audit log with 90-day retention
  - Settings > Automations pages (list, create, detail with execution log, template picker)
  - Plan gated: Pro=5, Business=20, Enterprise=unlimited
  - 17 backend API + 16 engine + 10 frontend = 43 TDD tests
- **UI Consistency Audit** (Apr 2026):
  - Replaced all 17 native confirm() calls with shadcn Dialog across 15+ files
  - Replaced 4 alert() calls with sonner toast
  - Replaced 2 native `<select>` with shadcn Select
  - Reports page: background pattern fix + View button error fix
  - Landing page: AI Workflow Automation bento card + FAQ entry
- **Advanced Churn Prediction (M4.1)** (May 2026, 7 phases):
  - Phase 1 — Foundation: Alembic migration (5 new tables + 7 columns on customer_health_scores), ChurnCalibrator service (isotonic regression, bootstrap CI), seeded global model
  - Phase 2 — Labeling UI + CSV import: MarkAsChurnedDialog, RecoverCustomerDialog, BulkMarkChurnedDialog, ChurnCsvImportDialog, `/system/churn-events` admin page, CSV validation + dedup
  - Phase 3 — Probability integration + winback: Probability recomputation on feedback ingest (worker-service), has_potential_winback auto-flag, PotentialWinbackBanner, ChurnProbabilityBadge, ChurnTimelineBadge, risk_level derived from probability bands
  - Phase 4 — Cohort analytics: `/analytics/churn-cohorts` page with 3 dimensions (source/month/volume), heatmap + bar chart + reason-code breakdown, Business+ gated
  - Phase 5 — Playbooks: Full CRUD + run + run-batch + executions, 7 pre-built templates (Critical Save, Prevention, At-Risk Outreach, Light-Touch Nudge, Power-User Recovery, New-Customer Save, Silent-Churn Watch), playbook_seeder.py (idempotent startup)
  - Phase 6 — Accuracy dashboard + weekly calibration: Celery Beat (refit Mondays 07:45 UTC, global refit daily 03:00 UTC), `/analytics/churn-accuracy` (org) + `/system/churn-accuracy` (admin), ModelAccuracyCard dashboard widget (Business+)
  - Phase 7 — Polish: Cross-page UI audit (probability badges everywhere), landing page bento card + FAQ, blog post draft, E2E test (label → refit → predict), performance check
  - 409 new tests (60 backend + 40 frontend + 309 worker), zero regressions
  - New tables: customer_churn_events, churn_calibration_models, churn_backtest_runs, churn_playbooks, churn_playbook_executions
  - New pages: /churn-cohorts (analytics), /playbooks (settings), /churn-accuracy (system admin)
  - New components: ChurnProbabilityBadge, ChurnTimelineBadge, CohortHeatmap, ReasonCodeBreakdown, ModelAccuracyCard, PlaybookTemplateCard, RunPlaybookDropdown
- **Other fixes** (Mar–May 2026):
  - Changelog: full descriptions with bullet list rendering, CORS fix, build fix
  - Sidebar: collapsible sections, conversation delete confirmation dialog
  - Footer consistency, API docs link removed
- **Custom Webhooks & Tech Debt** (M3.1, PRD-CUSTOM-WEBHOOKS-AND-TECH-DEBT.md):
  - Webhook endpoints CRUD API: HMAC-SHA256 signing, custom headers (Fernet-encrypted), configurable retry (fire-and-forget or exponential backoff)
  - Plan-gated endpoint limits: Free=2, Pro=5, Business=10, Enterprise=unlimited
  - 5 event types: feedback.created, feedback.analyzed, feedback.status_changed, feedback.urgent, feedback.category_match (tag-based filtering)
  - Dispatch engine: async Celery tasks, exponential backoff (1m/5m/30m), auto-disable after 10 consecutive failures
  - Delivery log with 30-day retention (weekly purge via Celery Beat)
  - Frontend: Settings > Webhooks pages (list, create, detail/edit with delivery log), shadcn Checkbox/ToggleGroup components
  - Sentry error tracking: free tier across backend-api (FastAPI), worker-service (Celery), frontend-web (Next.js)
  - Health endpoint: /health/detailed (system-admin only) with DB, Redis, Celery, memory, uptime checks
  - Collapsible sidebar sections (Workspace, Analysis, Settings, System) with auto-expand on active route
  - Alembic migration: webhook_endpoints + webhook_deliveries tables
  - 60 webhook + 24 Sentry + 17 health = 101 TDD tests

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
- Multi-model support: factory pattern with provider-specific clients, Fernet encryption for BYOK keys, fallback chain (primary → retry → system OpenAI), per-org config stored in DB
- LLM usage tracking: per-request logging with provider/model/tokens/cost, monthly budget limits, plan-gated model access
- Model registry: admin-managed catalog with tier classification (cheap/mid/premium), plan-based availability gating
- AI Copilot (M2.2): Cmd+K spotlight modal → /conversations page, WebSocket streaming, self-learning query templates, SQL generation with safety guardrails, plan gating with token budgets
- Copilot architecture: rule-based intent classifier + LLM fallback, cosine similarity template matching (0.85 threshold), schema whitelist, read-only SQL with 3-join max/5s timeout
- Copilot conversations: ChatGPT-style with folder organization, persistent history, auto-collapsing sidebar, org-wide shared conversations, UUID public_id for shareable URLs
- Copilot plan gating: Free=10 queries/day + 50K tokens/mo, Pro=unlimited + 500K tokens, Business=5M tokens, with upgrade CTAs and usage display in AI Settings
- AI Response Suggestions (M2.3): modal-based compose flow (not inline), system templates seeded at startup (idempotent), template scoring by category/sentiment/urgency/churn, Actions dropdown consolidates 4 buttons, Create Issue as stepped page (not dialog) matching feedback source wizard style
- Linear integration: own OAuth system (separate from generic Integration model), dedicated tables (not reusing integrations table), Pro+ plan gating, webhook signature verification, team/status mappings for org-level config
- Linear feedback sources: `requires_integration=false` in backend (uses its own OAuth), frontend adds `|| type.type === 'linear'` for "Requires OAuth" badge display
- Custom webhooks (M3.1): 5 event types, plan-gated endpoint limits, user-configurable retry mode (fire-and-forget or exponential backoff), HMAC-SHA256 signing, Fernet-encrypted headers, auto-disable after 10 failures
- Sentry: free tier (5K errors/mo) across all 3 services, hardcoded DSN (safe per Sentry docs), separate projects for backend vs worker
- Health endpoint: /health/detailed returns DB/Redis/Celery/memory/uptime, system-admin gated, always 200 (reports health, doesn't fail on unhealthy)
- Sidebar: all sections collapsible with Radix Collapsible, auto-expand based on active route, no localStorage persistence
- AI Workflow Automation (M4.4): 4 trigger types × 4 action types, event-driven execution, Redis cooldown, 5 pre-built templates, execution audit log with 90-day retention, plan-gated limits (Pro=5, Business=20, Enterprise=unlimited)
- UI Consistency Audit (Apr 2026): replaced all 26 native browser elements (17 confirm(), 4 alert(), 2 select, 3 misc) with shadcn Dialog, sonner toast, and shadcn Select across 15+ files — zero native browser dialogs remain
- On-Demand AI Reports (M2.4): 4 report types via Copilot Cmd+K template chips, 'report' as 4th intent type in classifier, WebSocket streaming via regular chat messages, My Reports page under Workspace sidebar, Business+ plan gating
- GDPR (M3.8 Track A): data export as ZIP (JSON+CSV), account deletion with 30-day grace period + deactivation + cancel flow, auth middleware blocks deactivated users, GDPR purge Celery task, all plans have access
- AI Trust Human-in-the-Loop (M3.8 Track B): ai_corrections model for thumbs up/down + category/sentiment correction, AI Accuracy stats tab in AI Settings, corrections stored as training signals for future fine-tuning
- Blog Engine (M3.8 Track C): draft/scheduled/published status field, date-based auto-publish filter, all 17 remaining posts (#8-#24) written with scheduled dates (bi-weekly Apr 1 - Dec 1)
- Advanced Churn Prediction (M4.1): Calibrated heuristic now (isotonic regression on 9-factor score), real ML model in v2 once labels ≥ 500 per org
- Churn Calibration: Weekly refit Mondays 07:45 UTC with bootstrap 90% CI, idempotent per-org + global fallback, model versioning with precision/recall/F1/AUC tracking
- Churn Probability Display: Replaces risk_level as primary signal (risk_level still shown as color hint, derived from probability bands), percentage + CI tooltip across all surfaces
- Churn Labeling: Structured reason codes (price, competitor, product_quality, no_longer_needed, silent_churn, other), manual + CSV import + auto-suggested sources, recovered_at winback tracking
- Churn Playbooks: 7 pre-built templates with probability-range binding, rate-limited 60min per (playbook, customer), actions reuse existing Automations engine
- Churn Plan Gating: Probability + timeline + cohorts + playbooks + accuracy = Business+. Existing risk_level + factor breakdown stays Pro+. Enterprise = unlimited playbooks + custom probability bands
- Churn Data Model: 5 new tables, BigInteger PKs (per codebase convention, not UUID), unique constraint on (org_id, email, churned_at) for dedup

---

## Related

- [SALES-TRACKING.md](SALES-TRACKING.md) - Sales strategy and growth metrics
