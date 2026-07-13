# Aspect Spec — settings-frontend (Next.js)

**Service:** `services/frontend-web/`
**Sequence:** after data-and-config exposes `urgency_classifier_mode` in the settings API. The accuracy
card works as soon as the accuracy API returns urgency data (post worker-trainer).

## Problem slice / outcome

Operators control the urgency head from Settings → AI (off/shadow/auto toggle) and see an urgency accuracy
card — visually identical to the category head.

## In scope

- **`lib/api/ai-settings.ts`:** add `urgency_classifier_mode: string` to `AISettings` (:19 area) and
  `urgency_classifier_mode?: string | null` to `AISettingsUpdate` (:31 area). No other client wiring
  (get/update pass through).
- **`components/settings/AISettingsGeneral.tsx`:** add a 4th `<Select>` mode card, copying the category
  card verbatim (:217-263) — swap icon (e.g. `AlertTriangle` from lucide, import :7), title
  ("Self-Improving Urgency Classifier"), copy, and bindings to `settings.urgency_classifier_mode` /
  `handleUrgencyClassifierMode` / `urgencyClassifierSaving`. Add state (:28-29 pattern) + handler
  (copy `handleCategoryClassifierMode` :82-96, calling `aiSettingsAPI.update({ urgency_classifier_mode })`).
  Keep the `?? 'off'` null-guard.
- **`components/settings/ClassifierAccuracyCard.tsx`:** add an `urgency` entry to `TYPE_COPY` (:28-40)
  with honest copy (trained on the org's urgency corrections; promoted only when it beats the keyword
  heuristic). No prop/fetch changes — already type-generic.
- **`app/(dashboard)/settings/ai/page.tsx`:** add
  `<ClassifierAccuracyCard classifierType="urgency" isAdminOrOwner={isAdminOrOwner} />` after the category
  card (~:488) in the accuracy tab. Add `urgency` to `CORRECTION_TYPE_LABELS` (:47-52) so the
  "Corrections by Type" breakdown reads "Urgency" (S-1, cosmetic).

## Out of scope

- `lib/api/classifier-accuracy.ts` — already type-generic, **zero change**.
- The feedback-detail urgent toggle control (that's in capture-seam).

## Acceptance criteria (testable, TDD — Vitest)

- Urgency mode `<Select>` renders with off/shadow/auto; changing it calls
  `aiSettingsAPI.update({ urgency_classifier_mode })`; reflects saved value; shows error on failure.
- `ClassifierAccuracyCard classifierType="urgency"` renders urgency copy (from `TYPE_COPY.urgency`, not the
  generic fallback) and fetches `getClassifierAccuracy("urgency")` / `rollbackClassifier("urgency")`.
- `AISettings`/`AISettingsUpdate` types include the new field (compile + api-client tests).
- `npm run test` and `npm run lint` green.

## Dependencies / sequencing

Depends on **data-and-config** (settings API returns/accepts the field). Accuracy card is live once the
accuracy endpoint reports urgency (after worker-trainer promotes/eval-runs).

## Risks

- Mirror existing category tests: analogues of `AISettingsGeneral.categoryClassifier.test.tsx`,
  `ClassifierAccuracyCard.test.tsx`, `AISettingsAIPage.accuracyTab.test.tsx`, `ai-settings.category.test.ts`.
- Keep the `?? 'off'` guard — older API responses may omit the field.
