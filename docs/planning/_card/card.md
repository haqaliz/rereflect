# Card — churn-triggered-playbooks (freeform feat, no GitHub issue)

**Type:** feat
**Slug:** churn-triggered-playbooks
**Branch:** feat/churn-triggered-playbooks
**Source:** Freeform task selected via `rereflect-next` (see brief below). No GitHub issue.

## Brief (from rereflect-next handoff)

Build **churn-triggered playbook auto-execution** — the deferred M4.1.5 slice from
`PRD-ADVANCED-CHURN-PREDICTION.md:465`:

> "Real-time playbook execution on probability threshold cross. v1 supports manual
> trigger + run-batch only. Auto-execution on threshold cross is M4.1.5."

When a customer's churn probability / health score crosses a per-org configured
threshold, automatically run a designated churn playbook — reusing the shipped
playbook `run-batch` execution and the existing per-org threshold-eval task in
`services/worker-service/src/tasks/alerts.py`.

### First testable slice
A single per-org rule (threshold + playbook id) evaluated on the existing
health/alert recompute tick, firing **once per crossing** via a stored last-fired
guard + cooldown (idempotent — never re-run while the customer stays above
threshold), emitting a `playbook_auto_run` timeline event.

### Framing / constraints
- Treat "real-time" as "on the next eval tick," **not** literally instant.
- Scope the first slice to **SMTP-free** playbook actions (create ticket / tag /
  assign owner). Gate any email-sending action behind configured operator SMTP —
  that's why the segment-actions outreach-campaign slice was deferred
  (`AI-TRACKING.md:228`).
- Everything it depends on has already shipped: churn scores + calibrated
  probability (M4.1, `AI-TRACKING.md:242`), health scores + alerts (M1.3),
  playbooks + run-batch / cohort (segment-actions, `AI-TRACKING.md:228`), and a
  per-org threshold-evaluating Celery task system (`worker-service/src/tasks/alerts.py`).
  This is integration + a small config surface, not net-new subsystems.

### Moat rationale
Dead-center of the stated moat: hardens the churn → health → playbook → automation
loop. Fits OSS/self-hosted/BYOK (pure server-side automation, no SaaS / cross-tenant
/ billing dependency).

### Known caveats to resolve in the dig / PRD
1. "Real-time" = on the next eval tick (health recompute cadence), not instant.
2. Crossing-detection idempotency is the core risk: fire once per crossing with a
   cooldown, using a stored "last-fired state" guard (same shape as the status-sync
   baseline-seed pattern). Never re-run while a customer sits above threshold.
3. Email-sending playbook actions need operator SMTP → first slice targets
   SMTP-free actions or gates email behind SMTP config.

**NOTE:** CLAUDE.md's billing / plan-gating / Stripe / Resend sections are STALE
(pre-OSS-pivot). All features are unlocked (MIT, self-hosted, BYOK). Do not gate
this feature behind a plan tier.
