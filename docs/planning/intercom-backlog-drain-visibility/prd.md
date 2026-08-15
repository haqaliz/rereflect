# PRD — Intercom backlog drain visibility

**Slug:** `intercom-backlog-drain-visibility` · **Branch:** `feat/intercom-backlog-drain-visibility`
**Type:** feat · **Created:** 2026-08-15
**Card:** `docs/planning/_card/card.md` (freeform, no GitHub issue) · **Source:** DEV-TRACKING deferred-v2 entry

---

## Problem Statement

A large Intercom backlog drains over **several 20-page runs** (first connect with a
big history; the cursor resumes where it stopped each run). The operator has **no
visible progress**: the Intercom settings page shows workspace, last-synced,
last-error, and an **ingested count** — but not how many conversations remain. The
deferred-v2 entry names the gap: *"the settings page shows a count but not 'N
remaining'"* (DEV-TRACKING.md:517-518).

The raw material already exists: Intercom's `POST /conversations/search` response
carries `total_count` for the query window — the client parses the payload
(`clients/intercom.py:148-154`) but **drops it**.

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| Operators see drain progress | After a completed sync run, the Intercom settings page shows "≈ N remaining" for a non-empty window — verified by tests |
| Honest, not a fake count | The number is labeled an estimate; absent for unconnected / never-synced / error states; never shown for OAuth connections (no pull) |
| No drain-mechanics change | Page cap, cursor, and counter semantics are untouched (characterization tests unchanged) |
| No stale numbers | Error-path runs reset the estimate instead of leaving a stale value |

Non-goals: metrics beyond the UI's presence (single-tenant OSS).

## User Personas & Scenarios

- **Self-hoster connecting a long-lived Intercom workspace.** First sync drains over
  many runs; the settings page now answers "is it still catching up, and how far?"
- **Operator checking a healthy install.** The window is empty after each run → no
  "remaining" row (the last-synced row already communicates health) — no noise.

## Requirements

### Must-have

**R1 — Client surfaces `total_count`.** `IntercomClient.search_conversations` returns
the query's `total_count` alongside conversations + next cursor. The current 2-tuple
return is load-bearing (`test_intercom_sync.py` `_fake_client` :175-191 and unpack at
:257) — the plan widens it to a 3-tuple `(conversations, next_cursor, total_count)`
with all unpack sites + the fake updated in the same change (strict TDD; the existing
contract tests are the RED). `total_count` is the same value on every page of a query
(the window is fixed at run start) — take it from any page; `None` when the payload
omits it (defensive; unknown → no estimate this run).

**R2 — Sync computes and persists the estimate.** In `_sync_org`
(intercom_sync.py:193-318): after the loop, `remaining_estimate = max(0, total_count -
conversations_seen)`; return it in the result dict (additive key). In
`_sync_intercom_org_body` (:366-368), alongside `last_sync_status = "ok"`, persist
`integ.backlog_remaining = remaining_estimate`. **Error paths reset:** the
`_persist_terminal_status` sites (auth_error :358, transient :403) set
`backlog_remaining = None` — a failed run must not leave a stale number.

**R3 — New column + mirrors + parity.** `intercom_integrations.backlog_remaining`
(Integer, nullable) chained off the single head `e4f5a6b7c8d9` (style: the
`e4f5a6b7c8d9_add_intercom_writeback_columns.py` migration + its migration test
pattern); worker mirror in `models/__init__.py` (no `server_default` — house
convention); **add `"backlog_remaining"` to the parity type-tuple**
(`WRITEBACK_INTEGRATION_COLUMNS`, test_intercom_tenancy_discriminator.py:324-331 —
the name-only test would otherwise silently pass mismatched types).

**R4 — Status API.** `IntercomStatusResponse` (intercom_integration.py:139-161) gains
`backlog_remaining: Optional[int] = None` (after `feedback_items_ingested` :155);
`_build_status_response` (:277-297) maps it from the row (between :291 and :292);
disconnected/absent rows keep the `None` default (no change to the
`IntercomStatusResponse(connected=False)` shape at :450).

**R5 — Frontend.** `IntercomConnectionStatus` (lib/api/intercom.ts:18-43) gains
`backlog_remaining: number | null` (after :34, mirroring the writeback fields' six
layers). The Connection card (intercom/page.tsx:168-236) renders a "≈ N remaining"
row after the "Feedback ingested" row (:199-202) — **only when `backlog_remaining` is
non-null AND > 0** — with honest copy ("≈ N conversations left to sync — estimate,
drains over runs"). Reconcile the "never backfills history" alert copy (:212-224) so
it does not contradict the existence of a drain estimate.

**R6 — Tests.** Backend: status characterization extended
(test_intercom_writeback_config.py `TestWritebackStatusExtension` — the byte-identical
loop is additive-safe; add the explicit `backlog_remaining` assertions + disconnected
default); worker: estimate computation, persistence on success, reset on auth/transient
error, client 3-tuple contract; frontend: card render (mirror the ingested-count test
pattern, IntercomPage.test.tsx:224-230) + no-row states (null, 0, disconnected,
OAuth/never-synced).

**R7 — Docs & tracking.** SELF_HOSTING Intercom section (the pull bullet + honest
limits: estimate semantics, token-paste-only, reset on error); CHANGELOG entry;
DEV-TRACKING deferred-v2 `intercom-backlog-drain-visibility` → SHIPPED (house
strikethrough + shipped summary + merge-facts placeholder).

### Should-have

- **S1 — First-sync framing:** the estimate's first-run meaning (window = since
  `connected_at`) is stated in the card copy, not left to the operator to infer.

### Nice-to-have (deferrable)

- **N1 — Also show total:** "N of M" instead of remaining-only. More noise; the
  deferred entry asked for remaining. Deferred.

## Technical Considerations

- **Services:** worker-service (client + sync task), backend-api (model + migration +
  status route), frontend-web (card). No new deps; no plan gate (`SELF_HOSTED=true`).
- **The client 3-tuple is the risky surface.** Every `search_conversations` consumer
  + the `_fake_client` fixtures unpack the 2-tuple; the plan updates them in the same
  commit with the contract tests as RED first (the dig enumerated the sites:
  test_intercom_sync.py:257, :175-191, intercom_sync.py:203-205).
- **`total_count` is per-query, not per-page** — any page's value is the window's
  total; the estimate uses the last page's value with `conversations_seen` (which can
  exceed `total_count` transiently due to the `>=` boundary re-fetch → `max(0, ...)`).
- **Estimate semantics are honest by construction:** arrivals during the drain shift
  the next run's window; the boundary conversation re-counts itself. "Estimate" in the
  copy, not a promise.
- **Token-paste only.** The pull iterates `IntercomIntegration` rows only
  (intercom_sync.py:296-304); OAuth orgs never produce an estimate → the row never
  renders for them (their `backlog_remaining` stays null).
- **Parity gap fixed in passing:** the type-parity tuple currently covers only
  writeback columns; `backlog_remaining` joins it so Integer/BigInteger drift is
  caught (test_intercom_tenancy_discriminator.py:324-331).

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | **3-tuple widening ripples** through the worker suite | The plan enumerates the unpack sites + `_fake_client`; RED-first; suite green after |
| R2 | **Stale estimate on error paths** | `_persist_terminal_status` resets to None (R2) — pinned by a test |
| R3 | **`total_count` absent/unknown** (API variance) | Defensive `None` → no estimate that run; row keeps last value? No — R2 writes the estimate only on a completed run; unknown → skip the write (leave prior value? A completed run with unknown total sets None) — decide in plan: unknown total on a completed run → set `backlog_remaining = None` (honest) |
| R4 | **Copy contradiction** with the existing "never backfills history" alert | R5 reconciles the copy |
| R5 | **Perceived precision** — "N remaining" read as an exact queue count | "≈" + "estimate, drains over runs" in the card copy; honest-limits block in docs |

**Open questions**
- **OQ1 — Show "0" when drained?** *Leaning: no row when `backlog_remaining` is null
  or 0 — an up-to-date install shows nothing, matching the deferred entry's "not N
  remaining" intent without adding noise.*
- **OQ2 — Include the estimate in the sync result dict?** *Yes — additive key, used
  by the task body to persist; also useful in task logs.*

## Out of Scope

- **Drain-mechanics changes** (page cap, cursor, window semantics) — visibility only.
- **OAuth-path pull** (`intercom-oauth-path-retirement` — gated on evidence of use).
- **The latent webhook reply/rating defect** (already flagged as a follow-up).
- **"N of M" total display** (N1).
- No plan gate; no new dependencies; no changes to the writeback stack.

## Honest limits (state in docs + card copy)

- The number is an **estimate** computed from Intercom's `total_count` for the sync
  window at run start; conversations updated during the drain shift later windows, and
  the boundary conversation re-counts itself.
- It exists only for **token-paste** connections (OAuth has no pull), only **after a
  completed run**, and is **reset on error** — a failed run shows no number rather
  than a stale one.
- The drain mechanics (20-page cap, cursor resume) are unchanged; the estimate reports
  progress, it does not speed it up.

## Self-critique (Phase 4)

- 🔴 **The 3-tuple widening is the whole risk.** The dig enumerated the sites, but the
  plan must treat the contract tests as the RED gate and update every consumer in the
  same commit — otherwise the suite breaks mid-branch. Called out; the plan owns it.
- 🟡 **"N remaining" semantics on a moving window** are inherently fuzzy; the honest
  framing (estimate, reset on error, per-run snapshot) is pinned in copy + docs rather
  than argued away.
- 🟡 **The parity-test gap** (type coverage only for writeback columns) is a latent
  drift risk the feature fixes in passing — worth noting for the sibling model-parity
  tests, not just this column.
- 🟢 Scope, error-path staleness, and token-paste-only framing are unambiguous.

**The question I'd want answered before greenlighting:** is an operator actually
confused without this, or is the ingested count + last-synced time sufficient? — The
deferred entry was written after the settings page shipped (count visible, remaining
not); the ask is explicit. Build it.
