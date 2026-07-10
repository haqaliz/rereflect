# Card — feat/local-analyzer-sentiment-model

**Type:** feat
**Source:** freeform (no GitHub issue) — originated from the `rereflect-next` recommendation
**Branch:** `feat/local-analyzer-sentiment-model`
**Worktree:** `.claude/worktrees/feat-local-analyzer-sentiment-model`
**Date:** 2026-07-10

---

## Brief (from rereflect-next handoff)

Build **M5.1 of the Local Model Layer** (`AI-TRACKING.md:320`): a pluggable
**analyzer-provider abstraction** for sentiment (mirroring the existing LLM /
embedding provider layers), with VADER wired through it as the **byte-stable
default** so existing installs are unchanged, plus one **opt-in
distilled-transformer sentiment provider** running CPU-only. Ship an **eval
harness + accuracy card** (labeled set → precision / recall / F1 / confusion)
that *proves* the model beats the lexicon before it is recommended.

### Why this was picked (moat + shipped-state grounding)
- **Unblocked first slice of the just-planned M5 moat, and the only M5 track that
  isn't data-gated.** `AI-TRACKING.md:329` marks M5.1 "Not data-gated → first
  shipped," vs M5.2 (gated on correction volume, `:332`) and M5.3 (gated at ~500
  churn labels, `:342`). M5 is docs-only so far — commit `9592f51` added the
  roadmap block; nothing is built and there is no `docs/planning/` entry for it.
- **Builds the spine everything else in M5 stands on.** M5.1 is explicitly
  "Track B + spine v1" (`AI-TRACKING.md:320`) — the provider abstraction that
  M5.2's per-org classifiers and M5.3's churn model plug into.
- **Deepens the real OSS / self-hosted / BYOK moat, honestly.** CPU-only,
  offline, default stays VADER (byte-stable), and the eval harness makes "more
  accurate than a lexicon" *proven, not marketing* (`AI-TRACKING.md:327-330`).
  The heavy stack (`torch`, `transformers`, `sentence-transformers`) is already
  installed (`AI-TRACKING.md:304`), so this is wiring + eval, not new infra.

## Scope (from the roadmap M5.1 bullets, `AI-TRACKING.md:320-330`)
1. **Pluggable analyzer-provider abstraction** — mirror the existing LLM/embedding
   provider layers so sentiment/category/urgency can be backed by
   `{ default (VADER/keyword) | shipped model | per-org trained }`. (This slice
   focuses on **sentiment**; category/urgency backends come later in M5.)
2. **Opt-in distilled transformer sentiment (+ optional emotion) provider** — CPU
   inference; download-on-first-run + cached; default stays VADER (lean image,
   zero-config, byte-stable); documented **air-gapped pre-bake** path.
3. **Eval harness + accuracy card** — a labeled eval set + precision/recall/F1/
   confusion so the model provably beats VADER on the eval set, offline.

## Known caveats to design around (from the handoff)
- **No labeled sentiment eval set exists in the repo yet** — slice 1 must source
  or hand-label one (a public sentiment corpus, or a hand-labeled sample of the
  org's own feedback) before the "beats VADER" gate means anything.
- **Model download breaks air-gapped self-hosters** — "download-on-first-run +
  cached" pulls a model over the network; the documented **pre-bake** path is
  part of slice 1, not optional polish.
- **Keep the transformer strictly opt-in and the default byte-identical to
  today** so existing installs don't change (characterization-test VADER-through-
  the-provider for byte-stability).

## Suggested testable first slice
Provider abstraction + VADER-as-default-provider (characterization-tested for
byte-stability) + the eval harness → then add the transformer provider behind an
opt-in flag. Optionally fold in the cheap **M5.0 readiness report**
(`AI-TRACKING.md:313`, no ML) since it de-risks the next M5 track.

## Exit criteria (roadmap M5.1, `AI-TRACKING.md:330`)
Opt-in model provably beats VADER on the eval set, offline; default unchanged.

---

_Note: this worktree inherited a stale `_card/understanding.md` from the prior
`segment-actions` task (committed to master). Phase 2 overwrites it with this
task's understanding note._
