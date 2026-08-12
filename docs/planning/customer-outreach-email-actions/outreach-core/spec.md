# Spec — outreach-core

**Feature:** `customer-outreach-email-actions`
**PRD:** `../prd.md` (approved 2026-08-12)
**Aspect boundary:** everything both send paths consume — the data model, the outreach
template registry, the worker send helper (opt-out + cooldown + List-Unsubscribe), the
unsubscribe token/endpoint, and the per-customer opt-out mutation. No playbook/bulk
endpoint logic here (their aspects consume this).

## Problem slice

Both send paths (playbook `send_email` step, bulk campaign) need one shared set of
primitives; without them they'd each reimplement opt-out, cooldown, unsubscribe and the
Resend call, and the two copies would drift (the repo's known trap class).

## In-scope requirements

1. **Migration** (one Alembic revision, single head): add
   `customer_health_scores.outreach_opt_out` (`Boolean NOT NULL`, server default `false`);
   create `outreach_campaigns` and `outreach_campaign_recipients` (schema in PRD Data
   Model; exact columns below).
2. **Outreach template registry** — backend `src/services/outreach_templates.py` with keys
   `re_engagement` and `weekly_digest_entry` (must match the seeder's `template:` config
   values verbatim: `playbook_seeder.py:111,215`), each `{key, label, description,
   subject, body}`; body is plain text with `{{CUSTOMER_NAME}}` / `{{PRODUCT_NAME}}`
   placeholders; a pure `render_outreach_template(key, customer_name, product_name)`
   function. Exposed read-only via `GET /api/v1/outreach/templates` (any authed role).
3. **Worker outreach sender** — `worker-service/src/services/outreach_sender.py`
   `send_outreach_email(db, org_id, customer_email, subject, body, *, product_name,
   template_key=None) -> dict` returning `{ok, status, reason}` with status
   `sent|skipped|failed`. Check order (each loud, never silent):
   1. opt-out flag → `skipped: opted out`
   2. cooldown key present → `skipped: in cooldown`
   3. `RESEND_API_KEY` unset → `failed: email not configured`
   4. send → on success set cooldown key; failure → `failed: <resend error>`
   Uses worker `src/email.py` `_send_email` (extended with `extra_headers` + `text`
   params); payload carries `List-Unsubscribe: <https://{APP_URL}/outreach/unsubscribe?token=…>`.
   Cooldown: Redis DB 1, key `outreach_cooldown:{org_id}:{customer_email}`, TTL
   `OUTREACH_COOLDOWN_HOURS` env (default 24). The cooldown **set** lives here; the
   **check** is also honored by both send paths (they call this helper or check the key).
4. **Unsubscribe token** — stateless HMAC-SHA256 over `"{org_id}:{email}"`, keyed by
   `LLM_ENCRYPTION_KEY`, helpers `make_unsubscribe_token` / `verify_unsubscribe_token`
   (backend canonical + worker mirror, per duplication precedent).
5. **Unsubscribe endpoint** — backend `GET /api/v1/outreach/unsubscribe?token=…` (public,
   no auth): verify → upsert the customer's `outreach_opt_out=true` on
   `customer_health_scores` (create the row if the email has no health row yet) → render a
   minimal "you're unsubscribed" HTML page. Invalid token → 400. Registered in `main.py`.
6. **Per-customer opt-out mutation** — backend `PATCH /api/v1/customers/{email}`
   (admin/owner) accepting `{"outreach_opt_out": bool}` only (extra fields 422, `extra="forbid"`),
   org-scoped 404, returns updated profile.
7. **Agreement pin** — test asserting the worker `OUTREACH_COOLDOWN_PREFIX` and the
   backend's are identical (both paths must write the same key); a
   `test_worker_import_sweep`-shaped test ensuring worker outreach modules import only
   worker-local code.

## Out-of-scope boundaries

- No playbook step, no bulk endpoint, no Celery campaign task (their aspects).
- No SMTP; no org-editable templates; no unsubscribe-token expiry.
- No changes to `response_sender.py`, `email_service.py` senders beyond the additive
  `extra_headers`/`text` params on `_send_email` in both processes.
- No plan gates; no churn/health/cooldown-scheme changes (automation cooldowns untouched).

## Acceptance criteria (testable)

- AC1: `alembic upgrade head` then `alembic downgrade -1` round-trips the migration;
  `alembic heads` prints exactly one head.
- AC2: `GET /api/v1/outreach/templates` returns both registry keys with label/description
  (authed, any role).
- AC3: `send_outreach_email` returns `skipped: opted out` for an opted-out customer, with
  no API call made.
- AC4: `send_outreach_email` returns `skipped: in cooldown` when the Redis key exists.
- AC5: with `RESEND_API_KEY` unset, `send_outreach_email` returns
  `failed: email not configured` (no exception).
- AC6: on successful send (Resend mocked), the cooldown key exists in Redis DB 1 with TTL
  ≈ `OUTREACH_COOLDOWN_HOURS` and the payload includes the `List-Unsubscribe` header.
- AC7: token round-trip: `verify(make(org, email))` is True; a token minted for a
  different email/org fails.
- AC8: `GET /outreach/unsubscribe?token=<valid>` sets `outreach_opt_out=true` (creating a
  health row when absent); invalid token → 400.
- AC9: `PATCH /api/v1/customers/{email}` with `{"outreach_opt_out": true}` flips the flag
  (admin/owner); cross-org email → 404; extra fields → 422; member role → 403.
- AC10: worker test asserts `outreach_sender` imports nothing from `src.api`/backend-api
  packages.

## Dependencies & sequencing

First aspect (everything else consumes AC2/AC3-6 contracts). Venv prerequisite: the
worktree has no venvs — create `services/backend-api/venv` + `services/worker-service/venv`
with `python3.12` and install `requirements.txt` before any pytest run.

## Open questions / risks

- Resend payload field for `List-Unsubscribe` is `headers` — verify against
  `email_service.py:91-123` payload shape in the plan; extend both `_send_email` copies
  identically (parameter names must match across processes).
- `APP_URL` default `http://localhost:3000` points at the **frontend** — the unsubscribe
  link therefore targets the frontend page (built in `bulk-campaign-ui`), which calls this
  backend endpoint. The header's URL must be `{APP_URL}/outreach/unsubscribe?token=…`.
- `verify_unsubscribe_token` lives in the backend only (the endpoint is backend-only) —
  the worker needs only `make_unsubscribe_token` to compose the header.
