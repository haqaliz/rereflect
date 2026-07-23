# Aspect — frontend-settings-and-evidence

**PRD:** `../prd.md` (M4 renderer, M6, should-haves)
**Sequence:** 4th. Depends on `config-and-migration` (API contract) and the evidence shape from
`detector-core`.

## Problem slice

The operator needs somewhere to turn this on, a way to judge whether it is working, and an evidence
display that isn't CRM-shaped. Today the review queue's `EvidenceCell` reads `deal_name`/`amount`/
`stage` and otherwise renders *"No CRM detail captured"*
(`app/(dashboard)/customers/churn-suggestions/page.tsx:27-47`).

## User outcome

An operator can enable shadow/active mode, set `sustain_days`, see how many suggestions have been
confirmed vs. rejected, and — in the queue — read a decline summary that lets them judge a
suggestion honestly.

## In scope

- **Settings → AI card** (alongside the existing AI settings cards):
  - Mode control: `off | shadow | active`.
  - `sustain_days` input, validated client-side to the same bounds as the API.
  - **Honest limits copy** — non-negotiable, this is a PRD must-have (M6). Must state: the
    ~12-16 day warm-up; the extra `sustain_days`; that customers below the **≥5 active-day baseline
    floor can never produce a suggestion**; and that only customers declining *recently* are visible
    (a long-departed customer will never appear). An operator who enables this and sees nothing must
    learn why here.
  - **Precision read-out:** confirmed / rejected / pending counts for `provider='usage_decline'`.
  - `last_detection_at` / `last_detection_status`, including the M3b suppression state with its
    counts when a run was withheld.
- **Evidence renderer:** a provider-aware branch in `EvidenceCell` rendering the decline summary
  (trend %, baseline vs. current `active_days_14d`, streak length, last active date; the
  `snapshot_series` as a compact sparkline or a terse series).
  - **Do not** smuggle usage data into `deal_name` to exploit the existing CRM renderer.
- **Type widening:** `ChurnSuggestionProvider` in `lib/api/churn-suggestions.ts:8` from
  `'hubspot' | 'salesforce'` to include `'usage_decline'`, so the provider can be filtered
  type-safely. TS-only; no runtime behaviour change.
- **De-CRM-ify shared copy**, now that the queue is genuinely multi-source:
  - Page header "CRM churn suggestions" + subtitle "CRM-sourced closed-lost deals…"
    (`page.tsx:127-132`).
  - The hardcoded **"CRM close date"** field label in
    `components/customers/ConfirmSuggestionDialog.tsx:88`.

## Out of scope

- Any new page or route — the review queue, its StatCard, and the confirm/reject/bulk dialogs are
  shipped and provider-agnostic.
- Changing confirm/reject behaviour or the reason-code requirement.
- Theming changes; use existing CSS variables (never hardcode colors), per repo guidelines.

## Acceptance criteria (testable)

1. Card renders the three modes; changing mode issues the expected PATCH.
2. Invalid `sustain_days` is blocked client-side and the API's 422 is surfaced, not swallowed.
3. Card renders the confirmed/rejected/pending counts for `usage_decline`.
4. Suppression state renders with its counts when the last run was withheld by M3b.
5. `EvidenceCell` with a `usage_decline` evidence payload renders the decline summary — **not** the
   "No CRM detail captured" fallback.
6. `EvidenceCell` with a CRM (`hubspot`/`salesforce`) payload renders **byte-identically to today**
   — characterization test; this is a shared component and CRM orgs must not regress.
7. A `usage_decline` suggestion row renders its provider badge without error.
8. Existing suggestion-queue tests
   (`__tests__/customers/ChurnSuggestionsPage.test.tsx`,
   `CustomersPageChurnSuggestionsStatCard.test.tsx`) stay green.
9. `npm run lint` clean; TypeScript strict mode passes with the widened union.
10. Limits copy is present in the DOM (assert on the key phrases — it is a requirement, not
    decoration).

## Dependencies & sequencing

- Needs the settings API contract from `config-and-migration`.
- Needs the `evidence` key names frozen by `detector-core` (`build_evidence`).
- Can be built against those contracts before `worker-detector` produces real rows.

## Open questions / risks

- Whether the precision read-out needs a new endpoint or can ride an existing settings/analytics
  response. Prefer extending an existing payload — it is a `GROUP BY status` over a table already
  indexed by `(org, status)`.
- Sparkline vs. terse numeric series for `snapshot_series`. Either is acceptable; favour whatever
  keeps the row scannable in a bulk-review workflow, since bulk review is the point of the queue.
