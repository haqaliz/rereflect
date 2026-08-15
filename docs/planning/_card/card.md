# Card — feat/intercom-backlog-drain-visibility (freeform, no GitHub issue)

Source: DEV-TRACKING.md "Deferred v2 — Intercom" entry `intercom-backlog-drain-visibility`
(line ~517-518). Branch `feat/intercom-backlog-drain-visibility`, worktree
`.claude/worktrees/feat-intercom-backlog-drain`.

## Brief

A large Intercom backlog drains over **several 20-page runs** (first connect with a big
history), with **no operator-visible progress**: the Intercom settings page shows a
count (ingested/workspace/last-sync state) but not **"N remaining"**. This card adds an
honest remaining-backlog estimate to the sync status the operator can read on
Settings → Integrations → Intercom.

## Facts (from prior digs, verified 2026-08-15)

- The pull (`worker-service/src/tasks/intercom_sync.py`) runs `POST /conversations/search`
  with `updated_at >= cursor`, `starting_after` pagination, `MAX_PAGES_PER_RUN = 20`,
  cursor advances to max `updated_at` per run. The search response carries
  `total_count` (Intercom's documented response field) — the client currently drops it.
- The Intercom settings page Connection card (`frontend-web/.../settings/integrations/intercom/page.tsx:167-235`)
  shows workspace, token hint, last-synced, last-error, and an **ingested count** —
  the count referenced by the deferred entry. `lib/api/intercom.ts` status type drives it.
- `GET /api/v1/integrations/intercom/status` (`backend-api/src/api/routes/intercom_integration.py:407-420`)
  returns workspace/admin metadata + sync state.
- `IntercomIntegration` (backend + worker mirror) has sync-status columns; model parity
  is CI-asserted. Alembic head on master: `e4f5a6b7c8d9`.

## Caveats (carried into the PRD, must not be papered over)

- **It is an estimate, not a count.** `total_count` reflects the window at the moment
  of the query (`updated_at >= cursor-at-run-start`); conversations updated during the
  drain shift the window, and the boundary re-fetch re-counts one conversation. The UI
  must label it an estimate (e.g. "≈ N remaining").
- **Token-paste only.** The pull iterates `IntercomIntegration` rows only — OAuth orgs
  have no pull, so no backlog number exists for them (already a documented truth fix
  from `intercom-pull-replies-and-ratings`). The card must not show a backlog for OAuth
  connections.
- **First-run semantics.** On connect, `last_synced_at` is absent → cursor = `connected_at`;
  the first run's `total_count` IS the full backlog. Absent sync history or empty
  window → no backlog line (or "0" only when a run has actually completed).

## Deliverables (proposed, refine in PRD)

1. Sync computes and persists an honest remaining estimate after each run (new
   `backlog_remaining` column on `IntercomIntegration` + worker mirror + parity).
2. `GET /status` exposes it; the settings page Connection card renders "≈ N remaining"
   (with honest copy; hidden for OAuth/unconnected/never-synced states).
3. Docs: SELF_HOSTING + CHANGELOG + DEV-TRACKING deferred-v2 entry → SHIPPED.

## Out of scope (guardrails)

- Not changing the drain mechanics (page cap, cursor) — this is visibility only.
- Not building `intercom-oauth-path-retirement` (gated on evidence of use) or the
  latent webhook reply/rating defect (already flagged as a follow-up).
- No plan gates (`SELF_HOSTED=true`); no new vendor dependency.
