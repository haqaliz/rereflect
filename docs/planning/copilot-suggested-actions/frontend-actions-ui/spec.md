# Spec: frontend-actions-ui

## Problem slice

The proposal is invisible until something renders it. `MessageBubble` currently branches only
on `data_type === 'table'` and `'chart'` and silently drops everything else — so without this
aspect the backend work is inert.

**User outcome:** the user sees "Tag these 3 customers…" under the answer, clicks it, types a
tag, confirms, and sees what changed.

## In-scope

- **Render the actions item.** Extend the `structured_data` loop
  (`MessageBubble.tsx:269-282`) with an `actions` branch, rendering one button per entry using
  the item's `label`. Note the existing `tableItem`/`chartItem` slots are single last-one-wins
  (`:257-258`); the actions branch should not inherit that pattern if more than one action can
  appear.
- **Collect the required input.** `requires_input: ["tag"]` opens a small dialog where the user
  types the tag. **The tag value comes from the user, never from the model or the server.**
  Use shadcn `Dialog` — the `ResponseModal` posture (`ResponseModal.tsx:145-164`) is the house
  match: AI fills context, a second explicit action commits.
- **Execute.** Call the execute route with the message reference, `proposal_id`, action id and
  collected params. In-flight state disables the button (the `RunPlaybookDropdown.tsx:80`
  spinner pattern).
- **Report the outcome honestly.** Surface `BulkActionSummary` — `matched`, `updated`,
  `skipped`, and `errors[]` (e.g. the 20-tag cap message). Do not report a bare "Success". Note
  `bulk/tags` uses set-union, so re-adding an existing tag still counts toward `updated`; copy
  must not over-claim.
- **Executed state.** After a successful execution the button reflects that it has run and does
  not re-fire. Cosmetic only — the server-side one-shot guard is the enforcement.
- **Render all item values as text.** Nothing sanitises `structured_data` at any layer; emails
  become button labels and must never be interpreted as markup.
- **Role hiding (nice-to-have).** Optionally hide the action for non-admins using the existing
  inline idiom `user?.role === 'owner' || user?.role === 'admin'`. Explicitly cosmetic — no
  copilot component reads `role` today, and the server enforces regardless.

## Out-of-scope

- Cmd+K. `CommandBar.tsx:57-65` renders no results at all — it only routes to
  `/conversations`. Adding a result surface there is a separate feature.
- Any action type beyond `tag_customers`; tag removal; multi-tag entry beyond what the dialog
  collects.
- Refactoring `tableItem`/`chartItem` into lists.
- Extracting the duplicated `isAdminOrOwner` idiom (~25 inline copies) or the duplicated
  `aiConfigured` probe.

## Acceptance criteria

- Given the golden fixture, one button per action renders with `label` as its accessible name.
- An unknown `data_type` still renders nothing and does not throw (the contract's negative
  test).
- Clicking the button opens the dialog; the execute call is **not** made until the user
  confirms.
- Confirming with an empty tag is refused client-side without a network call.
- A successful execution surfaces `matched`/`updated`/`skipped` and any `errors[]`.
- A failed execution surfaces the error and leaves the action re-clickable.
- A 403 (member) surfaces a clear message rather than a generic failure.
- After success the button shows an executed state and cannot re-fire.
- Existing table and chart rendering tests stay green.
- **The contract test is not done while it is inverted:** change `it.fails` back to a normal
  `it` in `actionsContract.test.tsx` once `MessageBubble` renders the `actions` data_type —
  the aspect is not complete while the guard test still passes by failing.

## Dependencies and sequencing

Depends on `action-contract` (fixture) and `action-registry` (the route to call). Can be built
against the fixture before the backend lands.

## Open questions / risks

- Where the outcome is shown: a toast (the `RunPlaybookDropdown.tsx:53` pattern) is
  house-standard but truncates `errors[]`. Inline under the message preserves detail and
  survives a page revisit. Leaning inline, with a toast for the headline.
- Tests: `__tests__/copilot/` holds `useCopilotWebSocket.test.ts`, `ChatArea.test.tsx` and
  `CopilotIntegration.test.tsx`. There is **no shared WS/test helper** — the WebSocket mock is
  inline in `useCopilotWebSocket.test.ts` and is the thing to copy. `vitest.config.ts` and
  `vitest.setup.ts` are repo-level and auto-loaded.
