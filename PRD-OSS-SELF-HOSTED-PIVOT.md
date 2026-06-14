# PRD — Open-Source Self-Hosted Pivot

**Status:** Draft for review
**Author:** Engineering (with codebase analysis agents)
**Date:** 2026-06-14
**License decision:** MIT (unchanged — already in `LICENSE`)

---

## 1. Overview & Goals

Rereflect pivots from a hosted multi-tenant SaaS to a **pure open-source, self-hosted product**. We stop operating the paid service, open the source under MIT, and make the codebase clean and honest for anyone to run themselves.

Three structural changes define this pivot:

1. **Strictly BYOK (bring-your-own-key) for AI.** Remove every system/owner-paid LLM key path. If an operator/org has no key, AI features disable gracefully and the product runs on the free local VADER/keyword pipeline.
2. **No paid tiers.** Plan gating, feature limits, and Stripe are neutralized — every self-hosted instance unlocks all features, unlimited, via a single `SELF_HOSTED` flag.
3. **Tear down the hosted product.** Shut down the portal (`frontend-web`), API (`backend-api`), worker (`worker-service`), Postgres, and Redis. Keep only the marketing site (`landing-web`) on Railway for now, and ultimately move it to fully static git hosting (Cloudflare/Vercel/GitHub Pages).

### Goals
- The public repo is something we're proud to show: no hardcoded secrets, no dead "pay us" surfaces, no system-key assumptions.
- A self-hoster can `docker compose up`, optionally paste their own LLM key, and get the full product — or run it $0 with no key at all on VADER.
- Our own operating cost drops to ~$0 (only a marketing site, eventually static).
- Monetization optionality is preserved but dormant (MIT lets us run a hosted tier later if we ever want to; nothing here forecloses it).

### Non-Goals
- Building a hosted/managed paid tier now.
- Removing multi-tenancy (`organization_id`) — it stays; a self-hosted instance can still have multiple orgs.
- A real ML churn model (still the calibrated-heuristic from M4.1).
- Rewriting the analysis algorithms.

---

## 2. Locked Decisions & Principles

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | License stays **MIT** | Max adoption + trust; no algorithmic moat to protect; keeps hosted-tier option open. |
| D2 | **No system LLM key anywhere** | Honors "remove our own keys totally." Cost can never land on us. |
| D3 | No-key state = **VADER/keyword fallback**, not an error | Product must fully work with zero AI spend. Fallback already exists. |
| D4 | Plan gating neutralized via **one `SELF_HOSTED` flag**, not 60 edits | All gates funnel through ~6 functions in `plans.py` + one field in `/auth/me`. |
| D5 | **Strip Stripe**, keep DB columns dead-but-harmless | Removing Stripe code kills the dependency; migrations to drop columns add risk for zero benefit. |
| D6 | Keep **RBAC** (owner/admin/member) and `organization_id` | Self-hosted instances still need roles and multi-org. |
| D7 | `landing-web` stays on Railway during transition, static migration is a **later** phase | De-risk: prove landing is API-independent before the API disappears. |
| D8 | Pre-launch, **no real users** → teardown is low-risk | Still take a final `pg_dump` archive before deleting data. |

---

## 3. Current-State Findings (evidence base)

Condensed from three codebase analyses. File:line references carry into the workstreams below.

### 3.1 Plan/billing gating is centralized (good)
- Single source of truth: `services/backend-api/src/config/plans.py` — tiers, limits, `FEATURE_PLANS`, and decision functions `has_feature()` (L289), `plan_includes()` (L295), `get_*_limit()` (L305–360).
- ~60 backend gate call sites (`require_feature`, `check_feedback_limit`, `check_seat_limit`, inline `has_feature`/`plan_includes`) **all route through those 6 functions**.
- Frontend derives everything from `user.plan`, emitted by `/auth/me` (`auth.py:105`) and stored in `AuthContext`. Set `plan="enterprise"` there → frontend unlocks with **no component edits**.
- Stripe is self-contained: `services/stripe_service.py`, `routes/billing.py`, `worker/tasks/billing.py`, `models/subscription.py`, `models/usage.py`. Routes `/billing/plans`, `/billing/usage`, `/billing/subscription` are **Stripe-free** and survive.

### 3.2 LLM key resolution has a live system-key fallback + 6 bypass sites
- Live resolver: `worker-service/src/llm/org_resolver.py` loads `_SYSTEM_OPENAI/ANTHROPIC/GOOGLE_KEY` from env (L23–26) and uses them when no BYOK exists (L155) **and** as a runtime fallback in `FallbackChain` (`fallback.py:124–136`).
- Dead parallel resolver: `worker-service/src/llm/service.py` — referenced nowhere, delete it.
- **6 sites bypass the resolver and read `OPENAI_API_KEY` directly** — these will keep using a system key unless fixed separately:
  - `backend-api/src/api/routes/copilot_ws.py:464–475, 538–549`
  - `backend-api/src/api/routes/linear_integration.py:222` (never checks BYOK)
  - `backend-api/src/services/response_generator.py:23, 186–192`
  - `backend-api/src/services/copilot/sql_generator.py:191`
  - `backend-api/src/services/copilot/template_matcher.py:120` (embeddings — OpenAI-only)
  - `backend-api/src/services/copilot/template_saver.py:494`
- VADER fallback confirmed working with no key: `worker-service/src/tasks/analysis.py:331–380` → `_apply_keyword_analysis` (L453+) + `_compute_heuristic_churn_risk` (L522+). When `categorize_feedback` returns `None`, it already falls back.
- Budget caps (`OrgAIConfig.monthly_budget_cents`, `check_budget()`) exist only to cap **owner** spend → obsolete once there's no system key.

### 3.3 Deployment: 5 Railway services + 2 datastores; landing has ONE API dependency
- Product (tear down): `frontend-web` (portal, `app.rereflect.ca`), `backend-api` (`api.`), `worker-service` (Celery+beat), Postgres, Redis.
- Keep: `landing-web` (`rereflect.ca`), Next.js **static export** already (`next.config.ts`: `output:"export"`, `images.unoptimized:true`, `trailingSlash:true`).
- Landing's only live backend call: **changelog** — `landing-web/app/changelog/ChangelogContent.tsx` client-fetches `getPublicChangelog()` (`changelog-api.ts:30`) from `backend-api`. Fails silently (empty state) if API is gone. Everything else is static; all signup CTAs are plain `<a href={APP_URL/signup}>` links (become dead links post-teardown).
- Self-host base already exists: root `docker-compose.prod.yml` (postgres + redis + backend + worker + frontend). Gaps: no `.env.example` for prod, no bundled TLS/proxy, frontend bakes `NEXT_PUBLIC_API_URL` at build time.
- `render.yaml` is legacy (predates landing-web) — mark/delete.

---

## 4. Workstream A — Strictly BYOK (remove system key)

**Outcome:** No system/owner key anywhere. Org with a valid BYOK key → AI works on their key. Org without → VADER/keyword fallback. Budget-cap machinery removed.

### A1. Core resolver (`worker-service/src/llm/org_resolver.py`)
- Delete `_SYSTEM_*` env reads (L24–26) and `_get_system_key_for_provider` (L49–57).
- `build_fallback_chain` (L128–171): `api_key = byok_key` only; if no `byok_key` → `return (None, False)`. Remove the `system_provider` block (L163–168), pass `system_provider=None`.
- `call_llm_for_org` (L174–212): delete the `if not is_byok:` budget-check block (L201–204).
- `check_budget()` (L60–84): **delete**. `log_usage()` (L87–125): **keep** (org sees its own usage) but drop the `is_byok` budget-update branch (L117–121).

### A2. Fallback chain (`worker-service/src/llm/fallback.py`)
- Drop the system-fallback Attempt-3 branch (L124–136); simplify `FallbackChain` to primary + retry only.

### A3. Dead code
- Delete `worker-service/src/llm/service.py` entirely.

### A4. The 6 direct-env bypass sites
Introduce one shared helper `resolve_org_byok_key(provider, org_id, db) -> Optional[str]` (no system fallback). Apply to:
- `copilot_ws.py:464–475, 538–549` — if no BYOK key, return a "configure your API key" message instead of using env.
- `ai_settings.py:_get_api_key_for_provider` (L589–614) — drop the system-key block (L602–608).
- `linear_integration.py:222`, `response_generator.py:23,186–192`, `copilot/sql_generator.py:191`, `copilot/template_matcher.py:120`, `copilot/template_saver.py:494` — resolve BYOK; disable feature if absent.
- **Known limitation (document, don't fix):** copilot template-matching/SQL embeddings require OpenAI specifically. An org whose only BYOK key is Anthropic/Google won't get copilot template features. Acceptable for BYOK-only.

### A5. Pending-retry edge (`worker-service/src/tasks/analysis.py:378–380`)
- Do **not** set `llm_analysis_pending = True` when the org simply has no key (only on transient failure) — otherwise it queues perpetual retries.

### A6. Budget UI / config cleanup
- `ai_settings.py`: remove `_get_plan_budget` / `_build_budget_status` / `PLAN_BUDGET_DEFAULTS` / `BudgetStatus` from the response (L174–196, 220).
- Frontend `components/settings/AISettingsUsage.tsx`: remove budget-cap UI. Keep usage/visibility.
- `OrgAIConfig.monthly_budget_cents/budget_used_cents/budget_reset_at` and `LLMUsageLog.is_byok`: leave as dead columns (zero-risk) or drop in a follow-up migration.

### A7. BYOK entry point
- Keep per-org UI (`settings/ai/page.tsx` → `AISettingsProviders.tsx` → `POST /settings/ai/keys`, Fernet-encrypted into `OrgApiKey`) as the **canonical** key source. Drop the `require_feature("byok_keys")` gate (`ai_settings.py:436`).
- **Open question (see §9, Q1):** whether to also seed a key from env (`OPENAI_API_KEY`) for single-tenant convenience, framed explicitly as "the operator's own key."

**Tests to update:** `backend-api/tests/test_multi_model_api.py` (budget/`is_byok` assertions L191–192, 335–364, 1108).

---

## 5. Workstream B — Neutralize Plan Gating & Strip Stripe

**Outcome:** Every feature unlocked, unlimited, on self-hosted instances; Stripe dependency removed.

### B1. The `SELF_HOSTED` flag (the core — ~8 lines in `plans.py`)
Add `SELF_HOSTED = os.environ.get("SELF_HOSTED", "true").lower() == "true"` and short-circuit:
- `has_feature()` → `if SELF_HOSTED: return True`
- `plan_includes()` → `if SELF_HOSTED: return True`
- `get_feedback_limit / get_seat_limit / get_saved_views_limit / get_webhook_limit / get_automation_rule_limit` → `if SELF_HOSTED: return None` (unlimited)
- `get_webhook_header_limit` → high constant when `SELF_HOSTED`

This neutralizes **all** backend gates (they all call these functions). 402/403 billing errors disappear.

### B2. Unlock frontend + remove all billing UI (Q4: full removal)
- `auth.py:105`: when `SELF_HOSTED`, emit `plan="enterprise"`. Every `user.plan === 'free'` / `isBusiness` check and every UpgradeModal trigger passes automatically (back-stop in case any billing surface is missed).
- **Remove the billing/upgrade UI outright** (not conditional hiding):
  - Delete `app/(dashboard)/settings/billing/page.tsx` and its route; remove the Billing tab from `components/SettingsTabs.tsx`.
  - Delete `components/UpgradeModal.tsx`, `components/copilot/UpgradeCTA.tsx`, `components/TrialBanner.tsx`, `components/UsageWarning.tsx`, `components/shared/BudgetBanner.tsx` and all their usages.
  - `components/AppSidebar.tsx`: remove `proBadge` / `isBusiness`-gated nav badges (L252, L281, L323) — nav items just always show.
  - `lib/api/billing.ts`: remove `canUpgrade`/`isUpgrade`/`isDowngrade` and the checkout/portal/invoices client calls; keep only what `/billing/usage` display (if retained) needs.
  - Remove 402/403 upgrade-prompt handling in `analytics/page.tsx`, `reports/page.tsx`, `copilot/ChatArea.tsx`, etc. (those 402/403s no longer occur once B1 lands).

### B3. Strip Stripe
- No-op/remove Stripe-only billing routes: `/checkout` (L495), `/portal` (L561), `/invoices` (L674), `/sync-subscription` (L324), `/webhooks/stripe` (L711) in `routes/billing.py`.
- Keep `/billing/plans`, `/billing/usage`, `/billing/subscription` (Stripe-free; useful to show "self-hosted / unlimited").
- Remove the 5 billing Celery beat entries (`worker-service/src/celery_app.py:106–121`) and `worker-service/src/tasks/billing.py`.
- No-op the retention-addon call in `notifications.py:490–525`.
- Drop the `admin_promo` router; import-guard `stripe_service.py` so nothing crashes if `stripe` isn't installed.

### B4. Schema — drop dead columns now (Q5)
- After A6 + B3 remove all code references, write **one dedicated Alembic migration** dropping the dead billing/budget surface:
  - `Organization.stripe_customer_id`, `Organization.max_seats`
  - `Subscription` Stripe fields (`stripe_subscription_id`, `stripe_price_id`, `billing_cycle`, `trial_*`, `current_period_*`, `cancel_at_period_end`, `canceled_at`) — or drop the whole `Subscription` table if nothing reads it post-removal.
  - `UsageRecord.overage_feedback`, `UsageRecord.overage_reported_to_stripe`
  - `OrgAIConfig.monthly_budget_cents`, `budget_used_cents`, `budget_reset_at`
  - `LLMUsageLog.is_byok`
- **Keep `organization.plan`** (defaulted to `enterprise`) — dozens of `org.plan or "free"` reads depend on it.
- Ordering constraint: the migration lands **after** the code edits so no live query references a dropped column. Verify against a Postgres test DB (not just SQLite — see M4.1 lessons).

### B5. Keep untouched
- All RBAC (`require_owner`, `require_admin_or_owner`, `require_system_admin`) and frontend role logic.
- `organization_id` scoping everywhere.

---

## 6. Workstream C — Hosted Teardown & Landing-Only

**Outcome:** Product compute is shut down; `landing-web` runs standalone on Railway, proven API-independent.

### C1. Decouple landing from the API (gate — do this FIRST)
- **Remove the changelog page (Q3):** delete `landing-web/app/changelog/` (incl. `ChangelogContent.tsx`) and `landing-web/lib/changelog-api.ts`; remove any nav/footer links to `/changelog`. This eliminates the only landing→API dependency outright (no static-data file needed).
- Fix the stray relative link `components/landing/BentoFeatures.tsx:294` (`href="/signup"` → `${APP_URL}/signup` or remove).
- Redeploy landing and **verify it renders fully with the API unreachable**. This is the gate before any teardown.

### C2. Snapshot data
- Final `pg_dump` of Postgres, archived. Redis is ephemeral — skip.
- (Pre-launch with no real users, so minimal — but archive anyway.)

### C3. Take down compute
- Delete/pause in order: `frontend-web` → `worker-service` → `backend-api`. Keep `landing-web` running.

### C4. DNS / CORS cleanup
- Remove/repoint `app.` (portal) and `api.` (backend) DNS records; keep apex `rereflect.ca` → landing.
- Optionally redirect `app.rereflect.ca` → landing or a "self-host this" page so existing outreach links (`OUTREACH-TRACKING.md`, `SALES-TRACKING.md`) don't dead-end.
- CORS becomes moot once backend is gone.

### C5. Delete datastores
- Delete Postgres + Redis plugins **only after** backup verified and no service references them.

### C6. Later — full static landing
- Build `landing-web` from repo root with pnpm workspaces (it depends on `@rereflect/ui` via `workspace:*`), deploy `out/` to Cloudflare/Vercel/GitHub Pages, set `NEXT_PUBLIC_*` build env, repoint apex DNS, then pause/delete the `landing-web` Railway service.

---

## 7. Workstream D — Pre-Publish Cleanup & OSS Scaffolding

**Outcome:** Repo is safe and welcoming to make public.

### D1. Secret scrub (blocking)
- Replace `ADMIN_PASSWORD=king_1374` in root `.env.example` with `change_me` (it seeds the first admin). Confirm this password was never used on a live deploy.

### D2. License hygiene
- Confirm GSAP usage is free-core only (no paid "Club GSAP" plugins); add a GSAP attribution note (custom non-OSI license).
- Optional `NOTICE` / `THIRD_PARTY_LICENSES` listing GSAP + psycopg2 (LGPL).

### D3. OSS scaffolding
- `README.md`: replace the "Railway Deployment" section (L189–220) with a **Self-Hosting** guide.
- Add `CONTRIBUTING.md`, issue/PR templates, `.github/FUNDING.yml` (GitHub Sponsors — set-and-forget).
- Mark/delete legacy `render.yaml`.

---

## 8. Workstream E — Self-Host Deliverable

**Outcome:** A clean `docker compose up` experience.

- Keep `docker-compose.prod.yml` as the self-host entrypoint.
- Add a prod `.env.example` documenting required vars: `DATABASE_URL`, `JWT_SECRET`, `LLM_ENCRYPTION_KEY` (Fernet, for BYOK), `ADMIN_EMAIL`/`ADMIN_PASSWORD`, `CORS_ORIGINS`, `SELF_HOSTED=true`, optional `OPENAI_API_KEY` etc. (operator's own key per Q1), `ai_analysis_enabled` default.
- Document that `frontend-web` bakes `NEXT_PUBLIC_API_URL` at build time → self-hosters on a real host must rebuild with their URL.
- Note that bundled deploy has plain HTTP on :3000/:8000 (no TLS/proxy) — point to a reverse-proxy example.
- Ship sensible defaults: `SELF_HOSTED=true`, `ai_analysis_enabled=false` (so a fresh install runs on VADER, $0, no key required).

---

## 9. Decisions (Finalized)

| # | Question | **Decision** |
|---|----------|--------------|
| **Q1** | BYOK key source | **Env + UI.** Seed a key from env (`OPENAI_API_KEY` etc.) for single-tenant convenience — framed as the operator's own key, never a Rereflect key — with the per-org UI as canonical. |
| **Q2** | Repo structure | **Single public monorepo** (product + landing together); landing builds from root via pnpm workspace. |
| **Q3** | Changelog when API gone | **Remove the `/changelog` page entirely** (and its `changelog-api.ts` client). Simplest; drops the only landing→API dependency outright. |
| **Q4** | Billing/upgrade UI under self-hosted | **Remove it entirely** (not just conditionally hide). Delete the billing tab, billing page, upgrade modals/CTAs, trial/usage/budget banners, and plan-comparison helpers. Harder than hiding, but leaves no billing surface in the OSS product. |
| **Q5** | Dead billing/budget DB columns | **Drop them now** via a dedicated Alembic migration (after code stops referencing them). Keep `organization.plan` (load-bearing; defaults to enterprise). |
| **Q6** | Timing | **Cleanup → public → teardown.** Finish code cleanup (A/B/D/E), make repo public, then tear down hosted services (C). |

---

## 10. Sequencing (Phased Delivery)

| Phase | Scope | Depends on |
|-------|-------|-----------|
| **P0** | Pre-publish cleanup (D1, D2) + decide Q1–Q6 | — |
| **P1** | BYOK-only (Workstream A) + tests | Q1 |
| **P2** | Neutralize gating + strip Stripe (Workstream B) | — |
| **P3** | OSS scaffolding + self-host deliverable (D3, E) | P1, P2 |
| **P4** | Make repo public | P0–P3 |
| **P5** | Decouple landing from API (C1) + verify | Q3 |
| **P6** | Hosted teardown (C2–C5) | P5 |
| **P7** | (Later) Full static landing migration (C6) | P6 |

P1 and P2 are independent and can run in parallel. P5/P6 are ops and loosely coupled to the code phases.

---

## 11. Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| A direct-env LLM site missed → silent system-key use after "BYOK-only" ships | High | The 6 sites in §3.2/A4 are enumerated; add a CI grep test forbidding `os.environ[...OPENAI_API_KEY...]` outside the resolver helper. |
| Landing breaks when API disappears (changelog) | Medium | C1 is a hard gate — prove API-independent before teardown. |
| Stripe import crashes app after partial removal | Medium | Import-guard `stripe_service.py`; remove beat entries together with tasks. |
| `SELF_HOSTED` default wrong → a future hosted instance accidentally unlocks everything | Medium | Default `true` for OSS; if we ever host, set `SELF_HOSTED=false` explicitly in that env. |
| Data loss on teardown | Low (pre-launch) | `pg_dump` archive before deleting datastores. |
| Dead "upgrade" buttons confuse self-host users | Low | Q4 — hide billing UI under `SELF_HOSTED`. |

---

## 12. Success Criteria

- [ ] Fresh `docker compose up` with **no LLM key** → product works end-to-end on VADER/keywords; no 402/403; all features visible.
- [ ] Adding a BYOK key in the UI → AI categorization/insights/copilot work on that key; **zero** calls ever hit a Rereflect/system key (verified by grep test + no `_SYSTEM_*` refs remain).
- [ ] No Stripe network calls anywhere; app boots with `stripe` uninstalled.
- [ ] `landing-web` renders fully with the API unreachable.
- [ ] Repo public, MIT, no secrets, README self-hosting guide present.
- [ ] Hosted product services deleted; only `landing-web` remains; our recurring cost ≈ marketing site only (→ $0 once static).

---

## 13. References

- Billing/gating: `services/backend-api/src/config/plans.py` (L289, L295, L305–360), `src/api/dependencies.py`, `routes/billing.py`, `services/stripe_service.py`, `auth.py:105`.
- LLM keys: `services/worker-service/src/llm/org_resolver.py` (L23–212), `fallback.py:124–136`, `service.py` (dead), `tasks/analysis.py:331–380`; bypass sites in §3.2/A4.
- Deployment: `services/*/railway.toml`, `services/*/Dockerfile`, root `docker-compose.prod.yml`, `landing-web/next.config.ts`, `app/changelog/ChangelogContent.tsx`, `backend-api/src/api/main.py:111–121`, `render.yaml` (legacy).
- Prior analyses: license audit (MIT, scrub admin password, GSAP note), cost analysis (fixed floor ~$25–60/mo or ~$0 on Pi; LLM is the only variable cost, now fully BYOK).
