# Spec: deterministic-proposer

## Problem slice

Something must decide *when* to offer an action, without an LLM in the loop. Using the model
to propose would put customer-authored feedback text in the path that produces a clickable
execution, and would behave worst on exactly the small local models this product targets.

**User outcome:** ask a question whose answer is a set of customers, and the action to act on
that set is right there.

## In-scope

- **Result-shape inspection.** After a `data`/`analysis` query returns rows, examine the SQL
  result's columns to decide which registry actions apply. Slice-1 rule: a result carrying a
  customer-email column offers `tag_customers`, with the emails from that column as the frozen
  cohort (M9).
- **The hook point.** `copilot_ws.py`, between the structured-data build (`:622-638`) and the
  emit (`:775-783`). The `general` intent branch never enters this section, so actions are
  inherently scoped to `data`/`analysis` — this is a property to assert, not to add.
- **Appending, not replacing.** The item is appended to the same list `format_table` and
  `format_chart` write into. Table and chart items are unaffected and keep their positions.
- **Email cap.** A result larger than the cap offers **no action** rather than a silently
  truncated one. (Truncating would mean the button acts on fewer customers than the user sees —
  the failure mode M9 exists to prevent.)
- **No LLM.** No call to `resolve_generation_llm`, no prompt, no `LLMUsageLog` entry. The
  proposer is pure and synchronous.
- **`proposal_id` generation**, per the contract.

## Out-of-scope

- Any trigger other than result shape — no intent changes, no keyword matching, and **no new
  intent**: `intent_classifier.py` is untouched.
- Proposing for the `general` intent or for `report`.
- LLM-authored proposals (slice 2, behind the same registry interface).
- Ranking or scoring multiple candidate actions — slice 1 has exactly one.

## Acceptance criteria

- A `data` query returning a customer-email column → an `actions` item is appended containing
  `tag_customers` with exactly the emails from that result.
- The same query with a result over the cap → no `actions` item.
- A query returning no customer-email column → no `actions` item; `structured_data` is exactly
  what it is today.
- A `general`-intent message → no `actions` item (asserts the branch property).
- A query returning zero rows → no `actions` item.
- Table and chart items are byte-identical to their current output when an actions item is
  also present.
- **The frame-emission change is pinned:** a query that previously produced an empty
  `structured_data` list (and therefore skipped the frame entirely, `copilot_ws.py:775`) now
  emits a frame when it produces an actions item. Explicit test — this is a real behavioural
  change for clients.
- Emitted output equals the golden fixture (the `action-contract` test).
- No LLM call is made during proposal — assert via the fake-LLM fixture.
- **The assertion crosses the seam, not just the proposer's return value:** the test must
  check the emitted `structured_data` payload (`copilot_ws.py:631-638` / the WS frame at
  `:775-783`), not only what the proposer function returns in isolation. A correct proposer
  whose output `copilot_ws` never appends must fail this test.
- **The contract test is not done while it is inverted:** remove the `xfail(strict=True)`
  marker on `test_copilot_actions_contract.py` once the proposer is implemented — the aspect
  is not complete while the guard test still passes by failing.

## Dependencies and sequencing

Depends on `action-contract`. Best built after `action-registry` so the proposer can name real
registry entries, but the two are independently testable.

## Open questions / risks

- How is the customer-email column identified — by column name, or by the SQL generator's
  knowledge of the whitelisted schema (`schema_whitelist.py`)? Name-matching is simpler and
  probably sufficient; schema-derived is more robust. Decide in the plan.
- Minimum row count: 1, or ≥2 to match `include_table`'s `row_count >= 2` gate?
- `structured_data` is unsanitised at every layer (`sanitize_markdown` runs only on `text`,
  `response_formatter.py:305`). The emails placed in the item are org data from the user's own
  database, not model output — but the renderer must still treat them as text.
