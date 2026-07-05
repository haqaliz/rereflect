# Aspect: landing-docs

**Slice:** Flip Zendesk from "coming soon" to a shipped/"available" integration on the marketing
site, and document operator setup for self-hosters.

## In scope
- `services/landing-web/lib/integrations.ts` (l.269-294): change `status: 'coming_soon'` →
  `'available'`; fill `useCases` and `setupSteps` (connect via subdomain+email+token; optional
  Zendesk trigger/webhook for real-time).
- `services/landing-web/app/integrations/zendesk/page.tsx`: swap the "coming soon" variant for the
  full available layout (mirror `app/integrations/intercom/page.tsx` — hero, how-it-works,
  features, setup steps, FAQ, CTA). Reuse the existing landing `ZendeskIcon` (already present).
- `docs/SELF_HOSTING.md`: add a Zendesk section — API token creation, connect steps, and the
  optional webhook (URL + secret, Zendesk trigger config), mirroring the Jira token-setup docs.

## Out of scope
- App-side UI (frontend aspect); backend/worker.

## Acceptance criteria
- Landing `IntegrationBar.test.tsx` / integrations index still pass with Zendesk `available`.
- Zendesk landing page renders the full available layout (no `Clock`/coming-soon imports).
- `SELF_HOSTING.md` documents both token-pull and webhook setup.
- `npm run lint`/`build` green for landing-web.

## Dependencies / sequencing
- Copy/docs only; can run in parallel. Best done last so setup steps match the shipped UX/routes.
