# Worker health recompute through a backend internal endpoint

Status: implementing (GitHub #3)
Aspect: `api-and-seam`

## Problem

`health_score_service` ships only in `services/backend-api`. The worker image does not
contain it, so `src/services/health_recompute.py` has always returned `False` in production.
Five worker call sites (analysis, usage, HubSpot, Salesforce, segments) therefore never
refreshed `customer_health_scores`. The worker tests hid this by injecting a fake module.

## Chosen fix (owner decision: option 1)

The worker calls a backend internal endpoint that runs the existing
`update_customer_health`. No scoring logic is copied or extracted, so backend- and
worker-triggered recomputes keep identical side effects.

## Requirements

1. **Backend endpoint** — `POST /api/v1/internal/health/recompute`
   - Shared-secret auth from `INTERNAL_API_SECRET`; header `X-Internal-Secret`.
   - Secret unset on the server → `503` (fail closed). Missing/wrong header → `403`.
   - Body `{org_id, customer_email}`; empty email → `422`.
   - Calls `update_customer_health`, commits, returns `{status, health_score}` read
     from the upserted `customer_health_scores` row.
2. **Worker seam** — `request_health_recompute` posts to the endpoint when
   `INTERNAL_API_URL` + `INTERNAL_API_SECRET` are configured.
   - Missing config → one ERROR log per process naming the consequence; return `False`.
   - Session in a transaction → register `after_commit` (`once=True`) so the backend
     reads committed feedback/usage/CRM rows. Session idle → post immediately.
   - HTTP timeout ~5 s; failures log org/email and never raise into the task.
   - Return `True` when the recompute was scheduled/attempted.
3. **Tests** — seam tests pin missing config, after-commit, rollback → no POST,
   HTTP failure → no raise; task tests assert delegation to the seam and keep ordering
   (probability updater after the health call).
4. **Config/docs** — `.env.example`, `.env.prod.example`, prod compose, self-hosting
   docs; CHANGELOG under Unreleased → Fixed.

## Non-goals

- No shared package, no scoring mirror, no retry queue for failed recomputes.
- `segments.py` keeps its own guarded import of `compute_sentiment_trend`.

## Acceptance criteria

- With both env vars set, a committed worker task causes one backend recompute and the
  `customer_health_scores` row reflects it.
- A rolled-back worker transaction causes no HTTP call.
- The backend rejects unauthenticated calls (503 when unconfigured, 403 otherwise).
- A backend outage does not fail the worker task that triggered the recompute.

## Risks

- Worker → backend is a runtime dependency; a slow/unreachable backend costs up to the
  5 s timeout per customer after commit.
- `after_commit` fires synchronously inside `Session.commit()`; a failed POST is logged,
  not retried.
