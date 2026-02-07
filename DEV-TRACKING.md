# Development Tracking

**Vision**: AI-powered feedback analysis SaaS
**Target**: $50K MRR in 12 months
**Last Updated**: 2026-02-07

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

### 3. Enhanced Analytics (Priority: MEDIUM)
> *Proves ROI and enables data-driven product decisions*

- [ ] Trends over time (sentiment/volume charts with date ranges)
- [ ] Saved views and filters (quick access to common queries)
- [ ] Export dashboard as PDF (for stakeholder reports)
- [ ] Dashboard sharing (public link for read-only access)

### 4. Feedback Workflow (Priority: MEDIUM)
> *Completes the feedback loop: collect → analyze → ACT. Focused scope, not project management.*

- [ ] Status tracking (New → In Review → Resolved → Closed)
- [ ] Feedback assignment (route to team member)
- [ ] Internal notes (add team-only context to feedback)

**Deliberately excluded** (not aligned with core value):
- ~~Comments on feedback items~~ (turns app into Slack)
- ~~@mentions~~ (not a project management tool)
- ~~Activity feed~~ (nice-to-have, not essential)

### 5. Additional Integrations (Priority: LOW)
> *Expands feedback sources, but existing customers can use CSV/Slack*

- [ ] Intercom API (pull support conversations)
- [ ] Zendesk API (pull support tickets)
- [ ] Email forwarding (receive feedback via email)
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

### Predictive Analytics
- [ ] Churn prediction model
- [ ] Feature impact prediction
- [ ] Customer lifetime value estimation
- [ ] Revenue impact scoring

---

## Technical Debt

- [ ] Add comprehensive test coverage
- [ ] Performance optimization (caching)
- [ ] Database query optimization
- [ ] Error tracking (Sentry)
- [ ] Monitoring dashboard (DataDog)

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

---

## Decisions Made

- Using Resend for transactional emails (with template management script)
- Stripe for all billing
- Railway for hosting
- Google OAuth via access token flow (full-width custom button)
- Phase 2 prioritizes AI/Notifications over Integrations (differentiator focus)
- Collaboration features scoped down to "Feedback Workflow" (status, assignment, notes only)
- Excluded @mentions, comments, activity feed (avoids becoming project management tool)
- Changelog auto-syncs via GitHub API at startup (idempotent, no manual intervention)
- `is_system_admin` boolean on User model for system-level access (separate from org roles)
- Notification bell in header (not sidebar) with Radix popover for quick access
- Per-type retention billing: each alert type has independent retention days, Stripe billed on total extra days
- Digest scheduling: hourly Celery Beat, tasks filter users by preferred hour/day (no per-user cron)

---

## Related

- [SALES-TRACKING.md](SALES-TRACKING.md) - Sales strategy and growth metrics
