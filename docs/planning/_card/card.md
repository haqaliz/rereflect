# Card — status-sync-realtime-mapping (freeform)

**Type:** feat
**Slug/id:** status-sync-realtime-mapping
**Branch:** feat/status-sync-realtime-mapping
**Source:** Freeform task from `rereflect-next` recommendation (no GitHub issue).

## Brief (as recommended)

**Real-time, operator-mapped integration status-sync (v2)** — close the
"file feedback → auto-create ticket → engineer resolves → Rereflect reflects it
instantly, mapped to your states" loop across the three shipped issue
integrations (Jira, Asana, Zendesk).

### Why this was picked
- Hardens a named moat pillar (the **integration layer**) and the
  integrated-workflow loop. Inbound status-sync is deferred-v2 with the *same
  two gaps* across all three providers: **real-time inbound webhook** + a
  **per-status-name mapping editor UI** (`AI-TRACKING.md` lines 59 Jira, 60
  Zendesk, 61 Asana; `DEV-TRACKING.md` M3.2/M3.3/M3.4 deferred lists).
- Genuinely unbuilt and unblocked. Jira and Asana status-sync are **poll-only**
  today; Zendesk already ships a webhook path (`feat/zendesk-status-sync`) but
  its toggle is **API-only** (`PATCH /status-sync`, `AI-TRACKING.md` line 60)
  with no in-app UI and no operator-facing status mapping.
- Fits OSS/self-hosted/BYOK: pure workflow/config surface, no SaaS tier, no
  vendor-model dependency, and does not decay as base models improve.

### Scope / slicing (from the recommendation's caveat)
This spans three providers, so it must be **sliced, not done all at once**:
- **Slice 1:** shared **per-status-name mapping editor UI** (map each provider's
  statuses to Rereflect's feedback states) + an in-app **Zendesk status-sync
  toggle** (API-only today) + the config API behind it.
- **Slice 2+:** generalize Zendesk's existing real-time inbound webhook pattern
  to **Jira** and **Asana** (both poll-only today), one provider per slice.

### Explicitly OUT of scope
- Outbound webhook-on-change (separate deferred-v2 item).
- OAuth 3LO / Jira Server-DC / multiple sites (separate deferred-v2 items).
- Not to be confused with: M5.3 per-org churn ML (blocker-deferred at ≥500
  labels), M4.3 industry benchmarks (dropped, single-tenant), M5.4 local
  embeddings (parked).

### Alternates considered (not picked)
- Whole-filter-cohort playbook execution (`AI-TRACKING.md` M3.4 line 228).
- Advanced RBAC custom roles (`DEV-TRACKING.md` line 248).
