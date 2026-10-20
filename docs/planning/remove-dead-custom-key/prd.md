# PRD — Remove dead `has_custom_key` from the AI settings contract

## Problem
`AISettings.has_custom_key` is declared in the frontend API type but never read or written by
`backend-api`, never read by any UI component, and only appears in test fixtures. It misleads
anyone trusting the type as the real response shape.

## Goal
Nothing in `services/frontend-web` mentions `has_custom_key`. The type matches the backend
response, and the settings tests stay green.

## Scope
In:
- Delete the field from `lib/api/ai-settings.ts`.
- Delete the field from every test fixture that carries it.

Out:
- Backend changes (there is nothing to remove).
- Any replacement field; `openai_api_key`/provider config already covers the real needs.

## Acceptance
- `grep -r has_custom_key services/frontend-web` (excluding node_modules) returns nothing.
- `npx tsc --noEmit` clean.
- Settings + affected suites green in `npm run test`.

## Risks
None functional: no reader exists. Only risk is a fixture left behind — caught by grep + tsc.
