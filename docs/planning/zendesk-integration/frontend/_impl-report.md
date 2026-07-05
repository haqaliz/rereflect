# Implementation report — Zendesk frontend aspect

**Branch:** `feat/zendesk-integration` · **Worktree:** `/Users/aliz/dev/at/rereflect/.claude/worktrees/feat-zendesk-integration`
**Method:** strict TDD (RED → GREEN), one commit per plan phase.
**Scope:** `services/frontend-web` only, per the aspect spec.

## Summary

Implemented the Zendesk connect UI end-to-end, mirroring the Jira token-paste
integration precisely, plus the two genuinely-new behaviors the plan called
out (one-time webhook secret reveal, `has_feedback_source` duplicate-source
guard in the wizard):

- `components/icons/ZendeskIcon.tsx` — mirrors `JiraIcon.tsx`'s structure.
- `lib/api/zendesk.ts` — inbound-only client (`connect`/`getStatus`/
  `disconnect`/`testConnection`/`triggerSync`), no outbound methods.
- Connect page `app/(dashboard)/settings/integrations/zendesk/page.tsx`.
- Integrations index page: Zendesk tile + Active card.
- Feedback-source wizard + list/detail/pending icon maps + trigger options.

## Commits (one per plan phase)

| Phase | Commit | Message |
|---|---|---|
| 1 — API client + types + icon | `ab56c90` | `feat(zendesk-ui): zendesk API client + types + icon (connect/status/disconnect/test)` |
| 2 — Connect page | `622de2b` | `feat(zendesk-ui): Zendesk connect page (subdomain/email/token, webhook secret display)` |
| 3 — Integrations index | `f97129c` | `feat(zendesk-ui): Zendesk tile + active card on integrations index` |
| 4 — Wizard + icon maps + triggers | `d2cf0e9` | `feat(zendesk-ui): zendesk in feedback-source wizard, icon maps, trigger options` |

**Commit range:** `ab56c90..d2cf0e9` (4 commits, on top of `5a76723`, the last
pre-existing commit on the branch before this aspect).

## Files added

- `services/frontend-web/components/icons/ZendeskIcon.tsx`
- `services/frontend-web/lib/api/zendesk.ts`
- `services/frontend-web/lib/api/__tests__/zendesk.test.ts` (6 tests)
- `services/frontend-web/app/(dashboard)/settings/integrations/zendesk/page.tsx`
- `services/frontend-web/app/(dashboard)/settings/integrations/zendesk/__tests__/ZendeskPage.test.tsx` (8 tests)

## Files edited

- `services/frontend-web/app/(dashboard)/settings/integrations/page.tsx` —
  `ZendeskIcon`/`zendeskAPI`/`ZendeskConnectionStatus` imports, `zendeskStatus`/
  `zendeskTesting`/`zendeskTestResult` state, `zendeskAPI.getStatus()` added to
  the `Promise.allSettled` fetch, empty-state gate extended, Active-integration
  card (mirrors Jira `:699-822`), Available tile (mirrors Jira `:981-1004`).
- `services/frontend-web/app/(dashboard)/settings/integrations/__tests__/IntegrationsPage.test.tsx` —
  third `describe('IntegrationsPage — Zendesk data fetch contract', ...)` block
  (mirrors HubSpot/Salesforce).
- `services/frontend-web/app/(dashboard)/settings/integrations/__tests__/SalesforceTile.test.tsx` —
  **unplanned but necessary fix**: this pre-existing test renders the real
  `IntegrationsPage` component and did not mock `@/lib/api/zendesk`. Adding
  `zendeskAPI.getStatus()` to the page's `Promise.allSettled` fetch made this
  test issue a real, unmocked `axios` request under jsdom, which surfaced as
  an unrelated-looking `UND_ERR_INVALID_ARG` (undici/jsdom) failure. Fixed by
  adding a `zendeskAPI` mock (mirroring the existing `jiraAPI` mock in the same
  file) with a default `{ connected: false }` `getStatus` resolution.
- `services/frontend-web/lib/api/feedback-sources.ts` — `'zendesk'` added to
  the `source_type` union (did **not** backfill the pre-existing missing
  `'jira'`, per plan); `TRIGGER_OPTIONS.zendesk`; `new_ticket?: boolean` added
  to `TriggerConfig`; `new_ticket: false` added to `DEFAULT_TRIGGERS`.
- `services/frontend-web/app/(dashboard)/feedback-sources/page.tsx`,
  `[id]/page.tsx` — `ZendeskIcon` import + `SOURCE_ICONS`/`SOURCE_COLORS`
  entries.
- `services/frontend-web/app/(dashboard)/feedback-sources/pending/page.tsx` —
  `ZendeskIcon` import + `SOURCE_ICONS` entry only (this file has no
  `SOURCE_COLORS` map — mirrored that asymmetry, did not invent one).
- `services/frontend-web/app/(dashboard)/feedback-sources/[id]/page.tsx` —
  additionally extended the generic trigger-checkbox `toggleTrigger`/
  `isEnabled` logic with a `new_ticket` case (see deviation below).
- `services/frontend-web/app/(dashboard)/feedback-sources/new/page.tsx` —
  `ZendeskIcon`/`zendeskAPI`/`ZendeskConnectionStatus` imports, `SOURCE_ICONS`/
  `SOURCE_COLORS` entries, `getInitialStep`/`handleTypeSelect` zendesk
  branches, `zendeskStatus` state + `zendeskAPI.getStatus()` in the data
  fetch, a dedicated Zendesk integration-step card, `renderStepIndicator`/
  triggers-Back-button/name-placeholder special-cases, "Requires OAuth" badge
  condition extended, and the `toggleTrigger`/`isEnabled` `new_ticket` case
  (same as `[id]/page.tsx`).

## TDD process (RED confirmed before every GREEN)

- **Phase 1:** `lib/api/__tests__/zendesk.test.ts` written first; ran via
  `npx vitest run lib/api/__tests__/zendesk.test.ts` and failed with
  `Failed to resolve import "@/lib/api/zendesk"` (module didn't exist).
  After implementing `zendesk.ts` + `ZendeskIcon.tsx`: **6/6 passed**.
- **Phase 2:** `ZendeskPage.test.tsx` (mirrors `HubSpotPage.test.tsx`'s richer
  RTL pattern, per the plan's recommendation over Jira's untested page)
  written first; failed with `Failed to resolve import "../page"` (page
  didn't exist). After implementing the connect page: **8/8 passed** (two
  test-design fixes made during GREEN: checking the token input is *removed*
  rather than *cleared* after a successful connect, since the connected view
  replaces the form entirely — matching Jira's existing behavior; and using
  `getByDisplayValue` instead of `getByText` for the readonly webhook-secret
  `Input`).
- **Phase 3:** added the third contract block to `IntegrationsPage.test.tsx`
  — since Phase 1 already existed on this branch by the time Phase 3 ran,
  this block was GREEN immediately (per the plan's explicit allowance: "if
  Phase 1 already merged this step is just adding the new block"). The actual
  RED→GREEN cycle for this phase was the `SalesforceTile.test.tsx` regression
  (see above) — confirmed the failure first (`UND_ERR_INVALID_ARG`), then
  fixed it by adding the missing mock.
- **Phase 4:** no new test file (per plan, to avoid scope creep on the
  1195-line, previously-untested `new/page.tsx`); validated via
  `npm run test` (full suite, unchanged baseline), `npm run lint`, and
  `npm run build` (type-checks the widened `source_type`/`selectedType`
  unions and confirms `/settings/integrations/zendesk` is generated as a
  route).

## Final validation

```
cd services/frontend-web
npx vitest run
 Test Files  13 failed | 81 passed (94)
      Tests  24 failed | 937 passed (961)

npx eslint .
✖ 51 problems (32 errors, 19 warnings)
```

All 14 new Zendesk-specific tests (`zendesk.test.ts` 6 + `ZendeskPage.test.tsx`
8) pass, plus the 2 new Zendesk blocks in `IntegrationsPage.test.tsx` (34 total
tests passing in `app/(dashboard)/settings/integrations/`, up from 32 pre-existing
+ 2 new). **Zero Zendesk-related test or lint failures.**

The 13 failed test files / 24 failed tests and the 51 lint problems are
**pre-existing, unrelated to this aspect** — confirmed by:
1. Running the full suite/lint before Phase 3's page.tsx edit and after each
   subsequent phase: the failure/problem count was identical every time
   (13 failed files / 24 failed tests, 51 lint problems) except for the one
   `SalesforceTile.test.tsx` regression I caused and fixed myself (see above).
2. None of the failing files or lint-flagged files are files this aspect
   touches: pre-existing failures are in `__tests__/settings/WebhooksSettings.test.tsx`,
   `__tests__/admin/QueryTemplatesAdmin.test.tsx`, `__tests__/copilot/*`,
   `__tests__/customers/FeedbackDetailCustomerLink.test.tsx`,
   `__tests__/feedback/FeedbackDetailActions.test.tsx`,
   `__tests__/integrations/{CreateIssueButton,LinearSettings}.test.tsx`,
   `__tests__/settings/{AutomationForm,ResponseTemplates,WebhookDetail}.test.tsx`,
   `__tests__/api/responses.test.ts` — none of which this aspect edits. The 51
   lint problems are all in `contexts/{RealtimeContext,ThemeContext,
   UrgentFeedbackPageContext}.tsx` and `hooks/{useCopilotWebSocket,
   useRealtimeEvents}.ts` (React-Compiler-style `set-state-in-effect`/`refs`
   rules and unused-eslint-disable warnings) — again, none touched here.
3. `node_modules` did not exist in this worktree at task start (`npm install`
   failed on the `workspace:*` protocol; resolved with
   `pnpm install --filter customer-feedback-frontend...` from the repo root)
   — a fresh install in an isolated worktree, so these are genuine
   already-broken/flaky tests on this branch, not something introduced by my
   work.

## Deviations from the plan (both required for correctness, not style choices)

1. **Trigger vocabulary is `new_ticket` + `keywords`, NOT `all_messages` +
   `keywords`.** The plan explicitly flagged this as an open item to confirm
   ("if it only supports `all_messages`, ship just that one"). I read the
   already-merged `services/worker-service/src/adapters/zendesk.py`
   (`ZendeskAdapter.check_triggers`) and its test file
   (`tests/test_zendesk_adapter.py`): the adapter reads
   `triggers.get("new_ticket")`, never `triggers.get("all_messages")`.
   Shipping `all_messages` as planned would have produced a checkbox that
   visually toggles but never actually enables ingestion — a silent,
   untestable-from-the-frontend bug violating the PRD's "never a silent drop"
   principle. I shipped `TRIGGER_OPTIONS.zendesk = [new_ticket, keywords]`
   and added `new_ticket?: boolean` to `TriggerConfig`.

   **Necessary follow-on:** both `new/page.tsx` and `[id]/page.tsx` have a
   *generic* trigger-checkbox renderer whose `isEnabled`/`toggleTrigger`
   logic only special-cased `'all_messages'` and `'mentions.bot'` (every
   other source type's primary trigger is one of those two keys). Since
   Zendesk's primary trigger is a new key, I extended both functions in both
   files with a `'new_ticket'` case — a small change beyond the plan's
   literal "just add SOURCE_ICONS/SOURCE_COLORS to `[id]/page.tsx`"
   description of that file, but required for the checkbox to functionally
   toggle rather than being permanently stuck unchecked/no-op.

2. **`handleTypeSelect`'s zendesk branch always routes to the `'integration'`
   step, never jumping straight to `'triggers'`.** The plan's literal wording
   suggested gating the straight-to-triggers jump on `zendeskStatus?.connected
   && zendeskStatus?.is_active && zendeskStatus?.has_source` (i.e., jump when
   a source *already exists*) — but that's precisely the case where letting
   the wizard continue to `handleSubmit` would create a **second** `zendesk`
   `FeedbackSource`, which contradicts the same paragraph's stated
   duplicate-avoidance goal for the integration-step card. I resolved this by
   always showing the integration step for Zendesk (regardless of connection
   state), so the has_feedback_source guard in the integration-step card can
   run before any path that could call `handleSubmit`. This is called out
   explicitly in a code comment at the `handleTypeSelect` branch. Flagging
   this precisely per the plan's own instruction ("flag this precisely with
   backend-connection once the real `has_source` semantics are confirmed")
   — the backend's field is named `has_feedback_source` (not `has_source` as
   the plan guessed throughout), which I used consistently since it's
   confirmed in `backend-connection/_impl-report.md` and the actual
   `ZendeskStatusResponse`/`ZendeskConnectResponse` Pydantic models.

## How `has_feedback_source` was handled

- Field name used throughout is `has_feedback_source` (the plan's prose used
  `has_source` as a placeholder guess; the merged backend contract uses
  `has_feedback_source` — confirmed in `zendesk_integration.py`'s
  `ZendeskStatusResponse`/`ZendeskConnectResponse`).
- Typed as `boolean | null | undefined` (`has_feedback_source?: boolean | null`)
  in `lib/api/zendesk.ts` — always optional, per the plan's "treat as
  always-optional" instruction, so absence on older/partial payloads is
  handled by normal JS falsy-checks rather than a runtime error.
- **Connect page:** if connected but `has_feedback_source === false`, an
  inline `Alert` renders with a link to `/feedback-sources/new?type=zendesk`
  ("fail open" — surfaces the gap rather than hiding it, per the plan's edge
  case note), instead of silently doing nothing.
- **Wizard integration step:** connected + `has_feedback_source` true →
  "a Zendesk feedback source already exists" card + a link to
  `/feedback-sources` (View Feedback Sources button) in place of the
  Continue-to-triggers button, so `handleSubmit` can never run and create a
  duplicate row. Connected + `has_feedback_source` false/absent → normal
  Continue button to `'triggers'` (fail-open, lets the wizard create one).

## How the one-time webhook-secret reveal was handled

- `ZendeskConnectResponse.webhook_secret` is `string | null | undefined` —
  only ever populated from the `POST /connect` response in local component
  state (`webhookSecret`), never persisted, never fetched from `GET /status`
  (which the backend never returns it from).
- Rendered in a dedicated "Set up real-time sync (optional)" card: a readonly
  `Input` + copy `Button` for the webhook URL (`{NEXT_PUBLIC_API_URL}/api/v1/
  webhooks/zendesk/events`, mirroring the existing `settings/api-keys/page.tsx`
  precedent for constructing a backend-origin URL client-side — confirmed the
  static path against the already-merged `services/backend-api/src/api/routes/
  source_webhooks.py:405` `@router.post("/zendesk/events")`, resolving the
  plan's §7 open item), and a readonly `Input` + copy `Button` for the secret
  itself, combining the `[id]/page.tsx` webhook-URL-copy pattern and the
  `new/page.tsx` `copyInboundAddress` one-time-reveal pattern as the plan
  directed.
- Degrades gracefully: if `webhookSecret` is `null` (e.g., a page revisit
  after the initial connect, where the component state was never populated),
  the card shows "Webhook secret already configured — reconnect (re-enter
  your API token) to view it again" instead of rendering `undefined` or an
  empty input.
- Also added (should-have, not explicitly required by this plan's file list
  but backed by an already-implemented backend endpoint and PRD "Should-have"
  item): a "Sync Now" button on the connected state, wired to
  `zendeskAPI.triggerSync()` → `POST /api/v1/integrations/zendesk/sync`.

## Environment note

`services/frontend-web/node_modules` did not exist in this worktree at task
start; `npm install` failed (`EUNSUPPORTEDPROTOCOL` on the `workspace:*`
dependency). Resolved with `pnpm install --filter customer-feedback-frontend...`
run from the repo root (this is a pnpm workspace monorepo per
`pnpm-workspace.yaml`).

## Manual QA (not run — no live backend/Zendesk sandbox in this session)

Per the plan's testing strategy, manual QA (`./start-all.sh`, connect a real/
sandboxed Zendesk subdomain, confirm token masking, webhook block, Test
Connection, Disconnect/reconnect, and the wizard's duplicate-avoidance
behavior) was not performed in this session — all validation here is via the
Vitest unit/component suite, `eslint`, and `next build`'s type-checking, per
the task's stated environment/validate instructions.
