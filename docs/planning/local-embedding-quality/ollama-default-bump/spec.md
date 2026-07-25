# Aspect spec — ollama-default-bump

**Parent PRD:** `../prd.md` (M5.4, Option B) · **Aspect 5 of 5** · **Sequencing: after `retrieval-eval-card`**

## Problem slice & user outcome

Operators who already run Ollama use `nomic-embed-text` (the current default recommendation). The
retrieval eval (Aspect 3) can also score stronger Ollama models, so we can make an **eval-backed**
recommendation instead of an asserted one. Outcome: the docs recommend the better model, and — because
the staleness fix keys on model — switching triggers a safe system-template reseed, not a silent
mis-match.

## In-scope

- Run the Aspect 3 eval over candidate Ollama models (`mxbai-embed-large`, `bge-m3`) vs
  `nomic-embed-text`; record numbers in the committed artifact.
- Update `docs/SELF_HOSTING.md` to recommend the winning Ollama embedding model, with the `ollama
  pull` command and the honest eval delta.
- **Decision (Q1):** whether to change the `_default_embedding_model('ollama')` string itself. Default
  stance = **docs-only** (preserve byte-stability for existing ollama installs). Only change the code
  default if the user explicitly approves the behaviour change (it would trigger a reseed via the
  model key — safe, but not byte-stable).

## Out-of-scope

- The in-process provider (Aspect 2) — this aspect is purely the external-server path.
- Any change to cloud provider defaults.

## Acceptance criteria (testable)

1. The committed eval artifact includes numbers for the candidate Ollama models vs `nomic-embed-text`.
2. `docs/SELF_HOSTING.md` recommends the eval-winning model with a runnable `ollama pull` command and
   states the measured delta and `n`.
3. If (and only if) the code default is changed: existing ollama installs reseed system templates on
   next boot (via the model key) and never produce a wrong-space match; a characterization test
   confirms no silent mis-match across the change.
4. If docs-only: `_default_embedding_model('ollama')` is unchanged and existing installs are
   byte-stable.

## Dependencies & sequencing

- **Depends on `retrieval-eval-card`** (needs the eval to back the recommendation) and
  `staleness-model-key` (safe model switch).
- Smallest aspect; land last.

## Open questions / risks

- Requires Ollama + the candidate models available in the eval environment to produce real numbers; if
  unavailable, record what was and wasn't measured honestly rather than asserting a winner.
- Bigger Ollama models (e.g. `mxbai-embed-large`, 1024-dim) raise the operator's own resource cost —
  note it in the recommendation.
