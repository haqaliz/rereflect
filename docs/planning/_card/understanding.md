# Phase 2 — Deep-dig understanding: Zendesk inbound feedback source

Synthesized from 3 read-only dig agents (worker / backend / frontend). All paths under the worktree.

## What the task really is

Add **Zendesk** as an inbound feedback source: operator connects their Zendesk (BYOK), tickets
flow into Rereflect as `feedback` rows, then ride the existing analysis → churn → health →
copilot → automations pipeline. Mirror the shipped Intercom/Jira/Linear slices. OSS self-hosted,
all unlocked.

## The one real architectural decision: how tickets get INGESTED

The dig surfaced that Rereflect has **two ingestion patterns**, and the shipped inbound
integration (Intercom) uses the *push* one — there is **no productionized inbound *pull***:

| | **Adapter / webhook-push** (canonical, tested) | **Connector / poll-pull** (stub, inert) |
|---|---|---|
| Worker | `src/tasks/source_events.py` `process_source_event` + `src/adapters/*` (`BaseSourceAdapter`) | `src/tasks/integrations.py` `sync_all_integrations` + `BaseConnector` |
| Trigger | Inbound webhook HTTP POST → `queue_source_event` | Celery beat daily 02:00 |
| Dedup | `FeedbackSourceEvent (source_id, external_message_id)` existence check | none |
| Cursor | n/a (pushed) | `Integration.last_synced_at` high-water mark |
| Status | **Intercom fully wired + tested** | **every connector (incl. `ZendeskConnector`) returns `[]`** |

- **Jira/Linear are OUTBOUND** (create issue from feedback) — they give us the **connection**
  template but **no inbound ingestion** to copy.
- **Intercom is the only inbound template**, and it is **webhook-push** via the adapter pattern.

### Option A — Pull/poll via the pasted API token  *(brief's default; best self-host fit)*
Operator pastes subdomain + email + token; a Celery beat task polls Zendesk
(`GET /api/v2/incremental/tickets` or search) using the stored token, cursor = `last_synced_at`,
creates `FeedbackItem` + `FeedbackSourceEvent` (dedup on ticket id). No public ingress needed —
good for self-hosters behind a firewall. **Cost:** the poll loop is un-productionized; we must
harden it (route pulled tickets through the same `FeedbackItem`/`FeedbackSourceEvent` creation +
add a `zendesk` source-matching branch), and it's near-real-time at best (beat interval).

### Option B — Webhook push (mirror Intercom adapter)  *(most-tested code path)*
Operator configures a Zendesk webhook/trigger → new `/api/v1/webhooks/zendesk/events`
(HMAC-verified) → `ZendeskAdapter` (`BaseSourceAdapter`) → existing tested pipeline. Real-time,
reuses the battle-tested path. **Cost:** requires the self-hosted Rereflect to be publicly
reachable by Zendesk + operator sets up a Zendesk trigger; the pasted API token becomes
vestigial for ingestion (only used for validate/enrichment).

> **Recommendation to pressure-test in the interview:** Option A (pull) for self-host coherence —
> the pasted token does real work, no inbound ingress requirement — while *reusing* the adapter's
> content-extraction + `FeedbackSourceEvent` dedup so we inherit the robust parts. Confirm with user.

## Connection (settled — Jira own-auth pattern)

- New `zendesk_integrations` table (one row/org): `subdomain`, `email`, `api_token`
  (Fernet-encrypted via `src/utils/encryption.py`), `token_hint`, identity fields, `is_active`,
  `last_synced_at`, `last_sync_status`, `last_error`, timestamps, `UniqueConstraint(organization_id)`.
- `ZendeskClient` (mirror `jira_client.py`): Basic auth `("{email}/token", api_token)`, base
  `https://{subdomain}.zendesk.com/api/v2`, `validate()` → `GET /users/me.json`, error taxonomy.
- Routes `/api/v1/integrations/zendesk/{connect,status,disconnect,test}` (mirror
  `jira_integration.py`), `require_admin_or_owner` + `get_current_org`, token never in responses.
- **Two-layer SSRF gate**: route normalizes host to `*.zendesk.com` + `socket.getaddrinfo`
  reject loopback/private/link-local (422); client re-asserts scheme+host suffix. Missing
  `LLM_ENCRYPTION_KEY` → 422 not 500.
- Register `zendesk` in `feedback_sources.py` `/types` (`requires_integration=False`, own-auth
  like jira/linear) + `valid_types`. `Integration.type`/`FeedbackItem.source` comments already
  list `zendesk`; no enum change.
- **Caveat: multiple Alembic heads** — run `alembic heads` and set `down_revision` correctly (or `merge`).

## Frontend (greenfield app; landing mostly done)

- App has **zero** Zendesk refs. Add: `ZendeskIcon.tsx`, `lib/api/zendesk.ts`, connect page
  `settings/integrations/zendesk/page.tsx` (mirror Jira token-paste — fields: subdomain, email,
  token). Wire into integrations list (tile + Active block), the 4 feedback-source pages'
  `SOURCE_ICONS`/`SOURCE_COLORS`, the `new` wizard's zendesk branch, and `TRIGGER_OPTIONS`.
- **Landing already has** a Zendesk "coming soon" page + `integrations.ts` entry (l.269-294) +
  IntegrationBar/FAQ/sitemap. Upgrade `status: 'coming_soon'` → `'available'`, fill
  `setupSteps`/`useCases`, swap page to the full intercom/jira layout.
- Zendesk is inbound-only → **no** outbound `createIssue`/`getProjects`/`CreateIssueDialog`.

## Test templates (TDD mirrors)

- Worker: `tests/test_intercom_adapter.py` → `test_zendesk_adapter.py` (if adapter path).
- Backend: `test_jira_connection.py`, `test_jira_client.py`, `test_feedback_sources_jira.py`,
  `test_jira_models.py` → zendesk analogs.
- Frontend: `lib/api/__tests__/jira.test.ts` → `zendesk.test.ts`; integrations contract test.

## Open questions for the interview

1. **Ingestion mechanism: pull (A) vs webhook-push (B)?** (biggest decision)
2. **Granularity:** one feedback per ticket (recommended) vs per ticket-comment.
3. **Which tickets:** all / only new / by status/tag/view filter? Trigger config shape.
4. **Slice-1 boundary:** connection + ingestion + wizard + landing upgrade in one slice, or
   connection-only first then ingestion?
5. Customer mapping: set `feedback.customer_email` from the ticket requester email (yes → feeds
   Customer 360 / health). Confirm.
