# Aspect: landing

**Slice of:** Asana Integration slice 1. **Owner:** one frontend engineer/agent (self-contained). **Depends on:** none (marketing + docs; independent of the app code).

## Problem slice & outcome
The marketing site lists Asana as an available integration with its own page, and self-hosters have setup docs for pasting the PAT. Mirror how Jira/Zendesk shipped their landing + docs together.

## In scope
- `services/landing-web/lib/integrations.ts` — add an `asana` entry: `slug:"asana"`, `name:"Asana"`, `status:"available"`, brand `color`/`gradient` (`#F06A6A` coral-pink family), hero/how-it-works/features/use-cases/FAQs/setupSteps (setup = mint PAT → paste in Settings → Integrations → Asana → create tasks from feedback). Follow the `jira` entry's shape so `getAvailableIntegrations()` picks it up.
- `services/landing-web/components/icons/AsanaIcon.tsx` — landing icon signature `{className, size}` (distinct from frontend-web's icon API).
- `services/landing-web/app/integrations/asana/page.tsx` — mirror `integrations/jira/page.tsx` (`getIntegration('asana')`).
- `services/landing-web/app/integrations/page.tsx` — add `asana`→`AsanaIcon` to the slug→icon map.
- `services/landing-web/components/landing/IntegrationBar.tsx` — import `AsanaIcon` + add to the marquee.
- `docs/SELF_HOSTING.md` — "Connecting Asana" section (mint a Personal Access Token in Asana → paste PAT into Settings → Integrations → Asana; note the token is pasted into the app, not an env var; create tasks from feedback). Add TOC link.

## Out of scope
- App code (connect page, wizard, API) — that's the frontend aspect.
- Inbound-source docs.

## Acceptance criteria (testable)
- Asana appears in `getAvailableIntegrations()` / the landing integrations grid and marquee.
- `/integrations/asana` renders from the registry entry.
- `SELF_HOSTING.md` documents the PAT paste flow.
- Landing-web builds (`npm run build`) and lints clean.

## Dependencies & sequencing
Fully independent — can run in parallel with all backend/frontend aspects.

## Open questions / risks
- Keep marketing copy honest: describe it as "create Asana tasks from feedback" (outbound), not two-way sync.
