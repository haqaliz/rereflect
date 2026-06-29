# Card — Product Usage Enrichment (freeform)

**Type:** feat
**Slug:** product-usage-enrichment
**Branch:** feat/product-usage-enrichment
**Source:** freeform task (no GitHub issue) — picked by `rereflect-next` as the next highest-leverage feature.
**Roadmap ref:** AI-TRACKING.md M3.2 — "Segment Product Usage Integration" (pending); DEV-TRACKING.md integration backlog.

---

## Brief (from the rereflect-next handoff)

Build **product-usage enrichment** for Customer 360 + churn (AI-TRACKING M3.2).

**First slice:** a Segment-compatible usage-event webhook receiver (`identify` / `track` schema)
that writes per-customer usage metrics (login frequency, feature usage, last-active),
surfaced as a usage section on the customer profile, and wired as a real component into the
health / churn score.

**Self-hosted-first:** accept any CDP or custom backend POSTing the event schema — no vendor
OAuth required. An operator points Segment *or* their own backend at the instance.

---

## Why this was picked (moat + shipped-state grounding)

- **Fills the biggest gap in the killer feature.** AI-TRACKING's stated killer feature is
  "churn prediction that actually works," yet `services/backend-api/src/services/health_score_service.py:64`
  shows the only usage-like component ("frequency") is just **feedback cadence** — a weak proxy.
  Real product-usage signal (declining logins = the canonical churn predictor) is **absent**.
  This is the highest-leverage signal to add to the churn → health → playbook loop.
- **Best OSS / self-hosted fit of the pending set.** A webhook receiver (operator points
  Segment or any CDP / their own backend at the instance) has far lower setup friction than
  HubSpot's OAuth-app-registration flow, and avoids vendor lock-in. Listed as M3.2 in both
  AI-TRACKING and DEV-TRACKING.
- **Unblocked, depth-first, clear first slice.** First slice = a usage-event ingest endpoint
  (identify/track schema) + a per-customer usage metrics model, testable immediately — no
  dependency on the other Q3 items. (Enhanced-360's timeline, M3.4, is half-blocked until an
  enrichment source like this exists.)

## Known caveat (carried into the dig + PRD)

- The health-score weights config currently validates **4 components summing to 100**
  (`health_weight_frequency` etc., in `health_score_service.py`). Adding a usage component
  means a **migration + re-validating the weight sum**, and a decision on whether usage
  **replaces or supplements** the existing feedback-"frequency" component (don't double-count).
- Usage enrichment only helps orgs that actually emit usage events. For everyone else the
  component must **degrade to a neutral score gracefully** (mirror the embedding-resolver's
  degrade-to-None pattern) — never tank an org's health to zero just because they emit no
  usage events.

## Out of scope (initial slice — confirm in PRD)

- HubSpot / CRM enrichment (M3.1) — separate feature.
- Full Segment OAuth / Connections API management UI — the receiver is a plain authenticated webhook.
- Enhanced Customer 360 unified timeline (M3.4) — downstream; this slice provides the usage source it needs.

## Open questions for the interview

1. Auth model for the webhook: reuse the existing public-API key (ingest scope) or a dedicated usage-source secret?
2. Usage component: replace the feedback-"frequency" component, or add a 5th component and re-weight?
3. What minimal usage metrics define the first slice (login frequency, last-active, feature-usage count)?
4. Event schema: accept Segment `identify`+`track` verbatim, or a normalized subset?
5. Customer matching key — `customer_email` (existing) vs Segment `userId`/`anonymousId`.
