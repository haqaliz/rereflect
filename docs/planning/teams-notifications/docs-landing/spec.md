# Spec: docs-landing

## Problem slice

Every place the product claims its integration surface is honest on day one — no
"Coming Soon", no stale provider sets.

## In-scope

- Landing `services/landing-web/lib/integrations.ts`: full Teams entry (`status:
  'available'`), mirroring the Slack outbound entry (:96-134) — name, tagline,
  description, color/gradient (brand `#6264A7`), howItWorks, features, useCases, faqs,
  setupSteps (webhook-URL steps). `getAvailableIntegrations()` (:448-450) picks it up
  automatically.
- README.md:62 "Sources & integrations" row — outbound clause gains Teams.
- `docs/SELF_HOSTING.md`:
  - Privacy table (:142) gains Teams.
  - New "### Teams alerts" section mirroring "### Discord alerts" (:763-808): connect
    steps, the per-type channel switch, the honest limits (MessageCard only; no OAuth;
    automations `send_notification` + playbook `notify` supported; classic + Workflows
    URL shapes; the automations-channels-editor absence and the API-created-rule-only
    reachability of `channels: ["teams"]`).
  - Automations notify claim (:1004-1007) gains Teams.
- Repo convention (git log: every shipped feature lands `docs: … changelog + tracking`):
  - `CHANGELOG.md` — a "Teams notifications" entry naming the shipped slice and its
    honest limits.
  - `AI-TRACKING.md` — new capability row (or extend the notification row) marking
    Teams shipped, with the out-of-scope inbound-source note.
  - `DEV-TRACKING.md` — close P7's "Teams … means another full round" framing with a
    shipped note (the bounded-sender decision), and record the Teams slice.
- Optional: sibling blog post (precedent `batch5.ts:7-75` Slack post) — only if a slot
  is open in BLOG-TRACKING; otherwise skip without claiming.

## Out-of-scope

Inbound-source docs; channel-editor docs; P7 refactor (decision recorded in planning
docs only, plus the DEV-TRACKING close-out above).

## Acceptance criteria

- Landing page shows Teams as available with webhook setup steps; no "coming soon" text
  anywhere for Teams.
- README outbound row names Teams.
- SELF_HOSTING.md section matches the shipped behavior (verified against the code the
  PR ships, not prose).
- No stale provider-set claims remain in the touched files.

## Dependencies / sequencing

Last aspect — depends on the shipped behavior of every other aspect.