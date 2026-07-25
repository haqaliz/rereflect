# Archived PRDs

Historical product requirement documents for features that have **shipped**. They are kept
here for provenance — several are cited by name and line number from the per-feature planning
records in [`docs/planning/`](../../planning/) and from [`CHANGELOG.md`](../../../CHANGELOG.md).

**These documents are not maintained and are not a source of truth.** Their `Status:` headers
were written before implementation and were never updated, so most still read
`Draft` / `Planned` even though the work is complete. For what actually exists today, read:

- [`AI-TRACKING.md`](../../../AI-TRACKING.md) — AI/ML milestones (M1–M5), what shipped and what was deferred
- [`DEV-TRACKING.md`](../../../DEV-TRACKING.md) — product milestones by phase
- [`CHANGELOG.md`](../../../CHANGELOG.md) — released, user-facing changes
- [`docs/SELF_HOSTING.md`](../../SELF_HOSTING.md) — the operator-facing feature and configuration reference

Note that these PRDs predate the open-source self-hosted pivot, so any plan gating, pricing
tier, or Stripe billing they describe is obsolete — every feature is unlocked.

| PRD | Shipped as |
|---|---|
| `PRD-PREDICTIVE-ANALYTICS.md` | Churn prediction + customer health scores |
| `PRD-TECHNICAL-DEBT.md` | Caching, query optimization, Sentry, health endpoint |
| `PRD-DASHBOARD-V2.md` | Customizable widget grid (20 widgets, 6 categories) |
| `PRD-CUSTOMER-360.md` | M1.2 — `/customers` list + profile pages |
| `PRD-CUSTOMER-SENTIMENT-ALERTS.md` | M1.3 — sentiment alerts |
| `PRD-CHURN-PREDICTION-ACCURACY.md` | M1.4 — churn scoring accuracy |
| `PRD-MULTI-MODEL-SUPPORT.md` | M2.1 — multi-provider LLM abstraction |
| `PRD-AI-COPILOT.md` | M2.2 — copilot command bar + conversations |
| `PRD-AI-RESPONSE-SUGGESTIONS.md` | M2.3 — response suggestions |
| `PRD-ON-DEMAND-AI-REPORTS.md` | M2.4 — on-demand reports |
| `PRD-CUSTOM-WEBHOOKS-AND-TECH-DEBT.md` | M3.1 — custom webhooks |
| `PRD-GDPR-AITRUST-BLOGENGINE.md` | GDPR export/delete, human-in-the-loop corrections, blog scheduling |
| `PRD-REALTIME-EVENTS.md` | WebSocket event push (`events_ws.py`, `useRealtimeEvents`) |
| `PRD-ADVANCED-CHURN-PREDICTION.md` | M4.1 — calibrated probabilities, cohorts, playbooks |
| `PRD-AI-WORKFLOW-AUTOMATION.md` | M4.4 — automation rules engine |
| `PRD-LOCAL-LLM-CUSTOM-AI-PUBLIC-API.md` | Open-source feature batch (local LLM, custom AI, public API) |
| `PRD-OSS-SELF-HOSTED-PIVOT.md` | The MIT / BYOK / self-hosted pivot itself |
| `PRD-promo-code-system.md` | Superseded — Stripe-backed, retired by the OSS pivot |
| `PRD-admin-promo-management.md` | Superseded — Stripe-backed, retired by the OSS pivot |
