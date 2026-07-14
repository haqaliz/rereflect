# Changelog

All notable changes to Rereflect (the open-source, self-hosted edition) are documented here.
Every feature is unlocked; the app runs on your own infrastructure with your own (or a local) LLM key.

This is the first tagged release. Prior work lives in the git history and the tracking files
(`AI-TRACKING.md`, `DEV-TRACKING.md`).

## Unreleased

### Public API: bulk feedback writes + custom-category CRUD (v3)

- **Bulk feedback writes** — `POST /api/public/v1/feedback/bulk` (`write` scope) applies one
  patch (`workflow_status` / `tags` / `is_urgent` / `correction` — the same fields as the
  single `PATCH /feedback/{id}`) to up to 500 feedback ids in a single request. The response
  reports `matched` / `updated` / `skipped` counts plus a per-id `results` array
  (`updated` / `noop` / `skipped` / `error`, with a `reason` on skip/error); ids outside your
  organization (or that don't exist) are skipped rather than erroring. Pass
  `?count_only=true` to preview how many ids would match without changing anything.
- **Custom-category (taxonomy) CRUD** — `GET/POST/PATCH/DELETE /api/public/v1/categories`
  (read scope for `GET`, write scope for the rest) lets you manage your custom pain-point /
  feature-request / urgency / general categories over the API, mirroring the existing
  Settings UI. Creating a duplicate `(category_type, name)` returns `409`; an id from another
  organization (or that doesn't exist) returns `404`; `category_type` can't be changed after
  creation. Deleting a category that's still referenced by an active automation rule succeeds
  (204) but carries an `X-Rereflect-Warning` response header naming the rule(s), so you don't
  silently break an automation.

### Self-improving on-device models (M5.2)

- **Per-organization urgency classifier** — a third self-improving head (after sentiment and category),
  trained on your own urgency corrections. It's a small, CPU-only, offline binary model
  (`urgent` / `not_urgent`) whose challenger is promoted only when it beats the built-in
  keyword+sentiment urgency heuristic on your held-out corrections (≥ +0.02 macro-F1), with one-click
  rollback. Off by default; independent `off` / `shadow` / `auto` toggle in Settings → AI.
- You now teach it by simply flipping a feedback item's **urgent flag** — from the new toggle on the
  feedback detail page or via `PATCH /api/public/v1/feedback/{id}`; each user-driven change is recorded
  as a training signal (the analyzer's own automatic flagging is not).
- **Add-only in `auto`, by design.** Because the urgent flag drives churn alerts and the urgent queue,
  the model in `auto` mode can only ever **escalate** an item to urgent — it never silently clears a
  flag the built-in heuristic raised. `shadow` mode logs both directions so you can judge accuracy first.

## v0.1.0 — 2026-07-13

First tagged release of the self-hosted edition. Headline theme: **close the integration loop**
(feedback status now stays in sync with your work-management and support tools) and **on-device,
self-improving models** (your data trains small models that run locally and only ship when they're
measurably better).

### Integrations — inbound status-sync (close the loop)

Rereflect could already create work items and ingest tickets; now it keeps the feedback item's
status in sync when the linked item changes on the other side.

- **Jira** inbound status-sync — a linked Jira issue moving to Done (or any status) updates the
  feedback item's workflow status. Poll-first (every 15 min), opt-in per org, off by default.
- **Asana** inbound status-sync — completing (or re-opening) a linked Asana task updates the
  feedback item. Bidirectional; Asana has no intermediate state, so it maps completed vs. not.
- **Zendesk** inbound status-sync — a linked ticket's status (new / open / pending / solved /
  closed) updates the feedback item, via **both** a 15-min poll and an optional real-time webhook.
- Common to all three: opt-in per organization (off by default), a non-destructive first-poll
  baseline (no retroactive bulk rewrites), a manual "Sync now" action, per-organization status
  mapping you can override, and an audit trail — every automatic change writes a timeline entry
  tagged with its source. A hand-set status is never overwritten by a sync unless the linked item
  genuinely changes.
- Built on a shared, provider-agnostic reconcile core, so adding the next tool is incremental.

### Self-improving on-device models (M5.2)

- **Per-organization sentiment and category classifiers** that train on your own feedback and your
  own corrections, run CPU-only and fully offline, and **auto-promote a new model only when it beats
  the current one on held-out data** — with one-click rollback. Off by default; the built-in
  analyzer stays the baseline until a challenger proves itself.
- Honest by design: these are small models, described as such. Churn remains a calibrated heuristic,
  sentiment defaults to VADER, and nothing claims accuracy it hasn't shown.

### Notes

- All of the above is **opt-in and off by default** — upgrading changes no behavior until you turn a
  feature on. Database migrations are additive.
- Fully compatible with bring-your-own-key cloud LLMs and local/offline models (Ollama or any
  OpenAI-compatible endpoint).

See `docs/SELF_HOSTING.md` for operator setup of each integration.
