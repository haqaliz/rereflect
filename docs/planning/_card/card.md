# Card — feat/customer-360-unified-timeline

**Type:** feat
**Slug / branch id:** `customer-360-unified-timeline`
**Source:** Freeform task (no GitHub issue) — selected via `rereflect-next` as the highest-leverage next feature.
**Worktree:** `.claude/worktrees/feat-customer-360-unified-timeline`
**Branch:** `feat/customer-360-unified-timeline`

---

## Brief (from rereflect-next handoff)

Build the **AI-TRACKING M3.4 "unified customer timeline"** first slice.

A single org-scoped, paginated endpoint that merges each customer's existing event
sources into one **reverse-chronological timeline**:

- **Feedback items** (the customer's feedback, with sentiment/category)
- **Product-usage events** (the `customer_usage` / `usage_event` tables that just
  merged in M3.2, commit `a8047d9`)
- **Churn / health-score change events** (health score changes, risk-level changes)

The timeline is surfaced on the existing `/customers/[email]` profile page, plus the
**read-only Customer 360 + health-score API endpoints** from AI-TRACKING M3.4
(`AI-TRACKING.md:201-206`).

### In scope (this slice)

- Unified, reverse-chronological, paginated timeline endpoint (3 sources: feedback +
  usage + churn/health).
- Surface the timeline on the existing `/customers/[email]` profile page.
- Read-only Customer 360 API + health-score API endpoints (programmatic / self-host
  consumption — fits BYOK/self-hosted positioning).
- Everything **unlocked** (OSS self-hosted — no plan gating).

### Out of scope (later slices / deferred)

- **CRM events** in the timeline — CRM (HubSpot, M3.1) is **not built**. Design the
  timeline event shape to be **source-extensible**, but do NOT build CRM rows now.
  CRM rows slot in when M3.1 ships.
- **Customer segments** (M3.4 "auto-group power users / silent churners / advocates")
  — leave out of this slice. Today this could only be heuristic/keyword-based; there
  is **no ML segmentation** and it must not be implied as such.
- **Bulk actions** (M3.4 export / bulk-assign CS owner / trigger outreach) — later slice.

---

## Why this was picked (moat / context)

- **Freshly unblocked by what just merged.** M3.2 usage events landed this week
  (`a8047d9`), so feedback + product-usage + churn events now all exist per-customer —
  but nothing stitches them together. AI-TRACKING M3.4's "unified customer timeline:
  feedback + CRM events + usage events in chronological order" is still pending `[ ]`
  (`AI-TRACKING.md:202`).
- **Deepens the real moat** on two axes: hardens the churn→health→playbook loop (a
  single chronological view is where an operator sees *why* a health score moved), and
  adds the **Customer 360 API + health-score API** (`AI-TRACKING.md:204-206`) — the
  programmatic/self-host developer surface, which fits OSS/BYOK and compounds as
  operators build on it.
- **Clean, testable, no external dependency.** First slice = a chronological merge of
  three event sources that already exist into one org-scoped endpoint, surfaced on the
  existing `/customers/[email]` profile. Unlike the CRM alternate, it needs no OAuth
  app registration to demo.

## Known caveats (carry into PRD/dig)

- M3.4's timeline spec lists **CRM events** as a source, but CRM isn't built — first
  slice covers feedback + usage + churn only; event shape must stay source-extensible.
- "Customer segments" is heuristic-only today — don't ship/sell it as ML. Keep it out
  of this slice.
- CLAUDE.md's billing / plan-tier / Resend / Stripe sections are **stale** (pre-OSS
  pivot). Everything ships unlocked. Use CLAUDE.md only for architecture/service layout.

## Roadmap references

- `AI-TRACKING.md:201-206` — M3.4 Enhanced Customer 360 (unified timeline, segments,
  bulk actions, Customer 360 API, health score API) — pending `[ ]`.
- M3.2 product-usage enrichment SHIPPED — merge `a8047d9` + ~24 commits (usage_event
  model, ingest receiver, rollup+score, health 5th component, profile usage card/timeline).
- M1.2 Customer 360 page (`/customers` list + `/customers/[email]` profile) — COMPLETE.
- `PRD-CUSTOMER-360.md` — original M1.2 PRD (profile page already exists;
  `customer_health_history` model already stores health-score snapshots).
