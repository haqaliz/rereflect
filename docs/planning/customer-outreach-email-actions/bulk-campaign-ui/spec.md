# Spec — bulk-campaign-ui

**Feature:** `customer-outreach-email-actions`
**PRD:** `../prd.md` (approved 2026-08-12)
**Aspect boundary:** everything the operator sees and clicks for bulk outreach —
the `BulkOutreachDialog` on `/customers`, the campaign list surface, the public
unsubscribe page, and the `lib/api/outreach.ts` client. No backend, no worker, no
migration, no playbook-editor changes (their aspects). The bulk-campaign-api aspect
is **not yet written** (verified: `docs/planning/customer-outreach-email-actions/`
contains only `prd.md` + `outreach-core/`) — this spec pins the PRD API Contracts
table (prd.md:160-167) as authoritative until that aspect lands; an implementing
agent must re-check for `bulk-campaign-api/spec.md` before starting and adopt its
exact response shapes verbatim, flagging any mismatch.

## Problem slice

The churn loop ends at a send button that doesn't exist. Must-have #6
(prd.md:117-122) requires a bulk outreach composer on `/customers` (subject + body,
tone + "✨ Draft with AI", count-only preview with loud skips, Send with confirm),
must-have #3 (prd.md:104-107) requires a small campaign list surface, and the
`List-Unsubscribe` header the worker puts in every outreach email
(outreach-core/spec.md:37) points at the **frontend** origin —
`{APP_URL}/outreach/unsubscribe?token=…` (outreach-core/spec.md:97-99) — so a
public, auth-free page must exist to honor it.

## In-scope requirements

1. **`lib/api/outreach.ts`** — client for: campaign create (`+count_only`),
   AI draft, campaign list, campaign retry, public unsubscribe GET. Mirrors the
   existing client conventions (`lib/api/customers.ts`, `lib/api/playbooks.ts`,
   `lib/api/issueDraft.ts`): named exports, typed payloads, `apiClient` for
   authed calls, `publicApiClient` for the unsubscribe call
   (`lib/api-client.ts:56-61`; usage precedent `lib/api/analytics.ts:135-143`).
2. **`BulkOutreachDialog`** (`components/customers/BulkOutreachDialog.tsx`) —
   mounted beside the existing bulk dialogs on `/customers` (wiring block
   customers/page.tsx:832-865), dropdown item "Trigger outreach campaign" placed
   directly after "Run playbook" (customers/page.tsx:601-607), gated by
   `isAdminOrOwner` (customers/page.tsx:143) because every outreach mutation is
   `require_admin_or_owner` (prd.md:169-170; backend precedent
   `customers.py:680,723`). Contains:
   - subject `Input` (≤200 chars, prd.md:101) + body `Textarea` (≤20,000 chars,
     prd.md:102) with live counters and inline 422 surfacing;
   - tone `Select` reusing `TONE_OPTIONS` from `lib/api/responses.ts:155-161`
     (values `professional|friendly|empathetic|concise|technical`, type at
     responses.ts:43); selector UI mirrors `components/feedback/ResponseModal.tsx:307-328`;
   - "✨ Draft with AI" button **hidden entirely** when no LLM is configured —
     resolution mirrors create-issue wizard (create-issue/page.tsx:241-256:
     `aiSettingsAPI.get()` → if `default_provider ∈ LOCAL_LLM_PROVIDERS`
     (`{'ollama','openai_compatible'}`, create-issue/page.tsx:83) require
     `base_url`, else require a stored key for the default provider;
     `.catch(() => false)`). Draft populates the editable fields; an
     already-edited field triggers `window.confirm('Replace your text with the
     AI draft?')` (create-issue/page.tsx:472-486 pattern);
   - count-only preview via the API (not the bulk-cap endpoint): shows
     `matched` will be emailed and `skipped` (opted out / no email) loudly —
     response `{matched, skipped, errors[]}` per prd.md:162 (count_only mutates
     nothing, prd.md:98). Refetch pattern mirrors
     `BulkRunPlaybookDialog.tsx:73-94` (effect keyed on open/selection, cancelled
     flag);
   - 500-cap guard (server 422s over cap, prd.md:96-97) — client-side guard
     mirrors `BulkRunPlaybookDialog.tsx:101,182-190`
     (`RUN_BATCH_MAX_CUSTOMERS = 500`, BulkRunPlaybookDialog.tsx:33);
   - **confirm step**: "Send" advances to a confirm state showing the resolved
     counts + read-only subject/body; "Confirm & send to N" POSTs the campaign
     (202 `{matched, queued, skipped, errors[]}`, prd.md:162), then
     `toast.success`, `queryClient.invalidateQueries({queryKey:['customers']})`
     (BulkRunPlaybookDialog.tsx:108-110) **plus** `['outreach-campaigns']`,
     `onSuccess?.()` (→ `clearSelection`, customers/page.tsx:173-176),
     `onOpenChange(false)`, reset — exact success path of
     `BulkRunPlaybookDialog.tsx:103-120`.
3. **Campaign list surface** — decision (tech-plan freedom, prd.md:131-132,
   prd.md:229-230): a **"Outreach campaigns" card directly under the DataTable
   on `/customers`** (admin/owner only). Rationale: campaigns are created there,
   so the list closes the loop (send → see status) in context with zero new
   navigation; a dedicated page or Settings section adds routing/sidebar cost for
   a surface the PRD sizes as "small". Lists the 5 most recent campaigns
   (`GET /api/v1/outreach/campaigns?page=1&page_size=5`, prd.md:165) with
   subject, created date, campaign status, per-recipient status counts, and a
   "Retry queued" button. Retry calls `POST /api/v1/outreach/campaigns/{id}/retry`
   — **pending contract** (bulk-campaign-api not yet written; the PRD's in-progress
   recovery note prd.md:231-233 promises a re-enqueue affordance but no path was
   pinned). If bulk-campaign-api lands with a different retry path, adopt it;
   otherwise implement against this path and flag the assumption in the PR.
4. **Public unsubscribe page** — `app/outreach/unsubscribe/page.tsx` **outside**
   the `(dashboard)` route group (public — no sidebar, no auth; group rule:
   `app/(dashboard)/layout.tsx` is the authed shell and pages outside it, like
   `app/login/`, `app/signup/`, `app/invite/[token]/`, `app/shared/[token]/`,
   get only the root providers, app/providers.tsx:12-37). Reads `token` via
   `useSearchParams` **inside a Suspense boundary** (repo rule — see
   `app/signup/page.tsx:20-33`; login page comment at `app/login/page.tsx:66`),
   calls `GET /api/v1/outreach/unsubscribe?token=` via `publicApiClient`
   (endpoint is public, outreach-core/spec.md:44-47; AC8 — valid token sets
   `outreach_opt_out`, invalid → 400), and renders an honest success ("You're
   unsubscribed…") or failure ("This link is invalid…") state. The backend also
   renders its own HTML (outreach-core/spec.md:47) — that is the direct-hit
   fallback; this frontend page is what the `List-Unsubscribe` link actually
   lands on because APP_URL defaults to the frontend origin
   (outreach-core/spec.md:97-99).
5. **Tests** — vitest units for the client and the components/page, following
   the repo's conventions (below).

## Out-of-scope boundaries

- No `GET /api/v1/outreach/templates` client/UI — the registry serves the
  playbook-editor aspect (prd.md:120-122, aspect #5 prd.md:261-262).
- No changes to `components/playbooks/PlaybookEditor.tsx` — separate aspect
  `playbook-editor-email-config` (prd.md:261-262).
- No per-customer opt-out toggle on the Customer 360 profile (aspect #5).
- No scheduled campaigns, SMTP, template CRUD, campaign detail drill-down
  (prd.md:139-143, 244-246).
- No plan gates (CLAUDE.md — SELF_HOSTED mode; outreach mutations are
  admin/owner gated by role, not plan).

## Acceptance criteria (testable)

- AC1: `outreachAPI.createCampaign(cohort, subject, body, tone)` POSTs
  `/api/v1/customers/bulk/outreach` with `{cohort, subject, body, tone}`; with
  `countOnly: true` it appends `?count_only=true` and the payload is identical
  (client test pins both shapes, `lib/api/__tests__/playbooks.runBatch.test.ts:52-63`
  precedent).
- AC2: `outreachAPI.draftCampaign` throws a typed error carrying status 409
  ("no LLM configured") / 422, mirroring `IssueDraftApiError`
  (lib/api/issueDraft.ts:17-46) and its tests (issueDraft.test.ts:43-81).
- AC3: `outreachAPI.unsubscribe(token)` uses `publicApiClient` and returns on
  2xx; a 400 rejects so the page can render failure.
- AC4: dialog renders subject/body with length counters and blocks Send when
  empty or over the 500 cap (client-side guard, server 422 still surfaced
  inline as a destructive alert).
- AC5: dialog shows the count-only preview (`matched`/`skipped`) and the
  confirm step requires an explicit second click; success path invalidates
  `['customers']` + `['outreach-campaigns']` and calls `onSuccess`.
- AC6: "Draft with AI" is absent when the LLM-config probe fails (mock
  `aiSettingsAPI.get` to reject) and visible when configured; a draft over
  edited fields asks `window.confirm` first.
- AC7: campaign list card renders subject/date/status/counts from the API and
  shows "Retry queued" only when `counts.queued > 0`; retry toasts + invalidates
  `['outreach-campaigns']`.
- AC8: `/outreach/unsubscribe` page: valid token → success state; invalid /
  missing token → failure state; page renders without auth and without the
  dashboard shell.

## Dependencies & sequencing

Depends on `bulk-campaign-api` (create/draft/list/retry endpoints) and
`outreach-core` (unsubscribe endpoint, token). Nothing else frontend-side: all UI
primitives already exist (`components/ui/dialog|button|input|textarea|select|alert|card|badge`,
`sonner` toast, `@tanstack/react-query`). No new packages. UI aspects are last in
the PRD's sequencing (prd.md:204-206).

## Open questions / risks

- **Retry endpoint path/shape** — not pinned anywhere yet. Implement
  `POST /api/v1/outreach/campaigns/{id}/retry` returning `{re_enqueued: number}`;
  flag in the PR when bulk-campaign-api's real contract is known. If the endpoint
  422s with nothing queued, surface the detail inline; keep the button disabled
  when `counts.queued === 0` either way.
- **Campaign list response shape** — `{items, total, page, page_size}` assumed
  (ExecutionListResponse precedent, lib/api/playbooks.ts:43-48); recipient counts
  assumed as `recipient_counts: {queued, sent, skipped, failed}`. Adopt
  bulk-campaign-api's exact field names when it lands.
- **Create body `tone`** — PRD contract lists `{cohort, subject, body}` only
  (prd.md:162) but the data model has `tone`? (prd.md:150). Send `tone` as
  optional; if bulk-campaign-api's schema forbids extra fields, drop it from the
  create call (keep it in the draft call — prd.md:163).
- **Unsubscribe GET response body** — may be HTML (outreach-core/spec.md:47);
  the client must treat status alone as success (parse `detail` for the error
  message when present).
