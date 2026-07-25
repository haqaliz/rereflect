# Aspect spec — staleness-model-key

**Parent PRD:** `../prd.md` (M5.4) · **Aspect 1 of 5** · **Sequencing: FIRST (foundation)**

## Problem slice & user outcome

`TemplateMatcher.find_match` skip-filters stored template vectors on `(embedding_provider,
embedding_dimension)` only — not the model. Any embedding-model change under the same provider string
at the same dimension compares old and new vectors in **incompatible spaces** and returns silent
garbage matches; auto-reseed heals only the 15 system templates. Before we introduce *any* new model
(Aspects 2 & 5), the match key must include the model so a model change can never produce a
wrong-space match. Outcome: operators can change the embedding model and never get a corrupt match —
system templates auto-re-embed, org-saved rows go dark (skipped) until overwritten.

## In-scope

- Migration: add `embedding_model String(100) nullable` to `query_template_mappings` (NULL =
  stale/pre-migration). Extend the covering index to `(embedding_provider, embedding_dimension,
  embedding_model)`.
- `TemplateSaver._create_mapping`: persist `embedding_model` (from the resolved config's selected
  model) on every write, alongside the existing `embedding_provider`/`embedding_dimension`.
- `TemplateMatcher.find_match`: add `embedding_model` to the skip-filter — a stored row is eligible
  only if `provider AND dimension AND model` all match the active embedder; NULL model rows are always
  skipped.
- `TemplateSaver.seed_system_templates`: make model-aware — re-embed the system templates when the
  active `(provider, model)` differs from what's stored (mirrors the existing provider-aware reseed);
  idempotent on an unchanged `(provider, model)`.
- Mirror the new column on the worker's `OrgAIConfig`/mapping model **only if** the worker mirrors
  `query_template_mappings` for schema parity (verify; worker has no embedding consumers).

## Out-of-scope

- Lazy re-embed of **org-saved** templates (nice-to-have #7 — skip-until-overwrite is accepted here).
- Introducing the new local model (Aspect 2) or the Ollama bump (Aspect 5).
- Changing the `0.85` threshold or ranking.

## Acceptance criteria (testable)

1. Migration applies on a DB with existing mappings; existing rows get `embedding_model = NULL`;
   `alembic upgrade head` then `downgrade -1` round-trips cleanly (single head preserved).
2. Given two stored vectors with identical `(provider, dimension)` but different `embedding_model`,
   `find_match` **excludes** the one whose model ≠ active model (unit test with a stub embedder).
3. NULL-`embedding_model` rows are always skipped by `find_match`.
4. `seed_system_templates` re-embeds all system templates when the active model changes and is a
   no-op (no re-embed) when `(provider, model)` is unchanged.
5. New writes via `TemplateSaver` persist a non-NULL `embedding_model`.
6. Characterization: the no-opt-in path (unchanged provider/model) produces byte-identical stored keys
   and match results vs pre-change (guards zero regression).

## Dependencies & sequencing

- **Blocks Aspects 2, 4, 5** (any model introduction/change is only safe once the key includes model).
- Depends on nothing. Land first.

## Open questions / risks

- Confirm whether an index already exists to ALTER vs add new (check the template-matching-local
  migration). Follow the Alembic single-head rule; run live `alembic heads`, do not grep revisions.
- Confirm the worker mapping model mirroring before touching it — avoid a needless worker migration.
