# Aspect Spec — segment-api

**Parent PRD:** `../prd.md` · **Services:** backend-api · **Sequence:** 2nd (after segment-engine)

## Problem slice & outcome

The persisted `segment` is exposed on the customers-list endpoint (as a returned field + a filter param)
and on the shared customer profile serializer — so both the internal dashboard route and the public REST
API carry `segment` with no drift.

## In scope

1. **List filter + column.** `GET /api/v1/customers/` (`list_customers`, `customers.py:247-347`):
   - Add `segment` query param, validated against the segment slug allowlist (near `customers.py:24-27`;
     reuse the slug set exported by `segment_service`). Invalid slug → 422.
   - Add filter clause to the query builder (`customers.py:276-306`): `WHERE segment = :segment`.
   - Add `segment` to `CustomerListItem` (`customers.py:39-50`) and populate it (`customers.py:322-337`)
     directly from the row (no recompute at read time).
   - Optional should-have: allow `sort_by=segment` (add to `VALID_SORT_FIELDS` + `sort_column_map`).
2. **Serializer field.** Add `segment` to `serialize_customer_profile` Core block
   (`customer_profile_serializer.py:57-66`) and to `CustomerProfileResponse` (`customers.py:83-116`) so the
   key survives the `model_fields` filter (`customers.py:397`). This automatically surfaces `segment` on the
   public REST API customer payloads (shared serializer).
3. **Docs (critique gap #3).** Update `docs/API.md` (new `segment` field on public customer profile/list),
   `AI-TRACKING.md` M3.4 (segment shipped), and `docs/SELF_HOSTING.md` (segment meanings + note that
   usage-dependent segments need usage events wired).

## Out of scope

- Computing/persisting the segment (that's `segment-engine`).
- Frontend rendering (`segment-ui`).
- A dedicated segments-list or segment-definitions endpoint (later slice).

## Acceptance criteria (testable)

- `GET /api/v1/customers/?segment=silent_churner` returns only rows with that segment; paginated; other
  filters (risk_level, search) compose correctly.
- Invalid `segment` value → 422 with a clear message.
- `CustomerListItem` and the profile response both include `segment` (nullable → `unsegmented` or null per
  PRD OQ2 decision).
- Public REST API customer profile/list payloads include `segment` (serializer shared — assert via the
  public endpoint test).
- All reads org-scoped (existing `organization_id` filter unchanged); cross-org still 404/empty.
- Existing customers-API tests stay green.

## Dependencies & sequencing

- Depends on `segment-engine` (column + slug set must exist).
- Blocks nothing hard, but `segment-ui` consumes this contract — keep the field name/param name stable.

## Risks

- Slug allowlist drift between engine and API — mitigate by importing the canonical slug set from
  `segment_service`, not re-declaring it.
