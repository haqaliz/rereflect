# PRD — Feature Batch: Local LLM · Custom AI · Public API

**Status:** Draft for review → implementation
**Date:** 2026-06-22
**Context:** First feature batch after the open-source self-hosted pivot (see `PRD-OSS-SELF-HOSTED-PIVOT.md`). All three features ship **unlocked** (no plan gating — `SELF_HOSTED`).

---

## 1. Overview & Goals

Three features, built in parallel, each chosen to fit the open-source/self-hosted/BYOK positioning:

1. **Local / Offline LLM** — run feedback analysis against a local model (Ollama or any OpenAI-compatible endpoint). Completes the "your data never leaves your infra, $0 API bill" story.
2. **Custom AI (taxonomies + health weights)** — wire user-defined categories into the analyzer for all three taxonomies (pain points, feature requests, urgency) and make the 4 health-score component weights configurable per org.
3. **Public REST API** — API-key-authenticated read endpoints + feedback ingestion + webhook management + auto OpenAPI docs, so people can build on top of Rereflect.

### Locked decisions
| # | Decision |
|---|----------|
| D1 | Local LLM provider = **Both**: a named "Ollama" preset (default base URL `http://localhost:11434/v1`) **and** a generic "OpenAI-compatible endpoint" (custom base URL + model). One shared adapter. |
| D2 | Local LLM coverage = **analysis pipeline only** (categorization, insights, churn). The AI Copilot + embeddings stay on a cloud key for now (documented limitation). |
| D3 | Custom AI = **all three taxonomies + configurable health weights** (validated to sum to 100). |
| D4 | Public API = **read + feedback ingest**: API-key auth, read endpoints (feedback/customers/health/churn/analytics), `POST` feedback ingestion, webhook management, OpenAPI docs. No full CRUD in v1. |
| D5 | Everything ships unlocked (no plan gates). |
| D6 | TDD throughout (Red→Green→Refactor); Postgres-verified migration. |

### Non-goals (v1)
- Local embeddings / fully-local AI Copilot (copilot NL→SQL + template embeddings stay cloud — accepted limitation).
- Per-org fine-tuning / custom trained models (deferred).
- Public-API full CRUD, rate-limit tiers, per-endpoint quotas (basic per-key only).
- Industry benchmarks (not viable single-tenant).

---

## 2. Current-State Findings (evidence base)

- **LLM providers** (`worker-service/src/llm/factory.py`): only `openai`/`anthropic`/`google`. Provider built from `(provider, api_key, model)`. Resolver (`org_resolver.py`) is **BYOK-only** — no key ⇒ provider disabled (falls back to VADER). Adding a local provider means a **keyless, base-URL-driven** path.
- **`OrgAIConfig`** (`models/org_ai_config.py`): `default_provider`, `model_categorization/analysis/insights`. **No `base_url`, no health weights.**
- **Health score** (`services/health_score_service.py`): hardcoded `WEIGHTS = {churn_risk:0.35, sentiment:0.25, resolution:0.25, frequency:0.15}`. Must read per-org.
- **`CustomCategory`** (`models/custom_category.py`): has `category_type` (`pain_point`/`feature_request`/`general`) + CRUD (`routes/categories.py`), but is **NOT wired into the analyzer** (worker prompt/keyword categorizer ignore it).
- **API keys**: `OrgApiKey` is **BYOK-LLM-keys only** (provider + Fernet-encrypted key). **No public-API-access key system** — greenfield.
- **Webhooks**: `webhook_endpoint`/`webhook_delivery` models + `routes/webhooks.py` exist (reuse for public API webhook management).
- **Categorizer**: LLM path = `worker-service/src/llm/` prompt (`prompts.py`/client) producing JSON; keyword fallback = `analysis-engine/src/analyzer/categorizer.py`.

---

## 3. Schema Changes (Wave 0 — done first, additive, one migration)

All additive; one Alembic migration off current head `w2x3y4z5a6b7`. Mirror `OrgAIConfig` changes in `worker-service/src/models/__init__.py`.

### 3.1 `org_ai_config` — add 5 columns
- `base_url` `VARCHAR` nullable — endpoint for local/custom providers (null for cloud).
- `health_weight_churn` `INT` default `35`
- `health_weight_sentiment` `INT` default `25`
- `health_weight_resolution` `INT` default `25`
- `health_weight_frequency` `INT` default `15`
(`default_provider` now also accepts `ollama` / `openai_compatible`; `model_*` holds the local model name.)

### 3.2 `custom_categories` — no schema change
`category_type` is a free `VARCHAR`; we simply start accepting `urgency` as a valid value (validation + UI). (Keep `general` working.)

### 3.3 New table `api_keys` (public API)
| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `organization_id` | INT FK→organizations | tenant scope |
| `name` | VARCHAR | user label |
| `key_prefix` | VARCHAR(16) | shown in UI (e.g. `rrf_a1b2c3`) |
| `key_hash` | VARCHAR | sha256 of full key; full key shown once at creation |
| `scopes` | VARCHAR | comma list: `read`, `ingest` |
| `created_by_user_id` | INT FK→users nullable | |
| `last_used_at` | TIMESTAMP nullable | |
| `revoked_at` | TIMESTAMP nullable | revoke = soft |
| `created_at` | TIMESTAMP | |

---

## 4. Feature A — Local / Offline LLM

**Outcome:** An org can select **Ollama** or a **custom OpenAI-compatible endpoint** for the analysis pipeline; it runs keyless against `base_url`. Cloud BYOK unchanged. No endpoint ⇒ VADER fallback (unchanged).

- **`worker-service/src/llm/providers/openai_compatible.py`** (new): wraps the OpenAI client with a custom `base_url`; `api_key` optional (Ollama ignores it; custom endpoints may require one — allow optional key from `OrgApiKey` if present).
- **`factory.py`**: handle `ollama` (preset base URL, overridable) and `openai_compatible` → build the compatible provider with `base_url` + `model`.
- **`org_resolver.py` `build_fallback_chain`**: if `OrgAIConfig.default_provider ∈ {ollama, openai_compatible}` → build the local provider from `base_url`+`model` **without requiring an `OrgApiKey`** (keyless). Else the existing BYOK path. Local has no system fallback (consistent with BYOK-only ethos).
- **Backend `routes/ai_settings.py`**: extend AI-settings GET/PUT to include `provider ∈ {openai,anthropic,google,ollama,openai_compatible}`, `base_url`, and model. Validate base URL when provider is local.
- **Frontend `components/settings/AISettingsProviders.tsx` + AI settings page**: add Ollama + Custom-endpoint options (base URL + model fields, no API-key field for keyless local; optional key field for custom).
- **Coverage:** analysis pipeline only — do **not** touch copilot/embeddings.
- **Tests (TDD):** compatible provider builds from base_url; resolver returns a keyless local provider when configured; analysis uses it; cloud BYOK path unchanged; invalid/missing base_url → disabled → VADER.

**Owns:** `worker-service/src/llm/{factory.py, fallback.py, org_resolver.py, providers/**}`, `backend-api/src/api/routes/ai_settings.py` (+ its schema), `frontend-web/components/settings/AISettingsProviders.tsx` + `app/(dashboard)/settings/ai/**`.

---

## 5. Feature B — Custom Taxonomies + Health Weights

**Outcome:** Custom categories influence analysis for pain points / feature requests / urgency; health-score weights are configurable per org.

### B1 — Custom taxonomies into the analyzer
- **`routes/categories.py`**: accept `category_type ∈ {pain_point, feature_request, urgency, general}`; CRUD covers all.
- **Worker `tasks/analysis.py`**: load the org's active `CustomCategory` rows and pass them to categorization.
- **`worker-service/src/llm/prompts.py`** (LLM path): inject the org's custom categories into the categorization prompt so the model can choose them.
- **`analysis-engine/src/analyzer/categorizer.py`** (keyword fallback): merge custom categories (name + optional keywords from `description`) into the keyword match sets.
- Built-in categories remain; custom **augment** them.

### B2 — Configurable health-score weights
- **New endpoints on the existing `categories.py` router** (avoids `main.py` churn): `GET/PUT /api/v1/categories/health-weights` (or a clearly-named sub-path) — read/update the 4 weights; **validate they sum to 100**; default 35/25/25/15.
- **`services/health_score_service.py`**: read weights from `OrgAIConfig` (fallback to defaults) instead of the hardcoded constant.
- **Frontend:** allow `urgency` in the categories page; add a health-weights editor (4 sliders/inputs with a live sum + validation) in settings (within the categories/AI settings area — a component, not a new top-level route, to avoid sidebar churn).
- **Tests (TDD):** custom category appears in prompt + keyword matcher; a feedback item gets a custom category; weights persist + reject non-100 sums; health score reflects changed weights.

**Owns:** `worker-service/src/llm/prompts.py` (+ client prompt builder), `worker-service/src/tasks/analysis.py`, `analysis-engine/src/analyzer/categorizer.py`, `backend-api/src/api/routes/categories.py`, `backend-api/src/services/health_score_service.py`, `frontend-web` categories page + a health-weights settings component.

---

## 6. Feature C — Public REST API (read + ingest)

**Outcome:** API-key-authenticated public API for reads + feedback ingestion + webhook management, with OpenAPI docs.

- **`api_keys` model** (Wave 0) + **key management route** `routes/api_keys.py` (JWT-auth, owner/admin): create (returns full key once), list (prefix only), revoke. Key format `rrf_<random>`; store sha256 hash + prefix.
- **Auth dependency** `verify_api_key` (new, e.g. `src/api/public/auth.py`): read `Authorization: Bearer rrf_...`, hash+lookup non-revoked key, set `last_used_at`, resolve `organization_id`, enforce scope (`read` vs `ingest`). 404/scoped to that org on everything.
- **Public router** `routes/public_api.py` mounted under `/api/public/v1`, tag `public`:
  - Reads (scope `read`): `GET /feedback` (paginated/filterable), `GET /feedback/{id}`, `GET /customers`, `GET /customers/{email}/health`, `GET /churn/customers` (at-risk), `GET /analytics/summary`.
  - Ingest (scope `ingest`): `POST /feedback` (single + small batch) → enqueues analysis like the existing internal path.
  - Webhooks (scope `read`+owner key): list/create/delete webhook endpoints (reuse `webhooks` service).
  - Reuse existing service/query logic; never bypass `organization_id` scoping.
- **OpenAPI docs:** tag-based; expose a docs view for the public surface (e.g. `/api/public/docs` via a mounted sub-app or a filtered schema). Mounted in `main.py` (C owns `main.py` edits).
- **Frontend:** API Keys settings page — create (show key once with copy), list (prefix, scopes, last used), revoke. Link to the docs.
- **Tests (TDD):** key create→hash stored, full key returned once; auth accepts valid, rejects revoked/unknown; scope enforced (read key can't ingest); every endpoint scoped to the key's org; ingest enqueues analysis.

**Owns:** `backend-api/src/api/routes/{api_keys.py, public_api.py}`, `backend-api/src/api/public/**` (auth dep), `backend-api/src/api/main.py` (router registration — **C is the only agent that edits main.py**), `backend-api/src/models/api_key.py` (Wave 0 stub), `frontend-web` API keys settings page.

---

## 7. Delivery Plan (parallel agent team)

To get true parallelism without model-file edit collisions, schema lands first, then features fan out.

| Wave | Work | Parallel? |
|---|---|---|
| **W0 — Schema** | Add `OrgAIConfig` columns (+ worker mirror), create `api_keys` model. (Models only; no migration yet — feature tests use SQLite `create_all`.) | done first (lead) |
| **W1 — Features** | **Agent A** (Local LLM), **Agent B** (Custom AI), **Agent C** (Public API) — each TDD, disjoint file ownership per §4–6. | ✅ 3 in parallel |
| **W2 — Migration** | One Alembic migration for all W0 schema (OrgAIConfig +5 cols, `api_keys` table), down_revision `w2x3y4z5a6b7`; Postgres upgrade/downgrade verified; ORM mirror synced. | after W1 |
| **W3 — Integration verify** | Lead: full backend `pytest` + worker tests + frontend `vitest` + boot + landing/app build; reconcile pre-existing baselines; commit. | after W2 |

**No-collision guarantees:** models only edited in W0; `main.py` only edited by C; A/B split the worker `llm/` dir by file (A: factory/providers/resolver/fallback; B: prompts/client); B's health-weights endpoints live on the already-registered `categories.py` router (no `main.py` edit).

A **task list** (TaskCreate) tracks every wave/feature/sub-task with status.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Keyless local provider breaks the BYOK-only invariant / system-key grep test | Local path uses `base_url`, never an env/system **key**; it's keyless by design. Keep the "no `os.environ[OPENAI_API_KEY]`" guard intact. |
| A & B both edit worker `llm/` | Split by file (factory/providers/resolver vs prompts/client); verify at W3. |
| Public API leaks cross-tenant data | Every public endpoint derives `organization_id` from the key; add an explicit test per endpoint. |
| API key stored reversibly | Store sha256 hash + prefix only; full key shown once. |
| Migration passes SQLite, fails Postgres | W2 Postgres upgrade/downgrade/upgrade verification (M4.1 lesson). |
| `main.py` merge churn | Only Agent C edits `main.py`. |

---

## 9. Success Criteria
- [ ] Configure Ollama (or custom endpoint) → feedback analysis runs against it, **zero cloud calls, no API key**; remove endpoint → VADER fallback. Cloud BYOK still works.
- [ ] Add a custom `urgency`/`pain_point`/`feature_request` category → it appears in the LLM prompt + keyword matcher and gets assigned to matching feedback.
- [ ] Change health weights (sum 100 enforced) → customer health scores recompute accordingly.
- [ ] Create an API key → call `GET /api/public/v1/feedback` with it (scoped to the org); `POST /feedback` ingests + enqueues analysis; revoked key → 401; read key → 403 on ingest. OpenAPI docs render.
- [ ] All suites green (zero new failures vs baseline); single Alembic head; Postgres migration verified.

---

## 10. References
- LLM: `worker-service/src/llm/{factory.py,org_resolver.py,providers/**,prompts.py}`, `models/org_ai_config.py` (+ worker mirror).
- Custom AI: `models/custom_category.py`, `routes/categories.py`, `services/health_score_service.py`, `analysis-engine/src/analyzer/categorizer.py`, `worker-service/src/tasks/analysis.py`.
- Public API: `models/org_api_key.py` (BYOK — do not reuse for public keys), `routes/webhooks.py`, `api/main.py`.
- Pivot context: `PRD-OSS-SELF-HOSTED-PIVOT.md`, `memory/rereflect-oss-pivot.md`.
