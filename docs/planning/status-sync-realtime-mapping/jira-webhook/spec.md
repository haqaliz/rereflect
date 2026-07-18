# Aspect spec — `jira-webhook`

Part of PRD `status-sync-realtime-mapping`. Depends on `status-writer-race-guard`.

## Problem slice & user outcome
A Jira issue status change is reflected on the linked feedback item's
`workflow_status` in **seconds** instead of ≤15 min. The 15-min poller is
retained as a guaranteed fallback for missed/failed webhook deliveries.

## Reference pattern
Generalize Zendesk's receiver (`source_webhooks.py::handle_zendesk_webhook`,
fail-closed) + Linear's (`routes/linear_webhook.py`, per-org secret matching).
**Use Zendesk's fail-closed posture**, NOT Linear's `return True` on missing
secret. Route the reconciled change through the SAME `status_sync_core` mapping +
the race-safe apply (from `status-writer-race-guard`) that the poller uses, so
poll and webhook can never diverge or double-write.

## In scope
- **Model + migration:** add `webhook_secret` (Text, Fernet-encrypted, nullable)
  to `JiraIntegration`. Generate via `secrets.token_urlsafe(32)` when the
  operator enables the webhook; return plaintext **once** (like Zendesk connect).
  Alembic migration — confirm single-head with live `alembic heads`.
- **Enable/config route:** extend the Jira integration routes so an admin/owner
  can enable the webhook and retrieve the secret + the inbound URL to paste into
  Jira (mirror Zendesk's connect/secret-reveal). Reuse `require_admin_or_owner`.
- **Receiver:** new `api/routes/jira_webhook.py`, prefix
  `/api/v1/webhooks/jira`, registered in `api/main.py`. Flow:
  1. Read raw body. Verify `X-Hub-Signature` = `sha256=<hex HMAC-SHA256(secret,
     raw_body)>`. Resolve the integration by trying each active org's secret
     (Linear-style) — fail-closed 401 on no match / missing signature.
  2. Parse JSON. Discriminate the event: only handle issue status-change events
     (`webhookEvent == "jira:issue_updated"` with a status changelog item);
     ignore others with 200.
  3. Extract issue id/key + new status name + Jira `statusCategory` key
     (new/indeterminate/done). Look up `FeedbackJiraIssue` links for that issue in
     the resolved org.
  4. Reconcile via a backend-api port mirroring the poller: `decide_link_update`
     → most-advanced category across the feedback's live links →
     `resolve_target_status(category, integ.status_mapping)` → race-safe apply
     with `metadata={"source":"jira","jira_status":...,"jira_issue_key":...}`.
     Upsert the link's last-observed status/category.
  5. Return `{"status":"ok","reconcile":...}`.
- Keep the Jira poll task unchanged (fallback). Observability: reuse/extend
  `last_status_synced_at` / `last_sync_status` / `last_error`.

## Out of scope
- Outbound webhooks. OAuth 3LO / Connect-app JWT auth (v1 uses the configured
  webhook secret + `X-Hub-Signature`). Per-raw-status-name mapping. Multiple
  Jira sites per org.

## Acceptance criteria (testable)
- Signature verify: valid `X-Hub-Signature` → processed; bad/missing → 401;
  missing stored secret → 401 (fail-closed). Verified over raw bytes.
- Unknown org (no secret matches) → 401; unrelated event type → 200 no-op, no
  writes.
- A status-change event on a linked issue updates `workflow_status` per the
  merged mapping and writes exactly one `FeedbackWorkflowEvent` (race-safe path).
- A duplicate/stale delivery (status already applied) → zero events (race guard).
- Migration test (mirror `test_jira_status_sync_migration.py`) for the new
  column; model test for the field.
- New `tests/test_jira_webhook.py` covering the above (mirror
  `test_zendesk_webhook.py` + `test_linear_webhook.py`).

## Dependencies & sequencing
- **Depends on** `status-writer-race-guard` (shared race-safe apply).
- Independent of `asana-webhook`; can run in parallel with it.
- The backend reconcile port must stay consistent with the worker poller's
  reconcile (shared `status_sync_core.py`, duplicated in both services).

## Open questions / risks
- **R1:** Confirm the exact Jira Cloud signature header/scheme during
  implementation (`X-Hub-Signature: sha256=...`). If a given Jira deployment
  can't sign, document that the webhook requires a secret and fall back to poll —
  never fail open.
- Org resolution by secret-matching assumes distinct per-org secrets (true, we
  generate them). Fine.
