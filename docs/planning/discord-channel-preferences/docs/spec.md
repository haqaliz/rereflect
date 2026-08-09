# Spec — docs

**Aspect of:** `discord-channel-preferences` · **PRD refs:** S1
**Date:** 2026-08-09

## Problem slice and user outcome

The operator documentation and changelog must describe the new per-type Discord
channel behavior instead of the old "Discord rides the Slack toggle" limitation,
and no other public surface may still describe the coupling.

## In-scope requirements

- **`docs/SELF_HOSTING.md`** — the "Discord alerts" section (`:678-710`):
  - The "⚠️ Discord currently rides on the Slack toggle" callout and its two
    consequences + "A dedicated `channel_discord` preference is a schema change
    and is not in this release" sentence → replace with the new behavior:
    per-type Discord channel switch in Settings → Notifications, default on;
    Slack and Discord route independently; Discord delivery requires an active
    Discord integration.
  - Keep: the custom-webhook warning and the "Not covered by Discord" list
    (automation-rule notifications etc. — unchanged, still accurate).
- **`CHANGELOG.md`** — add an entry under `## Unreleased` describing the change
  (per-type `channel_discord` preference; default-on preserves existing delivery;
  the one behavior change: a type with Slack off + Discord on now delivers).

## Out-of-scope boundaries

- Landing page / README feature copy: no changes needed (they don't describe the
  coupling; verified in the dig — README Highlights mention Discord only as an
  outbound channel).
- No code changes.

## Acceptance criteria (testable)

1. `rg -n "rides on the Slack toggle|channel_discord.*schema change|not in this release" docs/SELF_HOSTING.md` returns nothing (with the updated text committed).
2. CHANGELOG has an Unreleased entry naming the per-type Discord preference and
  the default-on behavior.
3. No remaining "Discord rides the Slack toggle" phrasing anywhere in `docs/`
  and `README.md` (grep check).

## Dependencies and sequencing notes

- Last aspect: write after the code aspects land so the docs describe shipped
  behavior.
