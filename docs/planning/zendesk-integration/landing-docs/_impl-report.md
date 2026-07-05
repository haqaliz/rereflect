# Implementation Report — Zendesk landing-docs (flip to "available")

**Aspect:** `landing-docs` · **Branch:** `feat/zendesk-integration` · **Date:** 2026-07-05
**Status:** DONE

Flipped the Zendesk marketing surface from "coming soon" to a shipped/"available"
integration and documented operator setup for self-hosters. Copy/data/docs only — no
app/backend/worker code touched.

## Files changed

| File | Change |
|------|--------|
| `services/landing-web/lib/integrations.ts` | Added `ZENDESK_FAQS` const (SHARED_FAQS + one honest Q&A). Rewrote the `zendesk` object: `status: 'coming_soon' → 'available'`; shipped-tone `description`/`heroMessage`/`howItWorks`; 6 `features` with icons `FileText, RefreshCw, Zap, Users, AlertTriangle, Shield`; 3 `useCases` (Headphones/Layers/Heart); `faqs: ZENDESK_FAQS`; 6 `setupSteps` (token-mint → connect → optional webhook). Kept slug/name/color/gradient/hover* as-is. |
| `services/landing-web/app/integrations/zendesk/page.tsx` | Replaced the coming-soon variant wholesale with the intercom-mirrored full "available" layout (hero, how-it-works, features, setup steps, expandable FAQ, CTA). Reuses the existing `ZendeskIcon`. lucide imports now `ArrowRight, ChevronRight, ChevronDown, FileText, RefreshCw, Zap, Users, AlertTriangle, Shield, Github` — all coming-soon-only imports (`Clock, X, Target, Settings, Sparkles, TrendingUp`) removed. `featureIconMap` kept in lockstep with `features[].icon`. CTA: "Self-host and connect Zendesk." Footer uses the simpler intercom footer (no X/ProductHunt). |
| `services/landing-web/app/integrations/page.tsx` | Guarded the now-potentially-empty Coming Soon section with `{comingSoonIntegrations.length > 0 && ( ... )}` (Phase 4 / Risk R1). Since Zendesk was the last `coming_soon` entry, the section no longer renders as a heading-only dead block. `Clock`/`comingSoonRef` remain referenced inside the guarded JSX (no unused-import lint). |
| `docs/SELF_HOSTING.md` | Added TOC link `- [Connecting Zendesk](#connecting-zendesk)` and a `## Connecting Zendesk` section (after Jira, before Production notes): shipped-scope intro (inbound source; new tickets only; one item per ticket; exactly-once; pull default + optional webhook; Basic auth, no OAuth), (1) create API token, (2) connect (subdomain/email/token table, SSRF safeguard, `LLM_ENCRYPTION_KEY`, token never returned, auto-provisioned source, webhook URL + signing secret shown once), (3) optional webhook (`<your-api-base>/api/v1/webhooks/zendesk/events`, trigger on "Ticket is created", signature scheme `X-Zendesk-Webhook-Signature = base64(HMAC-SHA256(secret, timestamp + raw_body))` verified over the raw body), Verify, All features unlocked. |

## Honesty guardrails (respected)

Copy describes only shipped scope: new tickets only (no historical backfill), one
feedback item per ticket (subject + description), connect via subdomain + agent email
+ API token (NOT OAuth), pull by default + optional real-time webhook, exactly-once by
ticket ID. No custom-field mapping, per-comment ingestion, tag/view filters, or OAuth
advertised anywhere.

## Validation

Dependencies were not installed in the fresh worktree, so they were installed first via
`pnpm install --frozen-lockfile` at the worktree root. The correct build path is the
workspace script (`pnpm --filter landing-web build`, matching root `build:landing`).

- **Lint** — `next lint`: `Errors: 0 | Warnings: 0`. ✅
- **Build** — `pnpm --filter landing-web build`: compiled successfully, type-check
  passed, all 35 routes generated including `○ /integrations/zendesk (5.04 kB)`. ✅
- **Tests** — `vitest run`: 8 files, **89 tests passed**, incl.
  `__tests__/landing/IntegrationBar.test.tsx` (3 tests). ✅
- **No coming-soon imports** — `grep -nE "Clock|Sparkles|coming|Target|Settings"
  app/integrations/zendesk/page.tsx` returns nothing. ✅
- **Coming-soon section guarded** — confirmed the `<section ref={comingSoonRef}>` on the
  integrations index is wrapped in `{comingSoonIntegrations.length > 0 && ( ... )}`, so
  no empty heading-only section renders now that Zendesk is `available`. ✅

## Deviations / notes

- A first `npx next build` failed with a Turbopack workspace-root inference error. This
  was an environment artifact (npx resolved a globally-cached Next 16 with Turbopack
  against an uninstalled worktree, while the package pins Next 15 with `output: "export"`).
  The real build path (`pnpm --filter landing-web build`) passes cleanly. No code issue.
- The landing site's feature-icon set for Zendesk (`FileText, RefreshCw, Zap, Users,
  AlertTriangle, Shield`) is kept identical between `features[].icon` (data) and
  `featureIconMap` (page), per the icon contract.
