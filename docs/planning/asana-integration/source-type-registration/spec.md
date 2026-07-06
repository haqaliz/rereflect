# Aspect: source-type-registration

**Slice of:** Asana Integration slice 1. **Owner:** one backend engineer/agent (small). **Depends on:** none (independent of connect/create).

## Problem slice & outcome
`asana` appears as a selectable own-auth source type, for parity with Jira/Zendesk/Linear. This is a **lightweight backend registration only** — the worker has no Jira adapter and gets no Asana adapter (outbound-only slice). No inbound ingestion is built.

## In scope
- `src/api/routes/feedback_sources.py`:
  - Add an `asana` `SourceTypeInfo` in `list_source_types()`: `type="asana"`, `name="Asana"`, `requires_integration=False`, `available=True` (mirror the `jira` entry).
  - Add `"asana"` to the `valid_types` list in `create_feedback_source`.

## Out of scope
- Any worker adapter / `get_adapter` registry entry.
- Any worker mirror model or column-parity test.
- Inbound feedback-source wizard pages (frontend) and `TRIGGER_OPTIONS.asana` — not built in the outbound-only slice.

## Acceptance criteria (testable)
- `test_feedback_sources_asana.py`: `GET /types` includes `asana` with `requires_integration=False` and `available=True`; `create_feedback_source` accepts `source_type="asana"` (mirror `test_feedback_sources_jira.py`).

## Dependencies & sequencing
Independent — can be done in parallel with backend-connection. Trivial.

## Open questions / risks
- None. Confirm no plan-gating branch is required (OSS — all unlocked).
