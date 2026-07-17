# Implementation Report — config-model-and-crud (SAML SSO, aspect 2/6)

**Branch:** `feat/saml-sso` · **Worktree:** `.claude/worktrees/feat-saml-sso`
**Commits:** `23d39ae` (model/route/guard/status/tests), `ef53794` (migrations)
**Base:** `n8o9p0q1r2s3` (confirmed sole live head before authoring)

## Summary

Implemented the SAML config model + CRUD + cross-provider single-enabled guard exactly per
`plan_20260717.md`, mirroring the shipped OIDC aspect. Strict TDD followed throughout: full
`tests/test_saml_config.py` written first (RED, confirmed failing for the right reason —
`ModuleNotFoundError` on `src.models.saml_config` / `src.api.routes.saml_config`), then
implementation added phase by phase until GREEN.

## Files changed

**New:**
- `services/backend-api/src/models/saml_config.py` — `SamlConfig` → `saml_configs`
- `services/backend-api/src/api/routes/saml_config.py` — CRUD router `/api/v1/settings/saml`
- `services/backend-api/src/api/routes/_sso_guard.py` — shared `assert_no_other_provider_enabled`
- `services/backend-api/alembic/versions/o9p0q1r2s3t4_add_saml_config_table.py`
- `services/backend-api/alembic/versions/p0q1r2s3t4u5_add_user_saml_subject.py`
- `services/backend-api/tests/test_saml_config.py` — 33 tests

**Edited:**
- `services/backend-api/src/models/__init__.py` — export `SamlConfig`
- `services/backend-api/src/models/user.py` — `saml_subject` column; `auth_provider` comment
- `services/backend-api/src/api/main.py` — register `saml_config_router`
- `services/backend-api/src/api/routes/auth.py` — `GET /api/v1/auth/saml/status` probe
- `services/backend-api/src/api/routes/oidc_config.py` — **+2 lines only** (see below)

## The OIDC edit — human-review checkpoint

`git diff services/backend-api/src/api/routes/oidc_config.py` (full diff, verified minimal):

```diff
+from src.api.routes._sso_guard import assert_no_other_provider_enabled
 from src.database.session import get_db
 from src.models.oidc_config import OidcConfig
 from src.models.organization import Organization
@@
     if payload.enabled:
         _assert_no_other_enabled(db, current_org.id)
+        assert_no_other_provider_enabled(db, enabling="oidc")
```

Exactly 1 import + 1 call, `+2 -0`. `_assert_no_other_enabled` and its 422 detail string
(`"Another OIDC config is already enabled; only one may be active per deployment."`) are
byte-identical to the shipped version — asserted directly in
`TestOidcCrossCheck::test_oidc_still_422s_a_second_oidc`.

## Test commands + output

```bash
cd services/backend-api && source venv/bin/activate
python -m pytest tests/test_saml_config.py tests/test_oidc_config.py tests/test_auth.py -q
```
```
====================== 78 passed, 373 warnings in 26.77s =======================
```

Breakdown: 33 new SAML tests (model/route/status/cross-provider-guard/characterization) +
24 OIDC regression tests (unchanged, all green) + 21 general auth regression tests (unchanged,
all green — confirms the new `saml/status` route and import additions to `auth.py` didn't
disturb existing auth routes).

RED phase (pre-implementation) was captured and confirmed to fail for the right reason:
33 errors, all `ModuleNotFoundError: No module named 'src.models.saml_config'` /
`'src.api.routes.saml_config'` — i.e. the test file was collected correctly and failed only
because the production code didn't exist yet.

Note on tooling: per the task brief, `rtk`'s pytest wrapper misreports output as
"No tests collected" even when invoked as plain `python -m pytest ...` in this environment
(the harness appears to intercept `pytest` invocations transparently). Redirecting stdout/stderr
to a scratch log file and reading it back worked around this and showed accurate pytest output
in every case above.

## Cross-provider matrix (§7.3 of the plan) — all verified

| Enabled now | Action | Expected | Test |
|---|---|---|---|
| nothing | enable SAML | 200 | `test_saml_can_enable_when_no_oidc_enabled` |
| SAML (own org) | re-PUT SAML enabled | 200 | `test_reenabling_own_saml_config_is_allowed` |
| SAML (other org) | enable SAML (this org) | 422 | `test_enabling_saml_while_other_saml_enabled_returns_422` |
| OIDC (any org) | enable SAML | 422 | `test_enabling_saml_while_oidc_enabled_returns_422` |
| SAML (any org) | enable OIDC | 422 | `test_enabling_oidc_while_saml_enabled_returns_422` |
| OIDC (other org) | enable OIDC (this org) | 422, byte-stable message | `test_oidc_still_422s_a_second_oidc` |
| OIDC (own org) | re-PUT OIDC enabled | 200 | `test_oidc_reenable_own_still_allowed` |

## Migration round-trip

`alembic heads` before authoring: `n8o9p0q1r2s3 (head)` — matched the plan's inference, confirmed live.

The test DB (`conftest.py`) uses `Base.metadata.create_all` and doesn't exercise Alembic, so the
round-trip was proven explicitly on a scratch SQLite DB. **Deviation from the plan's literal
recipe:** a plain `alembic upgrade head` from an empty DB fails partway through the *pre-existing*
migration history — unrelated to this aspect — at `d4e5f6g7h8i9` (`add_feedback_sources`, an old
migration doing `op.create_foreign_key` on SQLite, which raises
`NotImplementedError: No support for ALTER of constraints in SQLite dialect`). This is a
long-standing gap between this repo's SQLite-based migration testing and its actual Postgres
production target — not something introduced or touched by this aspect. Confirmed by tracing the
failure to a migration with no relation to OIDC/SAML/users.

**Workaround used to isolate and prove *this aspect's* migrations specifically:**
1. `Base.metadata.create_all(bind=engine)` on a fresh scratch SQLite DB (builds the *current*
   full schema, including `saml_configs` and `users.saml_subject`, via the ORM models).
2. Manually dropped `saml_configs`, `ix_users_saml_subject`, and `users.saml_subject` to
   reconstruct the schema as of `n8o9p0q1r2s3` (pre-this-aspect).
3. `alembic stamp n8o9p0q1r2s3` — marks that revision as applied without replaying the (broken)
   full history.
4. `alembic upgrade head` → applied `o9p0q1r2s3t4` then `p0q1r2s3t4u5` cleanly.
5. Inspected via `sqlite3`: `saml_configs` table present with the exact column set/types/defaults
   from the model (`CREATE TABLE saml_configs (id INTEGER NOT NULL, organization_id INTEGER NOT
   NULL, idp_entity_id VARCHAR(255) NOT NULL, idp_sso_url VARCHAR(512) NOT NULL, idp_x509_cert
   TEXT NOT NULL, email_attribute VARCHAR(255), enabled BOOLEAN DEFAULT (0) NOT NULL,
   allowed_email_domains JSON, button_label VARCHAR(255) DEFAULT 'Sign in with SSO' NOT NULL,
   created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, PRIMARY KEY (id), FOREIGN
   KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, CONSTRAINT
   uq_saml_configs_org_id UNIQUE (organization_id))`); `users.saml_subject` present;
   `ix_users_saml_subject` present.
6. `alembic downgrade n8o9p0q1r2s3` → both revisions reversed cleanly: `saml_configs` table gone,
   `users.saml_subject` column gone, `ix_users_saml_subject` gone. No errors.
7. `alembic upgrade head` (second time) → re-applied idempotently, no errors.
8. `alembic heads` → `p0q1r2s3t4u5 (head)` (sole head, confirmed).
9. Scratch DB file removed.

**Result: round-trip clean in both directions**, isolated from the unrelated pre-existing
SQLite-history issue. On Postgres (production target) the full history replay issue does not
apply (partial/constraint ALTER support differs), so this is a test-tooling-only finding, not a
correctness issue in the new migrations. Flagging as a known repo gap, not a blocker for this
aspect.

## Confirmation checklist (plan §7.4 branch-green definition)

- [x] `pytest tests/test_saml_config.py tests/test_oidc_config.py -v` all green (78/78 combined
      with `test_auth.py` also included as an extra regression check)
- [x] Alembic round-trip clean (with the scratch-DB isolation workaround documented above)
- [x] `git diff src/api/routes/oidc_config.py` is exactly the 2-line addition
- [x] Cross-provider matrix (§7.3) fully covered by tests, all 7 rows passing
- [x] OIDC characterization tests prove byte-stable same-provider behavior/message

## Scope discipline

No provider/assertion validation, no ACS/login routes, no replay store, no frontend, no
`python3-saml`/`xmlsec` usage, no Dockerfile edits — all out of scope for this aspect and not
touched. `organization_id` scoping validated on every SAML CRUD route
(`test_other_org_cannot_see_this_org_config`).
