# Aspect Spec — frontend-trend-and-weights

Parent PRD: `../prd.md`

## Problem slice & outcome

Two frontend-only slices, both about making a shipped-but-invisible capability reachable.

**(A) The trend is computed but never shown.** `trend-detection-and-health` puts
`usage_trend_state` / `usage_trend_pct` on the usage API response; without a UI they exist only
for API callers. Worse, the trend needs ~14 days of snapshots before it can say anything, so a
freshly-installed operator would look at an unchanged Usage Activity card and reasonably conclude
the feature is broken. PRD "Rollout & adoption" makes warm-up legibility an explicit obligation:
the `insufficient_history` state must be visible in the UI, not just the API.

**(B) The usage weight is editable nowhere, and saving weights destroys it (D4).** The backend has
accepted six weights since M3.2/M3.1; the editor sends four. Because the PUT model defaults
omitted keys to `0`, **every save from the UI silently zeroes the org's `usage` and `crm`
weights** — live data loss against two shipped features, with no error and no warning.

Outcome: an operator can see whether a customer's usage is stable, declining, or still warming up;
and an operator can set the usage weight from the UI without destroying their CRM weight in the
process.

## Evidence (observed, verified in this worktree)

Paths relative to `services/frontend-web/` unless noted.

### (A) The usage card

- `UsageActivityCard` is declared **inline** in the profile page
  (`app/(dashboard)/customers/[email]/page.tsx:476`) and rendered at `:802`. It is not a component
  file; there is no separate module to edit.
- It fetches with `useQuery({ queryKey: ['customer-usage', email, days], queryFn: () =>
  customersAPI.getUsage(email, days) })` (`:479-484`), with `days` held in local state at `30`
  (`:477`) — the setter is never called, so the card is permanently a 30-day query.
- `UsageTimeline` (`components/customers/UsageTimeline.tsx:24-32`) is embedded inside the same
  card (`page.tsx:539`) and issues **the same query key** `['customer-usage', email, days]` with
  its own `days` state, switchable to 30/60/90 (`UsageTimeline.tsx:21-25, 45-57`). So the two
  share a cache entry only while both sit at 30; selecting 60d or 90d in the timeline creates a
  second cache entry that the card does not read.
- The card's empty state is gated on `hasUsage = rollup && (login_count_30d > 0 ||
  active_days_30d > 0)` (`page.tsx:498`); when false it renders the "No product-usage events
  recorded yet… `POST /api/v1/webhooks/usage`" copy (`:511-518`). `UsageTimeline` renders a
  near-identical empty message independently (`UsageTimeline.tsx:67-76`), so the "nothing here"
  message already appears twice in one card.
- `UsageRollup` (`lib/api/customers.ts:155-169`) has no trend fields today;
  `CustomerUsageResponse` is `{ rollup, time_series, period_days }` (`:173-177`).

### (B) The weights editor (D4)

- `HealthWeights` is a **four-key** type (`lib/api/categories.ts:24-29`).
  `HealthWeightsResponse extends HealthWeights` and adds `usage` (`:31-37`) — so the GET already
  carries `usage`, and the editor already discards it.
- `updateHealthWeights(data: HealthWeights)` PUTs that four-key object verbatim
  (`lib/api/categories.ts:65-68`). Neither `usage` nor `crm` is ever sent.
- The backend `HealthWeightsUpdate` declares `usage: int = Field(default=0, ge=0, le=100)` and
  `crm: int = Field(default=0, ge=0, le=100)`
  (`services/backend-api/src/api/routes/categories.py:150-151`), with sum-to-100 across **all six**
  keys (`:153-158`), and unconditionally persists `config.health_weight_usage = data.usage` and
  `config.health_weight_crm = data.crm` (`:201-202`).
- **Consequence, verified end to end:** an org configured via the API with e.g.
  `usage=10, crm=10` and the four base weights summing to 80 will, the moment an admin presses
  Save in the UI, have that payload rejected (the four keys sum to 80, not 100) — and once the
  admin adjusts the base weights to sum to 100 to get past the error, the save succeeds and
  **writes `usage = 0` and `crm = 0`**. The opt-in is destroyed silently, with a success toast.
  This is live data loss affecting M3.2 (usage) and M3.1 (CRM). **Fixing only `usage` leaves the
  identical bug in place for `crm`.**
- The sum check is four-key: `const total = weights.churn + weights.sentiment +
  weights.resolution + weights.frequency` (`components/settings/HealthWeightsEditor.tsx:51`),
  feeding `isValid = total === 100` (`:53`), the sum indicator (`:117-127`) and the save gate
  (`:139`).
- The form renders by iterating `Object.keys(weights)`
  (`HealthWeightsEditor.tsx:93`), so field order and field set follow the state object; labels and
  descriptions are keyed maps at `:17-22` and `:24-29`, and `DEFAULT_WEIGHTS` at `:10-15`.
- The editor is mounted in exactly one place: `app/(dashboard)/settings/ai/page.tsx:378`
  (imported `:30`), inside the "Health Score Weights" card.

### Stale in-product copy

- `app/(dashboard)/settings/usage-events/page.tsx:208-216` tells operators to go to
  **Settings → Preferences** and raise the Usage Activity weight ("the five weights must sum to
  100"), linking `/settings/preferences`. That page contains no weight editor.
- `components/customers/ComponentProgressBars.tsx:32` repeats the same claim in a code comment
  ("Usage is 0 until an operator opts in via Settings → Preferences"); the same phrasing also sits
  in `lib/api/categories.ts:34`.

### Already-correct surface (do not regress)

`ComponentProgressBars.tsx` already renders **five** components including `usage`, reading the
live `usage` weight from the shared `['health-weights']` query. Five parallel structures are keyed
by the same component keys and must stay consistent with each other: `components` (`:22-28`),
`DEFAULT_WEIGHTS` (`:33-39`), `tooltips` (`:41-47`), `descriptions` (`:49-80`), `liveWeights`
(`:99-105`) and `values` (`:107-113`). Nothing here needs to change for this aspect; it is listed
so that a copy fix at `:32` does not disturb the maps around it.

## In scope

**(A) Trend on the Usage Activity card**

- Add `usage_trend_state` (`'insufficient_history' | 'stable' | 'declining' | 'sharp_decline'`)
  and `usage_trend_pct` (`number | null`) to the `UsageRollup` interface
  (`lib/api/customers.ts:155-169`), typed to tolerate absence (older backend / pre-migration rows).
- Render the trend inside `UsageActivityCard` (`page.tsx:476-543`): a labelled state with a
  direction affordance and, when non-null, the signed `usage_trend_pct`.
- Render `insufficient_history` as an explicit **"Warming up"** state with a one-line explanation
  of the ~14-day snapshot warm-up — visibly warming up, never a blank or a fabricated "stable".
- Define precedence between the existing no-usage empty state (`hasUsage === false`, `:498`) and
  the warm-up state: no-usage copy wins; warm-up is shown only when the customer has usage but the
  trend cannot yet be computed.
- Read the trend from the card's own `days = 30` query so it does not change when the operator
  switches the embedded timeline to 60d/90d. The trend is a property of the rollup, not of the
  selected chart period, and must not appear to.
- Use theme CSS variables for the state colours (no hardcoded colours), per the repo's frontend
  guidelines.
- Vitest coverage for all four states plus the no-usage and loading paths.

**(B) Minimal D4 fix**

- Add a fifth `usage` field to `HealthWeightsEditor`: `DEFAULT_WEIGHTS` (`:10-15`),
  `WEIGHT_LABELS` (`:17-22`), `WEIGHT_DESCRIPTIONS` (`:24-29`) — the render loop at `:93` picks it
  up automatically from state.
- Extend the sum-to-100 computation at `:51-53` to include `usage` (and `crm`, see below), so the
  frontend check matches the backend's six-key validator and the editor can never construct a
  payload the backend rejects for a reason the UI did not show.
- Extend `HealthWeights` / `updateHealthWeights` (`lib/api/categories.ts:24-29, 65-68`) so the PUT
  payload carries `usage` **and** `crm`.
- **Preserve `crm`**: the editor loads it from the GET response and round-trips it unchanged on
  save. It is *not* rendered as an editable input (see Out of scope) — but it must be included in
  both the payload and the sum, or the zeroing bug simply persists for CRM and the sum indicator
  disagrees with the backend for any org with a non-zero CRM weight.
- Update `DEFAULT_WEIGHTS` semantics so "Reset to Default" produces a six-key object that still
  sums to 100 (`churn 35 / sentiment 25 / resolution 25 / frequency 15 / usage 0 / crm 0`,
  matching `categories.py:130-133`).
- Correct the stale copy at `app/(dashboard)/settings/usage-events/page.tsx:208-216` to point at
  **Settings → AI → Health Score Weights** (`/settings/ai`), and the matching comment at
  `ComponentProgressBars.tsx:32` (and, for consistency, `lib/api/categories.ts:34`).
- Vitest coverage in `__tests__/settings/HealthWeightsEditor.test.tsx` for the fifth field, the
  six-key sum, and the crm round-trip.

## Out of scope

- **Making `crm` an editable field.** This aspect only stops it from being zeroed. Surfacing a CRM
  weight input is a separate decision with its own copy and docs; not taken here.
- Any backend change. `categories.py:145-158, 201-202` already accepts and persists six weights;
  the trend fields arrive from `trend-detection-and-health`. If a backend gap is discovered, it
  belongs to that aspect, not this one.
- Computing, thresholding or guarding the trend — this aspect renders whatever the API returns and
  makes no client-side inference. In particular the UI must not derive `stable` from a missing
  state.
- The customer-timeline `usage_trend_change` event (N1) and the `usage_trend` automation trigger
  (N2).
- Extracting `UsageActivityCard` into `components/customers/`. Tempting given it is inline at
  `page.tsx:476`, but it widens the diff and the blast radius of
  `__tests__/customers/CustomerProfilePage.test.tsx` for no functional gain.
- De-duplicating the two "no usage events yet" empty states (card `:511-518` vs
  `UsageTimeline.tsx:67-76`) or unifying the two `['customer-usage', …]` queries.
- Restructuring `ComponentProgressBars`' five parallel maps.
- `docs/SELF_HOSTING.md` / CHANGELOG copy (PRD S3) — documentation, tracked separately.

## Acceptance criteria (testable)

Numbered; each is a Vitest assertion unless stated otherwise.

1. Given a usage response with `usage_trend_state: 'declining'` and `usage_trend_pct: -45`, the
   Usage Activity card renders a visible declining indicator including the signed percentage.
2. `sharp_decline` renders a distinct, visually stronger state than `declining` (distinct label
   and/or test id — not merely a different number).
3. `usage_trend_state: 'stable'` renders a stable state and does not render a decline warning.
4. `usage_trend_state: 'insufficient_history'` renders an explicit "warming up" state that
   mentions the warm-up period, and renders **no** percentage (`usage_trend_pct` is null in this
   state per PRD M3).
5. A customer with **no usage at all** (`hasUsage === false`, i.e. `login_count_30d` and
   `active_days_30d` both 0/null) still renders the existing "No product-usage events recorded
   yet" copy and **not** the warming-up state — the empty state is not silently replaced.
6. A response whose rollup omits `usage_trend_state` entirely (older backend) renders the card
   without crashing and without inventing a trend state.
7. Switching the embedded `UsageTimeline` period to 60d or 90d does not change the rendered trend
   state or percentage.
8. **The zeroing bug is fixed for `usage`:** given `getHealthWeights` returns
   `{churn: 30, sentiment: 25, resolution: 25, frequency: 10, usage: 10, crm: 0}`, pressing Save
   with no edits calls `updateHealthWeights` with a payload containing `usage: 10` — not `0`, and
   not an object missing the key.
9. **The zeroing bug is fixed for `crm`:** given a response with `crm: 10`, the save payload
   contains `crm: 10`, even though no CRM input is rendered. (This criterion is the reason the fix
   cannot be `usage`-only.)
10. The editor renders exactly five editable weight inputs, including one for `usage`, with a
    label and description consistent with the existing four.
11. The sum indicator totals **all six** weights: with base weights summing to 80, `usage: 10`,
    `crm: 10`, the displayed total is `100` and Save is enabled. (Pre-fix this reads 80 and Save is
    blocked.)
12. With a six-key sum ≠ 100 the existing validation error shows and Save stays disabled — the
    frontend never emits a payload the backend's `validate_sum_is_100` would reject.
13. "Reset to Default" produces `churn 35 / sentiment 25 / resolution 25 / frequency 15 /
    usage 0 / crm 0`, a six-key object summing to 100, and Save remains reachable from that state.
14. Editing the `usage` input updates the total and marks the form dirty (existing `isDirty`
    behaviour, `HealthWeightsEditor.tsx:52`, extends to the new field).
15. `app/(dashboard)/settings/usage-events/page.tsx` no longer links `/settings/preferences` for
    the usage weight; it points to the page that actually hosts the editor (`/settings/ai`).
    Asserted in `__tests__/settings/UsageEventsPage.test.tsx`.
16. `__tests__/customers/ComponentProgressBars.test.tsx` and
    `__tests__/customers/UsageTimeline.test.tsx` still pass unchanged — the five-component
    breakdown and the timeline are not regressed by the copy and type edits.
17. `npm test` from `services/frontend-web` is green; `npm run build` succeeds (the `UsageRollup`
    type change compiles against every consumer).

## Dependencies & sequencing

- **Last aspect.** Part (A) depends on `trend-detection-and-health` having shipped
  `usage_trend_state` / `usage_trend_pct` on `GET /api/v1/customers/{email}/usage`. Until then the
  fields are absent, which AC-6 covers by design.
- **Part (B) has no dependency at all.** The backend has accepted six weights since M3.1/M3.2
  (`categories.py:145-158`), and this is active data loss on a shipped feature. It can be split
  out and landed first, ahead of the rest of the feature, and probably should be — nothing in
  aspects 1–3 needs it, and it is the PRD's stated adoption mechanism (M6, "why M6 is a must-have
  rather than polish").
- Frontend-only: `services/frontend-web/` exclusively. No migration, no worker, no API contract
  authored here.
- Tests: Vitest, `npm test` from `services/frontend-web`. Touched specs:
  `__tests__/settings/HealthWeightsEditor.test.tsx`,
  `__tests__/settings/UsageEventsPage.test.tsx`,
  `__tests__/customers/CustomerProfilePage.test.tsx` (the card is inline in that page).
  Read-only regression checks: `__tests__/customers/UsageTimeline.test.tsx`,
  `__tests__/customers/ComponentProgressBars.test.tsx`.

## Open questions & risks

- **Where in the card the trend sits.** The metrics row is a four-column grid (`page.tsx:520-537`)
  that would become five, or the trend becomes a separate line above the timeline. Layout call for
  implementation; AC-1 through AC-4 are agnostic to it.
- **Shared query key, unshared period.** The card and `UsageTimeline` share
  `['customer-usage', email, days]` but hold independent `days` state. Reading the trend from the
  card's own 30-day query (AC-7) keeps the trend period-invariant, but leaves the subtle situation
  where the same key is written by two components. Not fixed here (out of scope); flagged so it is
  not "discovered" as a bug mid-implementation.
- **`crm` invisible but load-bearing.** After this change the editor holds a value it never shows.
  If the GET ever fails, the fallback must not be a silent `crm: 0` — a failed load already leaves
  `DEFAULT_WEIGHTS` in state (`HealthWeightsEditor.tsx:41-49` swallows the error into a
  `console.error`), which is exactly the zeroing shape this aspect exists to remove. The
  implementation must either block saving on a failed load or surface the failure; choosing which
  is the one genuine design decision in part (B).
- **Sum-error legibility.** With `crm` hidden and non-zero, an operator can face "must sum to
  exactly 100 (currently 90)" while the five visible fields appear to sum to 90 correctly. The
  error copy may need to name the hidden CRM allocation. Not a separate AC; called out so the copy
  is written deliberately.
- **Warm-up copy must not overpromise.** The 12–16 day tolerance band (PRD M3) means "about two
  weeks", not a countdown. Do not render a precise "N days remaining" — the frontend has no
  snapshot history to compute it from.
- **Landing (A) before the backend** would ship a card that always reads as absent/warming up. If
  the aspects are split in time, land (B) early and (A) only after
  `trend-detection-and-health`.
