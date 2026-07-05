# Card — Zendesk feedback-source integration (freeform)

**Type:** feat · **Slug:** `zendesk-integration` · **Branch:** `feat/zendesk-integration`
**Source:** Freeform task from the `rereflect-next` recommendation handoff (verified against git — genuinely unbuilt). No GitHub issue.
**Date:** 2026-07-05

---

## Brief

Bring **Zendesk support tickets** in as a first-class **inbound feedback source**, mirroring
the already-shipped Intercom / Jira / Linear integration slices. Support tickets are the
richest untapped feedback channel for most SaaS; each ingested ticket flows straight into
the existing churn → health → copilot → automations pipeline, so one integration lifts
everything downstream. This deepens the product's real moat: **integration breadth**.

Positioning: **open-source, self-hosted, BYOK.** All features unlocked (no plan gating).

## Why now (grounded)

- **Genuinely unbuilt; scaffold is stubbed.** `services/worker-service/src/tasks/integrations.py:180`
  has a `ZendeskConnector` placeholder ("TODO: Implement actual Zendesk API integration in
  Month 2"; `fetch_new_items` logs "not implemented"). No real Zendesk code exists under
  `services/*/src`.
- **Backlog-confirmed pending:** `DEV-TRACKING.md:158` and `:206` (Zendesk API, unchecked);
  `AI-TRACKING.md:158` (`[ ] Zendesk API`).
- **Proven, repeatable pattern.** The exact slice shipped 3×: Intercom (pull support
  conversations), Jira, Linear. Reuse: `services/worker-service/src/adapters/intercom.py`
  (adapter), `services/backend-api/src/services/intercom_service.py` (backend service),
  source-type registration (Jira did it at commit `c2795a5`), frontend icon + create/source
  wizard, landing page + `SELF_HOSTING.md` docs.

## Scope (first slice — proposed, to be pressure-tested in PRD)

- Connect / status / disconnect / test via **API-token auth** (Zendesk email + API token,
  HTTP Basic `email/token:token`, encrypted at rest via `encrypt_api_key`) — the Jira BYOK
  precedent, **not** the OAuth marketplace flow (awkward for self-host).
- One Zendesk subdomain per org.
- Pull tickets → feedback as a `zendesk` source type (one feedback item per ticket; dedup on
  ticket id).
- Frontend: Zendesk tile + icon, settings/connect page, create/source wizard branch.
- Docs: landing integration page + `SELF_HOSTING.md` token-setup section.

## Deferred to v2 (proposed)

- Comment-level granularity (one item per ticket-comment).
- Any status write-back to Zendesk / bidirectional sync.
- OAuth flow, multiple subdomains per org.

## Known caveats (for the dig to resolve)

1. **Two ingestion patterns coexist** — do not blindly extend the wrong one:
   - **Legacy:** `services/worker-service/src/tasks/integrations.py` `BaseConnector` /
     `ZendeskConnector` polling loop.
   - **Newer (canonical):** `services/worker-service/src/adapters/intercom.py` +
     `services/backend-api/src/services/intercom_service.py` + source-type registration,
     used by Intercom / Jira / Linear.
   The dig must confirm which is canonical and decide whether to wire or retire the legacy
   `ZendeskConnector` placeholder.
2. **Auth model:** API token (email + token, Basic) vs OAuth — commit to API token for
   self-host fit.
3. **Ingestion granularity:** ticket vs ticket + comments as one feedback item.
4. **Dedup / incremental pull:** ticket id as the dedup key; how to track high-water mark
   (updated_at cursor) for incremental syncs.
