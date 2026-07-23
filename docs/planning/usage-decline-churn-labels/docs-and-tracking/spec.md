# Aspect — docs-and-tracking

**PRD:** `../prd.md` (M7)
**Sequence:** Last. Depends on the shipped behaviour of every other aspect.

## Problem slice

Every recent feature in this repo ships `docs(...)` commits, and `AI-TRACKING.md` currently carries a
stale claim: the M5.3 note calls usage-derived churn labels "feasible but **unplanned**"
(`:480-485`). Leaving that after shipping makes the roadmap lie.

## User outcome

A self-host operator can find out what this does, what it structurally *cannot* see, and how to turn
it on — without reading the source.

## In scope

- **`docs/SELF_HOSTING.md`** — a usage-decline churn-labels section:
  - what it does (suggestions, never labels; a human confirms),
  - how to enable (Settings → AI; `off` → `shadow` → `active`, and why shadow first),
  - `sustain_days` and what changing it trades off,
  - **the honest limits, in full**: the ~12-16 day warm-up, the extra sustain window, the
    **≥5 active-day baseline floor that permanently excludes light-usage customers**, the
    recently-declining-only visibility limit, and the requirement that the operator has instrumented
    usage events at all,
  - the M3b outage guard: what it suppresses and why an operator might see a warning instead of
    suggestions.
- **`CHANGELOG.md`** — an entry in the established style.
- **`AI-TRACKING.md`**:
  - **Update the M5.3 note at `:480-485`** — the usage-decline label source is no longer "unplanned";
    record what shipped and its limits.
  - Add the capability row / milestone entry consistent with how M3.2b and M3.2c were recorded.
  - **Do not** restate `CHURN_LABEL_TARGET = 500` as settled — the gate is under review
    (`:467-478`), and this feature's value is threshold-independent.
- **`README.md`** — only if the feature list mentions churn-label sources; keep it terse.

## Out of scope

- Landing-page / marketing copy (a separate concern; add only if the landing page enumerates
  churn-label sources).
- Any claim about churn-prediction accuracy, AUC, or that an org will reach the M5.3 gate.
- Re-deriving the 500-label gate (named as separate work in the PRD, R6).

## Acceptance criteria (testable)

1. `AI-TRACKING.md:480-485`'s "unplanned" wording no longer describes shipped work.
2. `SELF_HOSTING.md` states **all** the limits listed above — specifically including the ≥5
   active-day floor, which is the least discoverable and most misleading omission.
3. No document claims improved churn-prediction accuracy.
4. No document presents 500 labels as a settled target.
5. `CHANGELOG.md` entry matches the surrounding format.

## Dependencies & sequencing

- Write last, from what actually shipped — not from the PRD's intentions. If an aspect landed
  differently than specced, the docs follow the code.

## Open questions / risks

- Risk of documenting the *specced* rather than the *built* behaviour (e.g. if `sustain_days`
  defaults changed during implementation). Mitigation: write these from the merged diff, and re-read
  the settings copy actually rendered by `frontend-settings-and-evidence`.
