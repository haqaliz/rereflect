# Aspect spec — data-model-and-migration

**Parent PRD:** `../prd.md` (M1) · **Sequencing:** FIRST (everything depends on it).

## Problem slice
Add the durable per-type "auto-promotion hold" storage. No hold field exists today.

## In scope
- Add three nullable `Boolean` columns to `OrgAIConfig`
  (`services/backend-api/src/models/org_ai_config.py`):
  `sentiment_autopromote_hold`, `category_autopromote_hold`,
  `urgency_autopromote_hold` — `server_default='false'`, `default=False`. Mirror the
  existing `*_classifier_mode` column style (String(20) → here Boolean).
- Mirror the same three columns in the worker's `OrgAIConfig` definition
  (`services/worker-service/src/models/__init__.py`, the `OrgAIConfig` block — find
  where `classifier_mode` is defined and add alongside).
- One Alembic migration under `services/backend-api/alembic/versions/`. `down_revision`
  = current single head — get it via live `alembic heads` (NEVER grep version files
  for revision ids; repo memory: that has caused fork/collision incidents).
  `upgrade` adds the 3 columns with `server_default='false'`; `downgrade` drops them.

## Out of scope
- No columns on `OrgClassifierModel`/`OrgClassifierEvalRun` (hold lives on config).
- No behavior change (worker still promotes — that's the worker aspect).

## Acceptance criteria (testable)
- Backend model imports; a fresh `OrgAIConfig()` has all three holds `False`.
- Migration applies + reverts cleanly (`alembic upgrade head` / `downgrade -1`) on a
  Postgres test DB; `alembic heads` shows a single head after.
- Worker `OrgAIConfig` mirror has the three columns; any existing worker↔backend
  `OrgAIConfig` parity/characterization test still passes (add the columns to both).
- Existing `test_ai_settings*` / config tests pass unchanged (columns are additive,
  defaulted).

## Dependencies / notes
- Single-head alembic (repo memory: the "multiple heads" claim is a recurring
  static-parse artifact — always trust live `alembic heads`).
- SQLite in-memory tests: `Base.metadata.create_all` picks up the columns
  automatically; the `server_default` must not break SQLite (`sa.false()` is safe).

## Open questions / risks
- Confirm the worker reads its own `OrgAIConfig` mirror (not backend) — the worker
  aspect relies on these columns being present in the mirror.
