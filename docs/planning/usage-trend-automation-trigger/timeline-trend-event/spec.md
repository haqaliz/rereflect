# Aspect — `timeline-trend-event`

**Slice:** N1 — surface `usage_trend_change` on the customer timeline, derived at read time from
consecutive snapshots.

**PRD requirement:** M4, S2.

---

## Problem slice & outcome

An operator opening a Customer 360 profile can see when the customer's usage trend changed and
in which direction — so an auto-run playbook has a visible cause.

## In scope

1. `_fetch_usage_trend_changes(...)` in
   `services/backend-api/src/services/customer_timeline_service.py`, reading the customer's
   `customer_usage_history` rows (bounded by the 180-day retention) ordered by `snapshot_date`,
   emitting one `TimelineEvent` per state change between **consecutive** snapshots.
2. Wire into `build_timeline` (`:637-730`), following the few-rows-per-customer pattern
   (fetch-all + Python `_after_cursor` filter) used by churn/CRM/playbook sources.
3. Extend `TimelineEvent` (`:54-74`) with any new payload fields needed
   (`old_trend_state`, `new_trend_state`, `usage_trend_pct`).
4. Extend `ActivityEvent` (`api/routes/customers.py:186-203`), `_timeline_event_to_activity`
   (`:930-948`), and the hand-maintained public mirror `PublicActivityEvent`
   (`api/routes/public_api.py:1044-1065`) — additive optional fields only.
5. Frontend: add `'usage_trend_change'` to the `ActivityEvent['type']` union
   (`lib/api/customers.ts:220-233`) and an entry to `eventIconMap`
   (`components/customers/ActivityTimeline.tsx:46-116`). `CustomerTimeline` imports the same
   map, so one entry covers both surfaces.

## Behavior — which changes are reported

The timeline reports **every** state change in both directions, unlike the trigger:

- `stable → declining`, `declining → sharp_decline` — reported
- `declining → stable`, `sharp_decline → declining` (recovery) — reported
- `insufficient_history → X` — reported, phrased as the trend becoming measurable, **not** as a
  decline
- `X → insufficient_history` — reported (can happen if the baseline floor stops being cleared)
- `NULL` on either side (pre-existing rows, PRD M3 leaves them null) — **skipped**, never
  treated as a transition
- Missing days (worker downtime) — compare consecutive *rows*, not consecutive *dates*; a gap
  does not fabricate or suppress a transition

Copy is server-generated (`description`), per the existing convention — the frontend supplies
only icon + color.

## Out of scope

- Firing anything. This aspect is read-only.
- Backfill of `NULL` trend states.
- Rendering `usage_trend_pct` as a chart or adding a filter.

## Acceptance criteria

- **AC1** — A customer with snapshots `stable, stable, declining` yields exactly **one**
  `usage_trend_change` event, dated to the `declining` snapshot.
- **AC2** — Recovery (`declining → stable`) yields an event whose description reads as an
  improvement, not a decline.
- **AC3** — Consecutive snapshots with equal state yield **zero** events.
- **AC4** — A `NULL` trend state on either side of a pair yields zero events.
- **AC5** — Events interleave in correct `timestamp DESC` order with other event types, and
  cursor pagination over a mixed timeline produces no duplicates and no gaps (mirror
  `test_timeline_pagination_no_dup_no_gap`).
- **AC6** — Cross-org isolation: another org's snapshots never appear.
- **AC7** — The event is present in both the internal `/timeline` and the public
  `/api/public/v1/customers/{email}/timeline` responses with the same shape.
- **AC8** — Frontend: the new type has an icon/color entry; an unknown type still degrades to
  the muted dot (existing fallback test stays green).

## Dependencies & sequencing

**Depends on `snapshot-trend-columns`** — cannot start until the columns exist and are written
correctly. Independent of all trigger aspects.

Precedent to mirror throughout: `playbook_auto_run` (M4.1.5) — `_fetch_playbook_runs`
(`customer_timeline_service.py:443-486`) and its test class `TestTimelinePhase6`
(`tests/test_customer_timeline_service.py:1048-1235`).

## Risks / open questions

- Deriving from snapshots means the event appears only for changes that occurred **after** this
  branch ships; there is no history before the columns existed. Consistent with the warm-up.
- PRD Q1 (open): `sharp_decline → declining` is reported by the timeline but does not fire the
  trigger. Confirm this doesn't read as inconsistent once both are visible.
