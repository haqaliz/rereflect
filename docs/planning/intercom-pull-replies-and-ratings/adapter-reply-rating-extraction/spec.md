# Aspect spec — Adapter: reply & rating extraction + merge

**Feature:** `intercom-pull-replies-and-ratings` (prd.md R2) · **Aspect:** `adapter-reply-rating-extraction`

## Problem slice

The pull must turn fetched conversation parts into content the sync task can merge into
the existing per-conversation FeedbackItem, idempotently and without corrupting customer
attribution. Today the adapter (`services/worker-service/src/adapters/intercom.py`)
has `_extract_reply`/`_extract_rating` for **webhook-shaped** items (part-shaped top
level), which the pull will not produce — the pull has the full conversation object.

## In-scope

- New pure functions in `adapters/intercom.py` (or a sibling module — decide in plan,
  keeping the adapter's single-responsibility): from a **conversation object** with
  parts, produce:
  - `extract_reply_parts(conversation)` → `[{part_id, author, body, created_at}]` —
    reply-family parts only (verify `part_type`/`type` values; exclude the first
    message / non-reply parts), HTML-stripped bodies, author object retained for
    attribution decisions.
  - `extract_rating(conversation)` → `{rating, remark?, rated_at?}` (None when absent).
- `_contact_email` reuse: reply author types `user`/`contact`/`lead` → email available;
  `admin`/`bot` → **content included, email never** (existing rule, unchanged).
- The **merge format** (consumed by pull-enrichment, pinned here by tests):
  `"\n\n--- Reply by {author_name} ({created_at}) ---\n{body}"` appended to the item
  text; the reply list stored as `source_metadata["replies"]` (array of part objects
  with part_id) and rating as `source_metadata["rating"]`/`["remark"]`/`["rated_at"]`.
  Idempotency key = `part_id` membership.

## Out of scope

- Client/API access (client aspect); sync-task integration + dispatch (pull-enrichment);
  the webhook `_extract_reply`/`_extract_rating` paths are **not** modified.

## Acceptance criteria (testable)

1. `extract_reply_parts` returns only reply-family parts, in order, with stripped HTML
   bodies and author objects; the first message is never included.
2. Admin/bot-authored replies: body present in the parts list, `_contact_email` returns
   None for them (unit test on the existing rule through the new path).
3. `extract_rating` returns the rating/remark (and rated_at when present), None when
   absent.
4. Merge format pinned by tests: exact separator/attribution string, appended once
   per part_id (idempotent re-merge is a no-op).
5. Existing adapter tests pass unchanged (extraction paths untouched).

## Dependencies & sequencing

- After `client-conversation-parts` (consumes the verified payload shape).
- Consumed by `pull-enrichment`.

## Open questions / risks

- The real part objects' field names (`part_type` vs `type`, `body` vs `text`,
  `created_at` format) — pinned by the client aspect's verified shape; this aspect's
  fixtures mirror it exactly.
