# Spec: docs-tracking

## Problem slice

This repo's tracking files are the roadmap's source of truth, and `rereflect-next` reads them
to choose what to build. A capability that ships without updating them causes the exact drift
that `docs/planning/ingestion-source-visibility/` and the "Roadmap hygiene" entries
(`DEV-TRACKING.md:598`) were opened to fix — an entry that is *present but wrong* is worse
than absent.

**User outcome:** a self-hoster reading the docs learns what the copilot can now do, and —
just as importantly — what it cannot.

## In-scope

- **`CHANGELOG.md`** — a behaviour entry: the new `actions` item in `structured_data`, the
  execute route, and the honest limits (one action type; `data`/`analysis` queries only;
  admin/owner only; one-shot; proposals are server-derived, not model-authored).
- **`AI-TRACKING.md`** —
  - a Current AI Capabilities row for copilot suggested actions;
  - an **M2.2 follow-on marker** recording that `PRD-AI-COPILOT.md:33`'s "no action execution"
    non-goal is now *partially* closed;
  - an annotation on the strategic-decision row at `:25` marking it **partially delivered** —
    read + suggest is live, but for one action type and from a deterministic proposer only.
    Do not mark it done.
- **`README.md` / `docs/SELF_HOSTING.md`** — what the copilot can do, and the honest limits.
  Specifically worth stating: proposals are computed server-side from the result shape, so they
  behave identically on a keyless local model.
- **Record the adjacent defects** found during the dig in `DEV-TRACKING.md` so they are not
  re-discovered (PRD "Adjacent defects" section): the stale `copilot.py:5` docstring,
  `regenerate` not implemented while exposed in the frontend hook API, the always-zero token
  counters, the stale `RunPlaybookDropdown` plan gate, the inconsistent report-branch error
  send, and the dead `has_custom_key` field.

## Out-of-scope

- **Fixing** any of those adjacent defects.
- Landing-page copy. Slice 1 is one action type behind an admin gate — not yet a marketing
  claim. Revisit when the registry carries several actions.
- Re-litigating the plan-gating tables (pre-pivot and stale by design, `AI-TRACKING.md:461`).

## Acceptance criteria

- No tracking or docs surface claims the copilot can execute actions it cannot.
- The strategic-decision row at `AI-TRACKING.md:25` is marked partially delivered, not done.
- The M2.2 follow-on marker names the branch and the date, matching the house format used by
  the `scheduled-ai-reports` follow-on entry (`AI-TRACKING.md:184-186`).
- Every adjacent defect from the PRD has a `DEV-TRACKING.md` entry with enough detail to act on
  without re-running the dig.
- `README`/`SELF_HOSTING` state the limits, not just the capability.

## Dependencies and sequencing

**Last.** Depends on the shipped behaviour of every other aspect — write it once the behaviour
is final, so the claims are true.

## Open questions / risks

- Main risk is over-claiming. The temptation is "the AI Copilot can now take actions"; the true
  statement is "the copilot can propose one specific, admin-only, reversible action on the
  result set of a query, and execute it on click."
