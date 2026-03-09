# PRD: AI Response Suggestions (M2.3)

**Status**: Complete
**Priority**: High (next milestone)
**Owner**: Full-stack
**Date**: 2026-03-09
**Estimated Effort**: 2 weeks
**Milestone**: M2.3 (AI-TRACKING.md)

---

## 1. Problem Statement

When a team member reviews a feedback item, they often need to respond to the customer — acknowledge a bug, thank them for a feature suggestion, or reach out proactively to an at-risk customer. Today, users must:

1. Read the feedback and mentally decide what kind of response is appropriate
2. Switch to the external channel (Slack, Intercom, email, Linear) to find the original message
3. Manually compose a response from scratch every time
4. Hope they strike the right tone and don't miss important context

This is slow, inconsistent, and error-prone. Different team members respond in different styles. Churn-risk customers don't get the empathetic outreach they need. Routine acknowledgments eat up time that could be spent on higher-value work.

**Impact**: Teams spend 5-10 minutes per response on repetitive composition. Response quality varies across team members. At-risk customers don't get proactive outreach because it's too time-consuming to draft individually.

---

## 2. Goals

1. Let users respond to feedback directly from Rereflect — no channel-switching
2. Provide pre-built response templates that cover the most common feedback categories
3. Allow orgs to create custom templates matching their brand voice
4. Use AI to generate personalized, context-aware responses with one click
5. Support sending responses back through connected integrations (Slack, Intercom, Linear, email)
6. Save response history on each feedback item for team visibility
7. Gate AI generation by plan tier to drive upgrades

---

## 3. Non-Goals

- No bulk response generation (always one-at-a-time from feedback detail page)
- No auto-sending (user always reviews before sending)
- No channel-specific template variants (templates are universal)
- No rich text editor (plain text / markdown only)
- No response analytics dashboard (basic counters only, shown in AI Settings usage)
- No customer profile page integration (feedback detail page only for v1)
- No A/B testing of response effectiveness

---

## 4. User Flow

### 4.1 Happy Path — Template Response

```
User opens /feedbacks/[id]
  → Sees "Respond" button in the actions area
  → Clicks "Respond"
  → Modal opens with:
     - Top suggestion: AI-picked best matching template (pre-filled with variables resolved)
     - "Browse templates" link to see all templates
     - "Generate with AI" button
     - Tone dropdown (defaults to org setting)
  → User reviews the suggested template
  → Edits if needed in the textarea
  → Clicks "Copy" (copies to clipboard) or "Send via Slack" / "Send via Intercom" / etc.
  → Response is saved to the feedback item's timeline
  → Modal closes, success toast shown
```

### 4.2 Happy Path — AI-Generated Response

```
User opens /feedbacks/[id]
  → Clicks "Respond"
  → Modal opens with template suggestion
  → User clicks "Generate with AI"
  → Loading state while LLM generates
  → AI-generated response appears in the textarea
  → User edits, adjusts tone if needed
  → Clicks "Copy" or "Send via [channel]"
  → Response saved to timeline
  → Usage counter incremented (Pro: X/50 used)
```

### 4.3 Free Plan User

```
User opens /feedbacks/[id]
  → Sees "Respond" button (visible but gated)
  → Clicks "Respond"
  → Upgrade CTA modal: "Response Suggestions is available on Pro and above"
  → Link to billing page
```

---

## 5. Design Specifications

### 5.1 Feedback Detail Page — Respond Button

**Location**: In the actions area of `/feedbacks/[id]`, alongside existing action buttons (status dropdown, assignee selector).

**Button**: `<Button variant="outline">` with `<Reply className="w-4 h-4" />` icon + "Respond" text.

**Behavior**:
- Pro+ with responses remaining → Opens respond modal
- Pro+ with limit reached → Opens modal with limit exceeded banner + upgrade CTA
- Free → Opens upgrade CTA modal

---

### 5.2 Respond Modal

**Component**: `<ResponseModal>` — a dialog/modal (`shadcn Dialog`).

**Layout**:

```
┌─────────────────────────────────────────────────────┐
│  Respond to Feedback                            [X] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─ Suggested Template ──────────────────────────┐  │
│  │  📋 Bug Report Acknowledgment                 │  │
│  │  "Hi {{customer_name}}, thank you for..."     │  │
│  │                               [Use this]      │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  [Browse all templates]    [✨ Generate with AI]    │
│                                                     │
│  ─── Response ───────────────────────────────────── │
│                                                     │
│  Tone: [Professional ▾]                             │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │                                               │  │
│  │  (editable textarea with response text)       │  │
│  │                                               │  │
│  │                                               │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Variables: {{customer_name}} {{category}} ...      │
│  (clickable pills that insert at cursor position)   │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Pro: 12/50 AI responses used this month            │
│                                                     │
│  [Copy to clipboard]  [Send via Slack ▾]            │
│                        ├─ Send via Slack             │
│                        ├─ Send via Intercom          │
│                        ├─ Send via Linear            │
│                        └─ Send via Email             │
└─────────────────────────────────────────────────────┘
```

**Template Suggestion Section**:
- Shows the single best-matching template based on the feedback's category + sentiment
- Template body is shown with variables already resolved (using available data)
- "Use this" button loads the template into the editor textarea
- "Browse all templates" opens a sub-view listing all templates (system + custom) grouped by category
- "Generate with AI" triggers LLM generation (counts against monthly limit)

**Tone Dropdown**:
- Options: Professional, Friendly, Empathetic, Concise, Technical
- Defaults to org-wide setting (from Settings)
- Changing tone while AI response is loaded → re-generates with new tone

**Editor Textarea**:
- Plain text / markdown
- Auto-resizes to content
- Variable pills below the textarea — clicking inserts `{{variable_name}}` at cursor position

**Available Variables**:

| Variable | Source | Example Value |
|----------|--------|---------------|
| `{{customer_name}}` | Feedback source metadata | "Sarah Chen" |
| `{{customer_email}}` | `feedback_item.customer_email` | "sarah@acme.com" |
| `{{company_name}}` | Org name or customer company | "Acme Corp" |
| `{{feedback_excerpt}}` | First 200 chars of feedback text | "The export feature keeps failing when..." |
| `{{category}}` | AI-assigned category | "Bug Report" |
| `{{sentiment}}` | Sentiment label | "Negative" |
| `{{source}}` | Feedback source name | "Slack (#support)" |
| `{{product_name}}` | Org setting | "Rereflect" |
| `{{agent_name}}` | Current user's name | "Alex Kim" |
| `{{support_email}}` | Org setting | "support@acme.com" |
| `{{health_score}}` | Customer health score | "42" |
| `{{risk_level}}` | Customer risk level | "High" |
| `{{churn_factors}}` | Top 3 churn risk factors | "Sentiment trend declining, frustration keywords detected" |

**Footer**:
- Usage counter: "12/50 AI responses used this month" (only shown after AI generation, Pro/Business only)
- "Copy to clipboard" button — always available
- "Send via [channel]" dropdown button — shows only channels with active integrations for this feedback's source
  - If feedback came from Slack → "Send via Slack" is primary
  - If no integration connected → only "Copy to clipboard" shown
  - Dropdown lists all connected integrations + "Email to customer" (if customer_email exists)

---

### 5.3 Browse Templates Sub-View

When user clicks "Browse all templates" in the respond modal:

```
┌─────────────────────────────────────────────────────┐
│  ← Back                    Browse Templates         │
├─────────────────────────────────────────────────────┤
│  [Search templates...]                              │
│                                                     │
│  System Templates                                   │
│  ┌───────────────────────────────────────────────┐  │
│  │ 🐛 Bug Report Acknowledgment                  │  │
│  │ Acknowledge the bug and set expectations...   │  │
│  │                                    [Use]      │  │
│  ├───────────────────────────────────────────────┤  │
│  │ 💡 Feature Request Acknowledgment             │  │
│  │ Thank user for suggestion, explain process... │  │
│  │                                    [Use]      │  │
│  ├───────────────────────────────────────────────┤  │
│  │ ...                                           │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Custom Templates (Your Org)                        │
│  ┌───────────────────────────────────────────────┐  │
│  │ 🏢 Enterprise Onboarding Response             │  │
│  │ Welcome enterprise customer with...           │  │
│  │                                    [Use]      │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  [+ Create custom template]                         │
└─────────────────────────────────────────────────────┘
```

---

### 5.4 Settings > Response Templates Page

**Route**: `/settings/response-templates`

**Access**: Admin/Owner only (Members can use templates but not manage them)

**Layout**:

```
┌─────────────────────────────────────────────────────┐
│  Response Templates                   [+ New Template] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Brand Voice (org-wide AI instruction)              │
│  ┌───────────────────────────────────────────────┐  │
│  │ We're a developer tools company. Keep         │  │
│  │ responses technical and concise. Use first    │  │
│  │ person plural ("we"). Never use exclamation   │  │
│  │ marks. Reference documentation links when     │  │
│  │ relevant.                                     │  │
│  └───────────────────────────────────────────────┘  │
│  [Save brand voice]                                 │
│                                                     │
│  Default Tone: [Professional ▾]                     │
│                                                     │
│  Product Name: [Rereflect        ]                  │
│  Support Email: [support@rereflect.ca]              │
│                                                     │
│  ─── System Templates (8) ───────────────────────── │
│                                                     │
│  | Name                    | Category      | Used | │
│  |-------------------------|---------------|------| │
│  | Bug Report Ack          | Bug Report    | 23x  | │
│  | Feature Request Ack     | Feature Req   | 15x  | │
│  | Churn Risk Outreach     | Churn Risk    | 8x   | │
│  | Positive Feedback Thanks| Positive      | 31x  | │
│  | General Complaint       | Complaint     | 12x  | │
│  | Urgent Escalation       | Urgent        | 5x   | │
│  | Follow-up Check-in      | Follow-up     | 9x   | │
│  | Onboarding Help         | Onboarding    | 7x   | │
│                                                     │
│  ─── Custom Templates (2) ───────────────────────── │
│                                                     │
│  | Name                    | Category      | Used | │
│  |-------------------------|---------------|------| │
│  | Enterprise Welcome      | Onboarding    | 3x   | [Edit] [Delete] │
│  | Pricing Question        | Sales         | 1x   | [Edit] [Delete] │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Brand Voice Field**: A textarea (max 500 chars) where the org describes their communication style. This text is prepended to the LLM system prompt when generating AI responses.

**Default Tone**: Dropdown (Professional / Friendly / Empathetic / Concise / Technical). Sets the org-wide default used in the Respond modal.

**Product Name / Support Email**: Used to resolve `{{product_name}}` and `{{support_email}}` variables.

**System templates**: Read-only, cannot be edited or deleted. Show usage count.

**Custom templates**: Full CRUD — create, edit, delete. Each has: name, category, body (with variables).

---

### 5.5 Response Timeline Entry

When a response is generated or sent, it appears in the feedback item's timeline:

```
┌───────────────────────────────────────────────────┐
│ 💬 Alex Kim responded                  2 hours ago │
│                                                   │
│ "Hi Sarah, thank you for reporting this export    │
│ issue. We've identified the root cause and a fix  │
│ will be deployed by end of day..."                │
│                                                   │
│ 📋 Copied to clipboard                            │
│ — or —                                            │
│ ✅ Sent via Slack (#support)                       │
│                                                   │
│ Template: Bug Report Acknowledgment               │
│ — or —                                            │
│ 🤖 AI Generated (Professional tone)               │
└───────────────────────────────────────────────────┘
```

**Timeline entry metadata**:
- Response text (full)
- Method: `copied` | `sent_slack` | `sent_intercom` | `sent_linear` | `sent_email`
- Source: `template:{template_id}` | `ai_generated` | `manual`
- Tone used (for AI-generated)
- User who responded
- Timestamp

---

## 6. Default System Templates

### Template 1: Bug Report Acknowledgment
**Category**: Bug Report
**Body**:
```
Hi {{customer_name}},

Thank you for reporting this issue. We've logged it and our team is looking into it.

Here's what we know so far: your feedback about "{{feedback_excerpt}}" has been categorized and prioritized.

We'll follow up with an update as soon as we have more information. If you have any additional details that might help us reproduce the issue, please don't hesitate to share.

Best regards,
{{agent_name}}
{{product_name}} Team
```

### Template 2: Feature Request Acknowledgment
**Category**: Feature Request
**Body**:
```
Hi {{customer_name}},

Thank you for this feature suggestion! We really appreciate customers who take the time to share ideas for improving {{product_name}}.

Your request has been added to our product backlog and will be reviewed during our next prioritization cycle. While we can't commit to a specific timeline, customer feedback like yours directly influences our roadmap.

If you'd like to add more context or detail about your use case, we'd love to hear it.

Thanks again,
{{agent_name}}
{{product_name}} Team
```

### Template 3: Churn Risk Outreach
**Category**: Churn Risk
**Body**:
```
Hi {{customer_name}},

I wanted to reach out personally because I noticed you've been experiencing some friction with {{product_name}} recently.

Your satisfaction is really important to us, and I'd love to understand how we can improve your experience. Would you be open to a quick 15-minute call this week? I'm happy to work through any issues directly.

If you'd prefer, you can also reply to this message with your concerns and I'll make sure they get addressed promptly.

Looking forward to hearing from you,
{{agent_name}}
{{support_email}}
```

### Template 4: Positive Feedback Thanks
**Category**: Positive
**Body**:
```
Hi {{customer_name}},

Thank you so much for the kind words! It means a lot to our team to hear that {{product_name}} is making a difference for you.

We're always working to make things even better, so if you ever have suggestions or run into anything, don't hesitate to reach out.

Thanks for being a valued customer!

Best,
{{agent_name}}
{{product_name}} Team
```

### Template 5: General Complaint Response
**Category**: Complaint
**Body**:
```
Hi {{customer_name}},

Thank you for sharing your feedback with us. I'm sorry to hear about your experience, and I want you to know we take this seriously.

I've flagged your concern internally and our team will review it. We want to make sure this gets resolved properly.

Could you share any additional details that would help us understand the issue better? We'd like to get this right.

Best regards,
{{agent_name}}
{{support_email}}
```

### Template 6: Urgent Issue Escalation
**Category**: Urgent
**Body**:
```
Hi {{customer_name}},

I see this is a critical issue and I want to assure you it has our immediate attention. Your report has been escalated to our engineering team.

We understand the impact this is having and we're treating it as a top priority. You can expect an update from us within the next few hours.

In the meantime, if there's anything else you need, please reach out directly to {{support_email}} and reference this conversation.

Thank you for your patience,
{{agent_name}}
{{product_name}} Team
```

### Template 7: Follow-up Check-in
**Category**: Follow-up
**Body**:
```
Hi {{customer_name}},

I wanted to follow up on the issue you reported earlier. Has everything been resolved on your end?

We made some changes based on your feedback and I want to make sure things are working smoothly for you now.

If you're still experiencing any issues, or if there's anything else we can help with, please don't hesitate to let us know.

Best,
{{agent_name}}
{{product_name}} Team
```

### Template 8: Onboarding Help
**Category**: Onboarding
**Body**:
```
Hi {{customer_name}},

Welcome to {{product_name}}! I noticed you might be getting started and I wanted to reach out to make sure your onboarding goes smoothly.

Here are a few resources that might help:
- Our getting started guide covers the basics
- You can reach us anytime at {{support_email}}

If you'd like a personalized walkthrough, I'm happy to set up a quick call.

Looking forward to helping you get the most out of {{product_name}}!

Best,
{{agent_name}}
{{product_name}} Team
```

---

## 7. Template Suggestion Algorithm

The AI picks the best matching template using a simple scoring model:

```python
def score_template(template, feedback):
    score = 0

    # Category match (strongest signal)
    if template.category == feedback.category:
        score += 50

    # Sentiment alignment
    sentiment_map = {
        'positive': ['Positive Feedback Thanks'],
        'negative': ['General Complaint', 'Bug Report Ack', 'Churn Risk Outreach'],
        'neutral': ['Feature Request Ack', 'Follow-up Check-in'],
    }
    if template.name in sentiment_map.get(feedback.sentiment, []):
        score += 20

    # Urgency match
    if feedback.is_urgent and template.category == 'Urgent':
        score += 30

    # Churn risk match
    if feedback.churn_risk_score > 70 and template.category == 'Churn Risk':
        score += 25

    return score
```

The template with the highest score is shown as the suggestion. If no template scores above 10, no suggestion is shown (user browses manually or generates with AI).

---

## 8. AI Response Generation

### 8.1 System Prompt

```
You are a customer support AI for {{product_name}}. Generate a response to customer feedback.

{{#if brand_voice}}
Brand voice guidelines:
{{brand_voice}}
{{/if}}

Tone: {{tone}}

Context:
- Feedback: "{{feedback_text}}"
- Category: {{category}}
- Sentiment: {{sentiment}}
- Source: {{source}}
- Customer: {{customer_name}} ({{customer_email}})

Instructions:
- Write a natural, human-sounding response
- Address the specific feedback content
- Match the requested tone
- Keep it concise (3-5 short paragraphs max)
- Do not use placeholder text like "[insert X]"
- Resolve any known information (customer name, product name)
- Sign off with the agent's name
- Do not make promises about timelines unless the feedback is about a known resolved issue
```

### 8.2 LLM Configuration

- **Model**: Uses the org's configured default model (from multi-model settings)
- **Fallback**: System OpenAI if org model fails (existing fallback chain)
- **Max tokens**: 500 (keeps responses concise)
- **Temperature**: 0.7 (natural but not too creative)
- **Timeout**: 15 seconds

### 8.3 Usage Tracking

Each AI generation:
1. Checks monthly limit: `response_count < plan_limit`
2. Increments `ai_responses_generated` counter on `Usage` model
3. Logs to `LLMUsageLog` (existing model) with task_type `response_generation`
4. Returns remaining count in response for frontend display

---

## 9. Send via Integration

### 9.1 Channel Detection

The "Send via [channel]" dropdown shows options based on:

1. **Feedback source**: If the feedback came from Slack, "Send via Slack" is the primary action
2. **Connected integrations**: Only show channels where the org has an active integration
3. **Customer email**: "Send via Email" shown when `feedback_item.customer_email` exists
4. **Fallback**: If no integration is connected for the source, only "Copy to clipboard" is available

### 9.2 Send Implementations

#### Slack — Thread Reply
- Uses existing Slack integration's `access_token`
- Posts a message to the channel + thread_ts from `source_metadata`
- Requires: `source_metadata.channel_id` and `source_metadata.thread_ts` (or `source_metadata.message_ts`)
- API: `chat.postMessage` with `channel` and `thread_ts` params

#### Intercom — Conversation Reply
- Uses existing Intercom integration's `access_token`
- Posts an admin reply to the conversation
- Requires: `source_metadata.conversation_id`
- API: `POST /conversations/{id}/reply` with type `admin` and body

#### Linear — Issue Comment
- Uses existing Linear integration's `access_token`
- Posts a comment on the issue
- Requires: `source_metadata.issue_id`
- API: GraphQL `commentCreate` mutation

#### Email — Via Resend
- Sends an email to `feedback_item.customer_email`
- From: org's configured support email (or `noreply@rereflect.ca`)
- Subject: `Re: {{original_subject}}` (from source_metadata) or `Response from {{product_name}}`
- Body: plain text response
- No template — just sends the response text as email body

### 9.3 Send Response Schema

```python
class SendResponseRequest(BaseModel):
    feedback_id: int
    response_text: str
    channel: Literal['clipboard', 'slack', 'intercom', 'linear', 'email']
    template_id: Optional[int] = None  # if from template
    source: Literal['template', 'ai_generated', 'manual']
    tone: Optional[str] = None  # if AI generated
```

### 9.4 Error Handling

- If send fails (token expired, channel deleted, conversation closed): show error toast, response text stays in editor, offer "Copy to clipboard" as fallback
- Don't save to timeline as "sent" if send failed — save as "send_failed" with error reason
- Retry logic: no automatic retry. User can click "Send" again.

---

## 10. Data Model

### 10.1 New Models

#### ResponseTemplate

```python
class ResponseTemplate(Base):
    __tablename__ = 'response_templates'

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)  # null = system template
    name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False)
    body = Column(Text, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

#### FeedbackResponse

```python
class FeedbackResponse(Base):
    __tablename__ = 'feedback_responses'

    id = Column(Integer, primary_key=True)
    feedback_id = Column(Integer, ForeignKey('feedback_items.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    response_text = Column(Text, nullable=False)
    channel = Column(String(50), nullable=False)  # clipboard, slack, intercom, linear, email
    source = Column(String(50), nullable=False)  # template, ai_generated, manual
    template_id = Column(Integer, ForeignKey('response_templates.id', ondelete='SET NULL'), nullable=True)
    tone = Column(String(50), nullable=True)
    status = Column(String(50), default='sent', nullable=False)  # sent, copied, send_failed
    error_message = Column(Text, nullable=True)  # if send_failed
    created_at = Column(DateTime, server_default=func.now())
```

#### OrgResponseSettings (new columns on Organization or separate model)

```python
# Add to Organization model or create OrgResponseSettings
brand_voice = Column(Text, nullable=True)  # max 500 chars
default_tone = Column(String(50), default='professional', nullable=True)
product_name_display = Column(String(200), nullable=True)
support_email = Column(String(200), nullable=True)
```

### 10.2 Indexes

```python
Index('ix_response_templates_org', 'organization_id')
Index('ix_response_templates_category', 'organization_id', 'category')
Index('ix_feedback_responses_feedback', 'feedback_id')
Index('ix_feedback_responses_org', 'organization_id')
Index('ix_feedback_responses_user', 'user_id')
```

---

## 11. API Endpoints

### 11.1 Response Templates

```
GET    /api/v1/response-templates                    # List all (system + org custom)
POST   /api/v1/response-templates                    # Create custom template (admin/owner)
GET    /api/v1/response-templates/{id}               # Get template detail
PUT    /api/v1/response-templates/{id}               # Update custom template (admin/owner)
DELETE /api/v1/response-templates/{id}               # Delete custom template (admin/owner)
POST   /api/v1/response-templates/suggest            # Get best template for a feedback item
```

### 11.2 Feedback Responses

```
GET    /api/v1/feedback/{id}/responses               # List responses for a feedback item
POST   /api/v1/feedback/{id}/responses               # Save a response (copy/send)
POST   /api/v1/feedback/{id}/responses/generate      # AI-generate a response (counts against limit)
POST   /api/v1/feedback/{id}/responses/send           # Send response via integration channel
```

### 11.3 Response Settings

```
GET    /api/v1/response-settings                     # Get org response settings (brand voice, tone, etc.)
PUT    /api/v1/response-settings                     # Update org response settings (admin/owner)
GET    /api/v1/response-settings/usage               # Get AI response usage this month
```

### 11.4 Request/Response Schemas

```python
# POST /response-templates
class CreateTemplateRequest(BaseModel):
    name: str = Field(max_length=200)
    category: str = Field(max_length=100)
    body: str

# POST /feedback/{id}/responses/generate
class GenerateResponseRequest(BaseModel):
    tone: Optional[str] = None  # overrides org default

class GenerateResponseResponse(BaseModel):
    response_text: str
    tokens_used: int
    remaining_this_month: int

# POST /feedback/{id}/responses/send
class SendResponseRequest(BaseModel):
    response_text: str
    channel: Literal['clipboard', 'slack', 'intercom', 'linear', 'email']
    source: Literal['template', 'ai_generated', 'manual']
    template_id: Optional[int] = None
    tone: Optional[str] = None

class SendResponseResponse(BaseModel):
    success: bool
    response_id: int
    channel: str
    error: Optional[str] = None

# POST /response-templates/suggest
class SuggestTemplateRequest(BaseModel):
    feedback_id: int

class SuggestTemplateResponse(BaseModel):
    template: Optional[ResponseTemplateOut] = None
    score: int

# GET /response-settings/usage
class ResponseUsageResponse(BaseModel):
    ai_responses_generated: int
    monthly_limit: int  # -1 for unlimited
    templates_used: int
    responses_sent: int
```

---

## 12. Plan Gating

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| Respond button visible | Yes (upgrade CTA) | Yes | Yes | Yes |
| Use templates | No | Unlimited | Unlimited | Unlimited |
| AI-generated responses | No | 50/month | 500/month | Unlimited |
| Send via integration | No | Yes | Yes | Yes |
| Custom templates | No | Yes | Yes | Yes |
| Brand voice settings | No | Yes | Yes | Yes |
| Response history | No | Yes | Yes | Yes |

**Feature ID**: `response_suggestions` (added to Pro+ features in `plans.py`)

**Usage tracking**: `ai_responses_generated` counter on the monthly `Usage` model (same pattern as feedback limits).

---

## 13. RBAC

| Action | Owner | Admin | Member |
|--------|-------|-------|--------|
| Use "Respond" button | Yes | Yes | Yes |
| Use templates | Yes | Yes | Yes |
| Generate AI response | Yes | Yes | Yes |
| Send via integration | Yes | Yes | Yes |
| Manage templates (create/edit/delete) | Yes | Yes | No |
| Edit brand voice / response settings | Yes | Yes | No |

---

## 14. Implementation Phases

### Phase 1: Backend Foundation (~3 days)
1. Alembic migration: `response_templates`, `feedback_responses` tables, org response settings columns
2. SQLAlchemy models: `ResponseTemplate`, `FeedbackResponse`
3. Seed 8 system templates (migration or startup script)
4. Response templates CRUD endpoints (list, create, get, update, delete)
5. Template suggestion endpoint with scoring algorithm
6. Response settings endpoints (get, update brand voice/tone/product name/support email)
7. Plan gating: `response_suggestions` feature in `plans.py`

### Phase 2: AI Generation (~2 days)
1. Response generation endpoint with LLM prompt construction
2. Variable resolution service (resolve `{{var}}` from feedback + customer + org data)
3. Usage tracking (increment counter, check limits, return remaining)
4. Integration with existing multi-model LLM system (use org's configured model)

### Phase 3: Send via Integration (~2 days)
1. Send response endpoint with channel routing
2. Slack: thread reply via `chat.postMessage`
3. Intercom: admin reply via conversations API
4. Linear: comment via GraphQL `commentCreate`
5. Email: send via Resend with customer_email as recipient
6. Error handling: save `send_failed` status with error message
7. Save response to `feedback_responses` table (all channels including clipboard)

### Phase 4: Frontend — Response Modal (~3 days)
1. `ResponseModal` component (Dialog with template suggestion, editor, send buttons)
2. "Respond" button on feedback detail page with plan gating
3. Template suggestion display (best match, "Use this" button)
4. "Browse all templates" sub-view with search
5. "Generate with AI" button with loading state
6. Tone dropdown (defaults to org setting)
7. Variable pills (clickable insert at cursor)
8. "Copy to clipboard" + "Send via [channel]" dropdown
9. Usage counter display
10. Response saved → appears in feedback timeline

### Phase 5: Frontend — Settings & Polish (~2 days)
1. Settings > Response Templates page
2. Brand voice textarea + default tone dropdown + product name + support email
3. System templates list (read-only, usage count)
4. Custom templates CRUD (create/edit/delete dialogs)
5. Usage stats in AI Settings section (responses generated/sent this month)
6. Free plan upgrade CTA modal
7. Error handling (send failures, limit exceeded)

---

## 15. Key Files (Planned)

### Backend
- `src/models/response_template.py` — ResponseTemplate model
- `src/models/feedback_response.py` — FeedbackResponse model
- `src/api/routes/response_templates.py` — Template CRUD + suggestion endpoints
- `src/api/routes/feedback_responses.py` — Response generation, send, history endpoints
- `src/api/routes/response_settings.py` — Brand voice, tone, product name settings
- `src/services/response_generator.py` — LLM prompt construction, variable resolution
- `src/services/response_sender.py` — Channel-specific send logic (Slack, Intercom, Linear, Email)
- `src/config/plans.py` — Add `response_suggestions` feature
- `alembic/versions/xxx_add_response_templates_and_responses.py` — Migration

### Frontend
- `components/feedback/ResponseModal.tsx` — Main respond modal
- `components/feedback/TemplateBrowser.tsx` — Browse all templates sub-view
- `components/feedback/ResponseTimeline.tsx` — Response entry in timeline
- `app/(dashboard)/settings/response-templates/page.tsx` — Template management page
- `lib/api/responses.ts` — API client functions

---

## 16. Verification

1. `cd services/backend-api && pytest tests/ -v` — all tests pass
2. `cd services/frontend-web && npm run build` — builds without errors
3. Manual test: open feedback item → click Respond → see template suggestion → use template → copy to clipboard → verify timeline entry
4. Manual test: click "Generate with AI" → verify response generated → edit → send via Slack → verify Slack thread reply
5. Manual test: create custom template in Settings → use it from Respond modal
6. Manual test: Free plan user → sees upgrade CTA
7. Manual test: Pro user → generate 50 responses → verify limit enforcement
8. Manual test: set brand voice → generate AI response → verify tone matches

---

## 17. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Slack/Intercom tokens expired when sending | Check token validity before showing "Send via" option, show error + fallback to copy |
| LLM generates inappropriate response | User always reviews before sending (no auto-send), brand voice guidelines help |
| Variable resolution fails (missing customer data) | Graceful fallback: unresolved variables rendered as empty string, not `{{var}}` |
| Response sent to wrong thread/conversation | Validate source_metadata has required IDs before enabling send option |
| Monthly limit confusion | Clear counter in modal footer, warning at 80% usage, upgrade CTA at limit |
