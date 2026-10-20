# PRD — Roadmap marker hygiene: close markers already fixed in code

**Issue:** #46 · **Slug:** `roadmap-marker-hygiene` · **Date:** 2026-10-21
**Type:** docs-only chore. No code changes.

## Problem

`DEV-TRACKING.md` and `AI-TRACKING.md` carry open checkboxes and "deferred" notes for work
that has since shipped. A stale open marker costs more than an absent one: it sends the next
planner into already-built code and it understates the product to users. The tracking files'
own rule is that a wrong marker is worse than an absent one.

## Scope

Verify each claim in #46 against the code/docs on `origin/master`, then correct only the
markers that are factually stale. Where a claim is false, leave the marker and report it.

| # | Marker | Verification | Action |
|---|--------|--------------|--------|
| 1 | `DEV-TRACKING.md` copilot-dig bullet: stale plan gate in `RunPlaybookDropdown.tsx:26,47` | File has no `user?.plan` / `plan === 'business'`; gating is `useRole().isAdminOrOwner` | Close the bullet |
| 2 | `DEV-TRACKING.md` P1 Intercom/Zendesk discoverability | `README.md:38,62` name Intercom, Zendesk, Jira, Linear, Asana; `SELF_HOSTING.md` has `#connecting-zendesk` and `#connecting-intercom` (token vs OAuth, pull/webhook, env vars) | Tick Part A, mark Part B superseded, retitle section CLOSED |
| 3 | `DEV-TRACKING.md` M3.5 HubSpot five boxes | Shipped as `hubspot-crm-enrichment`; see AI-TRACKING M3.1. **OAuth box is false** — shipped as private-app access token (BYOK) | Tick with the OAuth correction, strike the plan gate |
| 4 | `AI-TRACKING.md` M3.4 "CRM events deferred" | `customer_timeline_service._fetch_crm_events` at `:661`, called at `:872`; emits `crm_contact_synced` + `crm_renewal_upcoming`, `crm_deal_stage_changed` still deferred to v2 | Update note, promote M3.4 to COMPLETE |
| 5 | "Phase 3 Custom AI models — delivered by M4.2 + M5.2" | The marker lives in `DEV-TRACKING.md:1065` ("Phase 3: Enterprise"), not AI-TRACKING; AI-TRACKING's equivalent is M3.3's "Corrections feed into fine-tuning pipeline (M4.2)" at `:363` | Tick both, one-line evidence each |
| 6 | "AI-TRACKING.md M3.7 Plan gate: Enterprise (RBAC)" | No M3.7 in AI-TRACKING; the marker is `DEV-TRACKING.md:1145` under M3.7 | Strike |
| 7 | Secondary DEV-TRACKING plan-gate/pivot drift | Not separately present beyond #1/#6 | No change |

## Non-goals

- No code, config, or test changes.
- Not rewriting the legacy "Plan Gating" tables wholesale — only the specific markers in #46.
- Not claiming shipped work that is not shipped (notably HubSpot OAuth, `crm_deal_stage_changed`,
  advanced RBAC/custom roles).

## Acceptance

- Every changed line names what shipped or what remains, dated 2026-10-21, with `#46`.
- Anything refused stays open with the reason in the PR body.
