# AI Feature Tracking & 1-Year Roadmap

**Product**: Rereflect
**Last Updated**: 2026-05-21
**Killer Feature**: Churn prediction that actually works (predict 30-60 days before churn with actionable reasons)

---

## Strategic Decisions

| Decision | Choice |
|----------|--------|
| **AI differentiation** | All four: predictive intelligence + deep customer understanding + real-time AI copilot + automated workflows |
| **Target buyers** | All personas: founders/executives, CS managers, PMs, support leads |
| **AI pricing** | Premium upsell (tiered access): basic AI free, advanced Pro+, enterprise AI Business+ |
| **Model strategy** | Hybrid: our default model + BYOK multi-model (OpenAI + Anthropic + Google) |
| **AI copilot UX** | Command bar (Cmd+K) — suits mixed usage patterns (quick check-ins to deep sessions) |
| **Processing** | Hybrid: real-time algorithmic (no LLM) + batch LLM deep analysis + streaming for copilot |
| **Customers page** | Customer 360 profiles (full per-customer view) |
| **Response AI** | Hybrid: template suggestions (all plans) + generated custom responses (Pro+, plan-gated limits) |
| **AI trust** | All three: confidence scores + explainability + human-in-the-loop corrections |
| **AI moat** | All four: historical intelligence + workflow integration + custom models + network effects |
| **CRM enrichment** | HubSpot first, then Salesforce |
| **Usage enrichment** | Segment first (CDP covers Mixpanel/Amplitude/GA) |
| **Copilot actions** | Read + suggest actions (user clicks to execute) |
| **Benchmarks** | Industry benchmarks only (opt-in, anonymized, grouped by industry) |
| **Custom models** | Enterprise: custom categories/weights + fine-tuned classification |
| **AI reports** | On-demand report generation via copilot |
| **Languages** | English only (for now) |
| **AI budget** | Minimal now ($50-100/mo), pass-through to customers via BYOK/usage pricing as we scale |
| **Custom webhooks** | 5 event types with tag-based filtering, plan-gated limits, configurable retry |

---

## Current AI Capabilities (Built)

| Feature | Backend | Frontend | Plan Gate |
|---------|---------|----------|-----------|
| VADER sentiment analysis | Yes | Feedback list badge, detail, dashboard chart, analytics | Free |
| LLM auto-categorization (pain points, features, urgency) | Yes | Feedback detail categories, dashboard aggregates | Free |
| Anomaly detection (sentiment + volume spikes) | Yes | Notification center + email alerts | Free |
| Weekly GPT-4 insights (suggested actions) | Yes | Dashboard "AI Insights" card | Free |
| 9-factor churn risk scoring | Yes | Feedback detail page only | Pro+ (enhanced) |
| Customer health scores (4-component weighted) | Yes | Dashboard widget (top 5 at-risk) | Pro+ |
| Weekly LLM churn deep-dive | Yes | Dashboard widget expandable section | Pro+ |
| Tag extraction (TF-IDF) | Yes | Feedback detail tags | Free |
| Multi-model LLM support (OpenAI, Anthropic, Google) | Yes | AI Settings page (providers, usage, budget) | Pro+ (BYOK) |
| AI Copilot (natural language queries) | Yes | /conversations page, Cmd+K | Tiered by plan |
| AI Response Suggestions | Yes | Feedback detail ResponseModal, template browser | Pro+ |
| Customer sentiment alerts | Yes | Notification center, Slack, email | Pro+ |
| On-Demand AI Reports | Yes | My Reports page, Copilot Cmd+K chips, PDF export | Business+ |
| AI Trust: Human-in-the-Loop | Yes | Thumbs up/down on Copilot, category/sentiment corrections, AI Accuracy tab | Pro+ |
| AI Workflow Automation | Yes | Settings > Automations (list, create, detail, templates, execution log) | Pro+ (5 rules), Business (20), Enterprise (unlimited) |
| Advanced Churn Prediction (probability, timeline, cohorts, playbooks, accuracy) | Yes | Churn Cohorts page, Playbooks editor, Churn Accuracy card, ChurnProbabilityBadge | Business+ |
| Unified Customer Timeline (feedback + usage + churn + health events, cursor-paginated) | Yes | Customer profile "Full Activity Timeline" card (load-more) + `/customers/{email}/timeline` | Unlocked (OSS) |
| Customer 360 Public API (full profile, timeline, health) | Yes | `GET /api/public/v1/customers/{email}` + `/timeline` + `/health` (API-key read scope) | Unlocked (OSS) |
| CRM Enrichment (HubSpot + Salesforce) — company/ARR/renewal/deal, provider-tagged, feeds health `crm_component`, CRM timeline events, health-score writeback to **both** HubSpot (contact property) and Salesforce (Contact field) | Yes | CrmCompanyCard on Customer 360, Settings > Integrations (HubSpot token / Salesforce OAuth), HubSpot + Salesforce writeback toggle cards, one-CRM-per-org guard | Unlocked (OSS) |
| Jira Cloud Integration (slice 1) — connect via Atlassian API token (Basic auth, encrypted), create issue from feedback (project/issue-type, ADF, duplicate guard), `jira` selectable source type; SSRF-hardened | Yes | Settings > Integrations (Jira token-paste page + tile), create-issue wizard Jira branch, landing page + `SELF_HOSTING.md`; OAuth 3LO / Server-DC / status-sync deferred v2 | Unlocked (OSS) |
| Zendesk Integration — inbound feedback source via agent email + API token (Basic auth, encrypted); tickets → feedback (one item/ticket, deduped by ticket ID, requester → `customer_email`); dual ingestion (incremental **pull** beat + optional HMAC **webhook**) through a shared dedup core; `zendesk` selectable source type; SSRF-hardened; auto-provisions a default source on connect | Yes | Settings > Integrations (Zendesk token-paste page + tile), source-wizard branch, landing page + `SELF_HOSTING.md`; OAuth / per-comment / backfill / filters / write-back deferred v2 | Unlocked (OSS) |
| Asana Integration (slice 1) — **outbound** work-management target via a **Personal Access Token** (Bearer auth, encrypted); create Asana **task** from feedback (workspace/project selection, plain-text notes, `permalink_url` link, org-scoped duplicate guard + `asana_task_created` timeline event); `asana` selectable own-auth source type; fixed host `app.asana.com` (no per-org subdomain → no SSRF DNS gate) | Yes | Settings > Integrations (Asana PAT token-paste page + tile), create-task wizard Asana branch (Workspace→Project pickers), landing page + `SELF_HOSTING.md`; **AI-drafted content shipped 2026-07-07** (see row below); OAuth / inbound status-sync / team-scoped-project picker deferred v2 | Unlocked (OSS) |
| AI-Drafted Issue/Task Content — "Draft with AI" in the create-work-item wizard (Jira + Asana branches) drafts issue/task **title + body** from the feedback item via the org's LLM; shared `POST /api/v1/feedback/{id}/issue-draft` (admin/owner), gated on `resolve_generation_llm().is_configured` (409 when no LLM); provider-agnostic (cloud BYOK + local Ollama/OpenAI-compatible), org tone/brand voice, `LLMUsageLog(task_type="issue_draft")`; **populates editable fields for review — never auto-creates**; button hidden when no LLM configured; prompt hardens against injection (feedback as delimited untrusted data) | Yes | "✨ Draft with AI" button in Jira + Asana wizard branches; overwrite-confirm if edited; degrades to manual fields when unconfigured | Unlocked (OSS) |
| Per-Org Self-Improving Sentiment Classifier (M5.2) — CPU-only, offline TF-IDF + logistic regression trained on org's own feedback text + sentiment corrections; three modes (off/shadow/auto); auto-promotes challenger only when macro-F1 delta ≥ +0.02 on held-out set and correction volume ≥ 20 per type; weekly refit Mon 06:30 UTC; promoted model is reversible via one-click rollback | Yes | Settings → AI (General tab: mode toggle; Accuracy tab: incumbent-vs-challenger macro-F1 + delta + rollback) + endpoint GET `/api/v1/settings/ai/classifier/accuracy`, POST `/api/v1/settings/ai/classifier/rollback` | Unlocked (OSS) |
| Per-Org Self-Improving **Category** Classifier (M5.2 v2) — same CPU-only offline spine trained on the org's `category` corrections; **dynamic labels from the org's own corrections** (built-ins + custom); independent `category_classifier_mode` (off/shadow/auto); in `auto` overrides `pain_point_category`/`feature_request_category` **only when the predicted label maps unambiguously to one built-in vocab** (else shadow-only); **fair-A/B** scores the challenger only over labels the keyword incumbent can emit; keyword categorizer is the incumbent; weekly refit + one-click rollback | Yes | Settings → AI (General tab: second **category** mode toggle; Accuracy tab: second incumbent-vs-challenger card) + the shared `classifier/accuracy` & `classifier/rollback` endpoints with `?classifier_type=category` | Unlocked (OSS) |

---

## Frontend Gaps (Data exists, not surfaced)

### 1. Feedback Detail: Customer Health Badge
- **Status**: COMPLETE (built in M1.1)
- **Scope**: Small — frontend-only
- **What**: Show health score badge on `/feedbacks/[id]` when item has `customer_email`
- **PRD Reference**: PRD-PREDICTIVE-ANALYTICS.md Phase 4.3

### 2. Feedbacks List: Churn Risk Indicator
- **Status**: COMPLETE (built in M1.1)
- **Scope**: Small — frontend column + backend already returns field
- **What**: Add `churn_risk_score` as a visual indicator column on feedbacks list table
- **Why**: Users can't scan for high-risk items without opening each one

### 3. Dedicated /customers Page
- **Status**: COMPLETE (built in M1.2)
- **Scope**: Medium — new page + API endpoint
- **What**: Full customer list with sortable health scores, search, filters, risk level breakdown
- **Why**: Dashboard only shows top 5 at-risk. No way to browse all customers or see healthy ones

---

## 1-Year AI Roadmap (Milestone-Driven)

### Q1 2026: Customer Intelligence Foundation (Feb-Mar)
> *Theme: Surface all existing AI data, build Customer 360, nail churn prediction accuracy*

**Goal**: Every customer with an email has a visible health profile. Churn predictions are accurate and actionable.

#### M1.1 — Frontend Gaps (1 week) — COMPLETE
- [x] Feedback detail: customer health badge (score circle + risk level when `customer_email` exists)
- [x] Feedbacks list: churn risk indicator column (color-coded dot/bar, sortable)
- [x] Churn risk filter on feedbacks list (filter by risk level: low/medium/high/critical)

#### M1.2 — Customer 360 Page (2 weeks) — COMPLETE
- [x] `/customers` page: sortable table (email, name, health score, risk level, feedback count, last active, sentiment trend)
- [x] Customer search + filters (risk level, health score range, last active, feedback count)
- [x] Risk distribution chart (pie/bar: healthy/moderate/at-risk/critical breakdown)
- [x] `/customers/[email]` profile page: health score timeline chart, all feedbacks, sentiment trend over time, component breakdown
- [x] LLM summary section on customer profile (latest churn analysis)
- [x] "View all feedbacks" link from profile to filtered feedbacks list
- [x] Customer health API endpoint (list all customers, paginated, filterable)
- [x] Plan gate: `/customers` page requires `customer_health_scores` feature (Pro+)

#### M1.3 — Customer Sentiment Alerts (1 week) — COMPLETE
- [x] New alert type: `customer_health_drop` — triggers when health score drops by X points or crosses threshold
- [x] Alert preferences: configurable threshold (e.g., "alert when score drops below 50" or "drops by 20+ points")
- [x] Notification: in-app + email + Slack (uses existing notification dispatch)
- [x] Trigger in health score recomputation: compare new vs previous score

#### M1.4 — Churn Prediction Accuracy (1 week) — COMPLETE
- [x] AI explainability on churn risk: show factor breakdown on feedback detail ("Churn risk: 72 — Sentiment trend -15, Frustration keywords +10, ...")
- [x] Confidence score on health scores ("87% confidence" based on data volume — low feedback count = low confidence)
- [x] Backtest validation: script to evaluate churn prediction accuracy against historical data (customers who actually churned)

**Q1 Deliverables**: Customer 360 page, health badges everywhere, sentiment alerts, churn explainability
**Plan Gating**: Customer 360 + alerts + explainability = Pro+, basic churn display stays Free

---

### Q2 2026: AI Copilot & Smart Responses (Apr-Jun)
> *Theme: Interactive AI that answers questions, suggests actions, and drafts responses*

**Goal**: Users can ask Rereflect questions in natural language and get instant, accurate answers. AI drafts responses and suggests actions.

#### M2.1 — Multi-Model Support (1 week) — COMPLETE
- [x] LLM abstraction layer: unified interface for OpenAI, Anthropic, Google
- [x] Model selection per org (settings page): choose default provider
- [x] BYOK key management: store API keys per provider (encrypted)
- [x] Fallback chain: if primary model fails, try secondary
- [x] Plan gate: Free = GPT-4o-mini only, Pro = OpenAI models, Business+ = all providers

#### M2.2 — AI Copilot: Command Bar (3 weeks) — COMPLETE
- [x] `Cmd+K` command bar UI: search input + template chips + keyboard navigation + Spotlight modal
- [x] Natural language query parser: rule-based regex + LLM fallback intent classifier (data/analysis/general)
- [x] Data queries: SQL generation from natural language (safe, read-only, org-scoped, schema-whitelisted)
  - [x] SQL query generation with 3-join max, 5s timeout, no subqueries, row limits by plan
  - [x] Result formatting: tables, charts (Recharts), deep links, markdown
- [x] Analysis queries: context assembly + LLM analysis with structured response
  - [x] Context scope selector (All Data, Feedbacks, Customers, etc.) + @mentions
  - [x] Structured response with supporting data
- [x] Self-learning query templates: auto-save successful queries, cosine similarity matching (0.85 threshold)
  - [x] 15 pre-built system templates + idempotent template saving + admin management page
- [x] WebSocket streaming: real-time token-by-token LLM response via `wss://{host}/ws/copilot?token={jwt}`
- [x] Conversations page: ChatGPT-style with folder organization, persistent history, auto-collapsing sidebar, UUID-based shareable URLs
- [x] Plan gating: Free = 10 queries/day + 50K tokens/mo, Pro = unlimited + 500K tokens, Business = 5M tokens
- [x] Usage display: copilot usage section in AI Settings, token budget bars, upgrade CTAs

#### M2.3 — AI Response Suggestions (2 weeks) — COMPLETE
- [x] Response templates library: 8 system templates seeded on startup (Bug Report, Feature Request, Churn Risk, Positive, Complaint, Urgent, Follow-up, Onboarding) with template CRUD and scoring algorithm for best-match suggestion
- [x] Template suggestion on feedback detail: AI picks best template based on category + sentiment via scoring algorithm
- [x] Custom response generation: ResponseModal with template browser, AI generation, and tone selector; Actions dropdown consolidating respond/re-analyze/create issue/delete
- [x] Copy-to-clipboard + edit before sending (no auto-send)
- [x] Plan gate: response_suggestions on Pro+; response settings per org (brand_voice, default_tone, product_name, support_email)

#### M2.4 — On-Demand AI Reports (2 weeks) — COMPLETE
- [x] Via copilot: "Generate a report on churn trends this quarter" (4 report types via Cmd+K template chips)
- [x] Report types: executive summary, customer health report, feature request prioritization, churn risk
- [x] Structured output: sections with headers, key metrics, charts data, recommendations
- [x] Export as PDF (reuse existing PDF export infrastructure)
- [x] Plan gate: Business+ feature
- [x] Report model + Alembic migration, ReportGenerator service, CRUD API
- [x] Intent classifier: 'report' as 4th intent type
- [x] WebSocket streaming via regular chat messages
- [x] Frontend: My Reports page, ReportPreview component, 4 Cmd+K template chips
- [x] Reports in sidebar under Workspace
- [x] 105 backend + 36 WS + 10 frontend tests

**Q2 Deliverables**: Multi-model LLM (M2.1 COMPLETE), AI copilot (M2.2 COMPLETE), response suggestions (M2.3 COMPLETE), on-demand reports (M2.4 COMPLETE)
**Plan Gating**: Copilot queries tiered by plan, response generation Business+, reports Business+

---

### Q3 2026: Data Enrichment & Customer Intelligence (Jul-Sep)
> *Theme: Enrich Customer 360 with external data sources, build deeper understanding*

**Goal**: Customer profiles combine feedback + CRM + product usage data. AI has full context for predictions.

#### M3.1 — HubSpot CRM Integration (3 weeks) — COMPLETE (shipped as `hubspot-crm-enrichment`)
- [x] HubSpot connect/disconnect — **private-app access token** (BYOK, pasted by the self-hoster), not the OAuth marketplace flow (awkward for self-host)
- [x] Sync contacts: pull company, deal stage, ARR, contract renewal date, lifecycle stage
- [x] Match by email: link HubSpot contacts to Rereflect customers (by `customer_email`)
- [x] Customer 360 enrichment: show CRM data on customer profile (company name, deal value, renewal date) — `CrmCompanyCard`
- [x] Churn prediction enrichment: CRM signals in the health score via the opt-in `crm_component` (renewal date), + `crm_*` timeline events
- [x] Bi-directional sync: push health scores to HubSpot contact properties (opt-in per org, on-change trigger + backfill, soft-pause on missing write scope/field)
- [x] Plan gate: removed — all features unlocked in the open-source self-hosted edition

#### M3.1b — Salesforce CRM Integration — COMPLETE (shipped 2026-07-01)
> Delivered as `salesforce-crm-enrichment` (commits ~`309c37c`..`47a3733`), the 2nd CRM per `AI-TRACKING.md` line 23 ("HubSpot first, then Salesforce"). See `docs/planning/salesforce-crm-enrichment/`. Reuses the HubSpot-built consuming layer (health `crm_component`, CrmCompanyCard, timeline) via a provider-agnostic generalization.
- [x] Salesforce **OAuth 2.0** web-server flow (connect/callback/status/disconnect/test) with CSRF-hardened, session-bound `state` (HttpOnly nonce cookie)
- [x] `crm_enrichment` generalized with a `provider` discriminator (existing HubSpot scores byte-identical — characterization-tested); provider-driven timeline source
- [x] Sync Account/Contact/Opportunity → company/ARR/renewal/deal (SOQL, token refresh, API-limit backoff), match by email; daily beat 03:45 UTC + manual trigger
- [x] Health/churn signal via the shared `crm_component`; provider-tagged rows
- [x] **One CRM connected per org at a time** — symmetric guard on both providers' connect + purge-on-disconnect
- [x] Bi-directional push-back — **Salesforce health-score writeback shipped 2026-07-05** as `salesforce-crm-writeback` (slice 2): opt-in per-org, off by default; describe-validated writable numeric Contact field (default `Rereflect_Health_Score__c`); on-change trigger (generalized `_maybe_enqueue_writeback`, HubSpot path unchanged) + backfill-on-enable (cap 500); idempotent (reuses `last_written_health_score`); soft-pause on scope/field/not-found/daily-limit (never flips `is_active`); persists `salesforce_contact_id` (deterministic on dup email) with re-query-by-email fallback. See `docs/planning/salesforce-crm-writeback/`. **Still deferred (v2):** multi-field push, Account-object target, simultaneous dual-CRM writeback + reconciliation, real-time/streaming push.
- [x] Plan gate: removed — OSS self-hosted, all unlocked

#### M3.2 — Product Usage Enrichment (2 weeks) — COMPLETE (shipped 2026-06-29)
> Delivered as `product-usage-enrichment` (commits ~`c64665a`..`5d7f21c`). See `docs/planning/product-usage-enrichment/`. Ingest is a plain authenticated POST (normalized, Segment-compatible), not a Segment OAuth connection — fits the OSS self-hosted / BYOK model.
- [x] Usage webhook receiver: `POST /api/v1/webhooks/usage` (ingest-scoped API key, `identify` + `track`, dedup on `messageId`, bounded batch/payload). Emits to Celery `process_usage_event`.
- [x] Usage metrics per customer: `usage_event` log + `customer_usage` rollup (last_active, login/active-days 7d/30d, distinct features) → `usage_score` (recency + frequency + breadth, neutral 50 when no data)
- [x] Customer 360 enrichment: "Usage Activity" card + UsageTimeline chart on the profile; "Last active (product)" list column
- [x] Health score enrichment: usage as **opt-in 5th component**, `health_weight_usage` **default 0** (byte-for-byte-stable upgrade), 5-field health-weights API; daily `recompute_usage_scores` applies recency decay
- [x] Operator setup docs (`docs/SELF_HOSTING.md`) + `settings/usage-events` panel
- [x] Plan gate: removed — all features unlocked in the open-source self-hosted edition

#### M3.3 — AI Trust: Human-in-the-Loop (2 weeks) — COMPLETE
- [x] Feedback on AI outputs: thumbs up/down on copilot answers, health scores, categorizations
- [x] Category correction: user can override AI category → stored as training signal
- [x] Sentiment correction: user can override sentiment label → stored as training signal
- [x] Correction dashboard: AI Accuracy stats tab in AI Settings, accuracy over time
- [x] Health score flag icon on customer profile
- [x] 9 backend + 7 frontend tests
- [ ] Corrections feed into fine-tuning pipeline (M4.2)

#### M3.4 — Enhanced Customer 360 (2 weeks) — PARTIAL (unified timeline + Customer 360 API shipped 2026-06-29)
- [x] Unified customer timeline: feedback + usage + churn + health-score events in chronological order (cursor-paginated `/timeline` endpoint + shared service; the existing `/activity` widget now delegates to it). **CRM events deferred** until HubSpot (M3.1) — the event shape is source-extensible.
- [x] Customer segments: rule-based, single-assignment classification into 7 slugs (`at_risk`, `silent_churner`, `dormant`, `power_user`, `happy_advocate`, `new`, `unsegmented`) — computed on ingest + nightly recompute, exposed as `segment` on the list (with `?segment=` filter) and profile endpoints (internal + public API). Heuristic only, no ML.
- [x] Bulk actions (shipped 2026-07-09 as `segment-actions`): row-selection **or** whole-filter cohort on `/customers` → **CSV export** (`GET /customers/export`, streaming, formula-injection-safe), **bulk tag** (`POST /customers/bulk/tags`, add/remove), **bulk assign CS owner** (`POST /customers/bulk/assign-owner`; new `cs_owner_user_id` + `tags` on `customer_health_scores`), and **run a churn playbook on a cohort** (`POST /playbooks/{id}/run-batch` extended with `emails`/`segment`, 500-cap + `count_only` preview). All actions share one `Cohort` contract (`emails[]` | `filter{segment,risk_level,search,include_archived}`, resolved server-side). See `docs/planning/segment-actions/`. **Deferred (v2):** trigger outreach campaign (needs operator SMTP/Resend); run-playbook on a whole-filter cohort currently requires a `segment` (or explicit emails) — a risk/search-only whole-filter cohort can be exported/tagged/assigned but not playbook-run yet.
- [x] Customer 360 API (for external consumption): public read endpoints `GET /api/public/v1/customers/{email}` (full profile) + `/timeline` (API-key `read` scope)
- [x] Health score API endpoint for programmatic access: `GET /api/public/v1/customers/{email}/health` (extended with component breakdown incl. usage)

**Q3 Deliverables**: HubSpot integration, Segment integration, human-in-the-loop (M3.3 COMPLETE), enriched Customer 360
**Plan Gating**: CRM/usage integrations = Business+, corrections = Pro+

---

### Q4 2026: Enterprise AI & Competitive Moat (Oct-Dec)
> *Theme: Custom models, advanced predictions, industry benchmarks — create switching cost*

**Goal**: Enterprise customers have custom-trained AI. Churn prediction accuracy is demonstrably high. Industry benchmarks create network effects.

#### M4.1 — Advanced Churn Prediction (3 weeks) — COMPLETE
- [x] 30-day churn probability score (percentage, not just risk level)
- [x] Churn prediction model: calibrated heuristic with label collection (train on customer-marked churn events + CSV import)
- [x] Churn timeline: time_to_churn_bucket (immediate / 2w / 2-4w / 1-3m / low) derived from probability + sentiment trend
- [x] Churn cohort analysis: 3 dimensions (source, acquisition month, volume segment) with heatmap + breakdown charts
- [x] Churn prevention playbooks: 7 pre-built templates (Critical Save, Prevention, At-Risk Outreach, etc.) + clone/edit with probability range binding
- [x] Accuracy tracking: precision/recall/F1/AUC metrics on organization + system admin accuracy dashboards, weekly refit Mondays 07:45 UTC
- [x] Plan gate: Business+ (Pro gets enhanced risk_level + factor breakdown)

#### M4.2 — Custom AI Models (3 weeks) — PARTIAL (categories + weights shipped 2026-06-22)
- [x] Custom category configuration: org-specific pain point, feature request, and **urgency** categories — injected into the LLM prompt + merged into the keyword categorizers
- [x] Custom health score weights: adjust the 4 component weights per org (validated to sum to 100); `health_score_service` reads them
- [ ] Fine-tuned classification: train per-org classification model on their feedback + corrections (from M3.3)
- [ ] A/B comparison: show fine-tuned vs default model accuracy side-by-side
- [ ] Model versioning: track model performance over time, rollback if accuracy drops
- [x] Plan gate: removed — all features unlocked in the open-source self-hosted edition

#### M4.3 — Industry Benchmarks (2 weeks)
- [ ] Opt-in benchmark program: customers choose to contribute anonymized aggregate metrics
- [ ] Industry classification: SaaS, ecommerce, fintech, healthcare, etc. (org setting)
- [ ] Benchmark metrics: NPS, sentiment distribution, churn rate, response time, feedback volume
- [ ] Benchmark display: "Your churn rate is 15% higher than similar SaaS companies" on dashboard
- [ ] Benchmark trends: "Industry average NPS improved 5% this quarter, yours declined 3%"
- [ ] Privacy: only aggregate metrics (counts, averages, percentiles). Zero text, zero emails, zero PII.
- [ ] Plan gate: Pro+ (incentive to upgrade)

#### M4.4 — AI Workflow Automation (3 weeks) — COMPLETE
- [x] Auto-escalation rules: "If health score drops below 30, auto-assign to CS lead + create urgent notification"
- [x] Auto-response triggers: "If category is bug_report and severity is critical, draft response from template and suggest to user"
- [x] AI-powered auto-routing: feedback → AI determines best team/person based on content, history, and workload
- [x] Workflow templates: pre-built automation recipes ("Churn Prevention", "Feature Request Triage", "Critical Bug Response", "Negative Sentiment Alert", "Positive Feedback Follow-up")
- [x] Automation audit log: every AI action is logged with reasoning and can be reviewed/overridden (90-day retention)
- [x] Plan gate: Pro (5 rules), Business (20 rules), Enterprise (unlimited)
- [x] 4 trigger types: health score threshold, sentiment pattern, churn risk level change, feedback category match
- [x] 4 action types: auto-assign (user/role/round-robin), change status, send notification, draft AI response
- [x] Multiple actions per rule, configurable cooldown (1h-7d), active/paused toggle
- [x] Real-time event-driven execution (fires on feedback analysis + health score update)
- [x] Redis cooldown per customer per rule
- [x] Settings > Automations pages (list, create, detail with execution log, template picker)
- [x] 17 backend API + 16 engine + 10 frontend = 43 TDD tests

**Q4 Deliverables**: Advanced churn prediction, custom models, benchmarks, workflow automation (M4.4 COMPLETE)
**Plan Gating**: Custom models = Enterprise, benchmarks = Pro+, automation = Pro+ (5 rules) / Business (20) / Enterprise (unlimited)

---

### Open-Source Feature Batch — COMPLETE (shipped 2026-06-22)
> First batch after the open-source self-hosted pivot. All unlocked (no plan gating). See `PRD-LOCAL-LLM-CUSTOM-AI-PUBLIC-API.md`.

- [x] **Local / Offline LLM** — run the analysis pipeline against Ollama or any OpenAI-compatible endpoint, keyless (no API key, no system key); falls back to free local VADER when no model is configured. Cloud BYOK unchanged. (extends M2.1 Multi-Model)
- [x] **Custom AI** — custom pain-point/feature-request/urgency taxonomies into the analyzer + per-org configurable customer-health-score weights (M4.2 partial)
- [x] **Public REST API** — API-key auth (read/ingest/**write** scopes), read endpoints (feedback/customers/health/churn/analytics), feedback ingestion, webhook management, OpenAPI docs
  - [x] **Write scope + feedback mutation (shipped 2026-07-06)** — new `write` scope + `PATCH /api/public/v1/feedback/{id}`: change `workflow_status` (via a shared `apply_status_change` helper — timeline event, `feedback.status_changed` webhook, cache invalidation; same-value = no-op) and record category/sentiment corrections as **record-only** `AICorrection` training signals (stored analyzer value unchanged, mirroring the dashboard). Org-scoped (cross-org → 404), single flat `write` scope, no DB migration. Internal (JWT) status-change + correction routes refactored onto the shared helpers with byte-identical behavior (characterization-gated). See `docs/planning/public-api-write-crud/`. **Deferred (v2):** mutating the stored category/sentiment column, customer/taxonomy CRUD, bulk writes. **`tags`/`is_urgent` edits + `DELETE /api/public/v1/feedback/{id}` shipped 2026-07-07** — `PATCH` now also accepts `tags` (replace; `[]` clears, omitted leaves unchanged; trimmed+deduped, max 20 tags, ≤50 chars each) and `is_urgent` (bool); unknown fields → `422` (`extra="forbid"`); combined-field PATCH is best-effort/non-atomic (separate commits, carried over from the initial write-scope release). `DELETE /api/public/v1/feedback/{id}` (204, `write` scope, org-scoped 404) mirrors the internal dashboard delete (health-record archive, cache invalidation, `feedback:deleted` event). See `docs/planning/public-api-write-v2/`.
- [x] **Fully-offline AI Copilot** — the Copilot's template-matching embeddings + answer generation now run through a pluggable provider layer, so a keyless local-LLM org (Ollama / OpenAI-compatible) gets an end-to-end working Copilot; vectors are provider/dim-tagged, system templates auto-re-embed at startup, and it degrades to the LLM path when no embedding provider resolves. (extends M2.2 Copilot + the Local/Offline LLM batch above). See `PRD-AI-COPILOT.md` + `docs/planning/local-embeddings-offline-copilot/prd.md`.

> **Note:** the Plan Gating tables below are pre-pivot and now stale — every feature is unlocked in the open-source self-hosted edition.

---

## M5 — Local Model Layer (self-improving, on-device) — IN PROGRESS (M5.0 + M5.1 shipped 2026-07-10; M5.2 sentiment + category heads shipped 2026-07-11; M5.3–M5.4 planned)

> **Strategic framing.** For an OSS / self-hosted / BYOK product the moat is **not** a trained
> foundation model, a central cross-tenant dataset (dead single-tenant — the reason M4.3 benchmarks
> were dropped), or fine-tuning the operator's BYOK LLM (can't do it uniformly across providers). The
> defensible play is a **per-org, local, self-improving model layer**: trains only on data one operator
> has, runs locally with no cloud dependency, improves the more it's used/corrected, and stays honest
> (small models, stated as such — as churn already is "a calibrated heuristic"). The heavy stack is
> **already installed** (`torch`, `transformers`, `sentence-transformers`, `scikit-learn`, `bertopic`),
> and per-org training is already live but shallow (`churn_calibrator.py` fits isotonic regression per
> org at `MIN_LABELS=20`). The corrections flywheel data (`AICorrection`, M3.3) is collected but not yet
> trained on (M4.2 fine-tuned classification was deferred). This milestone block closes that loop.
>
> **Cross-cutting principles:** CPU-only (no GPU ever required — adoption is the game); default analyzer
> paths stay byte-stable; every model swap is A/B-gated and reversible; no central/cross-tenant data;
> models are small and described honestly.

#### M5.0 — Data & Model Readiness Assessment (no ML) — COMPLETE (shipped 2026-07-10, as `local-analyzer-sentiment-model`)
- [x] Instrument, per org: feedback volume, `AICorrection` counts by type (**dynamic `by_type`** —
      real values are `sentiment`/`category`/`churn_risk`/`copilot_response`; there is no `urgency`
      correction in the code, so the report groups by whatever types exist), churn-label counts +
      distribution (from `CustomerChurnEvent`); shipped `GET /api/v1/analytics/ai-readiness` + a
      "Readiness" tab card on Settings → AI.
- [x] Output surfaces the activation thresholds that gate M5.2 (correction volume — stated
      `CORRECTION_VOLUME_TARGET`, explicitly unvalidated v1) and M5.3 (`CHURN_LABEL_TARGET = 500`),
      with honest ready/not-ready flags. **Exit met:** an operator can see per-org whether the next
      tracks are buildable.
- *Serves:* de-risks all tracks. Cheap, first, non-negotiable given data readiness is unknown.

#### M5.1 — Analyzer model-provider layer + better local defaults (Track B + spine v1) — COMPLETE (shipped 2026-07-10, as `local-analyzer-sentiment-model`)
> See `docs/planning/local-analyzer-sentiment-model/`. Built via 5 aspects (sentiment-provider-core,
> per-org-resolution, model-packaging, eval-harness-and-card, m5.0-readiness-report), strict TDD.
- [x] Pluggable **sentiment**-provider abstraction (`analysis-engine/src/analyzer/sentiment_providers/`,
      mirrors the embedding/LLM provider layers): `SentimentProvider` ABC + `VaderSentimentProvider`
      (byte-identical default, characterization-locked) + `TransformerSentimentProvider` + factory.
      Per-org opt-in via `OrgAIConfig.sentiment_provider` (default `'vader'`) + `resolve_sentiment_provider`
      (backend + worker mirrors), injected at both sentiment call sites; VADER fallback on any failure,
      per-process single model load. (category/urgency backends deferred to a later M5 slice.)
- [x] Ship a **CPU transformer sentiment** model (`cardiffnlp/twitter-roberta-base-sentiment-latest`,
      3-class) as an **opt-in** provider; **pull-on-first-enable + cached** (lean default image,
      `BAKE_SENTIMENT_MODEL=false`), default stays VADER (byte-stable); documented **air-gapped
      pre-bake** + `HF_HUB_OFFLINE` path in `docs/SELF_HOSTING.md`. (emotion head deferred.)
- [x] **Eval harness + accuracy card** — offline harness + two labeled sets (self-authored public
      n=180 + in-domain n=169) + precision/recall/F1/confusion (reuses the churn-accuracy metric
      pattern); `GET /api/v1/settings/ai/sentiment/accuracy` reads a committed results artifact; card
      on the Settings → AI "accuracy" tab.
- *Serves:* accuracy leadership + offline/zero-cloud + credibility floor. Not data-gated → shipped first.
      **Exit (honest, DISCLOSURE not gate):** on the in-domain set the transformer **marginally beats**
      VADER (macro-F1 **0.552 vs 0.526**, +0.026) but does **not** clear the ambitious +0.05 target
      (it under-recalls `neutral` on flat B2B feedback); on the public set 0.778 vs 0.758. Label order
      verified correct. Per the plan's decision the spine ships regardless, model **off by default**,
      and the card states the honest result (incl. `n`).

#### M5.2 — Corrections flywheel: per-org self-improving classifiers (Track A — flagship moat) — COMPLETE (sentiment shipped 2026-07-11; **category head shipped 2026-07-11**)
> Spine + sentiment + **category head (v2)**; real-org auto-promotion is the later exit — spine proven on synthetic corrections.
- [x] Train a small per-org model (TF-IDF + logistic regression via the installed `scikit-learn`) on the org's feedback + `AICorrection`s, on the worker, CPU, scheduled.
- [x] Per-org **shadow A/B** on held-out corrections; **auto-promote only when the challenger beats the
      incumbent** by a margin; operator sees the delta and can roll back.
- [x] Activates per-org once corrections ≥ the threshold from M5.0. Honesty: "your model, trained on your
      data, promoted only when measurably better."
- [x] **Category head (v2, shipped 2026-07-11 as `per-org-category-classifier`)** — a unified per-org
      **category** classifier (pain-point / feature-request) trained on `AICorrection.correction_type='category'`
      with **dynamic labels from the org's own corrections**; independent `category_classifier_mode`
      (off/shadow/auto, separate from sentiment); in `auto` the predicted label overrides
      `pain_point_category`/`feature_request_category` **only when it maps unambiguously to exactly one
      built-in vocabulary** (else shadow-log only — no silent mis-write); **fair-A/B** — the challenger is
      scored only over labels the keyword incumbent can emit ("evaluated on labels the baseline can
      produce"), so custom-only classes can't rig a promotion; same weekly refit + one-click rollback.
      See `docs/planning/per-org-category-classifier/`. **Deferred (v3):** separate per-kind heads
      (needs recording the corrected field on `AICorrection`), an urgency head, and multi-label per item.
- *Serves:* the self-improving data moat (flagship goal), accuracy, offline. **Exit:** spine proven on synthetic corrections (sentiment + category); real-org exit is deferred.

#### M5.3 — Per-org churn ML model (Track C — data-gated)
- [ ] Upgrade from isotonic calibration to a gradient-boosted / logistic churn classifier per org on
      labeled churn events + features; **activates at ~500 labels** (from M5.0); calibrated heuristic
      remains the fallback below the gate. Reuse the existing precision/recall/F1/AUC churn dashboard.
- *Serves:* churn credibility. **Exit:** for a qualifying org, ML beats the heuristic on backtest with
      the auto-fallback preserved.

#### M5.4 — Local embedding quality (Track D) — parked / nice-to-have
- [ ] Better local embedding model for copilot/template matching (incremental; fully offline).

---

## Plan Gating Summary (Full Year)

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| VADER sentiment + basic categorization | Yes | Yes | Yes | Yes |
| Anomaly detection + alerts | Yes | Yes | Yes | Yes |
| Enhanced 9-factor churn risk | - | Yes | Yes | Yes |
| Customer health scores + 360 page | - | Yes | Yes | Yes |
| Customer sentiment alerts | - | Yes | Yes | Yes |
| Churn explainability (factor breakdown) | - | Yes | Yes | Yes |
| AI Copilot (Cmd+K) | 10/day | 100/day | Unlimited | Unlimited |
| Response templates | - | Yes | Yes | Yes |
| Generated custom responses | - | 50/mo | 500/mo | Unlimited |
| On-demand AI reports | - | - | Yes | Yes |
| Multi-model BYOK | - | - | Yes | Yes |
| HubSpot/CRM enrichment | - | - | Yes | Yes |
| Segment/usage enrichment | - | - | Yes | Yes |
| Industry benchmarks | - | Yes | Yes | Yes |
| Advanced churn (30-day probability) | - | - | Yes | Yes |
| Custom categories/weights | - | - | - | Yes |
| Fine-tuned classification | - | - | - | Yes |
| Workflow automation | - | Basic | Full | Full |

---

## Architecture Notes

### LLM Abstraction Layer (Q2)
```
LLMProvider (interface)
├── OpenAIProvider (GPT-4o, GPT-4o-mini)
├── AnthropicProvider (Claude Sonnet, Haiku)
├── GoogleProvider (Gemini Pro, Flash)
└── FallbackChain (primary → secondary → tertiary)
```

### Processing Model
- **Real-time (no LLM)**: VADER sentiment, keyword churn scoring, anomaly detection, tag extraction
- **On-ingest (lightweight LLM)**: Auto-categorization, churn risk (9-factor)
- **Batch (heavy LLM)**: Weekly insights, churn deep-dive, health score LLM analysis
- **On-demand (streaming LLM)**: Copilot queries, response generation, report generation

### Customer 360 Data Model
```
CustomerProfile
├── Feedback data (Rereflect native): health score, sentiment history, feedback timeline
├── CRM data (HubSpot/Salesforce): company, ARR, deal stage, renewal date
├── Usage data (Segment): login frequency, feature usage, engagement
└── AI signals: churn probability, confidence, risk factors, LLM analysis
```

---

## Cost Projections

| Quarter | Estimated AI Cost | Revenue Offset |
|---------|------------------|----------------|
| Q1 2026 | ~$50/mo (existing + alerts) | BYOK covers LLM costs |
| Q2 2026 | ~$150/mo (copilot queries, response gen) | Pro+ subscription revenue + BYOK |
| Q3 2026 | ~$300/mo (enrichment processing, corrections) | Business+ subscriptions |
| Q4 2026 | ~$500/mo (fine-tuning, benchmarks, automation) | Enterprise contracts + pass-through |

*Costs scale with customer volume. BYOK + usage-based pricing ensures AI costs are covered by revenue.*

---

## Success Metrics

| Metric | Q1 Target | Q2 Target | Q3 Target | Q4 Target |
|--------|-----------|-----------|-----------|-----------|
| Churn prediction accuracy | Baseline established | 60% | 70% | 80%+ |
| Copilot queries/day (avg) | - | 50 | 200 | 500 |
| Customer 360 profiles | 100 | 500 | 2,000 | 5,000 |
| AI-generated responses used | - | 100/mo | 500/mo | 2,000/mo |
| Benchmark participants | - | - | - | 50+ orgs |
| Human corrections collected | - | - | 500 | 2,000 |

---

## Related

- [DEV-TRACKING.md](DEV-TRACKING.md) - Overall development tracking
- [PRD-PREDICTIVE-ANALYTICS.md](PRD-PREDICTIVE-ANALYTICS.md) - Predictive analytics PRD (completed)
