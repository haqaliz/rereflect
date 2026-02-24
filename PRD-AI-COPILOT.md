# PRD: AI Copilot — Command Bar & Conversations (M2.2)

**Product**: Rereflect
**Milestone**: M2.2
**Author**: AI-generated from product discovery session
**Date**: 2026-02-23
**Status**: Draft — Pending Review
**Estimated Effort**: 3 weeks

---

## 1. Overview

The AI Copilot gives users a natural-language interface to query, analyze, and understand their feedback data. It consists of two connected surfaces:

1. **Command Bar (Cmd+K)** — A quick-launch Spotlight-style modal for starting AI conversations from anywhere in the app
2. **Conversations Page (`/conversations`)** — A full ChatGPT-style chat experience where conversations live, persist, and are shared across the organization

The Cmd+K modal acts as a shortcut: user types a question, hits Enter, and is navigated to `/conversations` where a new conversation is created and the query is submitted.

---

## 2. Goals

- Let users ask questions about their feedback data in plain English
- Surface insights that are hard to find through manual browsing (trends, correlations, anomalies)
- Reduce time-to-insight from minutes (navigating pages, filtering, exporting) to seconds
- Create a shared knowledge base of AI conversations visible to the whole org
- Build a self-learning query system that gets faster and cheaper over time

## 3. Non-Goals (V1)

- No action execution (read-only — no mutations, no status changes, no assignments)
- No file/image attachments
- No conversation sharing/export (team can already view since conversations are org-shared)
- No conversation search (defer to V2 when volume grows)
- No real-time collaborative editing of conversations

---

## 4. User Experience

### 4.1 Command Bar (Cmd+K)

**Trigger**: `Cmd+K` keyboard shortcut OR sparkle/AI icon button in the top header bar

**Behavior**:
1. Pressing Cmd+K opens a centered Spotlight-style modal with backdrop blur
2. Modal contains a text input with placeholder: "Ask anything about your feedback..."
3. Below the input: 6-8 template starters as clickable chips (see §4.4)
4. User types a question and presses Enter
5. App navigates to `/conversations`, creates a new conversation, submits the query
6. If user presses Escape or clicks outside, modal closes (no navigation)

**Keyboard support**:
- `Cmd+K` / `Ctrl+K`: Open modal
- `Escape`: Close modal
- `Enter`: Submit query → navigate to /conversations
- `Arrow Up/Down`: Cycle through template suggestions
- `Tab`: Move focus between input and suggestions

**Plan gating**:
- Free users see the Cmd+K modal and can use it (up to daily limit)
- When limit is reached, show upgrade prompt inside the modal

### 4.2 Conversations Page (`/conversations`)

**Layout**: ChatGPT-style with auto-collapsing main sidebar

When the user navigates to `/conversations`:
1. The main app sidebar auto-collapses to icon-only mode (≈48px wide)
2. A conversation list panel (≈240px) appears showing folders + conversations
3. The remaining space is the chat area

```
┌──┬──────────────┬─────────────────────────────────┐
│  │ + New Chat   │                                 │
│  │ Search...    │   [Context: All Feedbacks ▼]    │
│  │              │                                 │
│🏠│ 📁 General   │   User: How many negative...    │
│📊│   > Churn Q1 │   ┌─────────────────────────┐   │
│💬│   > Weekly   │   │ 🔍 Searching feedbacks.. │   │
│⚙│ 📁 Customer  │   └─────────────────────────┘   │
│  │   > John D.  │   AI: Based on your data...     │
│  │              │   ┌──────────────┐               │
│  │              │   │ 📊 Table     │               │
│  │              │   │ negative: 47 │               │
│  │              │   │ neutral: 123 │               │
│  │              │   └──────────────┘               │
│  │              │                                 │
│  │              │   [Type a message... ⏎]         │
└──┴──────────────┴─────────────────────────────────┘
 ↑ collapsed      ↑ conv list        ↑ chat area
```

**Conversation list panel**:
- "New Chat" button at top
- Folder management: create, rename, delete folders
- Conversations grouped by folder, sorted chronologically within (recent first)
- Default folder: "General" (unfiled conversations go here)
- Right-click context menu: rename, move to folder, delete conversation
- Conversation title: first ~50 chars of first user message (user-editable via double-click)

**Chat area**:
- Context scope selector at top (see §4.3)
- Message bubbles: user messages right-aligned, AI messages left-aligned
- AI messages support: markdown, syntax-highlighted code blocks, data tables, inline charts, deep links
- Streaming: AI responses stream in token-by-token via WebSocket
- During streaming: show "Stop generating" button
- After response: show "Regenerate" button (↻ icon)
- Brief status indicators during processing: "Searching feedbacks...", "Analyzing data...", "Generating response..."
- Input area at bottom: text input + Enter to send, Shift+Enter for newline

**Navigating away**: When user clicks a sidebar icon to go to another page, the main sidebar expands back to full. Returning to `/conversations` re-collapses it and restores the last active conversation.

### 4.3 Context Scopes

Users can control what data the AI has access to for each conversation via a scope selector at the top of the chat area.

**Predefined page-based scopes**:
| Scope | Data Included |
|-------|---------------|
| All Data | Everything in the org (default) |
| Feedbacks | All feedback items with sentiment, categories, tags |
| Customers | Customer health scores, profiles, feedback history |
| Pain Points | Extracted pain points with categories and severity |
| Feature Requests | Extracted feature requests with priority and vote count |
| Dashboard | Summary stats, trends, charts data |

**Entity-based scopes** (via @mention in message):
- `@customer:john@example.com` — Scope to a specific customer's data
- `@feedback:#1234` — Scope to a specific feedback item
- `@period:last-30-days` — Scope to a date range
- `@tag:pricing` — Scope to feedbacks with a specific tag

The scope selector is shown as a dropdown chip. Users can change scope mid-conversation. When an @mention is used, the scope automatically adjusts and shows as a chip.

### 4.4 Template Starters

Shown in the Cmd+K modal and as suggestions in empty new conversations.

**Static templates** (always available):

| Category | Template |
|----------|----------|
| Feedback | "This week's feedback summary" |
| Feedback | "Top pain points this month" |
| Feedback | "Most requested features" |
| Feedback | "Urgent feedback that needs attention" |
| Customer | "Top churn risks right now" |
| Customer | "Healthiest customers" |
| Customer | "Customers with declining health scores" |
| Customer | "Sentiment trends over the last 30 days" |

**Dynamic suggestions** (user-triggered):
- Not auto-generated — user clicks a "Suggest queries" button to generate 2-3 suggestions based on recent activity, anomalies, or data patterns
- Example: "You had 5 urgent feedbacks today — ask about them"
- Example: "Customer churn risk increased 15% this week"

### 4.5 Error Handling

| Scenario | Behavior |
|----------|----------|
| Query fails (LLM error) | Show error bubble + "Retry" button + automatic fallback to simpler model |
| Query timeout (>30s) | Show timeout message + "Retry" button |
| Out of scope question | Decline politely + redirect: "I can help with feedback, customers, and trends. Try: [suggestions]" |
| No data found | "I couldn't find data matching your query. Try broadening your scope or rephrasing." |
| Rate limit reached | "You've used your daily query allowance. Upgrade to Pro for more." (Free) or "Monthly token budget reached." (paid) |
| WebSocket disconnected | Auto-reconnect with exponential backoff, show "Reconnecting..." indicator |

### 4.6 Markdown & Result Rendering

AI responses support:
- **Markdown**: Headers, bold, italic, lists, links, blockquotes
- **Code blocks**: Syntax-highlighted (SQL queries, JSON results)
- **Data tables**: Rendered as styled HTML tables with column headers
- **Inline charts**: Mini bar/line/pie charts for visual data (using Recharts)
- **Deep links**: Clickable links to specific pages: `/feedbacks/123`, `/customers/john@example.com`

---

## 5. Backend Architecture

### 5.1 Query Processing Pipeline

```
User Message
    │
    ▼
┌──────────────────┐
│  Intent Classifier │  ← Lightweight LLM call or rule-based
│  (data / analysis │
│   / general)      │
└────────┬─────────┘
         │
    ┌────┴────┬──────────────┐
    ▼         ▼              ▼
┌────────┐ ┌──────────┐ ┌──────────┐
│  Data  │ │ Analysis │ │ General  │
│ Query  │ │  Query   │ │  Query   │
└───┬────┘ └────┬─────┘ └────┬─────┘
    │           │             │
    ▼           ▼             ▼
Template    Context        Direct
Match?      Assembly       LLM Call
 │  │         │
 Y  N         ▼
 │  │     LLM Analysis
 │  ▼      with data
 │ LLM→SQL
 │  │
 │  ▼
 │ Auto-save
 │ as template
 │  │
 ▼  ▼
Execute Query
    │
    ▼
Format Response
(text + tables + charts + links)
    │
    ▼
Stream via WebSocket
```

### 5.2 Self-Learning Query Templates

The system maintains a table of query templates that grows over time:

**Template matching flow**:
1. User asks a question
2. System searches existing templates for a semantic match
3. If match found → execute the pre-saved SQL (fast, no LLM cost)
4. If no match → LLM generates SQL → execute → if successful, auto-save as new template

**Template table design**:
- **Idempotent**: Many different question phrasings map to the same SQL query
- **Mapping table**: `question_pattern → template_id` (many-to-one)
- **Template record**: `template_id, sql_query, description, parameter_schema, created_by (system/llm), usage_count, last_used, is_active`
- **Admin management**: Admins can view, edit, disable, or delete templates via `/system/query-templates`

**Dynamic indexing consideration**:
- When a new template is auto-saved, analyze its SQL for common WHERE/JOIN patterns
- Suggest (or auto-create) database indexes that would improve query performance
- Log slow queries (>1s) for admin review

### 5.3 SQL Safety Guardrails

| Guardrail | Implementation |
|-----------|----------------|
| Read-only | Only `SELECT` statements allowed. Reject any `INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE`. |
| Org-scoped | Every query automatically gets `WHERE organization_id = :org_id` injected. |
| Schema whitelist | Only allow queries against approved tables/columns. Exclude: `users.password_hash`, `org_api_keys.encrypted_key`, `sessions.*` |
| Row limits | Default limits by query type + plan tier (see §5.4). Enforced via `LIMIT` clause. |
| Join limit | Maximum 3 table JOINs per query. |
| Query timeout | 5-second execution timeout. Queries exceeding this are killed. |
| No subqueries | Disallow nested SELECT statements (prevents complex resource-hogging queries). |
| Parameterized | All user-provided values passed as parameters (prevent SQL injection). |

### 5.4 Row Limits by Query Type & Plan

| Query Type | Free | Pro | Business | Enterprise |
|------------|------|-----|----------|------------|
| Aggregation (COUNT, AVG, SUM, GROUP BY) | 100 | 200 | 500 | 1000 |
| Detail (SELECT with columns) | 50 | 250 | 1250 | 5000 |
| Export-style (SELECT *) | 25 | 125 | 625 | 2500 |

Base limits are defined per query type. Plan multipliers: Free = 1x, Pro = 5x, Business = 25x, Enterprise = 100x (applied to the base: 50 detail rows × 5 = 250 for Pro).

Users can request higher limits within their plan ceiling by explicitly stating it: "show me all" or "limit 5000".

### 5.5 WebSocket Protocol

**Connection**: `wss://{host}/ws/copilot?token={jwt}`

**Client → Server messages**:
```json
{
  "type": "query",
  "conversation_id": "uuid",
  "content": "How many negative feedbacks this week?",
  "context_scope": "all_data",
  "message_id": "client-uuid"
}

{
  "type": "stop",
  "conversation_id": "uuid",
  "message_id": "uuid-of-message-being-generated"
}

{
  "type": "regenerate",
  "conversation_id": "uuid",
  "message_id": "uuid-of-message-to-regenerate"
}
```

**Server → Client messages**:
```json
{
  "type": "status",
  "message_id": "uuid",
  "status": "searching_feedbacks"
}

{
  "type": "stream",
  "message_id": "uuid",
  "delta": "Based on your ",
  "done": false
}

{
  "type": "stream",
  "message_id": "uuid",
  "delta": "",
  "done": true,
  "metadata": {
    "model": "gpt-4o",
    "provider": "openai",
    "tokens_in": 1250,
    "tokens_out": 340,
    "cost_cents": 2.4,
    "latency_ms": 1830,
    "query_type": "data",
    "template_id": "tpl_abc123",
    "sql_generated": "SELECT sentiment, COUNT(*) ..."
  }
}

{
  "type": "structured_data",
  "message_id": "uuid",
  "data_type": "table",
  "data": {
    "columns": ["sentiment", "count"],
    "rows": [["negative", 47], ["neutral", 123], ["positive", 89]]
  }
}

{
  "type": "structured_data",
  "message_id": "uuid",
  "data_type": "chart",
  "chart_type": "bar",
  "data": { ... }
}

{
  "type": "error",
  "message_id": "uuid",
  "error": "Query timed out after 5 seconds",
  "suggestions": ["Try a more specific question", "Narrow your date range"]
}
```

### 5.6 Streaming Flow (Token-by-Token)

1. Client sends `query` message via WebSocket
2. Server classifies intent → sends `status` message ("Classifying query...")
3. Server fetches context / runs SQL → sends `status` message ("Searching feedbacks...")
4. Server starts LLM streaming → sends `stream` messages with `delta` tokens
5. If structured data (table/chart) is part of the response → sends `structured_data` message
6. Final `stream` message has `done: true` with full metadata
7. Client can send `stop` at any point to cancel generation

---

## 6. Data Model

### 6.1 New Tables

**`conversations`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| organization_id | UUID | FK → organizations |
| created_by_user_id | UUID | FK → users (who started it) |
| title | VARCHAR(200) | Auto-generated from first message, user-editable |
| folder_id | UUID | FK → conversation_folders (nullable) |
| context_scope | VARCHAR(50) | Current scope (all_data, feedbacks, customers, etc.) |
| is_active | BOOLEAN | Soft delete |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**`conversation_folders`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| organization_id | UUID | FK → organizations |
| name | VARCHAR(100) | Folder name |
| sort_order | INTEGER | Display order |
| created_at | TIMESTAMP | |

**`conversation_messages`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| conversation_id | UUID | FK → conversations |
| role | VARCHAR(20) | "user" or "assistant" |
| content | TEXT | Message text (markdown) |
| structured_data | JSONB | Tables, charts, links embedded in response |
| context_scope | VARCHAR(50) | Scope active when this message was sent |
| query_type | VARCHAR(20) | "data", "analysis", "general" (null for user messages) |
| template_id | UUID | FK → query_templates (if template was matched) |
| sql_generated | TEXT | SQL query generated/executed (if applicable) |
| llm_provider | VARCHAR(50) | Provider used (openai, anthropic, google) |
| llm_model | VARCHAR(100) | Model used (gpt-4o, claude-sonnet, etc.) |
| tokens_in | INTEGER | Input tokens consumed |
| tokens_out | INTEGER | Output tokens consumed |
| cost_cents | DECIMAL(10,4) | Cost of this message in cents |
| latency_ms | INTEGER | Total response time |
| raw_request | JSONB | Full LLM request payload (for debugging) |
| raw_response | JSONB | Full LLM response payload (for debugging) |
| is_regenerated | BOOLEAN | Whether this replaced a previous response |
| created_at | TIMESTAMP | |

**`query_templates`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| organization_id | UUID | FK → organizations (null = global/system template) |
| sql_query | TEXT | The SQL query template with parameter placeholders |
| description | VARCHAR(500) | Human-readable description of what this query does |
| parameter_schema | JSONB | Expected parameters: `{"date_from": "date", "sentiment": "string"}` |
| created_by | VARCHAR(20) | "system" (static), "llm" (auto-generated), "admin" (manually created) |
| usage_count | INTEGER | How many times this template has been used |
| last_used_at | TIMESTAMP | |
| is_active | BOOLEAN | Admins can disable templates |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**`query_template_mappings`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| template_id | UUID | FK → query_templates |
| question_pattern | TEXT | Normalized question text (lowercased, stopwords removed) |
| question_embedding | VECTOR(1536) | Embedding vector for semantic matching |
| match_count | INTEGER | How many times this pattern matched |
| created_at | TIMESTAMP | |

**Indexes**:
- `conversations`: `(organization_id, created_at DESC)`, `(organization_id, folder_id)`
- `conversation_messages`: `(conversation_id, created_at)`
- `query_templates`: `(organization_id, is_active, usage_count DESC)`
- `query_template_mappings`: `(template_id)`, GIN index on `question_embedding` for vector similarity search

### 6.2 Schema Whitelist Table

**`copilot_schema_whitelist`**
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| table_name | VARCHAR(100) | Allowed table |
| column_name | VARCHAR(100) | Allowed column (null = all columns) |
| description | TEXT | Human-readable description (fed to LLM for context) |
| is_active | BOOLEAN | Can be toggled by admin |

Pre-populated with safe tables: `feedbacks`, `customer_health`, `pain_points`, `feature_requests`, `tags`, `feedback_tags`, `anomaly_events`. Excludes: `users`, `organizations`, `subscriptions`, `org_api_keys`, `sessions`.

---

## 7. API Endpoints

### 7.1 REST Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/conversations` | List conversations (paginated, filterable by folder) | JWT |
| POST | `/api/v1/conversations` | Create new conversation | JWT |
| GET | `/api/v1/conversations/:id` | Get conversation with messages | JWT |
| PATCH | `/api/v1/conversations/:id` | Update title, folder, context_scope | JWT |
| DELETE | `/api/v1/conversations/:id` | Soft delete conversation | JWT |
| GET | `/api/v1/conversations/folders` | List folders | JWT |
| POST | `/api/v1/conversations/folders` | Create folder | JWT |
| PATCH | `/api/v1/conversations/folders/:id` | Rename folder, change order | JWT |
| DELETE | `/api/v1/conversations/folders/:id` | Delete folder (moves convos to General) | JWT |
| GET | `/api/v1/conversations/templates` | List suggested template starters | JWT |
| POST | `/api/v1/conversations/suggestions` | Generate dynamic suggestions based on recent activity | JWT |
| GET | `/api/v1/copilot/usage` | Get user's query usage stats (tokens used, remaining budget) | JWT |

### 7.2 WebSocket Endpoint

| Path | Description |
|------|-------------|
| `wss://{host}/ws/copilot?token={jwt}` | Real-time copilot streaming connection |

### 7.3 Admin Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/admin/query-templates` | List all auto-saved query templates | Admin |
| PATCH | `/api/v1/admin/query-templates/:id` | Edit/disable a template | Admin |
| DELETE | `/api/v1/admin/query-templates/:id` | Delete a template | Admin |
| GET | `/api/v1/admin/copilot/stats` | Usage stats, popular queries, template hit rate | Admin |

---

## 8. Plan Gating & Rate Limits

### 8.1 Query Limits

| Tier | Daily Cap | Monthly Token Budget | Max Conversations |
|------|-----------|---------------------|--------------------|
| Free | 10 queries/day | 50K tokens/month | 5 active |
| Pro | No daily cap | 500K tokens/month | Unlimited |
| Business | No daily cap | 5M tokens/month | Unlimited |
| Enterprise | No daily cap | Unlimited | Unlimited |

### 8.2 Feature Access

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| Cmd+K command bar | ✅ | ✅ | ✅ | ✅ |
| /conversations page | ✅ | ✅ | ✅ | ✅ |
| Data queries (SQL) | ✅ | ✅ | ✅ | ✅ |
| Analysis queries | ❌ | ✅ | ✅ | ✅ |
| Conversation folders | ❌ | ✅ | ✅ | ✅ |
| Dynamic suggestions | ❌ | ✅ | ✅ | ✅ |
| @mention entity scopes | ❌ | ❌ | ✅ | ✅ |
| Query template admin | ❌ | ❌ | ✅ | ✅ |
| Full audit trail access | ❌ | ❌ | ❌ | ✅ |

### 8.3 Enforcement

- **Daily cap (Free)**: Check `copilot_query_count` for user in current UTC day. Return 429 when exceeded.
- **Token budget**: Check `SUM(tokens_in + tokens_out)` for org in current billing month. Return 429 when exceeded.
- **Feature access**: Use existing `require_feature` dependency per endpoint/WebSocket message type.

---

## 9. Implementation Phases

### Phase 1: Data Layer & WebSocket Foundation (Week 1)
- [ ] Alembic migration: conversations, conversation_messages, conversation_folders, query_templates, query_template_mappings, copilot_schema_whitelist
- [ ] SQLAlchemy models for all new tables
- [ ] REST endpoints: conversations CRUD, folders CRUD
- [ ] WebSocket endpoint with JWT auth, connection management, heartbeat
- [ ] Basic query → LLM → stream response flow (no SQL generation yet)
- [ ] Message persistence with full audit trail metadata
- [ ] Rate limiting middleware (daily cap + token budget)

### Phase 2: Query Engine & Templates (Week 2)
- [ ] Intent classifier: data query vs analysis vs general
- [ ] Schema whitelist: populate approved tables/columns
- [ ] LLM→SQL generation with safety guardrails (read-only, org-scoped, row limits, timeout)
- [ ] SQL execution engine with parameterized queries
- [ ] Query template matching: semantic similarity search against existing templates
- [ ] Auto-save successful LLM-generated SQL as new templates (idempotent mapping)
- [ ] Context scope resolver: build LLM context based on selected scope + @mentions
- [ ] Structured data formatting: tables, charts data, deep links
- [ ] Error handling: fallback chain, retry, helpful error messages

### Phase 3: Frontend — Command Bar & Conversations Page (Week 2-3)
- [ ] Cmd+K modal component: trigger, input, template chips, keyboard navigation
- [ ] Header button (sparkle icon) for Cmd+K
- [ ] `/conversations` page layout: auto-collapsing sidebar, conversation list panel, chat area
- [ ] Conversation list: folders, chronological sort, right-click context menu, rename
- [ ] Chat UI: message bubbles, markdown rendering, syntax highlighting
- [ ] WebSocket client: connect, send messages, receive streaming tokens
- [ ] Structured data renderers: table component, inline chart component (Recharts), deep link component
- [ ] Stop generating / Regenerate buttons
- [ ] Status indicators: "Searching feedbacks...", "Analyzing data...", "Generating response..."
- [ ] Context scope selector dropdown
- [ ] @mention autocomplete for customers, feedbacks, tags, date ranges
- [ ] Template starters grid (static + dynamic suggestion button)
- [ ] Plan gating UI: upgrade prompts, usage indicators
- [ ] Sidebar nav: add "Conversations" item with chat icon

### Phase 4: Admin & Polish (Week 3)
- [ ] `/system/query-templates` admin page: list, edit, disable, delete auto-saved templates
- [ ] Admin copilot stats dashboard: usage, popular queries, template hit rate
- [ ] Dynamic index suggestion: log slow queries, suggest indexes
- [ ] Conversation title editing (double-click)
- [ ] Keyboard navigation polish (full Cmd+K → chat flow via keyboard)
- [ ] Mobile responsiveness (conversation list as drawer on small screens)
- [ ] Loading states, empty states, skeleton screens
- [ ] Token budget display in settings/usage page

---

## 10. Technical Notes

### LLM Model Selection
Uses the M2.1 multi-model infrastructure. The copilot uses the org's configured default model. If no BYOK key is configured, falls back to system OpenAI (GPT-4o-mini for Free, GPT-4o for paid plans).

### Conversation Context Window
No hard limit on conversation length. Internally, when conversation history exceeds the model's context window:
- Summarize older messages into a condensed context block
- Keep the last N messages in full
- Include the current scope's data context

### Vector Embeddings for Template Matching
- Use OpenAI `text-embedding-3-small` (1536 dimensions) for question embeddings
- Store in PostgreSQL with `pgvector` extension
- Cosine similarity search with threshold (>0.85 = match)
- Fallback to LLM generation if no template matches above threshold

### WebSocket Scaling
- FastAPI WebSocket with connection manager
- Redis pub/sub for multi-worker WebSocket message routing
- Connection heartbeat every 30s, auto-disconnect after 5min idle
- Reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)

### Cost Optimization
- Template matching avoids LLM calls for repeated question patterns
- Intent classification can use a lightweight model (GPT-4o-mini) or rule-based regex for obvious patterns
- Structured data responses are generated programmatically from SQL results (not by LLM)
- Token budget prevents runaway costs

---

## 11. Dependencies

| Dependency | Reason | Status |
|------------|--------|--------|
| M2.1 Multi-Model Support | LLM factory, BYOK keys, usage logging | ✅ Complete |
| pgvector PostgreSQL extension | Vector similarity search for template matching | Needs setup |
| WebSocket support in deployment | Railway/infra must support persistent WS connections | Needs verification |
| Redis (existing) | WebSocket pub/sub for multi-worker routing | ✅ Available |

---

## 12. Success Metrics

| Metric | Target (Week 1) | Target (Month 1) | Target (Month 3) |
|--------|-----------------|-------------------|-------------------|
| Daily active copilot users | 10 | 50 | 200 |
| Queries per user per day | 3 | 5 | 10 |
| Template hit rate | 10% | 40% | 70% |
| Avg response latency | <5s | <3s | <2s |
| Query success rate | 80% | 90% | 95% |
| Conversations created | 50 | 500 | 5,000 |

---

## 13. Open Questions

1. **pgvector availability**: Is pgvector already available on our Railway PostgreSQL instance, or do we need to enable/migrate?
2. **WebSocket on Railway**: Does our Railway deployment support persistent WebSocket connections, or do we need to configure anything?
3. **Embedding model cost**: At scale, should we switch from OpenAI embeddings to a self-hosted model (e.g., Sentence-BERT) to reduce costs?
4. **Conversation retention**: How long should we keep conversation history? Forever, or prune after X months for storage management?
5. **Dynamic indexing**: Should auto-index suggestions be applied automatically or require admin approval?
