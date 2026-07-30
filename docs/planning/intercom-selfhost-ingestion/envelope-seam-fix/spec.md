# Aspect Spec — `envelope-seam-fix`

**Feature:** `intercom-selfhost-ingestion`
**PRD:** `../prd.md` (requirement **R1**)
**Date:** 2026-07-31
**Size:** S (one production line + one rewritten assertion + a new contract fixture and two tests)

---

## Problem slice

Intercom webhook deliveries are received and authenticated, but produce **no feedback
item, in any release**. The backend route hands the worker adapter a payload shape the
adapter does not accept.

- `services/backend-api/src/api/routes/source_webhooks.py:333` queues
  `event_data=payload.get("data", {})` — the unwrapped `data` object.
- `services/worker-service/src/adapters/intercom.py` expects the **full envelope** at
  four sites: `:73` (`_get_body_text`), `:88-89` (`extract_content`), `:148`
  (`get_external_ids`), `:171` (`fetch_context`).

**Traced end state (verified by reading, not assumed):** with the stripped shape,
`extract_content` sees `topic == ""` and `item == {}`, falls to
`_extract_new_conversation({})`, and returns `text == ""`. `_process_event_for_source`
then hits its length guard (`source_events.py:287-293`) and returns
`{"source_id": ..., "status": "empty_text"}`, logging the event as `ignored`. **That
exact return value is the RED assertion for this aspect.**

Note two things the stripped shape does *not* break, so the fix is correctly scoped:
- `check_triggers` still matches non-keyword triggers, because the route passes the topic
  separately as `event_type` (`source_events.py:242`). Only *keyword* triggers are broken.
- `get_external_ids` degrades to `("", "")` rather than raising, so nothing crashes —
  which is precisely why this went unnoticed for every release.

## Which side is the bug — settled by the tests, not by preference

- `services/worker-service/tests/test_intercom_adapter.py:18,26,34,91-92,109-110` feeds
  the adapter the **full envelope** and passes. The adapter's contract is the envelope.
- `services/backend-api/tests/test_intercom.py:438` asserts `event_data=payload["data"]`
  — it **pins the defect as correct**.

Therefore: fix the **route**, leave the adapter untouched, and **rewrite** (never extend)
the route assertion. The route already reads the envelope correctly two lines earlier to
derive `conversation_id` (`source_webhooks.py:319`), confirming this is a handoff slip.

## Why a contract fixture rather than "one more test"

Both sides were already tested. Both were green. They disagreed with each other, and the
disagreement survived because **the two sides live in different services** — worker-service
cannot import backend-api, and their suites run from different working directories with
different `PYTHONPATH`s. No single test could see both halves, so none did.

`DEV-TRACKING.md:441-446` already generalized this family after three prior instances
("green tests over code that never executes in production"). This is the fourth. A test
that only re-checks one side would leave the seam exactly as unguarded as it is now.

**The artifact is a committed golden fixture** — the literal JSON envelope Intercom
delivers — read by both suites:

- the **backend** test asserts *"the shape I hand to the queue is this fixture"*;
- the **worker** test asserts *"given this fixture, I produce non-empty content"*.

Either side drifting breaks its own assertion against the shared file. That is the
smallest construct that actually pins a cross-process seam.

## In scope

1. `source_webhooks.py` — pass the full `payload` as `event_data`, with a comment naming
   the adapter's contract and this spec.
2. Commit the golden fixture: `services/worker-service/tests/fixtures/intercom_webhook_envelope.json`.
3. Rewrite the pinning assertion in `services/backend-api/tests/test_intercom.py`.
4. New backend test: the queued `event_data` equals the golden fixture exactly.
5. New worker test: the golden fixture through `IntercomAdapter` yields non-empty
   `text` and a real dedup id — and, at the `_process_event_for_source` level, a created
   `FeedbackItem` rather than `{"status": "empty_text"}`.

## Out of scope (later aspects, or other cards)

- Token-paste connect, per-org secrets, the pull path, `customer_email` side-loading —
  R2/R4/R5/R7, separate aspects.
- The adapter's four envelope-reading sites are **not** refactored. They are correct.
- `fetch_context` enrichment (`intercom.py:171`) is exercised only when a source sets
  `include_context`/`include_author`; not enabled here.
- Docs/changelog truth-up. The changelog's known-limitation entry (`CHANGELOG.md:53-60`)
  is **deliberately left standing** by this aspect: the limitation is only genuinely gone
  once an operator can *connect* on a self-host, which is `token-paste-connect`. Removing
  it here would trade one false statement for another. Handled in `cleanup-and-docs`.

## Acceptance criteria

| # | Criterion | Verification |
|---|---|---|
| A1 | A conversation-created delivery produces one `FeedbackItem` with the message body as text | Worker test over `_process_event_for_source`; asserts a real item, not `empty_text` |
| A2 | The queued `event_data` is byte-equal to the golden fixture | Backend test reading the shared fixture |
| A3 | The old assertion pinning `payload["data"]` no longer exists | `grep` returns no match; the rewritten test asserts the envelope |
| A4 | `get_external_ids` yields a non-empty dedup id, so re-delivery dedups | Worker test asserts a second identical delivery returns `duplicate` |
| A5 | Keyword triggers work | Worker test with a `keywords` trigger matching body text |
| A6 | No regression in the other six adapters | Full worker suite green |
| A7 | Signature verification is untouched and still fails closed | `tests/test_webhook_verifiers_fail_closed.py` green, unmodified |

## Dependencies & sequencing

**None — this is the root of the dependency graph.** Every other aspect assumes the
adapter receives a usable envelope; building the pull path first would mean building on a
seam known to be broken. Ship this first and independently.

## Risks

| Risk | Mitigation |
|---|---|
| Other producers rely on the stripped shape | Only the webhook route produces `intercom` events today (the pull path does not exist); confirm by grep before changing |
| The fixture drifts from what Intercom really sends | Derive it from the shape already encoded in the passing adapter tests, and cite the source in the file |
| A cross-service relative path breaks in CI | CI uses `actions/checkout@v4` (full repo) with per-service `working-directory`; the path resolves. The test must **fail loudly** if the fixture is missing — never skip, which is how this class of gap hides |
