# AI Feature Tracking & 1-Year Roadmap

**Product**: Rereflect
**Last Updated**: 2026-04-13
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

#### M3.1 — HubSpot CRM Integration (3 weeks)
- [ ] HubSpot OAuth flow (connect/disconnect)
- [ ] Sync contacts: pull company, deal stage, ARR, contract renewal date, lifecycle stage
- [ ] Match by email: link HubSpot contacts to Rereflect customers (by `customer_email`)
- [ ] Customer 360 enrichment: show CRM data on customer profile (company name, deal value, renewal date)
- [ ] Churn prediction enrichment: add CRM signals to health score (renewal coming up + declining health = critical)
- [ ] Bi-directional sync: push health scores to HubSpot contact properties (custom fields)
- [ ] Plan gate: Business+ feature

#### M3.2 — Segment Product Usage Integration (2 weeks)
- [ ] Segment webhook receiver: receive identify + track events
- [ ] Usage metrics per customer: login frequency, feature usage, session duration, last active
- [ ] Customer 360 enrichment: usage activity section on profile page
- [ ] Health score enrichment: add usage frequency as 5th component (declining usage = warning)
- [ ] Plan gate: Business+ feature

#### M3.3 — AI Trust: Human-in-the-Loop (2 weeks) — COMPLETE
- [x] Feedback on AI outputs: thumbs up/down on copilot answers, health scores, categorizations
- [x] Category correction: user can override AI category → stored as training signal
- [x] Sentiment correction: user can override sentiment label → stored as training signal
- [x] Correction dashboard: AI Accuracy stats tab in AI Settings, accuracy over time
- [x] Health score flag icon on customer profile
- [x] 9 backend + 7 frontend tests
- [ ] Corrections feed into fine-tuning pipeline (M4.2)

#### M3.4 — Enhanced Customer 360 (2 weeks)
- [ ] Unified customer timeline: feedback + CRM events + usage events in chronological order
- [ ] Customer segments: auto-group by behavior (power users, silent churners, happy advocates)
- [ ] Bulk actions: export customer list, bulk assign CS owner, trigger outreach campaign
- [ ] Customer 360 API (for external consumption)
- [ ] Health score API endpoint for programmatic access

**Q3 Deliverables**: HubSpot integration, Segment integration, human-in-the-loop (M3.3 COMPLETE), enriched Customer 360
**Plan Gating**: CRM/usage integrations = Business+, corrections = Pro+

---

### Q4 2026: Enterprise AI & Competitive Moat (Oct-Dec)
> *Theme: Custom models, advanced predictions, industry benchmarks — create switching cost*

**Goal**: Enterprise customers have custom-trained AI. Churn prediction accuracy is demonstrably high. Industry benchmarks create network effects.

#### M4.1 — Advanced Churn Prediction (3 weeks)
- [ ] 30-day churn probability score (percentage, not just risk level)
- [ ] Churn prediction model: train on historical churn data (customers who stopped sending feedback or had subscription cancelled)
- [ ] Churn timeline: "This customer is likely to churn within 2-4 weeks based on: [factors]"
- [ ] Churn cohort analysis: which customer segments have highest churn rate
- [ ] Churn prevention playbooks: automated action plans per risk profile
- [ ] Accuracy tracking: compare predictions vs actual churn, show precision/recall metrics
- [ ] Plan gate: Business+ (Pro gets basic risk level only)

#### M4.2 — Custom AI Models (3 weeks)
- [ ] Custom category configuration (Enterprise): org-specific pain point categories, feature request categories, urgency definitions
- [ ] Custom health score weights: CS teams can adjust component weights (e.g., "sentiment matters more for us")
- [ ] Fine-tuned classification: train per-org classification model on their feedback + corrections (from M3.3)
- [ ] A/B comparison: show fine-tuned vs default model accuracy side-by-side
- [ ] Model versioning: track model performance over time, rollback if accuracy drops
- [ ] Plan gate: Enterprise only

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
