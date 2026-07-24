# Aspect — detector-core

**PRD:** `../prd.md` (M1, M3b)
**Sequence:** 2nd (can run in parallel with `config-and-migration`). Blocks `worker-detector`.

## Problem slice

"Sustained decline" is a level-based concept, and the shipped trend stack only exposes **edges**
(`worker-service/src/tasks/usage_metrics.py:635-638` appends to `pending_trend_transitions` only on
a state *change*). The streak logic, and the population-level outage guard, must be built — and they
must be pure, so they are testable without a database.

## User outcome

Indirect: this is the correctness core that decides whether a customer's decline is real enough to
put in front of a human, and whether the whole run looks like an instrumentation outage.

## In scope

A new **pure** module, mirrored byte-identically into both services (house pattern, as
`usage_trend_severity.py` and `usage_score_service.py` already are):
- `services/backend-api/src/services/usage_decline_labels_core.py`
- `services/worker-service/src/services/usage_decline_labels_core.py`

Functions (no I/O, no ORM, no Celery — take plain data, return plain data):

1. `qualifying_streak(states: List[Tuple[date, str]], sustain_days: int) -> Optional[date]`
   - Input: the customer's recent `(snapshot_date, usage_trend_state)` rows, newest-last.
   - Returns the **streak start date** when the most recent `sustain_days` consecutive snapshots
     are all `sharp_decline`; else `None`.
   - `declining` does **not** qualify in v1. `insufficient_history` never qualifies **and breaks a
     streak** (it is an absence of evidence, not evidence of stability) — pin this explicitly, it is
     the subtlest rule here.
   - Missing days (gaps in snapshot history) break the streak — "consecutive" means consecutive
     calendar snapshots, not "the last N rows that happen to exist".
2. `suggestion_key(email: str, streak_start: date) -> str`
   - Returns `f"usage:{email}:{streak_start.isoformat()}"`. Stable while a streak continues; a new
     episode after recovery mints a new key. Must be ≤ 64 chars to fit
     `external_opportunity_id` (`String(64)`) — **truncate/hash deterministically if the email is
     long enough to overflow, and test the boundary.**
3. `build_evidence(...) -> dict`
   - `{trend_state, trend_pct, baseline_active_days_14d, current_active_days_14d, streak_days,
      streak_start_date, last_active_at, snapshot_series: [{date, active_days_14d}]}`.
   - JSON-serializable only (dates → ISO strings).
4. `outage_suspected(qualifying: int, eligible: int, max_share: float, min_population: int) -> bool`
   - The M3b guard. `True` when `eligible >= min_population` **and**
     `qualifying / eligible > max_share`.
   - Below `min_population` the ratio is meaningless (2 of 6 customers is 33%) — return `False` and
     let the per-customer rules stand. Default `min_population` ≈ 20, `max_share` = 0.25.

## Out of scope

- Any DB access, Celery task, or session handling (that is `worker-detector`).
- Re-implementing or altering trend **classification** — `classify_usage_trend` /
  `select_nearest_in_band_snapshot` in `usage_score_service.py:203-366` are read-only inputs here
  and must stay byte-stable.
- Writing suggestions.

## Acceptance criteria (testable)

1. `sustain_days` consecutive `sharp_decline` snapshots → returns the correct streak start date.
2. `sustain_days - 1` consecutive → returns `None` (the boundary, both sides).
3. A single `stable` in the middle breaks the streak.
4. A single `insufficient_history` in the middle **breaks** the streak.
5. `declining` never qualifies, alone or mixed with `sharp_decline`.
6. A calendar gap (missing snapshot_date) breaks the streak even if the surrounding states qualify.
7. A continuing streak returns the **same** start date on consecutive days ⇒ `suggestion_key` is
   stable ⇒ idempotent re-detection.
8. Recovery then re-decline yields a **different** key.
9. `suggestion_key` never exceeds 64 chars, including for a 255-char email (the `customer_email`
   column max).
10. `build_evidence` output is JSON-round-trippable (`json.dumps`/`loads`) with no date objects.
11. `outage_suspected`: above-threshold share with sufficient population → `True`; identical share
    below `min_population` → `False`; exactly-at-threshold → `False` (strict `>`).
12. **Purity guard test** — module imports no `celery`, `sqlalchemy`, `fastapi`, `httpx`, or CRM
    client, mirroring `worker-service/tests/test_churn_harvest_core.py::TestPurityGuard`.
13. **Parity test** — the two copies are byte-identical (mirror the existing parity-test pattern).

## Dependencies & sequencing

- Independent of `config-and-migration`; both can proceed in parallel.
- `worker-detector` consumes every function here.

## Open questions / risks

- Whether `min_population` and `max_share` should be config (JSON keys) or constants. Spec leans
  constants for v1 with a named module-level default, since neither has a validated value; promote
  to config only if the plan finds a reason.
- Gap handling assumes the daily snapshot job ran. A worker outage creates gaps that break streaks —
  this makes the detector *conservative* under our own downtime, which is the right direction.
