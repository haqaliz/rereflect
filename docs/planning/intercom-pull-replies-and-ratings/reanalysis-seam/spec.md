# Aspect spec — Re-analysis seam (verify + reuse)

**Feature:** `intercom-pull-replies-and-ratings` (prd.md R4) · **Aspect:** `reanalysis-seam`

## Problem slice

Enriched items must be re-analyzed so sentiment/categories/churn reflect the full
thread — but the analysis task skips already-analyzed items by default
(analysis.py:166-168). The pull needs the same force path the UI "re-analyze" action
uses, with identical semantics.

## In-scope

- **Verify (plan task 0)** how the UI re-analyze action re-analyzes a feedback item:
  trace the frontend action → API route → worker task (or direct service call), and
  whether it uses a force flag on `analyze_single_feedback` or a separate path.
- Expose/confirm a callable seam the pull can use from the sync task: given a feedback
  id, run the full analysis pipeline (sentiment, categorization, churn factors,
  health recompute when `customer_email` present) exactly as a manual re-analyze would.
  If the seam already exists (e.g. a `force` flag or a dedicated re-analyze task),
  reuse it — do not build a parallel pipeline.
- **Bounded dispatch:** the pull must call the seam only for items that gained new
  content (the enrichment returns the changed ids); unchanged items never dispatch.
- Tests: (a) the seam's force semantics pinned (re-analyze on an already-analyzed item
  refreshes its analysis; without force it skips); (b) a seam test in the pull's style
  asserting dispatch happens for changed items and NOT for unchanged ones (the
  "silently never fires" guard family).

## Out of scope

- Changing the analysis pipeline itself; analysis content/quality; the UI.

## Acceptance criteria (testable)

1. Plan task 0 records which seam the UI uses (file:line).
2. The pull-facing entry point reuses that seam — characterization: a manual re-analyze
   and the pull's re-analysis produce identical analysis results for the same item.
3. Seam tests: changed → dispatched once; unchanged → never dispatched; re-analysis of
   an already-analyzed item actually refreshes the stored analysis.
4. Worker suite green.

## Dependencies & sequencing

- After the adapter aspect (needs the merge that produces "changed" content).
- Consumed by `pull-enrichment` (which calls the seam).
- Small aspect — verification-first.

## Open questions / risks

- If no force seam exists (the UI may re-analyze via a different mechanism), the plan
  must add the minimal force flag to the existing task — TDD, behavior-identical to a
  fresh analysis, and flag it in the plan rather than silently building a parallel path.
