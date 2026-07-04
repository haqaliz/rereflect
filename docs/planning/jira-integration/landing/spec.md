# Aspect Spec — landing

**Parent PRD:** `../prd.md` · **Aspect dir:** `landing/` · **Depends on:** none (independent)

## Problem slice & outcome

Keep the public integrations story accurate and give self-hosters the setup steps to mint an Atlassian
API token. Outcome: a `/integrations/jira` marketing page renders (data-driven) and operator setup
docs exist.

## In scope

- **`services/landing-web/lib/integrations.ts`**: add a `jira` entry (copy the **HubSpot** entry's
  token-paste `setupSteps` wording, not Linear's OAuth wording): heroMessage, howItWorks, features,
  **setupSteps** (mint token at id.atlassian.com → Security → API tokens; paste site URL + email +
  token in Rereflect Settings → Integrations → Jira), faqs (Cloud-only; Server/DC + OAuth are v2).
- **`services/landing-web/app/integrations/jira/page.tsx`**: copy the Linear landing page, swap to
  `getIntegration('jira')`.
- **`services/landing-web/components/icons/JiraIcon.tsx`** (landing copy of the icon).
- If the integrations index/overview or an `IntegrationBar` on landing enumerates integrations, add Jira there.
- **Operator setup docs**: add a short "Jira" section to `docs/SELF_HOSTING.md` (mirror the
  usage-enrichment precedent) — how to mint the API token + accepted `site_url` format + that it's
  Cloud-only in slice 1.

## Out of scope

- Any product-app (dashboard) code (→ `frontend`).
- OAuth/marketplace-listing copy (v2).

## Acceptance criteria (testable)

- `/integrations/jira` builds and renders from the `jira` data entry (no hardcoded content).
- `landing-web` build/lint pass.
- `docs/SELF_HOSTING.md` has a Jira setup section covering token minting + site URL.

## Dependencies & sequencing

Fully independent — can be built in parallel with all backend/frontend aspects. Lowest risk.

## Open questions / risks

- Keep FAQ copy OSS-accurate (self-hosted, BYOK, all-unlocked) — the repo just corrected other
  integration FAQs for OSS accuracy (`0cd6c8f`); match that tone, no SaaS/pricing claims.
