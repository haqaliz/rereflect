# Aspect spec — data-model

**Parent PRD:** `../prd.md` (M3, M4) · **Slug:** `data-model` · **Sequencing:** wave 1

## Problem slice & outcome

Every other aspect (harvester, review queue, settings cards, readiness) needs a place to put a
suggestion and a per-org opt-in flag to read. This aspect owns **the single Alembic revision and
all model definitions** for the feature, and nothing else — no routes, no tasks, no fetch logic.

Outcome: `churn_label_suggestions` exists in both services' metadata, `churn_labels_enabled` /
`churn_label_config` exist on both CRM integration rows defaulting to **off**, and `alembic
upgrade head` is unambiguous.

> **Finding that overrides the PRD (verified, do not skip).** PRD R6 and Technical Considerations
> state the graph has **two heads** (`c4d5e6f7a8b9`, `e6f7a8b9c0d1`) and that `upgrade head` is
> ambiguous. **This is false in this worktree.** `alembic heads` returns **exactly one head:
> `e6f7a8b9c0d1`**. `c4d5e6f7a8b9` is not a head — it is an ancestor via
> `c4d5e6f7a8b9 → d5e6f7a8b9c0 → f1a2b3c4d5e6 → … → 3e26b38cbd15 → e6f7a8b9c0d1`
> (`d5e6f7a8b9c0_add_asana_status_sync_columns.py:24` sets `down_revision = "c4d5e6f7a8b9"`).
> The PRD reached its conclusion the same way `c4d5e6f7a8b9`'s own docstring
> (`c4d5e6f7a8b9_add_jira_status_sync_columns.py:9-17`) warns a previous plan did: by reading a
> *plan's* assumed head instead of running `alembic heads`. **No merge revision is needed**;
> inventing one would fabricate the fork it claims to fix. See item 1.

## In scope

1. **ONE Alembic revision** `alembic/versions/<rev>_add_churn_label_suggestions.py`, with
   `down_revision = "e6f7a8b9c0d1"` — the **single verified current head**. The docstring MUST
   record: head count re-verified with `alembic heads` immediately before authoring, the observed
   result (one head), and that PRD R6's two-head claim was checked and found stale — mirroring the
   honesty precedent at `c4d5e6f7a8b9_add_jira_status_sync_columns.py:9-17`. If `alembic heads`
   returns >1 at authoring time, **stop and re-plan**; do not silently pick one.
2. `op.create_table("churn_label_suggestions", ...)` — exact columns per PRD "Data Model"
   (`prd.md:290-309`): `id` PK; `organization_id` INT NOT NULL FK `organizations.id` ON DELETE
   CASCADE; `customer_email` String(255) NOT NULL; `provider` String(50) NOT NULL;
   `external_opportunity_id` String(64) NOT NULL; `suggested_churned_at` DateTime NOT NULL;
   `evidence` JSON NULL; `status` String(20) NOT NULL `server_default="pending"`;
   `reviewed_by_user_id` INT NULL FK `users.id` ON DELETE SET NULL; `reviewed_at` DateTime NULL;
   `churn_event_id` INT NULL FK `customer_churn_events.id` ON DELETE SET NULL;
   `created_at`/`updated_at` DateTime NOT NULL.
3. Constraints/indexes in the same revision:
   `UniqueConstraint("organization_id","provider","external_opportunity_id",
   name="uq_churn_label_suggestion_org_provider_ext")` (the idempotent-re-harvest guarantee,
   `prd.md:207-209`); `Index("ix_churn_label_suggestion_org_status","organization_id","status")`;
   `Index("ix_churn_label_suggestion_org_email","organization_id","customer_email")`.
4. Same revision adds to **both** `hubspot_integrations` and `salesforce_integrations`:
   `sa.Column("churn_labels_enabled", sa.Boolean(), nullable=False, server_default=sa.false())`
   and `sa.Column("churn_label_config", sa.JSON(), nullable=True)` — byte-for-byte the opt-in
   shape of `c4d5e6f7a8b9_add_jira_status_sync_columns.py:35-47`.
5. `downgrade()` reverses exactly: drop the 4 columns (2 per table), then `drop_table`.
6. **Backend model** `services/backend-api/src/models/churn_label_suggestion.py` —
   `class ChurnLabelSuggestion(Base)`, real `ForeignKey(...)` + `relationship("Organization")` /
   `relationship("User", foreign_keys=[reviewed_by_user_id])`, styled on
   `models/churn_event.py:46-96`. Registered wherever `CustomerChurnEvent` is (model package
   import surface) so `Base.metadata` sees it.
7. **Module-level status enum list** in that model file, above the class, mirroring
   `models/churn_event.py:30-43` exactly:
   `CHURN_SUGGESTION_STATUSES = ["pending", "confirmed", "rejected"]` — plain Python list,
   validated in Pydantic by the routes aspect, **no DB CHECK constraint** (house convention;
   `understanding.md` Finding 6 confirms `CHURN_REASON_CODES` is Pydantic-only).
   Add `# status: one of CHURN_SUGGESTION_STATUSES` on the column, per `churn_event.py:60,72`.
8. **Worker mirror**, appended to `services/worker-service/src/models/__init__.py` — **no FK, no
   `relationship()`**, same column names/types/order, same `__table_args__` names; copy the
   `CustomerChurnEvent` mirror at `worker-service/src/models/__init__.py:703-723` (note
   `organization_id = Column(Integer, nullable=False)` — bare, no FK). Also add
   `churn_labels_enabled` + `churn_label_config` to the worker's `HubSpotIntegration` (`:1031`)
   and `SalesforceIntegration` (`:1070`) mirrors.
9. **Column-parity tests** in `services/worker-service/tests/` — copy the `sys.path`/`sys.modules`
   swap technique from `test_hubspot_sync.py:136-177` (CrmEnrichment) verbatim; the
   HubSpotIntegration variant at `:179+` is the second precedent. Three parity tests:
   `ChurnLabelSuggestion`, `HubSpotIntegration`, `SalesforceIntegration`.
10. **Migration round-trip test** in `services/backend-api/tests/`, following
    `test_jira_status_sync_migration.py` (real SQLite `db` fixture, model-level asserts,
    defaults + settability).

## Out of scope

- Any **merge revision** — the graph has one head (see Finding above); a merge would be fiction.
- Fixing the two shipped `source`-filter/dedup inconsistencies (`understanding.md` Findings 3, 5)
  and the readiness count (PRD M6) — other aspects / explicitly out of scope.
- Pydantic schemas, routes, harvester, adapters, backfill task, UI, `evidence` payload shape.
- New `reason_code` values (`prd.md:190`, resolved: none) and any `auto_suggested` write path.
- Backfilling/seeding rows; touching `customer_churn_events`' own columns or constraints.

## Acceptance criteria (testable)

- `assert len(alembic heads) == 1` before authoring **and** after the revision is added (the new
  revision is the sole head; `down_revision == "e6f7a8b9c0d1"`).
- `alembic upgrade head` then `alembic downgrade -1` runs clean and returns the schema to its
  prior state (no residual table/columns) — round-trip, per `test_jira_status_sync_migration.py`.
- `assert "churn_label_suggestions" in Base.metadata.tables` in **both** services.
- `assert HubSpotIntegration(...).churn_labels_enabled is False` on a freshly committed row with
  the field unset; same for `SalesforceIntegration` (mirrors
  `test_jira_status_sync_migration.py:17-33`).
- `assert integration.churn_label_config == {"renewal_pipelines": ["default"]}` after commit +
  refresh — JSON dict round-trips (mirrors `:35-53`).
- `assert suggestion.status == "pending"` on a row inserted without an explicit status
  (server_default applies).
- Inserting a second row with the same `(organization_id, provider, external_opportunity_id)`
  raises `IntegrityError`; the same triple under a **different** `organization_id` commits fine.
- `assert CHURN_SUGGESTION_STATUSES == ["pending", "confirmed", "rejected"]` and no DB CHECK
  exists on `status` — an out-of-list value inserts at the ORM layer without error.
- `assert worker_cols == backend_cols` for `ChurnLabelSuggestion`, `HubSpotIntegration`, and
  `SalesforceIntegration` (parity tests, `test_hubspot_sync.py:173-177` assert shape).
- `assert not [c for c in WorkerChurnLabelSuggestion.__table__.columns if c.foreign_keys]` —
  worker mirror carries no FKs.
- Existing suites stay green — in particular `test_hubspot_sync.py`, `test_hubspot_model.py`,
  `test_salesforce_model.py` (scope the run; per repo notes the full suite has a pre-existing
  segfault in `test_report_ws.py`).

## Dependencies & sequencing

- **Wave 1 — blocks everything.** No aspect can land before this one: harvester/adapters need the
  table + mirror, routes need the model + status list, settings cards need the two columns,
  readiness needs `status='pending'` to count.
- Depends only on shipped state: `organizations`, `users`, `customer_churn_events`,
  `hubspot_integrations`, `salesforce_integrations` all exist at head `e6f7a8b9c0d1`.
- Hand off to routes: `CHURN_SUGGESTION_STATUSES` is the single source of truth for the Pydantic
  literal — routes import it, never redeclare it.

## Risks

- **R-DM1 — the PRD's head claim is stale (already materialized).** Following `prd.md:262-265`
  literally would add an unnecessary merge revision. **Mitigation:** re-run `alembic heads` at
  authoring time and trust the tool, not the plan — the failure mode `c4d5e6f7a8b9:9-17`
  documents. Record the verification in the docstring.
- **R-DM2 — a second head appears before merge.** Another branch could land a revision while this
  one is open, making `down_revision = "e6f7a8b9c0d1"` fork the graph. **Mitigation:** re-verify
  `alembic heads` immediately before merge, not just at authoring; rebase the `down_revision`.
- **R-DM3 — mirror drift.** The worker mirror silently diverges from the backend model.
  **Mitigation:** the three parity tests are the guard, and they fail loudly with a column diff.
- **R-DM4 — `server_default` dialect skew.** `hubspot_integration.py:39` uses the string
  `server_default="false"` while `c4d5e6f7a8b9:41` uses `sa.false()`. **Mitigation:** use
  `sa.false()` in the migration (portable) and match the neighbouring model's existing string
  style in the model file; assert the Python-side default is `False` in tests rather than
  comparing DDL text.
- **R-DM5 — `evidence` JSON is unbounded.** A large CRM payload per suggestion. **Mitigation:**
  out of scope here (the harvester aspect owns what it writes); the column is nullable JSON and
  the shape is that aspect's contract.
- **R-DM6 — FK to `customer_churn_events` couples suggestion lifetime to label lifetime.**
  `ON DELETE SET NULL` (per PRD) means deleting a churn event orphans provenance rather than the
  row. Accepted: matches `prd.md:302`; the suggestion keeps `status='confirmed'`.
