# PRD — Batch sentiment threshold trigger

**Slug:** `batch-sentiment-trigger` · **Branch:** `feat/batch-sentiment-trigger`
**Type:** feat · **Created:** 2026-07-29 · **Card:** `../_card/card.md` · **DEV-TRACKING P1**

---

## Problem Statement

A v1.0.0 user asked to be pinged when *"a batch of new feedback crosses a certain sentiment
threshold."* Rereflect cannot express that today.

The closest trigger, `sentiment_pattern`, fires when **one customer** sends ≥`count`
feedbacks of a sentiment within `days`. It answers *"is this account souring?"*. The user is
asking *"did our incoming feedback as a whole just get worse?"* — an aggregate question.

**These are genuinely different signals.** A spike of 30 angry feedbacks from 30 different
customers — the textbook triage emergency — trips `sentiment_pattern` zero times, because no
single customer reaches `count`. The user's stated goal ("make triaging way faster") is
exactly the case the product cannot detect.

This will be the **first org-wide trigger**. Every existing one is per-customer, and that
assumption is baked into the cooldown key, the execution row, and the action executors.

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| Aggregate sentiment shifts are detectable | A window where negative share crosses the threshold produces an `AutomationExecution` |
| No false alarms from tiny samples | A window with 2 negative of 3 total does **not** fire when the sample floor is unmet |
| Both threshold shapes work | Percentage-based and absolute-count rules each fire on their own terms |
| It cannot silently never-fire | A seam test asserts the call site actually invokes the evaluator |
| One alert per crossing | A sustained breach produces one execution per cooldown period, not one per feedback item |

---

## Requirements

### Must-have

- **R1 — New trigger type `batch_sentiment_threshold`**, registered at **all** points below.
- **R2 — Config shape**, validated by a new `BatchSentimentConfig`:

  | Field | Type | Default | Meaning |
  |---|---|---|---|
  | `sentiment` | str | `"negative"` | Which sentiment to measure |
  | `window_hours` | int 1-168 | `24` | Trailing window |
  | `mode` | `"percentage"` \| `"count"` | `"percentage"` | Which threshold shape |
  | `threshold` | float | `0.5` | Share (0-1) when percentage, absolute count when count |
  | `min_total` | int ≥1 | `5` | **Sample floor** — below this the rule never fires |

  Use `model_config = {"extra": "forbid"}`, following `UsageTrendConfig` — it is the only
  config model that rejects unknown keys, and a silently-ignored typo'd threshold is exactly
  the failure this feature must not have.
- **R3 — `min_total` is mandatory, not optional.** A percentage threshold without a sample
  floor is a false-alarm generator: 2 negative of 3 is 67%. Default `5`, never `0`.
- **R4 — Evaluate in the existing per-item seam** (`evaluate_feedback_triggers`, called from
  `analysis.py:201`). See *Technical Considerations* for why this beats a new Celery beat
  task, contra the dig's recommendation.
- **R5 — Cooldown identity.** The key is
  `automation_cooldown:{rule_id}:{customer_email}`. An org-wide rule has no customer. Pass an
  explicit sentinel as the cooldown identity rather than inheriting today's empty-string
  degeneration. **Do not** let it be written into `AutomationExecution.customer_email` —
  an org-wide execution must log `NULL` there, as it already does via `customer_email or None`.
- **R6 — Short-circuit before the aggregate query.** Check cooldown first, and skip entirely
  unless the item in hand matches the configured sentiment. Without this, every analysed item
  runs a `COUNT` over the window for every matching rule.
- **R7 — Seam test.** Mirror `worker-service/tests/test_usage_trend_trigger_seam.py`: assert
  the call site genuinely invokes the evaluator. This is the test class that catches the
  "silently never fires" bug this repo has now shipped three times.
- **R8 — Ship the template in `mode: "shadow"`**, following `usage_decline_outreach`. Nobody
  knows this trigger's firing rate on real data. Note the subtlety at `automations.py:515-523`:
  the handler must set `mode` and **not** pass `is_active=True`, because `is_active` is a
  write-through alias whose validator *promotes* shadow to active.

### Registration points (miss one and it 422s or silently never fires)

| # | File | What |
|---|---|---|
| 1 | `backend-api/src/api/routes/automations.py:49-56` | add to `VALID_TRIGGER_TYPES` |
| 2 | same, `TriggerSchema.validate_trigger` if-chain (203-226) | **has no `else`** — a type in the set but not the chain persists an unvalidated config |
| 3 | same, new `BatchSentimentConfig` model | alongside the other per-trigger models |
| 4 | `worker-service/src/services/automation_feedback_trigger.py:66` | add to `FEEDBACK_TRIGGER_TYPES` |
| 5 | same, `_check_trigger` if-chain (271-282) | new `_trigger_batch_sentiment` |
| 6 | `backend-api/src/config/automation_templates.py` | new template, `mode: "shadow"` |
| 7 | `frontend-web/lib/api/automations.ts:5-11` | `TriggerType` union |
| 8 | same, `TRIGGER_TYPE_LABELS:135-142` | TS enforces this — missing label is a compile error |
| 9 | `settings/automations/new/page.tsx` | `TriggerConfigFields` chain, `triggerDefaults`, `TRIGGER_DEFAULT_MODE`, pre-submit validation |
| 10 | `settings/automations/[id]/page.tsx` | the same four surfaces, duplicated |
| 11 | `docs/SELF_HOSTING.md:566-624` | per-trigger operator section, as `usage_trend` has |
| 12 | `CHANGELOG.md` | enumerates trigger types |
| 13 | both `automation_rule.py` model comments | already stale (missing `usage_trend`); non-functional |

### Out of scope

- Changing the cooldown key scheme in all four evaluator modules. R5 solves this locally.
- Fixing `seed_churn_cooldowns` for level-based triggers — document the choice, follow the
  `usage_trend` precedent of explicitly refusing to extend it (shadow-default covers it).
- Discord delivery (DEV-TRACKING P2) and the per-import batch interpretation (rejected).
- **The `[id]/page.tsx` config-key bug found during the dig — see Risks #4.** Separate defect.

---

## Technical Considerations

### Why the per-item seam, contra the dig

The dig recommended a dedicated Celery beat task, calling per-item evaluation "fragile".
Rejecting that, for three reasons:

1. **The action executors need a feedback object.** `auto_assign`, `change_status` and
   `draft_response` all return `{"error": "No feedback object"}` when `feedback is None`
   (`_execute_assign:448`, `_execute_change_status:490`, `_execute_draft_response:703`), which
   makes the execution row `failed` on **every** fire. The per-item seam has a real feedback
   item in hand — the one that tripped the threshold — so all four actions work and the
   execution log links somewhere meaningful.
2. **A new evaluator is a fifth dispatch path with its own rule-selection query** — one more
   thing that can silently stop firing. This session has fixed that exact bug class three
   times. Reusing a seam that is now covered by a seam test is the lower-risk choice.
3. **Alert latency.** A triage alert that arrives on the next beat tick is worth less than one
   that arrives on ingest.

The dig's real objection — N aggregate queries per batch — is answered by R6: cooldown check
and sentiment pre-filter both short-circuit before the `COUNT`.

**Accepted trade-off:** the rule fires on the *first* item that crosses the threshold, then
self-suppresses for `cooldown_hours`. That is the desired behaviour for an alert, but it is
worth stating that it is a design choice and not an accident of the shared cooldown key.

### Other

- **No Alembic migration.** `trigger_type` is a plain `String(50)` with no enum or CHECK
  constraint in either the backend or worker model.
- **No new delivery code.** Reuses the notification channels, including the Slack channel
  shipped in `52c763dd`.
- **Template contract test is automatic**: `test_automation_template_usage_trend.py:95-99` is
  parametrized over every template and asserts its config passes `TriggerSchema`, so a bad new
  template fails CI without new test code.
- **No plan gate.** `SELF_HOSTED=true`.

---

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| 1 | Activation stampede — enabling a rule while the org is already over threshold fires immediately. `seed_churn_cooldowns` only seeds `churn_probability_threshold`. | Shadow-by-default (R8). Document, following the `usage_trend` precedent. |
| 2 | Cooldown collision. Today an empty `customer_email` degenerates to one shared key per rule — which happens to be the right semantic here, but by accident. | R5 makes it explicit. |
| 3 | Noisy in high-volume orgs; a 24h window at 50% may fire constantly. | `min_total` floor + shadow-first + configurable window. |
| 4 | **Pre-existing bug found during the dig (not ours):** `[id]/page.tsx`'s `CategoryMatchTriggerFields` reads/writes `config.tags` and `config.urgent` (lines 96, 145), while `new/page.tsx` and the backend's `FeedbackCategoryConfig` use `categories` / `is_urgent`. **Editing an existing category-match rule via the detail page writes keys the backend ignores.** Do not copy this shape. Logged for DEV-TRACKING. |
| 5 | Enabling a template twice creates duplicate rules — `enable_template` has no uniqueness check. | Pre-existing; out of scope; do not assume idempotency in tests. |

**Open questions**
- Should `batch_sentiment_threshold` restrict which actions are allowed? The per-item seam
  makes all four work, so *no restriction is needed* — but a user may still find
  "auto-assign the one item that happened to trip an org-wide threshold" surprising.
  *Leaning: allow all, document the semantic.*
- Is a 168-hour (7-day) max window enough, or should it reach 30 days like `sentiment_pattern`'s
  `days`? *Leaning 168h: beyond a week this stops being a triage alert and becomes a trend
  report, which `/analytics` already does.*

---

## Self-critique (Phase 4)

- 🔴 **No evidence about firing rate on real data.** Every threshold default here
  (`0.5`, `min_total=5`, `24h`) is reasoned, not measured. Shadow-by-default is the mitigation,
  but the PRD should not pretend the defaults are calibrated. They are a starting point for the
  operator to tune, and the docs must say so.
- 🟡 **"One alert per crossing" is asserted, not proven** for the case where an org has
  multiple matching rules with different windows — they will fire independently and could
  triple-alert. Not wrong, but worth a test.
- 🟢 Registration surface is exhaustively enumerated; the seam decision is argued rather than
  assumed.

**The question I'd want answered before greenlighting:** the user asked for this to triage
faster — but if the alert fires on the first item that crosses a 24-hour aggregate threshold,
is that actionable, or does it just tell them something they'd see anyway when they open the
dashboard an hour later?
