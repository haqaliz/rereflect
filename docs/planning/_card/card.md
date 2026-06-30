# Card — HubSpot CRM Enrichment (freeform)

**Type:** feat
**Slug / branch:** `feat/hubspot-crm-enrichment`
**Worktree:** `.claude/worktrees/feat-hubspot-crm-enrichment`
**Source:** Freeform task (no GitHub issue). Selected by `rereflect-next` as the
single highest-leverage next feature; started via `rbf feat hubspot-crm-enrichment`.

---

## Brief (from rereflect-next handoff)

Build **HubSpot CRM enrichment for Customer 360 and churn** — the last open
data-enrichment source. After product-usage enrichment (M3.2, merged `a8047d9`)
and the unified Customer 360 timeline + public API (M3.4, merged `ca73cc9`)
shipped, HubSpot is the one enrichment source still pending.

Scope the **first slice** around a HubSpot **private-app access token**
(BYOK-style, pasted by the self-hoster — **not** the OAuth marketplace flow,
which needs a public redirect URI and is awkward for a self-hosted product):

1. **Connect** — operator pastes a HubSpot private-app access token (stored
   encrypted, per-org), with connect / disconnect / test.
2. **Sync contacts by email** — pull HubSpot contacts and match them to Rereflect
   customers by `customer_email` (the email-match machinery already exists from
   the usage work).
3. **Enrich Customer 360** — surface company name, ARR / deal value, contract
   renewal date, deal stage, lifecycle stage on `/customers/[email]`.
4. **Churn/health signal** — feed a CRM-renewal factor into the health/churn
   signal: "renewal coming up + declining health = critical".
5. **Timeline** — surface CRM events on the unified customer timeline. The
   timeline event shape was deliberately left **source-extensible** for exactly
   this; CRM events are the deferred-until-HubSpot item from `AI-TRACKING.md:204`.

---

## Why this feature (moat grounding)

- **Next explicitly-pending milestone**, not shipped and not blocker-deferred:
  `AI-TRACKING.md` M3.1 (lines 178–186) is entirely unchecked; `DEV-TRACKING.md`
  M3.5 (lines 209–213) restates it.
- **Feeds the killer feature** — "churn prediction that actually works"
  (`AI-TRACKING.md:5`). Renewal date / ARR / deal stage are the most predictive
  external churn signals the model currently lacks (`AI-TRACKING.md:183`).
- **Unblocked + depth-first** — unblocks the CRM timeline events deferred in the
  just-shipped Customer 360 timeline (`AI-TRACKING.md:204`), and follows an
  already-proven integration pattern (Intercom / Slack: adapter + webhook
  receiver + email-match + two-way sync, `DEV-TRACKING.md:606`).

## Fit with OSS / self-hosted / BYOK

- MIT, all features unlocked — **no plan gating** (the `Business+` framing in
  `AI-TRACKING.md` M3.1 and `CLAUDE.md` is pre-pivot and stale).
- Single-tenant: the operator connects **their own** HubSpot portal. No central
  cross-customer dataset.
- BYOK-style: private-app token pasted by the operator, stored encrypted (reuse
  the existing Fernet encryption pattern used for LLM keys / webhook headers).

---

## Known caveats / open questions (to resolve in deep dig + PRD interview)

1. **No dedicated HubSpot PRD exists.** The feature lives only in `AI-TRACKING.md`
   M3.1 + `DEV-TRACKING.md` M3.5 bullets + the enrichment hooks in
   `PRD-CUSTOMER-360.md`. The PRD will be written from those during this run.
2. **Auth method:** first slice uses a **private-app access token**, not OAuth.
   Full OAuth marketplace app + bi-directional push-back (health scores → HubSpot
   custom properties) are **deferred to v2**.
3. **Sync model:** pull-only for v1 (read from HubSpot). Bi-directional push is v2.
4. **Sync trigger:** on-demand vs scheduled (Celery beat) vs both — TBD.
5. **Data model:** where CRM enrichment lives (new table vs columns on an existing
   customer/profile model) — TBD in deep dig + interview.
6. **Health-score integration:** whether CRM becomes a new weighted component or a
   modifier/override on the existing components — TBD (interacts with the
   configurable per-org health weights shipped in M4.2).

---

## Reference files (in primary repo root)

- `AI-TRACKING.md` — M3.1 (HubSpot), M3.4 (Customer 360, CRM events deferred)
- `DEV-TRACKING.md` — M3.5 (HubSpot), integration backlog + Intercom pattern
- `PRD-CUSTOMER-360.md` — Customer 360 enrichment hooks
- `PRD-LOCAL-LLM-CUSTOM-AI-PUBLIC-API.md` — OSS pivot context, public API
- `memory/rereflect-oss-pivot.md` — OSS/self-hosted/BYOK reality + stale-CLAUDE.md caveat
