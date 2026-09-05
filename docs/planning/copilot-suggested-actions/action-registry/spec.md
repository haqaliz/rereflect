# Spec: action-registry

## Problem slice

Something must decide what is executable, who may execute it, and what happens when it runs.
Without a registry the only alternatives are trusting a model to name an executor or wiring
the copilot directly to mutation routes — both unacceptable.

**User outcome:** clicking a proposed action applies it, reports what changed, and cannot be
made to do anything the registry does not permit.

## In-scope

- **The registry.** A server-side map of `action` id → entry declaring: `min_role`, a params
  schema, and the executor callable. It is the *only* dispatch path; an unknown `action` id is
  rejected before anything else happens. Structural precedent: `sql_validator.py` +
  `schema_whitelist.py` — the model proposes, an allowlist decides.
- **Slice-1 entry:** `tag_customers` → `min_role: admin` → executes the same logic as
  `POST /api/v1/customers/bulk/tags` (`customers.py:689`), i.e. `resolve_cohort` +
  set-union tag apply, returning `BulkActionSummary{matched, updated, skipped, errors}`.
  Prefer calling the shared service (`cohort_service.resolve_cohort`) and reusing the handler's
  logic rather than issuing an internal HTTP request. If the tag-apply logic must be shared,
  extract it from the handler **without changing the route's behaviour**
  (characterization-test the existing route first).
- **The execute route.** A normal authenticated REST endpoint — deliberately *not* a WebSocket
  message, so it gets ordinary FastAPI auth, RBAC, and testability. Takes the message the
  proposal came from, the `proposal_id`, the `action` id, and the user-supplied params.
- **RBAC.** `min_role` enforced by the registry at execute time, independent of the underlying
  route's own dependency. For `tag_customers` this coincides with the executor
  (`require_admin_or_owner`, `customers.py:692`), so slice 1 introduces no asymmetry.
- **Org scoping.** From the user's DB row (`dependencies.py:99`), never a request field.
  `resolve_cohort` scopes internally and absorbs unknown/foreign emails as `skipped`.
- **One-shot guard (M9).** A successful execution of a `proposal_id` is recorded; a second
  attempt returns the prior outcome rather than re-executing. Leaning: derive from `AuditLog`
  (`target_type="copilot_action"`, `target_id=<message id>`, `details.proposal_id`) —
  append-only, no mutation of `structured_data`, no migration.
- **Audit.** Every execution writes one `AuditLog` row via `audit_service.log_action`
  (`src/services/audit_service.py`), carrying the action id, the resolved target, the params,
  and the outcome counts in `details`. The `Request` is passed so IP/UA are captured.
- **Params validation.** User-supplied values are validated against the entry's schema before
  the executor is called. Tag values inherit the executor's own rules — trimmed, de-duped, 50
  chars max (422), 20-tags-per-customer cap enforced per row at apply time.

## Out-of-scope

- Any action other than `tag_customers`, including `mode="remove"`.
- Changing `POST /customers/bulk/tags`'s own contract.
- Repairing the repo-wide RBAC inconsistency (`playbooks.py:496`, `workflow.py:142`,
  `feedback.py:715` carry no role dependency). Out of scope, recorded in the PRD.
- Rate limiting beyond what already applies.

## Acceptance criteria

- Unknown `action` id → rejected, nothing executed, nothing audited.
- A `member` JWT → **403**, nothing executed, nothing audited.
- An admin executing `tag_customers` with valid params → tags applied, `BulkActionSummary`
  returned, exactly one `AuditLog` row written.
- Emails belonging to another org, or not present → absorbed as `skipped` and reported; never
  an error, never a cross-org write.
- Executing the same `proposal_id` twice → second call does not re-execute and does not write a
  second `AuditLog` row; the prior outcome is returned.
- A tag over 50 chars → 422, nothing applied.
- A customer already at 20 tags → that row lands in `errors[]`, others still update
  (per-row behaviour, not a whole-request failure).
- A `proposal_id` that does not match a proposal on the referenced message → rejected.
- Characterization: the existing `POST /customers/bulk/tags` route behaves identically before
  and after any extraction.

## Dependencies and sequencing

Depends on `action-contract` (needs `proposal_id` and the params shape). Independent of
`deterministic-proposer` — the route can be built and tested against a hand-written proposal.

## Open questions / risks

- Route namespace: `/api/v1/copilot/actions/execute` vs under `/conversations`. Leaning
  copilot — `copilot.py` currently holds only `GET /usage`.
- Deriving one-shot state from `AuditLog` needs a `details->>'proposal_id'` lookup. Acceptable
  at this scale; revisit if actions become high-volume.
- **Registry drift risk:** as actions are added, a `min_role` could be declared weaker than the
  executor route's own dependency. Add a test asserting every entry's `min_role` is at least as
  strict as its executor's route dependency.
