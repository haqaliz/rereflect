# Aspect Spec — segment-ui

**Parent PRD:** `../prd.md` · **Services:** frontend-web · **Sequence:** 3rd (after segment-api contract)

## Problem slice & outcome

Operators see each customer's segment as a labeled chip in the Customers list and on the profile, and can
filter the list by segment — with honest "rule-based" framing and theme-correct colors.

## In scope

1. **API-client types.** `lib/api/customers.ts`: add `segment?: string | null` to `CustomerListItem`
   (:8-25), `segment?: string` to `CustomerListParams` (:53), and `query.set('segment', …)` in
   `customersAPI.list()` (:232-245). Add `segment` to `CustomerProfileData` (:67-111).
2. **SegmentBadge component.** New `components/customers/SegmentBadge.tsx` mirroring
   `ChurnTimelineBadge.tsx` (per-slug config map: label + `lucide` icon + color; rounded-full pill;
   `color-mix(in oklch, …)`). Add a `SEGMENT_COLOR` map in `lib/constants/churn.ts` (or a new
   `lib/constants/segments.ts`) using `--chart-*` CSS vars only — **no hardcoded colors**. Handles the
   `unsegmented`/null case (subtle neutral chip or none — per PRD OQ2).
3. **List column.** New `ColumnDef<CustomerListItem>` for `segment` in `app/(dashboard)/customers/page.tsx`
   (after :329), rendering `SegmentBadge`.
4. **Filter dropdown.** New shadcn `<Select>` "Segment" in the filter bar (after :467), with `segmentFilter`
   state (near :112), `handleSegmentFilterChange` (near :159, resets `currentPage` to 1), spread into
   `queryParams` (near :132, mirroring `risk_level`).
5. **Profile badge.** Render `SegmentBadge` in the profile header badge row
   (`app/(dashboard)/customers/[email]/page.tsx:647-671`, after the `ChurnTimelineBadge`).
6. **Honest labeling (PRD must-have #7, critique gap #2/G3).** A short "rule-based" tooltip/help affordance
   near the Segment filter or column header (and/or on the profile badge), mirroring churn's
   calibrated-heuristic framing.

## Out of scope

- Segment breakdown card on the list summary (later).
- Any editable-rules settings UI.
- Copilot/automation/playbook targeting UI.

## Acceptance criteria (testable)

- Customers page renders a Segment column with a colored chip per row; `unsegmented`/null renders per the
  agreed empty treatment.
- Selecting a segment in the filter refetches with `?segment=…` and resets to page 1.
- Profile header shows the segment badge.
- Colors resolve from CSS vars (no literal hex/oklch in component); light + dark themes both legible.
- A "rule-based" affordance is present and discoverable (assert in the component/UI test).
- `npm run test` and `npm run lint` green.

## Dependencies & sequencing

- Depends on `segment-api` (the `segment` field + `?segment=` param contract).
- Depends on `segment-engine` for real values, but can be built/tested against the API contract with
  fixtures.

## Risks

- Theme legibility of many chip colors — reuse the existing `--chart-*` token discipline from
  `ChurnTimelineBadge`; keep to the palette, don't invent hues.
