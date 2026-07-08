# Card — Customer Segments (freeform)

**Type:** feat · **Slug:** `customer-segments` · **Branch:** `feat/customer-segments`
**Source:** freeform (no GitHub issue) — handed off from `rereflect-next` on 2026-07-08.

---

## Brief (from rereflect-next handoff)

Build behavioral **Customer Segments** — the last deferred piece of M3.4 (`AI-TRACKING.md:222`).
Auto-group customers into **rule-based cohorts** (e.g. power users, silent churners, happy
advocates) computed from signals that **already exist** — health score, usage rollup
(`customer_usage`), sentiment trend, and recency — **no new ML**. Surface segment as a **column +
filter** on the existing Customers page, and make segments **selectable as targets** in workflow
automation, playbooks, and copilot queries so they multiply across the shipped AI loop.

Slice 1 = segment-definition engine + Customers-page column/filter; automation/copilot targeting
can follow.

## Why (moat / grounding — not invented)

- **Closes the last open piece of the core Customer-Intelligence area.** M3.4 is the only milestone
  still marked **PARTIAL**; unified timeline + Customer 360 API shipped, but "Customer segments"
  remains explicitly deferred — `AI-TRACKING.md:222`. Everything else M1–M4 is `COMPLETE` and the
  OSS batch shipped (`AI-TRACKING.md:94–290`).
- **Multiplier on the moat, not a leaf feature.** Segments become filters/targets for the shipped
  **workflow automation** (`AI-TRACKING.md:263`), **playbooks** (`:242`), **copilot** ("show me
  silent churners", `:137`) and **reports** (`:160`) — deepening the integrated-AI-workflow +
  product-breadth pillars.
- **Unblocked with a clean first slice.** Deferral reason is a design choice (heuristic vs ML), not
  a hard dependency. A rule-based engine over existing signals (health score, usage rollup,
  sentiment trend, recency) fits the honest OSS brand — churn already ships as a *calibrated
  heuristic, stated as such* (`AI-TRACKING.md:240`).

## Caveats to respect from the start

- **Rule-based / heuristic only — NOT ML clustering.** That is exactly why the docs deferred it
  (`AI-TRACKING.md:222`: "heuristic-only today; no ML segmentation"). Acceptable under the OSS
  honesty brand **provided the UI states it plainly** (mirror churn's "calibrated heuristic"
  framing). Do **not** frame it as ML.
- **Reuse existing signals** — health score, `customer_usage` rollup (last_active, active-days,
  feature breadth, `usage_score`), sentiment trend, recency. Don't invent new scores.
- **Alembic multiple-heads:** any new migration inherits the repo-wide 6-heads condition
  (`asana-integration/prd.md:71`). If segments need a table, resolve `merge heads` first.

## Out of scope (initial)

- ML / clustering-based segmentation (KMeans, embeddings, behavioral clustering).
- New ingestion or new external data sources.
- Auto-executing campaigns/actions from segment membership (targeting *hooks* for
  automation/copilot are in-scope follow-on; auto-execution is not).

## Reference points to confirm in Phase 2 dig

- Customers page + list API (health list endpoint, filters) — where the column/filter lands.
- `customer_usage` rollup + `usage_score` (M3.2, shipped 2026-06-29) — a primary signal source.
- Health score service + components (health/sentiment/recency signals).
- Workflow automation trigger/target model (M4.4) + copilot context scopes — the follow-on
  targeting surface.
