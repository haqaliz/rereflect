# Card — feat/per-org-churn-model (freeform, no GitHub issue)

Source: `rereflect-next` recommendation (2026-08-14), grounded in `AI-TRACKING.md` M5.3
and the M5 strategic framing. Branch `feat/per-org-churn-model`, worktree
`.claude/worktrees/feat-per-org-churn-model`.

## Brief

Build M5.3 ("Per-org churn ML model", `AI-TRACKING.md:521-573`) with the **gate
re-derivation as slice 1**: re-derive the per-org label threshold from single-tenant
reality via a simulation/learning-curve harness in the M5.1/M5.4 eval-card style, since
the current 500-label/org figure is a stale pre-pivot copy that the roadmap itself flags
as under review (`AI-TRACKING.md:542-553`). Then build the gradient-boosted/logistic
churn spine per-org on churn-event/feature data, A/B-shadowed against the calibrated
heuristic, auto-promoting only on measurable gain with one-click rollback and the
heuristic as automatic fallback (the M5.2 pattern).

## Caveat (carried into the PRD, must not be papered over)

- There is **no real org at label volume** (self-hosted, no production data). Any
  "beats the heuristic" claim starts from simulation, and the M5.3 exit stays conditional
  on a qualifying org.
- Keep the "churn = calibrated heuristic" honesty framing throughout; the calibrated
  heuristic remains the current truth either way.
- The 500-label/org gate is **not settled**: `CHURN_LABEL_TARGET = 500` was copied
  verbatim from the pre-pivot hosted PRD (`PRD-ADVANCED-CHURN-PREDICTION.md:463`), and
  half of its original criterion ("≥ 5,000 globally") is meaningless single-tenant.

## Roadmap facts (from AI-TRACKING.md, cited)

- M5.3 status: "M5.3 planned" (`AI-TRACKING.md:440`); the only unshipped milestone in
  the M5 block (M5.0/M5.1/M5.2/M5.4 are COMPLETE).
- M5.3 scope (`AI-TRACKING.md:521-526`): upgrade from isotonic calibration to a
  gradient-boosted / logistic churn classifier per org on labeled churn events +
  features; activates at ~500 labels (from M5.0); calibrated heuristic remains the
  fallback below the gate; reuse precision/recall/F1/AUC churn dashboard. Exit: for a
  qualifying org, ML beats the heuristic on backtest with the auto-fallback preserved.
- Recommended follow-up (`AI-TRACKING.md:551-553`): "an M5.3-scoped re-derivation of the
  gate from single-tenant data before anyone builds against the number."
- Label sources now live (`AI-TRACKING.md:528-573`): manual ("Mark as churned" + CSV
  import), CRM lost renewals (`crm-churn-labels`, shipped 2026-07-15), usage decline
  (`usage-decline-churn-labels`, shipped 2026-07-24). Suggestions are confirm-in-review;
  `pending_suggestions` excluded from `churn_labels_ready`.
- `churn_labels_ready` gates on `churn_labels_trainable` (excludes `auto_suggested`
  events the calibrator never trains on) — CHANGELOG.md:750-757.
- M5 cross-cutting principles (`AI-TRACKING.md:453-455`): CPU-only; default analyzer
  paths byte-stable; every model swap A/B-gated and reversible; no central data; models
  small and described honestly.
- M5.2 pattern to reuse (`AI-TRACKING.md:493-519`): per-org shadow A/B on held-out data,
  auto-promote only on measurable margin (macro-F1 ≥ +0.02), operator sees the delta,
  one-click rollback, weekly refit, activation thresholds surfaced via the M5.0
  readiness report (`GET /api/v1/analytics/ai-readiness`).

## Deliverables (proposed, refine in PRD)

1. Re-derive the label gate (slice 1): simulation + learning-curve harness, committed
   eval artifact + accuracy card in the M5.1/M5.4 style; documented decision.
2. Per-org churn model spine: logistic/GBM per org, shadow A/B vs the calibrated
   heuristic, auto-promote only on measurable gain, rollback, heuristic fallback.
3. Honest UI: readiness/accuracy surface per the M5.0/M5.2 pattern.

## Out of scope (guardrails)

- No cross-tenant data / no benchmarks (M4.3 DROPPED — `AI-TRACKING.md:388-402`).
- No per-org fine-tuning of the BYOK LLM.
- No plan gates; everything unlocked.
- No claims about churn-prediction quality beyond what the eval artifact measures.
