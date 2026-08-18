# Card — chore/slack-email-signature-enforcement (freeform, no GitHub issue)

Source: the follow-up recorded in DEV-TRACKING.md:423-426, opened by the P0
`intercom-webhook-unauthenticated-cross-org-write` hardening
(`feat/integration-auth-tenancy-hardening`, 2026-07-29). Branch
`chore/slack-email-signature-enforcement`, worktree `.claude/worktrees/chore-slack-email-sig`.

## Brief

The P0 webhook hardening shipped Slack and the inbound-email (Resend) verifiers in
**shadow mode**: they accept unverified deliveries while logging a `SECURITY-SHADOW`
marker + a startup warning + a Settings badge, because their ingestion works and a hard
flip would stop real traffic. The follow-up: **flip both verifiers to fail closed** and
delete their entries from the `SHADOW_ALLOWLIST` in
`tests/test_webhook_verifiers_fail_closed.py` (that test fails until you do). Update
the `SELF_HOSTING.md` table which still describes them as accepting unverified
deliveries.

## Facts (from DEV-TRACKING.md, cited)

- DEV-TRACKING.md:423-426: "**`slack-email-signature-enforcement`** — flip the two
  shadow-mode verifiers to fail closed and delete their entries from
  `SHADOW_ALLOWLIST` in `tests/test_webhook_verifiers_fail_closed.py` (that test fails
  until you do). Update the `SELF_HOSTING.md` table, which still describes them as
  accepting unverified deliveries."
- The hardening entry (DEV-TRACKING.md:366-370): "**Slack and email ship in shadow**
  (accept + `SECURITY-SHADOW` log + startup warning + a Settings badge) because their
  ingestion works and a hard flip would stop real traffic. Intercom and Linear fail
  closed immediately. `tests/test_webhook_verifiers_fail_closed.py` enumerates all
  seven verifiers and allowlists exactly those two — flipping either breaks that test
  by design, so the shadow period cannot become permanent."

## Caveats (carried into the PRD, must not be papered over)

- **Real-traffic risk.** Slack/email ingestion works today with unverified deliveries
  (the operators' webhooks may not yet send valid signatures, or the secret env vars
  are unset). Flipping to fail-closed means: an install without `SLACK_SIGNING_SECRET`
  / Resend signature verification configured will now REJECT Slack/email webhook
  deliveries until the operator configures the secret. This is the intended security
  posture but is a behavior change — the PRD must state it plainly and the changelog +
  SELF_HOSTING must tell operators exactly how to restore delivery (set the secret).
- **Two different verification mechanisms** (Slack: `X-Slack-Signature` + timestamp
  HMAC; email: Resend's `svix`-style signature headers) — the flip must fail closed in
  the same way for both, and the sweep test enumerates all seven verifiers.
- The shadow machinery (log + startup warning + Settings badge) may need removal or
  re-scoping once nothing is shadowed — decide in the PRD (leave the generic
  shadow plumbing for future use, or delete it).

## Deliverables (proposed, refine in PRD)

1. `verify_slack_signature` + the email/Resend verifier fail closed when the secret is
   missing/invalid (reject with 401, no shadow log path).
2. `SHADOW_ALLOWLIST` in `tests/test_webhook_verifiers_fail_closed.py` loses the two
   entries (test goes RED first — the guard).
3. SELF_HOSTING.md table + the webhook sections updated (no more "accepts unverified
   deliveries" claims; operators told how to configure the secrets).
4. CHANGELOG entry (behavior change: Slack/email webhooks now require a configured
   signing secret) + DEV-TRACKING follow-up → FIXED.
5. Decide the shadow-plumbing fate (keep generic machinery for future verifiers vs
   delete).

## Out of scope (guardrails)

- Not changing the verifiers' crypto (HMAC scheme) — only the fail-open→fail-closed
  posture.
- Not touching Intercom/Linear/Zendesk verifiers (already fail closed).
- No plan gates; no new dependencies; no frontend work (unless the Settings badge
  removal is trivial and in scope — decide in PRD).
