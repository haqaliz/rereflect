# Aspect Spec — customer-fields-model

**Parent PRD:** `../prd.md` · **Owner agent:** `db-schema-designer` → `be-fastapi-specialist`
**Sequence:** FIRST (no deps). Blocks `bulk-actions-api`, `playbook-cohort-run`, `customers-bulk-ui`.

## Problem slice & outcome

Customers (the `CustomerHealth` / `customer_health_scores` record) have no `tags` and no CS-owner field.
Add both so the bulk tag/assign actions have something to write, and surface them on the read paths.

## In scope

- **Alembic migration** (single head → `down_revision = "6d7e00e682c7"`; verify with `alembic heads` before
  writing) adding to `customer_health_scores`:
  - `tags` — `sa.JSON`, nullable, server/py default empty list `[]`.
  - `cs_owner_user_id` — `Integer`, `ForeignKey("users.id", ondelete="SET NULL")`, nullable.
  - Index `ix_customer_health_cs_owner` on `(organization_id, cs_owner_user_id)`.
  - `downgrade()` drops index + both columns.
- **Model** (`src/models/customer_health.py`): add `tags` (JSON, default list) and `cs_owner_user_id`
  columns + a `cs_owner` relationship to `User` (lazy, `foreign_keys=[cs_owner_user_id]`). Confirm no
  cascade surprise on the User side.
- **Serializers** (`src/api/routes/customers.py`): add `tags: list[str]` and a compact
  `cs_owner: {id, email} | None` to `CustomerListItem` (list) and the profile response
  (NOTE: the `User` model has only `email` — there is no `name`/`full_name` field, so the owner ref is
  `{id, email}` only)
  (`CustomerProfileResponse`). Resolve owner without an N+1 — batch-load owner users for the page (mirror the
  existing batched `CustomerUsage` fetch at `customers.py:324-336`).

## Out of scope

- The bulk endpoints themselves (aspect `bulk-actions-api`).
- Tag *filtering* on the list API (display + bulk-set only; JSON column is deliberate).
- Any change to segment/health computation or the duplicated `segment_service`.

## Acceptance criteria (testable)

- `alembic upgrade head` then `alembic downgrade -1` round-trips cleanly on a scratch DB.
- New `CustomerHealth` rows default `tags == []`, `cs_owner_user_id is None`.
- `GET /customers/` and `GET /customers/{email}` return `tags` and `cs_owner` (null owner when unassigned);
  existing fields byte-identical (characterization test on the list response before/after).
- Deleting a user sets owned customers' `cs_owner_user_id` to NULL (FK behavior test).
- No N+1 for owner resolution on a multi-row page (assert query count or batched load).

## Dependencies & sequencing

None upstream. Must land before the API aspects (they import the columns). TDD: write the migration
round-trip + serializer tests RED first.

## Risks

- `sa.JSON` default: use a callable/`default=list` in the model and `server_default` care in the migration to
  avoid the shared-mutable-default trap.
- Batch owner-load must not regress the list endpoint's existing no-N+1 property.
