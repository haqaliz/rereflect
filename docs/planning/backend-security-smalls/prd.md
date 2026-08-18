# PRD — Backend security smalls (oauth state, generic webhook secret, events-emit)

**Slug:** `backend-security-smalls` · **Branch:** `chore/backend-security-smalls`
**Type:** chore · **Created:** 2026-08-18
**Card:** `docs/planning/_card/card.md`

---

## Item 1 — P3: OAuth state out of the process dict

**Problem.** `oauth_states` (integrations.py:45-46) is a module-level dict with no
TTL: OAuth callbacks (Slack :841-871, Intercom :1032-1062) fail intermittently on any
multi-replica backend, and entries never expire (the stored `created_at` is never
read). **Linear has the identical dict** (linear_integration.py:57) — same defect
class; fixed together or half the bug stays.

**Fix (locked): stateless HMAC-signed state, the Salesforce precedent.**
`salesforce_integration.py:252-289` already implements signed state
(`_sign_state`/`_verify_state`, app-secret keyed, `STATE_TTL_SECONDS = 600`, fail
closed on any invalid/expired). Mirror it for Slack, Intercom, and Linear:
- `state = sign({organization_id, name, nonce, exp})` — org + name travel in the
  signed blob (the dict's payload), no store, cross-process by construction, no
  Redis-outage question (the cooldown-style fail-open would be a CSRF hole — this
  sidesteps it entirely).
- Callback verifies signature + freshness → same fail-closed
  `?oauth_error=invalid_state` path on any failure.
- Single-use: the 10-min TTL bounds replay; the OAuth code exchange is
  single-use anyway (Salesforce accepts the same trade).
- **Tests:** the ~12 direct-seeding sites (test_integrations.py:765-771, :818-824;
  test_intercom.py:157-165, :221-228; test_linear_oauth.py:210-215, :267-274,
  :334-338, :412-415) rewrite to drive the signed-state helpers (or the authorize
  route's state generation). The RBAC-spec constraint (oauth_states must keep
  name/signature) is superseded — the dict goes away; documented in the PRD.

## Item 2 — S1: generic inbound webhook secret posture

**Problem.** `handle_generic_webhook` (source_webhooks.py:232-305) verifies the
per-source `secret_token` only `if secret_token:` (:265-271) — and the dig found
`secret_token` is **dead configuration**: nothing generates it, no UI sets it, the
route is undocumented in SELF_HOSTING. Every generic source is a pure capability-URL
source — and the capability URL is **member-visible** (GET sources returns
`provider_config.webhook_id` + `webhook_url`), so the "capability" is weak.

**Fix (locked): mint-and-require on new sources; grandfather + document existing.**
- On webhook-source creation (`feedback_sources.py:412-414`): generate
  `secret_token = secrets.token_urlsafe(32)`, store in `provider_config`, return it
  **display-once** in the create response (the Zendesk/Jira/Asana display-once
  pattern). New sources fail closed: missing header or mismatch → 401.
- Existing sources without a secret: unchanged (capability-URL) — **no breaking
  change for installs**; SELF_HOSTING documents how to add a secret via PATCH
  (`provider_config.secret_token` passes through verbatim) and the model.
- Docs: a SELF_HOSTING row for the generic inbound webhook (currently absent from
  the inbound-secrets table) stating the model + the secret requirement for new
  sources.
- Storage caveat: `secret_token` lives in `provider_config` JSON (same as
  `webhook_id`); the credential-encryption sweep covers dedicated credential
  columns — flag per-source secret encryption as a follow-up note.
- **Tests:** the route currently has ZERO tests — add: no-secret source (grandfathered
  → accepted), new source without header → 401, wrong secret → 401, correct → 200,
  display-once in create response.

## Item 3 — events-emit: delete the orphan

**Problem.** `POST /api/internal/events/emit` (events_ws.py:149-178) has zero
production callers (verified repo-wide; it is a realtime-WS push seam, NOT the webhook
dispatcher — deletion cannot break webhook dispatch). The env examples say "Nothing
in Rereflect calls it today"; the archived PRD's example would have 403'd anyway.

**Fix (locked): delete.** The HTTP endpoint + `InternalEventRequest` model
(:142-146) + the 11 tests (`test_event_emitter.py` TestInternalEmitEndpoint /
TestInternalEmitAuth) + the env-example blocks (.env.example:45-51,
.env.prod.example:136-143) + SELF_HOSTING:2485-2492. The WS side (`/ws/events`),
`emit_event` service, and its ~11 in-process callers all survive.

## Out of scope (guardrails)

- P7 (provider duplication), intercom-oauth-path-retirement — stay deferred.
- No migrations (stateless state needs none; provider_config is JSON).
- No plan gates.

## Honest limits

- Stateless signed state uses the app secret (`LLM_ENCRYPTION_KEY`-adjacent or the
  auth signing secret — the plan pins which; Salesforce's precedent shows the
  pattern) — a secret compromise invalidates state freshness the same way it would
  with any HMAC scheme.
- The S1 grandfathering means pre-existing sources stay capability-URL until their
  operator adds a secret — documented, not silent.
