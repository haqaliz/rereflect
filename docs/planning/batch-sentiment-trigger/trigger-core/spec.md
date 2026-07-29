# Spec — `trigger-core`

**Parent PRD:** `../prd.md` · Single aspect, three parallel tracks (backend / worker / frontend)

## THE CONTRACT (all three tracks implement against this — do not deviate)

Trigger type string: **`batch_sentiment_threshold`**

```jsonc
{
  "sentiment":    "negative",   // "negative" | "neutral" | "positive"
  "window_hours": 24,           // int, 1..168
  "mode":         "percentage", // "percentage" | "count"
  "threshold":    0.5,          // percentage mode: 0<x<=1 share. count mode: >=1 absolute
  "min_total":    5             // int >=1. Sample floor. NEVER 0.
}
```

**Firing rule** — evaluated over the org's `FeedbackItem` rows with
`created_at >= now - window_hours`:

```
total    = count(all feedback in window)
matching = count(feedback in window with sentiment_label == config.sentiment)

if total < min_total:              -> DO NOT FIRE     (sample floor)
if mode == "percentage":           -> fire when matching / total >= threshold
if mode == "count":                -> fire when matching >= threshold
```

**Short-circuit order (performance, PRD R6) — check in exactly this order:**
1. cooldown → skip
2. the feedback item in hand does not have `sentiment_label == config.sentiment` → skip
3. only then run the aggregate `COUNT` queries

**Cooldown identity (PRD R5).** The shared key is
`automation_cooldown:{rule_id}:{customer_email}`. This trigger is org-wide, so it must use a
single per-rule key. Pass the sentinel `"__org__"` as the **cooldown identity only**.
`AutomationExecution.customer_email` must still be written as `NULL` for an org-wide fire —
do **not** let `"__org__"` reach the row. The existing `customer_email or None` handles a
real email; the sentinel must be kept out of that path explicitly.

**Sentiment values** must match how `sentiment_label` is stored on `FeedbackItem`
(`"negative"` / `"neutral"` / `"positive"`) — verify against the model, do not assume.

---

## Track A — backend (`services/backend-api`)

- **A1** Add `"batch_sentiment_threshold"` to `VALID_TRIGGER_TYPES`
  (`src/api/routes/automations.py:49-56`).
- **A2** Add `BatchSentimentConfig` alongside the other per-trigger config models (~75-149),
  with `model_config = {"extra": "forbid"}` (follow `UsageTrendConfig:120` — the only one that
  rejects unknown keys; a silently-ignored typo'd threshold is the failure this must not have).
  Validate: `sentiment` in the 3 values; `window_hours` 1..168; `mode` in the 2 values;
  `min_total` >= 1; `threshold` > 0, and <= 1 when `mode == "percentage"`.
- **A3** Add the `elif` branch to `TriggerSchema.validate_trigger` (~203-226).
  **⚠️ A1 without A3 persists a completely unvalidated config — the chain has no `else`.**
- **A4** New template in `src/config/automation_templates.py`, copying the shape of
  `usage_decline_outreach` (147-174) including **`"mode": "shadow"`**. Actions:
  `send_notification` to admins on `["dashboard", "email"]`. Cooldown 24h.
- **A5** Tests: 201 on valid create, 422 on each invalid field, 422 on an unknown extra key
  (proves `extra: "forbid"`), and the template's config passing `TriggerSchema`.
  Precedents: `tests/test_automations_api_usage_trend.py`, `tests/test_automations.py`.
- **A6** Add a no-op assertion to `tests/test_automations_activation_seeding.py` — this
  trigger is **not** seeded by `seed_churn_cooldowns` (deliberate; shadow-default covers the
  activation stampede, following the `usage_trend` precedent).

**Do NOT** add a trigger checker to `backend-api/src/services/automation_engine.py` — its
feedback-trigger checkers are dead in production (see the comment block at 246-261). The
worker mirror is what evaluates this.

## Track B — worker (`services/worker-service`)

- **B1** Add `"batch_sentiment_threshold"` to `FEEDBACK_TRIGGER_TYPES`
  (`src/services/automation_feedback_trigger.py:66`) and update the comment above it.
- **B2** New `_trigger_batch_sentiment(cfg, context, db)` implementing THE CONTRACT exactly,
  wired into the `_check_trigger` chain (~271-282).
- **B3** Cooldown identity per THE CONTRACT — `"__org__"` for the key, `NULL` on the
  execution row.
- **B4** Tests in `tests/test_automation_feedback_trigger.py`:
  fires at threshold; does **not** fire below; does **not** fire when `total < min_total`
  (the false-alarm case: 2 negative of 3 = 67% but under the floor); `count` mode fires on
  absolute count; window boundary excludes older items; cooldown suppresses a second fire;
  shadow mode logs `status="shadow"` and runs no actions; the execution row has
  `customer_email IS NULL`.
- **B5** Seam test (PRD R7) — mirror `tests/test_usage_trend_trigger_seam.py`: assert
  `analysis.py` genuinely invokes the evaluator. **This is the test class that catches the
  "silently never fires" bug this repo has shipped three times.**

## Track C — frontend (`services/frontend-web`)

- **C1** `lib/api/automations.ts`: add to the `TriggerType` union (5-11) and to
  `TRIGGER_TYPE_LABELS` (135-142) as `'Batch Sentiment Threshold'`. The `Record<TriggerType,
  string>` type makes a missing label a compile error — good.
- **C2** `settings/automations/new/page.tsx`: config fields in the `TriggerConfigFields`
  chain, an entry in `triggerDefaults` (~394-402) matching THE CONTRACT defaults, and
  `TRIGGER_DEFAULT_MODE` (~351-353) set to `'shadow'`.
- **C3** `settings/automations/[id]/page.tsx`: the same four surfaces (they are duplicated).
  **⚠️ If your config UI needs `useState`, extract it into its own component** — see the
  rules-of-hooks warning at `[id]/page.tsx:82-88`. A stateless field group may stay inline.
- **C4** **Do NOT copy `CategoryMatchTriggerFields` in `[id]/page.tsx`.** It reads/writes
  `config.tags` / `config.urgent` while the backend uses `categories` / `is_urgent` — a
  pre-existing bug (PRD Risk 4). Use the exact key names from THE CONTRACT.
- **C5** Tests following `__tests__/new-usage-trend-trigger.test.tsx` and
  `id-usage-trend-trigger.test.tsx`. Note those suites mock `TRIGGER_TYPE_LABELS` with a
  **partial** literal — add the new key to the mocks or the type won't appear in those tests.

## Acceptance criteria

1. `POST /api/v1/automations` with a valid batch config → 201; the rule persists.
2. Same with `threshold: 2.0` and `mode: "percentage"` → 422.
3. Same with an unknown extra key → 422.
4. Window with 6 of 10 negative, threshold 0.5, min_total 5 → **fires**.
5. Window with 2 of 3 negative (67%), min_total 5 → **does not fire**.
6. `count` mode, threshold 3, 4 negative → fires.
7. Second qualifying item within `cooldown_hours` → no second execution.
8. Shadow rule → `status="shadow"`, `actions_executed == []`.
9. Org-wide execution row has `customer_email IS NULL`.
10. Seam test proves `analysis.py` calls the evaluator.
11. Existing trigger types are unaffected (all current suites still pass).

## Test commands

```
cd services/backend-api  && ./venv/bin/pytest tests/test_automations.py tests/test_automations_api_usage_trend.py tests/test_automation_template_usage_trend.py tests/test_automations_activation_seeding.py -v
cd services/worker-service && SENTRY_DSN="" ./venv/bin/pytest tests/ -q     # baseline 1380 passed
cd services/frontend-web && pnpm test    # pnpm workspace; install from REPO ROOT if needed
```
