# PRD — Slack & email webhook signature enforcement (fail-closed flip)

**Slug:** `slack-email-signature-enforcement` · **Branch:** `chore/slack-email-signature-enforcement`
**Type:** chore (security) · **Created:** 2026-08-17
**Card:** `docs/planning/_card/card.md` (freeform, no GitHub issue) · **Source:** the
follow-up recorded in DEV-TRACKING.md:423-426 from the P0 webhook hardening.

---

## Problem Statement

The P0 webhook hardening (2026-07-29) shipped the Slack and inbound-email (Resend)
verifiers in **shadow mode**: an unset signing secret was accepted (`return True` +
`SECURITY-SHADOW` log + startup warning + Settings badge), because their ingestion
worked and a hard flip would stop real traffic. The guard test
(`test_webhook_verifiers_fail_closed.py`) allowlists exactly those two and fails by
design once they're removed — the shadow period is meant to end.

The flip: **both verifiers fail closed** — an unset/missing secret rejects the
delivery (401), matching the other five verifiers (Intercom/Zendesk/Jira/Asana/Linear).
The shadow period ends; operators who haven't configured `SLACK_SIGNING_SECRET` /
`RESEND_INBOUND_WEBHOOK_SECRET` must now do so or Slack/email webhooks stop delivering.

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| No verifier accepts an unverified delivery | `test_webhook_verifiers_fail_closed.py` passes with an **empty** allowlist — the seven verifiers all return `False` when the secret is unset (pinned) |
| Behavior change is explicit | CHANGELOG + SELF_HOSTING tell operators that unset secrets now reject deliveries and how to configure them |
| No shadow remnants | `SECURITY-SHADOW` "accepted unverified" claims gone from live docs; startup warning re-scoped; the two inline fail-open branches removed |
| Consistent with siblings | The flipped verifiers log a non-shadow warning + `return False` exactly like the five already-fail-closed verifiers (Intercom :339-341, Linear :48-50 pattern) |

## User Personas & Scenarios

- **Operator with Slack/email webhooks but no signing secret configured.** After the
  flip: deliveries return 401 until they set the env var (documented). The startup
  warning and Settings badge (Slack) tell them exactly what to set.
- **Operator already configured** (or using fail-closed-ready webhooks): no change —
  valid signatures still accepted; invalid rejected (unchanged).

## Requirements

### Must-have

**R1 — Flip `verify_slack_signature`** (`source_webhooks.py:108-115`): when
`SLACK_SIGNING_SECRET` is empty, log a non-shadow warning (the Intercom/Linear
fail-closed wording) and `return False` (reject). The route already 401s on `False`
(:183-184) — no route change.

**R2 — Flip the email verifier** (`email_webhooks.py:45-52`): same change for
`RESEND_INBOUND_WEBHOOK_SECRET` → warning + `return False`; route already 401s on
`False` (:153-154). Both shadow log strings were deliberately kept verbatim-in-agreement
— the replacement strings stay in agreement too.

**R3 — Empty the allowlist + pin.** `test_webhook_verifiers_fail_closed.py:47-50` —
remove both entries; `:130-133` `test_allowlist_only_contains_known_shadow_verifiers`
becomes an empty-set pin (or is deleted — decide in plan). The parametrized flip test
then asserts `False` for Slack + email when the secret is unset (RED first).

**R4 — Flip the shadow tests.** `test_slack_webhook.py:31-80` (shadow-accept → 401 /
`False`, drop the marker assertions) and `test_email_webhooks.py:367-397` (→ `False`,
no shadow log). Configured-secret tests (:82-122 Slack; :350-365 email 401) unchanged.

**R5 — Startup warning re-scoped, not deleted.** `warn_unconfigured_webhook_secrets`
(`main.py:140-187`): the "being accepted unverified" wording is false post-flip →
re-word to a fail-closed notice ("webhook deliveries will be rejected until you set X —
see SELF_HOSTING.md"). Kept because an unset secret now silently breaks delivery;
`test_startup_webhook_secret_warnings.py` updated to the new wording.

**R6 — Docs truth.** SELF_HOSTING.md:2468-2469 (table rows) + :2473-2478 (grace-period
paragraph) → fail-closed wording + configure-the-secret instructions;
`.env.example:36-44` + `.env.prod.example:128-136` shadow copy → fail-closed copy.
CHANGELOG: a behavior-change entry (unset secrets now reject Slack/email webhooks) +
correction of the grace-period entry (CHANGELOG.md:319-324); DEV-TRACKING follow-up
(:423-426) → **FIXED** with a shipped summary + merge-facts placeholder.

**R7 — Badge stays.** The Settings badge (`integrations.py:263-275` +
frontend `integrations/page.tsx:401-419`) reports "signature not verified — set the env
var"; accurate post-flip (unset ⇒ deliveries rejected). No copy says "future release" —
leave it; only add a test/assertion if the plan wants to pin the flipped semantics.

### Should-have

- **S1 — Note the generic-webhook per-source `secret_token` fail-open** (source_webhooks.py:270-274)
  as a separate follow-up (out of the seven verifiers; not in scope here) — recorded,
  not fixed.

### Nice-to-have (deferrable)

- **N1 — Delete the now-empty shadow machinery** beyond the two inline branches — the
  shared plumbing is minimal (badge + startup warning, both re-scoped live); nothing
  further to delete. (Skip.)

## Technical Considerations

- **Services:** backend-api only (verifiers, sweep test, shadow tests, startup warning,
  docs). No frontend change (badge survives); no migration; no plan gate
  (`SELF_HOSTED=true`).
- **Env vars read at import time** (`source_webhooks.py:33`, `email_webhooks.py:38`) —
  the flip is only the `if not secret` branch; no env handling change. The email
  verifier takes no secret argument (module constant) — tests patch the constant
  (`_call_email`, test_webhook_verifiers_fail_closed.py:65-69).
- **The sweep test is the guard.** RED first: remove the entries + empty-set pin, watch
  it fail against the still-fail-open verifiers, then flip the branches → GREEN. The
  shadow period "cannot become permanent" is enforced by this exact sequence.

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Real-traffic breakage** — an operator with Slack/email webhooks and no secret loses deliveries | Explicit CHANGELOG + SELF_HOSTING behavior-change note with configure instructions; startup warning re-scoped to a fail-closed notice; the Settings badge (Slack) stays as the visible cue |
| R2 | **Shadow remnants** — the startup-warning test or env-example copy still claims "accepted unverified" | R5/R6 cover both; grep-sweep gate in the plan |
| R3 | **Two-string agreement drift** (Slack + email warning wording) | The plan pins the replacement strings in one place; both verifiers keep the identical wording |

**Open questions**
- **OQ1 — Keep or delete the startup warning?** *Keep, re-scoped* — an unset secret now
  silently breaks delivery; a boot notice prevents the silent-failure class the repo
  has repeatedly shipped.
- **OQ2 — Empty-set pin vs delete** of `test_allowlist_only_contains_known_shadow_verifiers`:
  *Keep as an empty-set pin* — it prevents a future verifier being silently added back
  to shadow.

## Out of Scope

- **The generic-webhook per-source `secret_token` fail-open** (source_webhooks.py:270-274)
  — recorded as S1 follow-up, not fixed.
- Changing the HMAC/verification schemes (only the fail-open posture).
- Intercom/Zendesk/Jira/Asana/Linear verifiers (already fail closed).
- Frontend work (badge survives unchanged).

## Honest limits

- This is a **behavior change**: Slack/email webhook deliveries are rejected until the
  signing secret is configured. Not a regression — the intended end of the documented
  grace period.
- The email verifier had no Settings badge (it's a FeedbackSource, not an
  Integration) — its enforcement is surfaced via the startup warning + the 401s only.

## Self-critique (Phase 4)

- 🔴 **The flip is the breaking change.** Every plan step must treat the sweep test as
  RED-first and the docs/CHANGELOG as "operators will hit this" copy, not afterthoughts.
  The behavior-change note is not optional.
- 🟡 **Email-badge asymmetry** (email had no badge) is a documentation-only gap — the
  startup warning + docs carry the load; stated honestly, not papered over.
- 🟢 The change set is small, precisely mapped (dig enumerated every line), and
  reversible (set the secret back / revert the branch).

**The question I'd want answered before greenlighting:** has anyone actually configured
`SLACK_SIGNING_SECRET` / `RESEND_INBOUND_WEBHOOK_SECRET` in a real install — if the
majority of self-hosters run without them, this flip silently breaks their Slack/email
ingestion and the "helpful" notice is the only safety net. — The shadow period was
always temporary by design (the guard test enforces it); the grace has run its course.
Flip it, with the notice front and center.
