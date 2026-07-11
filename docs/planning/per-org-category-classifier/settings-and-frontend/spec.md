# Aspect: settings-and-frontend

**Slice:** surface a category mode toggle + a category accuracy/rollback card on Settings → AI, reusing the
already-type-parameterized backend accuracy/rollback API.

## Problem slice & outcome
The backend `GET/POST .../classifier/accuracy|rollback` already accept `classifier_type` (default
sentiment). The frontend just never sends it. Thread the type through and render a second card + a second
mode toggle for category.

## In scope (`services/frontend-web/`)
- `lib/api/classifier-accuracy.ts`: add optional `classifierType='sentiment'` to `getClassifierAccuracy`
  and `rollbackClassifier`, sending `?classifier_type=${classifierType}` (currently no param, `:49-62`).
- `components/settings/ClassifierAccuracyCard.tsx`: add `classifierType?: string` prop; pass to the two
  calls (`:94,121`); make title (`:138`) + subtitle (`:140-144`) reflect the type (not hard-coded
  "sentiment"). Rest is already type-agnostic.
- `app/(dashboard)/settings/ai/page.tsx`: render a second card in the Accuracy tab after `:486` —
  `<div className="mt-6"><ClassifierAccuracyCard classifierType="category" isAdminOrOwner={...} /></div>`.
- `lib/api/ai-settings.ts`: add `category_classifier_mode` to `AISettings` (`:18`) and `AISettingsUpdate`
  (`:29`).
- `components/settings/AISettingsGeneral.tsx`: add a second "Self-Improving Category Classifier" `<Select>`
  block mirroring the sentiment one (`:156-197`), bound to `settings.category_classifier_mode`, calling
  `aiSettingsAPI.update({ category_classifier_mode })`; category-appropriate copy.

## Out of scope
- Backend accuracy/rollback changes (already type-generic — none needed). The config column itself
  (→ data-and-config). No new frontend routes.

## Acceptance criteria (testable)
- The Accuracy tab shows two stacked cards: sentiment + category, each hitting the API with its
  `classifier_type`; the category card renders "not ready"/empty gracefully when the org has no category
  model (reuse existing empty/error states).
- The General tab shows two independent mode selects; changing the category select PATCHes
  `category_classifier_mode` and does not touch `classifier_mode`.
- Rollback on the category card posts `classifier_type=category` and is admin/owner-gated.
- `npm run lint` + `npm run test` green.

## Dependencies & sequencing
**Blocked by:** data-and-config (the `category_classifier_mode` field must exist on the settings API).
Frontend accuracy/rollback needs no backend change. Build last (or in parallel once data-and-config lands).

## Open questions / risks
- Copy should stay honest: "trained on your team's category corrections; promoted only when it beats the
  keyword categorizer on your held-out data." Match `SentimentAccuracyCard` styling primitives.
