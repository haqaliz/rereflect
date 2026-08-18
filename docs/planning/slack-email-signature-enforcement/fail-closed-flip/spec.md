# Aspect spec — Fail-closed flip

**Feature:** `slack-email-signature-enforcement` (prd.md R1-R7) · **Aspect:** `fail-closed-flip`

## Problem slice

The two shadow-mode verifiers (Slack, email/Resend) flip to fail closed; the sweep
guard's allowlist empties; the shadow tests flip; the startup warning re-scopes; docs
+ env examples + CHANGELOG tell the truth; DEV-TRACKING marks the follow-up FIXED.

## In-scope (the dig enumerated every line — follow exactly)

1. `services/backend-api/src/api/routes/source_webhooks.py:108-115` —
   `verify_slack_signature`: empty `SLACK_SIGNING_SECRET` → non-shadow warning (the
   Intercom/Linear fail-closed wording pattern, e.g. intercom :339-341) + `return
   False`. Route unchanged (:183-184 already 401s).
2. `services/backend-api/src/api/routes/email_webhooks.py:45-52` —
   `_verify_webhook_signature`: same for `RESEND_INBOUND_WEBHOOK_SECRET` → warning +
   `return False`. Route unchanged (:153-154 already 401s). Both replacement warning
   strings kept in agreement.
3. `services/backend-api/tests/test_webhook_verifiers_fail_closed.py:47-50` — remove
   both allowlist entries; `:130-133` → empty-set pin. **RED first** (the guard).
4. Flip shadow tests: `test_slack_webhook.py:31-80` (shadow-accept → 401/`False`,
   marker assertions dropped) + `test_email_webhooks.py:367-397` (→ `False`, no shadow
   log). Configured-secret tests unchanged (:82-122 Slack, :350-365 email).
5. `warn_unconfigured_webhook_secrets` (`main.py:140-187`) — re-scope the wording from
   "being accepted unverified" to a fail-closed notice ("webhook deliveries will be
   rejected until you set X — see docs/SELF_HOSTING.md"); `test_startup_webhook_secret_warnings.py`
   updated to the new wording (warn-when-unset semantics unchanged).
6. Docs: SELF_HOSTING.md:2468-2469 (table rows) + :2473-2478 (grace-period paragraph) →
   fail-closed + configure instructions; `.env.example:36-44` + `.env.prod.example:128-136`
   shadow copy → fail-closed copy; CHANGELOG behavior-change entry + correction of the
   grace-period entry (:319-324); DEV-TRACKING follow-up (:423-426) → **FIXED** with a
   shipped summary + `(merged <merge-sha>, PR <# pending>)` placeholder.
7. Record the S1 follow-up (generic-webhook per-source `secret_token` fail-open,
   source_webhooks.py:270-274) inside the FIXED marker.

## Out of scope

- The generic-webhook per-source fail-open (S1 — recorded only).
- HMAC/verification scheme changes; other verifiers; frontend (badge survives).

## Acceptance criteria (testable)

1. `test_webhook_verifiers_fail_closed.py` passes with an empty allowlist; unset-secret
   → `False` for all seven verifiers.
2. Slack + email webhook shadow tests now assert 401/`False` without the
   SECURITY-SHADOW marker.
3. Startup-warning tests assert the fail-closed wording.
4. Grep sweep: "Accepted unverified" / "accepted unverified" / "SECURITY-SHADOW"
   absent from live docs (SELF_HOSTING, .env examples, CHANGELOG beyond the correction
   note) and from the flipped verifier code paths.
5. Backend suite green.

## Dependencies & sequencing

- Single aspect; no dependencies. One implementation pass.

## Open questions / risks

- None beyond the PRD's OQ1/OQ2 (kept/re-scoped startup warning; empty-set pin).
