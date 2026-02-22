# PRD: M2.1 — Multi-Model Support

**Milestone**: M2.1 (Q2 2026)
**Timeline**: 1 week
**Status**: Draft
**Last Updated**: 2026-02-22
**Depends On**: M1.4 (Churn Prediction Accuracy) — COMPLETE

---

## Overview

Replace the hardcoded OpenAI integration with a provider-agnostic LLM abstraction layer using the factory method pattern. Support OpenAI, Anthropic, and Google as providers. Enable per-org model selection, BYOK key management, automatic fallback chains, usage tracking with cost budgets, and a revamped AI settings UI.

---

## Goals

1. **Provider flexibility**: Orgs choose their preferred LLM provider and model per task type
2. **BYOK key management**: Pro+ orgs bring their own API keys with encrypted storage
3. **Cost control**: Hard monthly budget limits on our system key with usage dashboard
4. **Reliability**: Automatic fallback chain with retry and provider-level resilience
5. **Transparency**: Full token/cost tracking, model audit trail, fallback notifications

---

## Non-Goals (Deferred)

- Streaming responses (interface defined in M2.1, implemented in M2.2 for copilot)
- Model comparison / A-B testing (Q4)
- Fine-tuned per-org models (Q4 M4.2)
- Local/Ollama self-hosted models (future)

---

## Architecture

### Factory Method Pattern

```
worker-service/src/llm/
├── __init__.py
├── types.py          # LLMRequest, LLMResponse, ProviderConfig dataclasses
├── factory.py        # LLMProviderFactory.create(provider, api_key, model) -> LLMProvider
├── base.py           # Abstract LLMProvider base class
├── fallback.py       # FallbackChain orchestrator (retry + fallback logic)
├── providers/
│   ├── __init__.py
│   ├── openai.py     # OpenAIProvider (chat.completions.create)
│   ├── anthropic.py  # AnthropicProvider (messages.create)
│   └── google.py     # GoogleProvider (generate_content)
└── pricing.py        # Cost estimation utilities
```

### Abstract Base Class

```python
class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 500,
        json_mode: bool = True,
    ) -> LLMResponse:
        """Synchronous completion. Returns structured response."""
        ...

    async def stream(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 500,
    ) -> AsyncIterator[str]:
        """Streaming completion. M2.2 implementation."""
        raise NotImplementedError("Streaming not yet implemented")

    @abstractmethod
    def validate_key(self) -> tuple[bool, str]:
        """Validate API key. Returns (success, error_message)."""
        ...
```

### LLMResponse Dataclass

```python
@dataclass
class LLMResponse:
    content: str                    # Raw text response
    provider: str                   # "openai" | "anthropic" | "google"
    model: str                      # "gpt-4o-mini", "claude-haiku-4-5", etc.
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_cents: float     # Calculated from pricing table
    latency_ms: int                 # Wall clock time
    was_fallback: bool              # True if this was a fallback call
    fallback_reason: str | None     # "rate_limit", "server_error", "timeout"
```

### Factory Method

```python
class LLMProviderFactory:
    @staticmethod
    def create(provider: str, api_key: str, model: str) -> LLMProvider:
        match provider:
            case "openai":
                return OpenAIProvider(api_key=api_key, model=model)
            case "anthropic":
                return AnthropicProvider(api_key=api_key, model=model)
            case "google":
                return GoogleProvider(api_key=api_key, model=model)
            case _:
                raise ValueError(f"Unknown provider: {provider}")
```

### Fallback Chain

```python
class FallbackChain:
    """
    Orchestrates retry + provider fallback.

    Strategy:
    1. Try primary provider (org's chosen provider/model)
    2. On transient failure (429, 5xx, timeout): retry once with 2s backoff
    3. If retry fails: fall back to system OpenAI key with default model
    4. Auth errors (401, 403) are NOT retried or fallen back — config problem

    BYOK orgs: primary = their key → fallback = our system key
    System key orgs: primary = system key → no further fallback
    """

    def complete(self, request: LLMRequest, org_config: OrgAIConfig) -> LLMResponse:
        ...
```

### Provider-Specific JSON Handling

| Provider | JSON Mode | Strategy |
|---|---|---|
| **OpenAI** | `response_format={"type": "json_object"}` | Native JSON mode |
| **Anthropic** | Not supported | Prompt instruction "Return ONLY valid JSON" + strip ```json fences from response |
| **Google** | `response_mime_type="application/json"` | Native JSON mode |

### System Message Handling

| Provider | System Message |
|---|---|
| **OpenAI** | `{"role": "system", "content": "..."}` in messages array |
| **Anthropic** | Separate `system` parameter on `messages.create()` |
| **Google** | `system_instruction` parameter on model init |

Each provider adapter normalizes our internal message format to the provider-specific API.

---

## Database Schema

### New Tables

#### `org_api_keys`
Stores encrypted BYOK API keys per provider per org.

```sql
CREATE TABLE org_api_keys (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,          -- "openai", "anthropic", "google"
    encrypted_key TEXT NOT NULL,             -- Fernet-encrypted API key
    key_hint VARCHAR(8),                    -- Last 4 chars for display: "...abc1"
    is_valid BOOLEAN DEFAULT TRUE,          -- Set false on persistent auth errors
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, provider)
);
CREATE INDEX idx_org_api_keys_org ON org_api_keys(organization_id);
```

#### `org_ai_config`
Per-org AI configuration: default provider, model per task type, budget.

```sql
CREATE TABLE org_ai_config (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
    default_provider VARCHAR(20) DEFAULT 'openai',
    model_categorization VARCHAR(50) DEFAULT 'gpt-4o-mini',
    model_analysis VARCHAR(50) DEFAULT 'gpt-4o-mini',
    model_insights VARCHAR(50) DEFAULT 'gpt-4o-mini',
    monthly_budget_cents INTEGER,            -- NULL = use plan default
    budget_used_cents INTEGER DEFAULT 0,
    budget_reset_at TIMESTAMP,               -- Next reset date (1st of month)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### `llm_usage_logs`
Per-request usage tracking for cost attribution and the usage dashboard.

```sql
CREATE TABLE llm_usage_logs (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,
    model VARCHAR(50) NOT NULL,
    task_type VARCHAR(30) NOT NULL,          -- "categorization", "analysis", "insights", "churn_analysis"
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    estimated_cost_cents FLOAT NOT NULL,
    latency_ms INTEGER,
    was_fallback BOOLEAN DEFAULT FALSE,
    fallback_reason VARCHAR(30),
    is_byok BOOLEAN DEFAULT FALSE,           -- True if org's own key was used
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_llm_usage_org_date ON llm_usage_logs(organization_id, created_at);
CREATE INDEX idx_llm_usage_org_month ON llm_usage_logs(organization_id, DATE_TRUNC('month', created_at));
```

#### `llm_model_prices`
System-wide model pricing table managed by system admins.

```sql
CREATE TABLE llm_model_prices (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(20) NOT NULL,
    model_id VARCHAR(50) NOT NULL,           -- "gpt-4o-mini", "claude-haiku-4-5", etc.
    display_name VARCHAR(100) NOT NULL,      -- "GPT-4o Mini", "Claude Haiku 4.5"
    input_price_per_1m_tokens FLOAT NOT NULL,   -- Price per 1M input tokens (dollars)
    output_price_per_1m_tokens FLOAT NOT NULL,  -- Price per 1M output tokens (dollars)
    context_window INTEGER,                  -- Max context tokens
    max_output_tokens INTEGER,               -- Max output tokens
    supports_json_mode BOOLEAN DEFAULT FALSE,
    tier VARCHAR(10) NOT NULL,               -- "cheap", "mid", "premium"
    min_plan VARCHAR(20) DEFAULT 'free',     -- Minimum plan to use this model
    is_available BOOLEAN DEFAULT TRUE,       -- Set false to hide deprecated models
    is_deprecated BOOLEAN DEFAULT FALSE,     -- Model deprecated by provider
    replacement_model_id VARCHAR(50),        -- Auto-switch target when deprecated
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(provider, model_id)
);
```

### Modified Tables

#### `feedback_items` — Add columns
```sql
ALTER TABLE feedback_items ADD COLUMN llm_provider VARCHAR(20);
ALTER TABLE feedback_items ADD COLUMN llm_model VARCHAR(50);
```

#### `customer_health_scores` — Add columns
```sql
ALTER TABLE customer_health_scores ADD COLUMN llm_provider VARCHAR(20);
ALTER TABLE customer_health_scores ADD COLUMN llm_model VARCHAR(50);
```

#### `organizations` — Drop column (after migration)
```sql
ALTER TABLE organizations DROP COLUMN openai_api_key;
```

### Data Migration

1. For each org with `openai_api_key IS NOT NULL`:
   - Encrypt the key with Fernet
   - Insert into `org_api_keys` (provider="openai", key_hint=last 4 chars)
2. Create default `org_ai_config` row for every org
3. Drop `organizations.openai_api_key` column

---

## Plan Gating

### Model Access by Plan

| Plan | Cheap Tier | Mid Tier | Premium Tier | BYOK |
|------|-----------|----------|-------------|------|
| **Free** | gpt-4o-mini, haiku, flash | — | — | — |
| **Pro** | All cheap | gpt-4o, sonnet, gemini-pro | — | Yes (any model) |
| **Business** | All cheap | All mid | All premium | Yes (any model) |
| **Enterprise** | All | All | All | Yes (any model) |

### Initial Model Registry (Seed Data)

| Provider | Model ID | Display Name | Tier | Min Plan | Input $/1M | Output $/1M |
|---|---|---|---|---|---|---|
| openai | gpt-4o-mini | GPT-4o Mini | cheap | free | $0.15 | $0.60 |
| openai | gpt-4o | GPT-4o | mid | pro | $2.50 | $10.00 |
| openai | gpt-4-turbo | GPT-4 Turbo | premium | business | $10.00 | $30.00 |
| anthropic | claude-haiku-4-5 | Claude Haiku 4.5 | cheap | free | $0.80 | $4.00 |
| anthropic | claude-sonnet-4-6 | Claude Sonnet 4.6 | mid | pro | $3.00 | $15.00 |
| anthropic | claude-opus-4-6 | Claude Opus 4.6 | premium | business | $15.00 | $75.00 |
| google | gemini-2.0-flash | Gemini 2.0 Flash | cheap | free | $0.075 | $0.30 |
| google | gemini-2.0-pro | Gemini 2.0 Pro | mid | pro | $1.25 | $5.00 |

*Prices are approximate and managed via the admin page.*

### Monthly AI Budget (System Key Only)

| Plan | Monthly Budget | BYOK |
|---|---|---|
| Free | $1 | — |
| Pro | $10 | Unlimited |
| Business | $50 | Unlimited |
| Enterprise | Custom | Unlimited |

BYOK calls do not count against the budget.

### Budget Lifecycle

1. Budget resets on the 1st of each month at 00:00 UTC
2. Each LLM call on system key: estimate cost → check budget → execute → deduct
3. When budget exceeded:
   - New feedback items marked as `pending_analysis` (queued)
   - Scheduled tasks (insights, churn analysis) skip and log
   - UI shows budget warning banner with Upgrade/BYOK CTAs
   - Re-analyze buttons disabled with tooltip "AI budget limit reached"
4. On budget reset (1st of month):
   - Reset `budget_used_cents` to 0
   - Trigger batch analysis of queued `pending_analysis` items

---

## API Endpoints

### AI Settings (Updated)

```
GET    /api/v1/settings/ai                   → AISettingsResponse (all roles, read-only for members)
PATCH  /api/v1/settings/ai                   → AISettingsResponse (admin/owner)
```

**AISettingsResponse** (updated):
```json
{
  "ai_analysis_enabled": true,
  "default_provider": "openai",
  "models": {
    "categorization": "gpt-4o-mini",
    "analysis": "gpt-4o-mini",
    "insights": "gpt-4o-mini"
  },
  "budget": {
    "monthly_limit_cents": 1000,
    "used_cents": 723,
    "resets_at": "2026-03-01T00:00:00Z",
    "is_exceeded": false
  }
}
```

**AISettingsUpdate**:
```json
{
  "ai_analysis_enabled": true,
  "default_provider": "anthropic",
  "model_categorization": "claude-haiku-4-5",
  "model_analysis": "claude-sonnet-4-6",
  "model_insights": "claude-haiku-4-5"
}
```

### API Keys (New)

```
GET    /api/v1/settings/ai/keys              → list of {provider, key_hint, is_valid, created_at}
POST   /api/v1/settings/ai/keys              → add key {provider, api_key} (owner only)
DELETE /api/v1/settings/ai/keys/{provider}    → remove key (owner only)
POST   /api/v1/settings/ai/keys/validate     → validate key {provider, api_key} → {valid, error}
```

Rate limits: 10 key saves/hour per org.

### Model Testing (New)

```
POST   /api/v1/settings/ai/test-model        → {provider, model, result, tokens, cost, latency_ms}
```

Body: `{"provider": "anthropic", "model": "claude-sonnet-4-6"}`

Runs a canned sample feedback through the specified model and returns the analysis result. Rate limit: 5 calls/minute per org.

### Available Models (New)

```
GET    /api/v1/settings/ai/models             → list of available models for org's plan
```

Returns models from `llm_model_prices` filtered by:
- `is_available = true`
- `min_plan` <= org's current plan
- Provider is available (system key exists OR org has BYOK key for that provider)

### Usage (New)

```
GET    /api/v1/settings/ai/usage              → monthly usage summary
GET    /api/v1/settings/ai/usage/daily        → daily breakdown (for chart)
```

**Usage Summary Response**:
```json
{
  "month": "2026-02",
  "total_tokens": 125400,
  "total_requests": 342,
  "estimated_cost_cents": 123,
  "by_provider": [
    {"provider": "openai", "tokens": 85000, "requests": 250, "cost_cents": 90},
    {"provider": "anthropic", "tokens": 40400, "requests": 92, "cost_cents": 33}
  ],
  "fallback_count": 3
}
```

**Daily Breakdown Response**:
```json
{
  "days": [
    {"date": "2026-02-01", "tokens": 5200, "requests": 15, "cost_cents": 5},
    ...
  ]
}
```

### System Admin: Model Prices (New)

```
GET    /api/v1/admin/ai-models                → list all models with prices
PATCH  /api/v1/admin/ai-models/{id}           → update price/availability
POST   /api/v1/admin/ai-models/sync-prices    → fetch latest prices from provider APIs
```

System admin only (`is_system_admin = true`).

---

## Frontend

### Settings > AI Page (Restructured)

Restructure `/settings/ai` into 4 tabs:

#### Tab 1: General
- AI analysis toggle (existing)
- Budget status progress bar: "$7.20 / $10.00 used this month (resets Mar 1)"
- Budget exceeded banner (when applicable)

#### Tab 2: Providers
- **Provider cards**: OpenAI, Anthropic, Google — each with:
  - Provider logo (SVG)
  - Connection status: "System key" (default) or "BYOK: sk-••••abc1" with Remove button
  - "Add Key" button → input with "Save" (test call on save, show provider error on failure)
  - Show last 4 chars of key masked
- **Model Selection per Task**:
  - Categorization: dropdown (filtered by plan + available providers)
  - Analysis: dropdown
  - Insights: dropdown
  - Each dropdown shows: provider icon + model name + tier badge (🟢 cheap / 🟡 mid / 🔴 premium)
  - "Test" button next to each dropdown → runs sample feedback, shows result inline
- Plan-gated models show lock icon with "Upgrade to Pro" tooltip

#### Tab 3: Usage
- **Stat cards**: Total tokens, Estimated cost, Total requests (this month)
- **Daily bar chart** (Recharts): token usage per day, stacked by provider
- **Provider breakdown table**: provider, tokens, requests, cost
- **Fallback events**: list of recent fallback occurrences with timestamp, reason, provider switch

#### Tab 4: Categories
- Existing custom categories UI (unchanged)

### RBAC

| Element | Member | Admin | Owner |
|---|---|---|---|
| General tab | Read-only | Edit | Edit |
| Providers tab (view) | Yes | Yes | Yes |
| Providers tab (change models) | — | Yes | Yes |
| Providers tab (manage keys) | — | — | Yes |
| Usage tab | Yes | Yes | Yes |
| Categories tab | Read-only | Edit | Edit |

### Budget Exceeded Banner

When org's AI budget is exceeded, show across all dashboard pages:

```
⚠️ AI budget exceeded ($10.00 / $10.00) — New feedback won't be analyzed until Mar 1.
[Upgrade Plan] [Add Your Own API Key]
```

- Re-analyze buttons: disabled with tooltip "AI budget limit reached"
- Scheduled analysis: silently skips (logged in usage tab)
- Existing analysis results remain visible

### System Admin: AI Models Page

New page at `/system/ai-models`:
- Table: provider, model ID, display name, tier, min plan, input price, output price, available, deprecated
- Inline edit for prices and availability
- "Sync Prices" button → calls provider APIs to fetch latest pricing
- Deprecate model → set `is_deprecated=true`, configure `replacement_model_id`

---

## Encryption

### Fernet Symmetric Encryption

```python
from cryptography.fernet import Fernet

# Key from env var (generated once, stored in Railway)
ENCRYPTION_KEY = os.environ["LLM_ENCRYPTION_KEY"]
fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt_api_key(plain_key: str) -> str:
    return fernet.encrypt(plain_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    return fernet.decrypt(encrypted_key.encode()).decode()
```

- Encryption key: `LLM_ENCRYPTION_KEY` env var on Railway (both backend-api and worker-service)
- Generate once: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Key rotation: generate new key, re-encrypt all stored keys, update env var (future enhancement)

---

## Fallback Chain

### Flow

```
1. Determine primary provider + model from org_ai_config
2. Determine API key: org's BYOK key (if exists for provider) → system key
3. Attempt call
4. On transient failure (429, 5xx, timeout):
   a. Retry once with 2s backoff
   b. If retry fails → step 5
5. Fallback to system OpenAI key + default model (gpt-4o-mini)
   a. If already using system OpenAI → fail (no further fallback)
6. On auth error (401, 403):
   a. Mark org_api_keys.is_valid = false
   b. Fail immediately (do NOT fallback — config problem, user must fix)
7. Log to llm_usage_logs (including was_fallback + fallback_reason)
8. If fallback occurred: dispatch llm_fallback notification to org admins
```

### Fallback Notifications

New notification type: `llm_fallback`

Dispatched to org admins when fallback occurs. Includes:
- Original provider + model
- Error type (rate_limit, server_error, timeout)
- Fallback provider + model used
- Recommendation: "Check your API key" or "Provider experiencing issues"

Deduplicated: max 1 fallback notification per provider per org per hour (Redis cooldown).

---

## Model Deprecation

When a model is deprecated by its provider:

1. System admin marks model as `is_deprecated=true` in `/system/ai-models`
2. System admin sets `replacement_model_id` (e.g., gpt-4-turbo → gpt-4o)
3. On next LLM call for any org using the deprecated model:
   - Auto-switch to `replacement_model_id`
   - Update `org_ai_config` to use the new model
   - Dispatch `model_deprecated` notification to org admins
4. Deprecated models hidden from model dropdowns (but visible in admin page)

---

## Worker Service Changes

### New Models (worker-service/src/models.py)

Add SQLAlchemy models for:
- `OrgApiKey` (reads from `org_api_keys`)
- `OrgAIConfig` (reads from `org_ai_config`)
- `LLMUsageLog` (writes to `llm_usage_logs`)
- `LLMModelPrice` (reads from `llm_model_prices`)

### Integration Points

All existing LLM callers switch from `openai_client.py` functions to the new factory:

1. **`analysis.py` → `_analyze_feedback_item()`**
   - Uses task type `categorization`
   - Reads org's `model_categorization` from `org_ai_config`
   - Stores `llm_provider` + `llm_model` on `feedback_items`

2. **`insights.py` → `generate_weekly_insights()`**
   - Uses task type `insights`
   - Reads org's `model_insights`

3. **`insights.py` → `generate_churn_insights()`**
   - Uses task type `churn_analysis`
   - Reads org's `model_analysis`

4. **`insights.py` → `analyze_customer()`**
   - Uses task type `analysis`
   - Reads org's `model_analysis`
   - Stores `llm_provider` + `llm_model` on `customer_health_scores`

### Budget Check

Before each LLM call on system key:

```python
def check_budget(org_id: int, estimated_cost_cents: float, db: Session) -> bool:
    """Check if org has remaining AI budget. Returns True if OK."""
    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    if not config or not config.monthly_budget_cents:
        return True  # No limit configured
    if config.budget_used_cents >= config.monthly_budget_cents:
        return False
    return True
```

If budget exceeded: mark feedback as `pending_analysis`, skip LLM call, return None.

### Budget Reset

Celery Beat task: `reset_ai_budgets` — runs at 00:05 UTC on the 1st of each month.

```python
@celery_app.task
def reset_ai_budgets():
    """Reset monthly AI budgets and trigger queued analysis."""
    # 1. Reset budget_used_cents to 0 for all orgs
    # 2. Set budget_reset_at to next month
    # 3. Find all feedback items with pending_analysis status
    # 4. Dispatch batch analysis for queued items
```

---

## Prompts

All existing prompts remain unchanged. The factory just routes them to the configured provider. No prompt modifications needed for different providers — the "Return ONLY valid JSON" instruction works across all models.

For Anthropic specifically, the provider adapter strips markdown fences:
```python
def _strip_json_fences(content: str) -> str:
    """Remove ```json ... ``` wrapping if present."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()
```

---

## Phases

### Phase 1: Database Schema & Models (Day 1)
- [ ] Create Alembic migration: 4 new tables (`org_api_keys`, `org_ai_config`, `llm_usage_logs`, `llm_model_prices`)
- [ ] Add `llm_provider`, `llm_model` columns to `feedback_items` and `customer_health_scores`
- [ ] Data migration: move existing `openai_api_key` to `org_api_keys` (encrypted)
- [ ] Drop `organizations.openai_api_key` column
- [ ] Seed `llm_model_prices` with initial model registry (8 models)
- [ ] Create default `org_ai_config` for all existing orgs
- [ ] Add SQLAlchemy models to both backend-api and worker-service
- [ ] Generate and set `LLM_ENCRYPTION_KEY` env var on Railway

### Phase 2: LLM Factory & Providers (Day 2-3)
- [ ] Create `worker-service/src/llm/` package structure
- [ ] Implement `LLMProvider` abstract base class with `complete()`, `stream()` (NotImplementedError), `validate_key()`
- [ ] Implement `LLMResponse` dataclass
- [ ] Implement `OpenAIProvider` (chat.completions.create with json_object mode)
- [ ] Implement `AnthropicProvider` (messages.create with prompt-based JSON + fence stripping)
- [ ] Implement `GoogleProvider` (generate_content with response_mime_type)
- [ ] Implement `LLMProviderFactory.create()`
- [ ] Implement `FallbackChain` with retry (1x, 2s backoff) and fallback logic
- [ ] Implement budget check function
- [ ] Implement usage logging (write to `llm_usage_logs`)
- [ ] Add `anthropic` and `google-generativeai` to worker-service requirements.txt
- [ ] Delete `worker-service/src/openai_client.py`
- [ ] Update all callers in `analysis.py` and `insights.py` to use factory
- [ ] Store `llm_provider` + `llm_model` on feedback_items and customer_health_scores

### Phase 3: Backend API Endpoints (Day 3-4)
- [ ] Encryption utility module (`src/utils/encryption.py`)
- [ ] Update `GET/PATCH /api/v1/settings/ai` with new response/request schemas
- [ ] New: `GET/POST/DELETE /api/v1/settings/ai/keys` (BYOK management with encryption)
- [ ] New: `POST /api/v1/settings/ai/keys/validate` (test call on save)
- [ ] New: `POST /api/v1/settings/ai/test-model` (sample feedback test, rate limited)
- [ ] New: `GET /api/v1/settings/ai/models` (available models by plan)
- [ ] New: `GET /api/v1/settings/ai/usage` + `GET /api/v1/settings/ai/usage/daily`
- [ ] New: `GET/PATCH /api/v1/admin/ai-models` + `POST .../sync-prices`
- [ ] Rate limiting: 5 tests/min, 10 key saves/hour per org (Redis DB 3)
- [ ] Budget check API: `GET /api/v1/settings/ai/budget` (for frontend banner)
- [ ] Update plan gating: add `multi_model_support` feature to Pro+, `byok_keys` to Pro+

### Phase 4: Frontend — Settings UI (Day 4-5)
- [ ] Restructure `/settings/ai` into tabbed layout (General, Providers, Usage, Categories)
- [ ] General tab: AI toggle + budget status progress bar + exceeded banner
- [ ] Providers tab: provider cards (logo, status, BYOK key input with masked display)
- [ ] Providers tab: model selection dropdowns per task type with provider icon + tier badge
- [ ] Providers tab: "Test" button per model → inline result display
- [ ] Usage tab: stat cards (tokens, cost, requests)
- [ ] Usage tab: daily bar chart (Recharts, stacked by provider)
- [ ] Usage tab: provider breakdown table
- [ ] Usage tab: fallback events list
- [ ] Categories tab: move existing categories UI (unchanged)
- [ ] RBAC: members read-only, admin edit models, owner edit keys
- [ ] Plan-gated model options with lock icon + upgrade tooltip
- [ ] Provider logos (SVG): OpenAI, Anthropic, Google
- [ ] API client functions in `lib/api/ai-settings.ts`

### Phase 5: Budget UX & Notifications (Day 5-6)
- [ ] Budget exceeded banner component (shown across dashboard pages)
- [ ] Disable re-analyze buttons when budget exceeded with tooltip
- [ ] `pending_analysis` status on feedback items when budget exceeded
- [ ] Celery Beat task: `reset_ai_budgets` (1st of month, 00:05 UTC)
- [ ] Batch analysis of queued items on budget reset
- [ ] New notification type: `llm_fallback` with 1hr per-provider dedup
- [ ] New notification type: `model_deprecated`
- [ ] Notification display in bell + notifications page

### Phase 6: System Admin & Testing (Day 6-7)
- [ ] System admin page: `/system/ai-models` (model price management)
- [ ] "Sync Prices" button with provider API fetch
- [ ] Model deprecation flow (mark deprecated, set replacement, auto-switch)
- [ ] Backend tests: factory, providers, fallback chain, budget, encryption, API endpoints
- [ ] Worker tests: updated analysis + insights tasks with factory
- [ ] Frontend tests: settings UI tabs, provider cards, usage display, budget banner
- [ ] Integration test: full flow (set BYOK key → change model → analyze → check usage)

---

## Feature IDs (Plan Config)

Add to `plans.py`:
- `multi_model_support` → Pro+ (access to non-default models)
- `byok_keys` → Pro+ (bring your own API keys)
- `ai_usage_dashboard` → Pro+ (usage tab on settings page)

Free plan: locked to cheap tier models (gpt-4o-mini, haiku, flash) with system key only, no usage dashboard.

---

## Environment Variables

### New (Railway)

| Variable | Service | Description |
|---|---|---|
| `LLM_ENCRYPTION_KEY` | backend-api, worker-service | Fernet key for encrypting BYOK keys |
| `ANTHROPIC_API_KEY` | worker-service | System Anthropic API key (optional, for system fallback) |
| `GOOGLE_AI_API_KEY` | worker-service | System Google AI API key (optional, for system fallback) |

### Existing (unchanged)

| Variable | Service | Description |
|---|---|---|
| `OPENAI_API_KEY` | worker-service | System OpenAI API key (primary system provider) |

---

## Dependencies (pip)

### worker-service/requirements.txt — Add

```
anthropic>=0.40.0
google-generativeai>=0.8.0
cryptography>=43.0.0
```

### backend-api/requirements.txt — Add

```
cryptography>=43.0.0
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Anthropic JSON parsing fails | Analysis returns None | Robust fence stripping + JSON validation + fallback to OpenAI |
| Google API differences | Provider implementation bugs | Comprehensive test suite per provider |
| BYOK key leaked via logs | Security breach | Never log API keys; only log key_hint; encrypt at rest |
| Budget estimation inaccurate | Over/under-charging orgs | Prices are estimates, not billing; clear "estimated" label in UI |
| Migration breaks existing BYOK users | Analysis stops working | Test migration on staging; verify encrypted keys decrypt correctly |
| Provider API changes | Broken provider adapters | Version-pin SDKs; abstract away provider specifics |

---

## Success Metrics

| Metric | Target |
|---|---|
| Orgs with BYOK keys configured | 5+ within 30 days |
| Model switch events (orgs changing default) | 10+ within 30 days |
| Fallback success rate | >95% of fallback calls succeed |
| Budget exceeded notifications | <5% of orgs hit budget per month |
| Provider diversity | At least 2 providers actively used |

---

## Related

- [AI-TRACKING.md](AI-TRACKING.md) — AI roadmap (M2.1 section)
- [PRD-CHURN-PREDICTION-ACCURACY.md](PRD-CHURN-PREDICTION-ACCURACY.md) — M1.4 (predecessor)
- `worker-service/src/openai_client.py` — Current LLM code (to be replaced)
- `services/backend-api/src/api/routes/ai_settings.py` — Current AI settings API
- `services/frontend-web/app/(dashboard)/settings/ai/page.tsx` — Current AI settings UI
