# Aspect Spec — source-type-registration

**Parent PRD:** `../prd.md` · **Aspect dir:** `source-type-registration/` · **Depends on:** `backend-connection`

## Problem slice & outcome

Make `jira` a **selectable** feedback-source type (own-auth, like Linear) so it appears in the source
wizard. This is *registration only* — NO inbound Jira→feedback ingestion. Outcome: `GET
/api/v1/feedback-sources/types` includes a `jira` entry with `requires_integration=false`, and
creating a source of type `jira` validates.

## In scope (backend only; frontend wizard entries live in the `frontend` aspect)

- `services/backend-api/src/api/routes/feedback_sources.py`:
  - Add `"jira"` to the `valid_types` list (~L269).
  - Add a `SourceTypeInfo` entry in `list_source_types()` (~L157-203): `type="jira"`,
    `requires_integration=False`, `available=True`, name/description mirroring the Linear entry (own
    OAuth/own-auth — Jira brings its own `JiraIntegration`, not a generic `Integration` row).
  - **No** feature-gating branch (unlocked) and **no** `integration_id`/`provider_config` hydration
    block (own-auth, like Linear — Linear has no branch in the validation section either).
- **No worker change** (`source_events.py` untouched — inbound ingestion is out of scope; a
  source_type with no matching branch falls through to the base query, exactly as `linear` does).

## Out of scope (this aspect)

- Frontend source-wizard icon/color/branch (→ `frontend`).
- Any inbound Jira event/poll pipeline (v2).

## Acceptance criteria (testable — TDD)

- Extend the existing feedback-sources tests (or add `test_feedback_sources_jira.py`):
  - `GET /types` includes a `jira` entry with `requires_integration=false`, `available=true`.
  - Creating a feedback source with `source_type="jira"` is accepted (passes `valid_types`); a bogus
    type still 422s.
  - No plan gate blocks `jira` source creation on a Free-plan org.

## Dependencies & sequencing

Small. Logically after `backend-connection` (the wizard's own-auth check calls `jiraAPI.getStatus()`),
but the backend enum change itself is independent and can land in parallel with `backend-create-issue`.
Blocks the `frontend` source-wizard entries.

## Open questions / risks

- Confirm no other backend switch enumerates source types (grep `valid_types`/`source_type ==`), so a
  single enum addition is sufficient.
