import type { BlogPost } from '../blog';

// Cluster: Integrations, API, webhooks & automation
export const batch5: BlogPost[] = [
  {
    slug: 'connect-slack-to-customer-feedback',
    title: 'Connect Slack to Your Customer Feedback Pipeline',
    excerpt:
      'Rereflect can push feedback alerts directly to Slack — so urgent churn signals, new pain points, and sentiment shifts surface in the channels your team already watches, without anyone having to log into a dashboard.',
    date: '2026-11-03',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['Integrations', 'Slack', 'Alerts', 'Automation'],
    seoTitle: 'Connect Slack to Customer Feedback Analysis | Rereflect',
    seoDescription:
      'Learn how to wire Rereflect to Slack so urgent feedback, churn signals, and pain-point spikes appear in the right channels automatically.',
    sections: [
      {
        heading: 'Why Slack and not just email',
        content: [
          'Feedback dashboards are only useful if people actually open them. In practice, the team members who most need to act on a piece of feedback — a support lead, a product manager, an engineer on-call — are already living in Slack. If a customer posts a churn-risk signal at 4 pm on a Thursday, a notification in your #customer-feedback channel is far more likely to get a response than an email digest that lands overnight.',
          'Rereflect\'s Slack integration is designed around that reality. Instead of pulling people to a new tool, it pushes the right signal to the place where decisions already happen.',
        ],
      },
      {
        heading: 'What gets sent to Slack',
        content: [
          'The integration is rule-driven, so you control exactly what triggers a notification. Common setups include:',
        ],
        listItems: [
          'Urgent feedback — any item the AI flags as a churn risk or high-urgency issue gets posted to a dedicated channel immediately.',
          'Negative sentiment spikes — a daily or weekly digest fires when the negative-sentiment ratio crosses a threshold you define.',
          'New pain-point categories — when the analyzer surfaces a pain point cluster that has not appeared before, a one-line summary lands in #product.',
          'High-volume feature requests — when a feature request reaches a count you set, it gets surfaced for triage.',
          'Webhook fallthrough — anything not caught by a more specific rule can be routed to a catch-all channel for later review.',
        ],
        content2: [
          'Each Slack message includes the feedback excerpt, the AI-assigned sentiment label, the pain-point or feature category, and a direct link back to the full record in Rereflect. Your team can read the signal and jump into context in one click.',
        ],
      },
      {
        heading: 'Setting up the integration',
        content: [
          'The integration uses an incoming webhook URL generated from the Slack app you install in your workspace. Rereflect stores that URL per-organization and uses it when a routing rule fires.',
          'The setup path in Rereflect is: Settings → Integrations → Slack → paste your Slack webhook URL → Save. From there you configure which rule types post to which channel. You can use a single webhook for everything, or create multiple Slack apps pointing at different channels and route different rule types accordingly.',
        ],
        listItems: [
          '1. Create a Slack app in your workspace and add an incoming webhook scoped to your target channel.',
          '2. Copy the webhook URL from the Slack app configuration.',
          '3. Paste it into Rereflect under Settings → Integrations → Slack.',
          '4. Create one or more routing rules that send to that webhook (Automation → Rules).',
          '5. Send a test feedback item that matches a rule to confirm the message lands.',
        ],
      },
      {
        heading: 'Keeping Slack from becoming noise',
        content: [
          'The most common complaint about alert integrations is that they produce so many messages that people start ignoring the channel. A few practices help keep the signal clean:',
        ],
        listItems: [
          'Use threshold rules, not raw volume — fire on "sentiment score below 0.2" rather than "any negative feedback", so minor gripes do not flood the channel.',
          'Separate channels by urgency — urgent/churn-risk to a #alerts-urgent channel, general trends to a #feedback-digest channel.',
          'Batch low-priority digests — configure daily digest rules instead of per-item rules for anything that does not need an immediate response.',
          'Review and prune rules quarterly — as your product matures, the categories that matter change. Rules that were useful at launch can become noise later.',
        ],
        content2: [
          'The goal is to make the #customer-feedback channel a place where a message means something. That takes a bit of initial configuration, but it is worth it — the teams that get the most value from the integration are the ones that treat their alert rules as a living configuration rather than a one-time setup.',
        ],
      },
      {
        heading: 'Self-hosted notes',
        content: [
          'Because Rereflect is self-hosted, the webhook URL you configure lives in your own database and your own environment variables. The outbound HTTP call to the Slack API goes from your server directly — no Rereflect cloud service is involved. If your deployment is behind a firewall or VPN, make sure outbound HTTPS to Slack\'s API endpoints is permitted from your Rereflect host.',
          'The integration is part of the core open-source codebase, not a premium add-on. If you have Rereflect running, you have the Slack integration available — it just needs a webhook URL and a routing rule.',
        ],
      },
    ],
  },
  {
    slug: 'intercom-feedback-integration-guide',
    title: 'Collecting and Analyzing Intercom Conversations in Rereflect',
    excerpt:
      'Intercom conversations are a rich, underused source of structured customer feedback. This guide covers how to pipe Intercom data into Rereflect for AI analysis — sentiment scoring, pain point extraction, and churn risk detection — without writing a custom integration from scratch.',
    date: '2026-11-05',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['Integrations', 'Intercom', 'Customer Support', 'AI Analysis'],
    seoTitle: 'Intercom Feedback Integration Guide | Rereflect',
    seoDescription:
      'Learn how to bring Intercom conversation data into Rereflect for AI-powered sentiment analysis, pain point detection, and churn risk scoring.',
    sections: [
      {
        heading: 'Why Intercom conversations are worth analyzing',
        content: [
          'Support conversations carry a different quality of signal than surveys or NPS scores. A customer writing into Intercom is usually experiencing a problem right now — the friction is fresh, the language is unguarded, and the category of problem is concrete. Aggregated over weeks and months, that corpus tells you exactly which parts of your product are breaking down and for whom.',
          'The challenge is volume. A team handling hundreds of Intercom conversations a week cannot manually read every thread for patterns. That is the gap Rereflect fills: bulk ingestion, automated categorization, and trend detection that surfaces the signal without requiring a human to read everything.',
        ],
      },
      {
        heading: 'How the integration works',
        content: [
          'Rereflect does not have a native one-click Intercom connector (yet), but the path is straightforward using a combination of Intercom\'s export, webhook, or API capabilities alongside Rereflect\'s ingestion API.',
          'The most common setup depends on your volume and cadence:',
        ],
        listItems: [
          'Export + CSV import — Intercom lets you export conversation data as CSV. Import that file into Rereflect periodically (daily or weekly). Good for teams getting started without engineering time.',
          'Intercom webhooks → Rereflect API — configure Intercom to fire a webhook on conversation_closed or note_created events, and write a small handler that posts the conversation text to the Rereflect POST /api/v1/feedback endpoint. New conversations land in Rereflect within seconds of closing.',
          'Intercom API polling — use the Intercom REST API to pull resolved conversations on a schedule and push them to Rereflect in batches. Works well if you already have a backend service you can add a cron job to.',
        ],
        content2: [
          'For teams that want real-time analysis, the webhook approach is the right choice. For teams that just want historical trend data, periodic CSV imports get you there with no code.',
        ],
      },
      {
        heading: 'What Rereflect does with Intercom data',
        content: [
          'Once conversation text lands in Rereflect, the same AI analysis pipeline that handles any other feedback source runs on it. That means:',
        ],
        listItems: [
          'Sentiment scoring — each conversation gets a positive, neutral, or negative label and a numeric score.',
          'Pain point extraction — the AI categorizes the core complaint or friction point using your taxonomy (billing, onboarding, performance, data export, etc.).',
          'Feature request detection — if the conversation includes a request ("it would be great if..."), it is extracted and tagged.',
          'Urgency and churn risk — explicit cancellation intent, expressions of frustration, or patterns matching your churn model flag the record as urgent.',
          'Customer linkage — if you include a customer_id or email in the ingestion payload, the conversation is linked to that customer\'s health profile.',
        ],
      },
      {
        heading: 'Structuring the ingestion payload',
        content: [
          'When using the API or webhook handler to push Intercom data, the ingestion payload shape matters. A minimal POST to /api/v1/feedback looks like this:',
          'POST /api/v1/feedback',
          '{ "content": "<conversation text>", "source": "intercom", "customer_id": "<intercom_contact_id>", "metadata": { "conversation_id": "<intercom_id>", "closed_at": "<ISO8601 timestamp>" } }',
          'Including the source field (set to "intercom") lets you filter your Rereflect dashboard by source, so you can compare Intercom sentiment against survey or review-site data. The metadata object is a freeform JSON blob — you can put any Intercom fields you want to preserve there without any schema changes on the Rereflect side.',
        ],
      },
      {
        heading: 'Practical tips',
        content: [
          'A few things that come up repeatedly when teams set this integration up:',
        ],
        listItems: [
          'Exclude bot messages — if Intercom uses an automated bot for initial triage, strip those messages from the conversation text before ingestion. The AI will treat bot-generated text as customer sentiment, which skews results.',
          'Use resolved conversations only — open conversations are incomplete; closed ones represent a full interaction and give the AI enough context to categorize accurately.',
          'Deduplicate on conversation_id — if you are both doing periodic exports and have a webhook, you may push the same conversation twice. Store conversation IDs in your handler and skip duplicates.',
          'Test with a small batch first — import 20-30 conversations manually and review the AI categorization before switching to automated ingestion. This is the fastest way to tune your custom categories for the language your customers actually use.',
        ],
      },
    ],
  },
  {
    slug: 'create-linear-issues-from-feedback',
    title: 'Automatically Create Linear Issues from Customer Feedback',
    excerpt:
      'When Rereflect identifies a recurring pain point or a high-priority feature request, the next step is usually creating a ticket. This guide shows how to close that loop automatically — routing AI-analyzed feedback into Linear issues without manual copy-paste.',
    date: '2026-11-07',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['Integrations', 'Linear', 'Automation', 'Product Management'],
    seoTitle: 'Create Linear Issues from Customer Feedback Automatically | Rereflect',
    seoDescription:
      'Learn how to route AI-analyzed customer feedback from Rereflect into Linear issues automatically — closing the loop between customer signal and engineering backlog.',
    sections: [
      {
        heading: 'The gap between feedback and tickets',
        content: [
          'Most teams collect customer feedback in one system and manage engineering work in another. The bridge between them — deciding which feedback warrants a ticket, writing that ticket, and getting it into the backlog — is manual work that usually falls on a product manager or support lead. It is slow, it is inconsistent, and things fall through the cracks.',
          'The automation pattern that works well in practice: Rereflect analyzes incoming feedback, and when it matches a rule (a specific pain point category, a feature request that has now been mentioned more than N times, or an urgent churn-risk item), it fires a webhook. A small handler picks up that webhook and creates a Linear issue with the relevant context already filled in.',
        ],
      },
      {
        heading: 'Architecture of the integration',
        content: [
          'The integration has three parts: Rereflect routing rules, an outbound webhook, and a handler that calls the Linear API.',
        ],
        listItems: [
          'Routing rule — define a rule in Rereflect (Automation → Rules) that fires when, for example, pain_point_category equals "data-export" and sentiment equals "negative". Set the action to call a webhook URL.',
          'Webhook handler — a small HTTP endpoint (a Vercel function, a Cloudflare Worker, or a route in your existing backend) receives the Rereflect webhook payload and extracts the fields you want in the ticket: the feedback excerpt, the AI-assigned category, the customer ID, and the urgency flag.',
          'Linear API call — the handler calls the Linear GraphQL API to create an issue in the target team and project, using the extracted fields to populate the title, description, and labels.',
        ],
        content2: [
          'The whole path from feedback submission to Linear issue creation can run in under five seconds. The product manager sees a ticket appear in the backlog with a pre-written description and the right labels — they do not have to figure out where it came from or what it means.',
        ],
      },
      {
        heading: 'What the Linear issue looks like',
        content: [
          'A well-structured auto-created issue should give an engineer or PM all the context they need without clicking through to Rereflect. A typical template:',
          'Title: [Pain Point] Data Export — customer reported failure on large CSV downloads',
          'Description: Customer feedback (2026-11-06): "The export button just spins for five minutes and then shows a generic error. I need this to send to my accountant." — Sentiment: Negative (score: 0.14) — Category: Data Export — Urgency: High — Customer ID: cust_abc123 — View in Rereflect: https://your-rereflect.example.com/feedbacks/f_xyz789',
          'Labels: customer-reported, pain-point, high-urgency',
          'This structure means the issue is immediately actionable. The engineer can read the raw customer quote, understand the severity, and link back to the full record if they need more context.',
        ],
      },
      {
        heading: 'Deduplication and grouping',
        content: [
          'One concern with automated issue creation is creating dozens of duplicate tickets for the same underlying problem. A few strategies help:',
        ],
        listItems: [
          'Threshold-based triggers — do not fire on the first mention of a pain point; fire when it has been mentioned more than a threshold you set (e.g., 5 unique customers in the last 30 days). This ensures the issue represents a real pattern, not a one-off.',
          'Check before creating — before calling the Linear API, search for existing open issues with the same pain-point label. If one exists, add a comment with the new feedback excerpt instead of creating a new issue.',
          'Use Rereflect\'s grouping data — the API response includes a cluster_id for related feedback items. Use that to link new feedback to an existing issue rather than creating a new one.',
          'Cool-down period — configure the routing rule to fire at most once per 24 hours per pain-point category, preventing a spike of similar feedback from creating many tickets simultaneously.',
        ],
      },
      {
        heading: 'Extending the pattern to other issue trackers',
        content: [
          'The same pattern works for GitHub Issues, Jira, Shortcut, or any tracker with an API. The Rereflect webhook payload is the same regardless of where you route it — the handler is the only thing that changes. If your team switches trackers, you update the handler and leave the Rereflect configuration untouched.',
          'This is the advantage of building the integration on webhooks rather than a native connector: you own the mapping logic, you can customize the issue format, and you are not locked into whatever a pre-built integration decided the ticket should look like.',
        ],
      },
    ],
  },
  {
    slug: 'zendesk-feedback-analysis-integration',
    title: 'Analyzing Zendesk Tickets with Rereflect',
    excerpt:
      'Zendesk ticket data is a concentrated source of customer frustration — and often the most under-analyzed corpus a support-heavy team has. This guide covers how to route Zendesk ticket content into Rereflect for systematic AI analysis.',
    date: '2026-11-10',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['Integrations', 'Zendesk', 'Customer Support', 'AI Analysis'],
    seoTitle: 'Zendesk Feedback Analysis Integration Guide | Rereflect',
    seoDescription:
      'Learn how to pull Zendesk ticket data into Rereflect for AI-powered sentiment scoring, pain point categorization, and churn risk detection.',
    sections: [
      {
        heading: 'What Zendesk data tells you',
        content: [
          'Zendesk tickets are customer-initiated, unguarded, and specific. Unlike surveys (which ask structured questions) or NPS scores (which give you a number with no context), a support ticket describes exactly what went wrong, in the customer\'s own words, at the moment they were frustrated enough to write in.',
          'At low volumes you can read every ticket. At scale, you cannot — and that is when the same patterns repeat invisibly across hundreds of tickets while no one has the bandwidth to connect the dots. AI analysis changes that: you can find the patterns the same day they emerge, not in the quarterly review.',
        ],
      },
      {
        heading: 'Three paths from Zendesk to Rereflect',
        content: [
          'The right integration path depends on your team\'s engineering capacity and how real-time you need the analysis to be.',
        ],
        listItems: [
          'CSV export (no code) — Zendesk\'s export UI lets you download resolved tickets as CSV. Upload to Rereflect\'s bulk import. Good for a one-time historical analysis or a weekly manual pull.',
          'Zendesk webhook → Rereflect API (real-time) — configure a Zendesk trigger to fire when a ticket is solved, sending the ticket body and requester metadata to a handler endpoint. The handler posts the ticket content to POST /api/v1/feedback. New solved tickets appear in Rereflect within seconds.',
          'Zendesk API polling (scheduled) — use the Zendesk REST API (GET /api/v2/tickets?status=solved) to fetch resolved tickets on a schedule and push them to Rereflect in batches. Works without a public webhook endpoint.',
        ],
        content2: [
          'For teams that want ongoing trend analysis without writing code, the weekly CSV export is a reasonable starting point. For teams that want the analysis available when a ticket closes — so support leads can see patterns before the end-of-day standup — the webhook path is worth the setup time.',
        ],
      },
      {
        heading: 'Mapping Zendesk fields to the ingestion payload',
        content: [
          'When pushing Zendesk tickets via the API, mapping the right fields into the Rereflect payload makes the output more useful:',
          'POST /api/v1/feedback',
          '{ "content": "<ticket description + latest comment>", "source": "zendesk", "customer_id": "<requester email or zendesk user id>", "metadata": { "ticket_id": "<zendesk_ticket_id>", "ticket_subject": "<subject>", "tags": ["billing", "urgent"], "created_at": "<ISO8601>" } }',
          'The content field should include the ticket description and, optionally, the customer\'s most recent comment — not agent notes or internal comments, which introduce noise. The metadata blob accepts anything you want to carry through; ticket_id lets you link back to Zendesk from the Rereflect UI.',
        ],
      },
      {
        heading: 'Using Zendesk tags to seed Rereflect categories',
        content: [
          'If your Zendesk agents already apply tags to tickets (billing-issue, feature-request, integration-bug), you can pass those tags in the metadata and use them to pre-populate Rereflect\'s category field. This gives the AI a hint and can improve categorization accuracy on your specific taxonomy.',
          'The approach: include the Zendesk tags in the metadata object, then write a pre-processing step in your handler that maps known Zendesk tags to Rereflect category slugs before posting. Unmapped tags still land in the metadata and are preserved for search, they just do not influence the AI category.',
        ],
        listItems: [
          'billing-issue → pain_point_category: "billing"',
          'feature-request → is_feature_request: true',
          'churn-risk → urgency: "high"',
          'integration-bug → pain_point_category: "integrations"',
        ],
      },
      {
        heading: 'What to do with the analysis',
        content: [
          'Once Zendesk ticket data flows into Rereflect, the dashboard gives you trend views that are difficult to produce from Zendesk alone: which pain point categories are growing week-over-week, which customer segments generate the most negative sentiment, and which ticket themes co-occur with churn events.',
          'A common workflow: route the Zendesk integration output to a weekly Slack digest that summarizes the top three pain point categories from the past week\'s resolved tickets. Support leads get a structured summary without reading every ticket; product managers get data to prioritize against.',
        ],
      },
    ],
  },
  {
    slug: 'feedback-webhooks-real-time-events',
    title: 'Using Webhooks for Real-Time Feedback Events',
    excerpt:
      'Rereflect can fire outbound webhooks when feedback is analyzed — letting your own systems react to sentiment shifts, urgency flags, and pain point detections the moment they happen. This guide covers the webhook payload shape, delivery guarantees, and patterns for consuming events reliably.',
    date: '2026-11-12',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['Webhooks', 'API', 'Automation', 'Real-Time'],
    seoTitle: 'Feedback Webhooks: Real-Time Events from Rereflect | Rereflect',
    seoDescription:
      'Learn how Rereflect outbound webhooks work — payload shape, event types, delivery behavior, and patterns for building reliable consumers.',
    sections: [
      {
        heading: 'What webhooks unlock',
        content: [
          'Polling the Rereflect API for new feedback works, but it introduces latency proportional to your polling interval and burns API quota on requests that often return nothing new. Webhooks invert that model: Rereflect calls you when something happens, and your system reacts immediately.',
          'The practical effect is that a high-urgency piece of feedback can trigger a Slack alert, create a Linear issue, update a CRM record, or kick off a custom workflow within seconds of the AI analysis completing — with no polling loop and no human in the middle.',
        ],
      },
      {
        heading: 'Event types',
        content: [
          'Rereflect currently fires webhooks on the following event types. You subscribe to the ones you care about when configuring a webhook endpoint.',
        ],
        listItems: [
          'feedback.analyzed — fires after the AI pipeline finishes processing a piece of feedback. Payload includes the raw content, all AI-assigned labels, scores, and categories.',
          'feedback.urgent — fires when a feedback item is flagged as urgent (churn risk, explicit cancellation intent, or a high-severity pain point). A subset of feedback.analyzed events.',
          'customer.health_changed — fires when a customer\'s computed health score crosses a threshold (configurable). Useful for CRM sync or proactive outreach triggers.',
          'pain_point.threshold_reached — fires when a pain point category reaches a count you set (e.g., 10 mentions of "billing" this week). Useful for issue-tracker automation.',
          'feature_request.threshold_reached — same pattern for feature requests.',
        ],
      },
      {
        heading: 'Payload shape',
        content: [
          'All webhook events follow the same envelope structure:',
          '{ "event": "feedback.analyzed", "occurred_at": "2026-11-12T14:23:01Z", "organization_id": "org_abc123", "data": { "feedback_id": "f_xyz789", "content": "...", "source": "intercom", "sentiment": "negative", "sentiment_score": 0.12, "pain_point_category": "billing", "is_feature_request": false, "is_urgent": true, "customer_id": "cust_def456", "analyzed_at": "2026-11-12T14:23:00Z" } }',
          'The data object shape varies by event type — a pain_point.threshold_reached event carries the category, the count, and the time window rather than a single feedback record. The envelope fields (event, occurred_at, organization_id) are always present.',
        ],
      },
      {
        heading: 'Delivery behavior and retries',
        content: [
          'Rereflect delivers webhooks over HTTPS with a 10-second timeout per attempt. If your endpoint returns a non-2xx status or times out, Rereflect retries with exponential backoff — once after 30 seconds, once after 5 minutes, once after 30 minutes. After three failed attempts, the event is marked as failed and logged; it will not be retried further.',
          'Implications for your consumer:',
        ],
        listItems: [
          'Respond fast — return 200 immediately and process the payload asynchronously. If your handler does expensive work (a Linear API call, a database write) synchronously, you risk timeouts under load.',
          'Idempotency — you may receive the same event more than once (network issues can cause re-delivery even after a 200). Use the feedback_id or a compound (event, feedback_id) key to deduplicate.',
          'Verify the source — Rereflect signs webhook payloads with an HMAC-SHA256 signature in the X-Rereflect-Signature header. Always verify this before processing the payload to prevent spoofed requests.',
        ],
      },
      {
        heading: 'Registering and managing endpoints',
        content: [
          'Webhook endpoints are managed through the Rereflect UI (Settings → Integrations → Webhooks) or via the API (POST /api/v1/webhooks). Each endpoint has a URL, a list of subscribed event types, and an auto-generated signing secret.',
          'You can register multiple endpoints — one for your Slack handler, one for your Linear handler, one for your CRM sync — each subscribed to only the event types it needs. Event routing is per-endpoint, not global. The delivery log in the UI shows the HTTP status and response body for recent deliveries, which is useful for debugging consumer failures without needing to instrument your own handler.',
        ],
      },
    ],
  },
  {
    slug: 'automate-feedback-routing-with-rules',
    title: 'Automating Feedback Routing with Rules',
    excerpt:
      'Manual triage does not scale. Rereflect\'s rule engine lets you define conditions — sentiment, category, urgency, source, customer segment — and map them to actions like Slack notifications, webhook calls, or email alerts. This guide covers how to build a routing system that handles the common cases automatically.',
    date: '2026-11-14',
    status: 'scheduled',
    readTime: '9 min read',
    author: 'Rereflect Team',
    tags: ['Automation', 'Rules', 'Routing', 'Workflow'],
    seoTitle: 'Automate Feedback Routing with Rules | Rereflect',
    seoDescription:
      'Build a feedback routing system using Rereflect\'s rule engine — route urgent items to Slack, send pain points to Linear, and trigger webhooks based on sentiment and category.',
    sections: [
      {
        heading: 'Why routing rules matter',
        content: [
          'The value of AI analysis is not just the labels it assigns — it is what happens next. A piece of feedback marked "urgent, billing, negative" has no impact if it sits in a dashboard that nobody checks. The goal of a routing system is to ensure that the right signal reaches the right person through the right channel automatically, without anyone having to manually monitor the queue.',
          'Rereflect\'s rule engine is the mechanism for expressing that logic. Rules are condition-action pairs that evaluate against every feedback item after analysis completes. If the conditions match, the action fires.',
        ],
      },
      {
        heading: 'Anatomy of a rule',
        content: [
          'Each rule has three parts:',
        ],
        listItems: [
          'Name — a human-readable label so you remember what the rule does when you come back to it six months later.',
          'Conditions — one or more logical tests on feedback fields. Fields available for conditions include: sentiment (equals/not equals), sentiment_score (greater/less than), pain_point_category (in list / not in list), is_urgent (boolean), is_feature_request (boolean), source (equals), customer_id (matches pattern), and metadata keys you populate at ingestion time.',
          'Action — what fires when all conditions match. Currently supported actions: send Slack notification (to a webhook URL), call an outbound webhook (arbitrary HTTPS endpoint), send email (to a list of addresses), and add a tag to the feedback item.',
        ],
        content2: [
          'Conditions within a single rule are AND\'ed together: all conditions must match for the action to fire. To express OR logic (fire if sentiment is negative OR if item is urgent), create two separate rules that share the same action.',
        ],
      },
      {
        heading: 'A practical ruleset to start with',
        content: [
          'Most teams converge on a similar starting configuration. Here is a ruleset that covers the most common cases:',
        ],
        table: {
          headers: ['Rule name', 'Conditions', 'Action'],
          rows: [
            ['Urgent churn alert', 'is_urgent = true', 'Slack → #alerts-urgent'],
            ['Billing pain points', 'pain_point_category = billing AND sentiment = negative', 'Slack → #team-billing + webhook → Linear handler'],
            ['High-value customer negative', 'sentiment_score < 0.15 AND metadata.plan = enterprise', 'Email → csm@example.com'],
            ['Feature request triage', 'is_feature_request = true AND sentiment != positive', 'Slack → #product-requests'],
            ['Onboarding friction', 'pain_point_category = onboarding', 'Webhook → internal Notion handler'],
          ],
        },
      },
      {
        heading: 'Rate limiting and cool-down',
        content: [
          'Without rate limiting, a single burst of similar feedback — say, an outage that generates 50 "downtime" tickets in an hour — can flood your Slack channel with 50 identical-looking alerts. Rules support a per-rule cool-down period: once a rule fires, it will not fire again for the same category + source combination until the cool-down expires.',
          'Reasonable defaults: 15 minutes for urgent alerts (you want to know quickly but not get paged every 30 seconds), 24 hours for pain-point threshold notifications (daily rollup is enough), and no cool-down for high-value customer rules (every enterprise customer complaint deserves its own alert).',
        ],
      },
      {
        heading: 'Iterating on your rules over time',
        content: [
          'A routing configuration that made sense when you had 100 customers per month will have different failure modes when you have 1,000. Common iteration triggers:',
        ],
        listItems: [
          'Channel is too noisy — tighten the conditions (add a sentiment_score threshold, restrict to a specific source) or increase the cool-down.',
          'Urgent items are being missed — the is_urgent condition is too restrictive; add a secondary rule that catches sentiment_score below a raw threshold even without the urgency flag.',
          'New integration added — add a source condition to route Intercom tickets differently from Zendesk tickets.',
          'Team structure changed — update the Slack channel or email list in the action; the condition stays the same.',
          'Pain point taxonomy updated — if you renamed a category, update the condition values that reference it. The UI shows you which rules reference each category name.',
        ],
        content2: [
          'The rule engine is intentionally simple: conditions are field comparisons, actions are HTTP calls and notifications. That simplicity means you can reason about what will fire and why, and debug unexpected behavior without digging through code. The delivery log shows every rule evaluation and its outcome.',
        ],
      },
    ],
  },
  {
    slug: 'rereflect-api-quickstart-for-developers',
    title: 'Rereflect API Quickstart for Developers',
    excerpt:
      'The Rereflect REST API gives you programmatic access to your feedback data, customer health scores, analytics, and ingestion endpoints. This quickstart covers authentication, the two scope types, and the core request patterns you need to get productive quickly.',
    date: '2026-11-17',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['API', 'Developers', 'Integration', 'REST'],
    seoTitle: 'Rereflect API Quickstart for Developers | Rereflect',
    seoDescription:
      'Get started with the Rereflect REST API — API key scopes, authentication, core endpoints for feedback, customers, health scores, and analytics.',
    sections: [
      {
        heading: 'What the API exposes',
        content: [
          'Rereflect ships with a documented REST API that covers the core data surfaces of the product. Everything you can see in the dashboard is also accessible via the API — plus ingestion endpoints for pushing feedback in from your own systems.',
          'The API surface breaks into four areas:',
        ],
        listItems: [
          'Feedback — read analyzed feedback items with their AI-assigned labels, filter by sentiment / category / urgency / source / date range, and ingest new feedback items.',
          'Customers — read customer records with health scores, churn probability, and linked feedback history.',
          'Analytics — read aggregated metrics: sentiment breakdown by period, pain point frequency, feature request volume, and trend data.',
          'Webhooks — register and manage outbound webhook endpoints.',
        ],
        content2: [
          'The full OpenAPI spec is served at /api/v1/openapi.json on your self-hosted instance, and the Swagger UI is available at /api/v1/docs. For any endpoint not covered in this quickstart, that is the authoritative reference.',
        ],
      },
      {
        heading: 'Authentication: API keys and scopes',
        content: [
          'The API uses API key authentication. Keys are generated in Settings → API Keys and are scoped to limit what each key can do. There are two scopes:',
        ],
        listItems: [
          'read — allows GET requests to feedback, customer, analytics, and webhook endpoints. Use this for dashboards, reporting tools, or any integration that only needs to query data.',
          'ingest — allows POST /api/v1/feedback (pushing new feedback into Rereflect). Does not grant read access to existing data. Use this for webhook handlers, SDK integrations, and ingestion pipelines.',
        ],
        content2: [
          'A key can have one or both scopes. For a handler that both ingests feedback and reads analytics to deduplicate, create a key with both scopes. For a read-only analytics dashboard, use a read-scoped key and do not give it ingest access.',
          'Include the key in the Authorization header: Authorization: Bearer <your_api_key>',
          'Keys are prefixed with rrk_ so they are easy to identify in logs. Rotate them in the UI at any time — old keys stop working immediately on rotation.',
        ],
      },
      {
        heading: 'Core request patterns',
        content: [
          'A few patterns appear repeatedly across the API and are worth learning upfront.',
          'Pagination: all list endpoints accept page and page_size query params (page_size max: 100). Responses include a meta object with total, page, page_size, and total_pages.',
          'Filtering: list endpoints accept filter params as query strings. Example: GET /api/v1/feedback?sentiment=negative&is_urgent=true&source=zendesk&page=1&page_size=50',
          'Date ranges: use created_after and created_before (ISO 8601) to scope queries to a time window: GET /api/v1/feedback?created_after=2026-10-01T00:00:00Z&created_before=2026-11-01T00:00:00Z',
          'Sorting: sort_by and sort_order params on list endpoints. Example: GET /api/v1/feedback?sort_by=sentiment_score&sort_order=asc (worst-sentiment-first).',
        ],
      },
      {
        heading: 'A minimal working example',
        content: [
          'The following fetches the 10 most recent urgent feedback items. It requires a read-scoped API key:',
          'curl -H "Authorization: Bearer rrk_your_key_here" "https://your-rereflect.example.com/api/v1/feedback?is_urgent=true&sort_by=created_at&sort_order=desc&page_size=10"',
          'The response is a JSON object with a data array of feedback items and a meta pagination object. Each item in data includes the feedback_id, content, sentiment, sentiment_score, pain_point_category, is_feature_request, is_urgent, customer_id, source, and analyzed_at fields.',
        ],
      },
      {
        heading: 'Error handling and rate limits',
        content: [
          'The API returns standard HTTP status codes. The ones you will encounter most:',
        ],
        listItems: [
          '200 OK — success.',
          '400 Bad Request — malformed request (missing required field, invalid filter value). The response body includes a detail field describing the problem.',
          '401 Unauthorized — missing or invalid API key.',
          '403 Forbidden — valid key but wrong scope (e.g., an ingest-scoped key trying to read analytics).',
          '422 Unprocessable Entity — request body failed validation. Common causes: page_size over 100, invalid ISO 8601 date, unrecognised sort_by field.',
          '429 Too Many Requests — rate limit hit. The Retry-After header tells you how many seconds to wait. Default limits are generous for typical integration use; if you are bulk-importing historical data, use batching with short delays between requests.',
        ],
        content2: [
          'For all 4xx and 5xx responses, the body is { "detail": "<human-readable message>" }. Log that field — it is the fastest path to diagnosing integration problems.',
        ],
      },
    ],
  },
  {
    slug: 'ingest-feedback-via-the-api',
    title: 'Ingesting Feedback via the Rereflect API',
    excerpt:
      'The POST /api/v1/feedback endpoint is the programmatic entry point for all feedback sources that are not CSV imports. This guide covers the payload schema, how to include customer context, batching strategies for bulk imports, and how to handle the async analysis pipeline.',
    date: '2026-11-21',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['API', 'Ingestion', 'Developers', 'Integration'],
    seoTitle: 'Ingest Feedback via the Rereflect API | Rereflect',
    seoDescription:
      'Complete guide to the Rereflect POST /api/v1/feedback endpoint — payload schema, customer context, async analysis, batching, and deduplication.',
    sections: [
      {
        heading: 'When to use the API vs CSV import',
        content: [
          'The CSV import in the Rereflect UI is the fastest path for one-time historical loads or periodic manual exports from tools like Zendesk or Intercom. The API is the right choice when you need:',
        ],
        listItems: [
          'Real-time ingestion — feedback lands in Rereflect within seconds of it arriving in your source system.',
          'Programmatic control — your existing backend, serverless function, or webhook handler pushes feedback directly without any human step.',
          'Rich metadata — you want to attach source identifiers, customer segment data, or arbitrary key-value metadata that the CSV format does not accommodate.',
          'Deduplication logic — your code can check for existing records before posting and skip duplicates, which is harder to enforce with manual imports.',
        ],
      },
      {
        heading: 'The ingestion endpoint',
        content: [
          'POST /api/v1/feedback',
          'Requires a key with the ingest scope (Authorization: Bearer rrk_your_ingest_key).',
          'Minimal payload:',
          '{ "content": "The export feature keeps timing out on large date ranges. We\'ve been waiting 3 days for this to work." }',
          'Full payload with all optional fields:',
          '{ "content": "The export feature keeps timing out on large date ranges.", "source": "zendesk", "customer_id": "cust_abc123", "external_id": "zd_ticket_98765", "created_at": "2026-11-20T10:15:00Z", "metadata": { "plan": "business", "ticket_subject": "Export timeout", "zendesk_tags": ["export", "bug"] } }',
        ],
      },
      {
        heading: 'Field reference',
        content: [
          'Understanding what each field does helps you get the most out of the analysis:',
        ],
        table: {
          headers: ['Field', 'Required', 'Notes'],
          rows: [
            ['content', 'Yes', 'The feedback text. Plain text; HTML is stripped. Max 10,000 characters.'],
            ['source', 'No', 'Free-text label for the origin (zendesk, intercom, survey, app-review, etc.). Used for source-based filtering.'],
            ['customer_id', 'No', 'Your internal customer or user identifier. Links the feedback to a customer health profile.'],
            ['external_id', 'No', 'Your system\'s identifier for this record. Used for deduplication — posting the same external_id twice is a no-op.'],
            ['created_at', 'No', 'ISO 8601 timestamp of when the feedback was originally created. Defaults to now if omitted. Affects trend charts.'],
            ['metadata', 'No', 'Freeform JSON object. Preserved as-is; searchable in the UI. No schema requirements.'],
          ],
        },
      },
      {
        heading: 'Async analysis and the feedback lifecycle',
        content: [
          'When you POST to /api/v1/feedback, the endpoint returns 202 Accepted immediately — not 200 OK. The feedback record is created synchronously, but the AI analysis runs asynchronously in the background. This means:',
        ],
        listItems: [
          'The response body includes the feedback_id and a status field set to "pending".',
          'Sentiment, pain point, feature request, and urgency fields will be null until analysis completes (usually within a few seconds, longer under heavy load).',
          'If you need to read the analysis results immediately after ingestion, poll GET /api/v1/feedback/{feedback_id} until status changes to "analyzed".',
          'Webhooks subscribed to feedback.analyzed fire automatically when analysis completes — this is the preferred alternative to polling for event-driven consumers.',
        ],
        content2: [
          'For bulk ingestion (thousands of historical records), the async model is a feature: you can submit the full batch without waiting for each item to analyze, and the worker queue processes them as capacity allows.',
        ],
      },
      {
        heading: 'Batching and rate-limit-friendly bulk imports',
        content: [
          'The API does not have a native batch endpoint — each feedback item is a separate POST. For large historical imports, a few practices keep things smooth:',
        ],
        listItems: [
          'Send in batches of 20-50, not one at a time — parallelise the POST calls within each batch to improve throughput while staying well within rate limits.',
          'Use external_id for every record — this makes it safe to re-run the import if it fails partway through; already-ingested records are skipped.',
          'Respect the Retry-After header on 429s — back off for the indicated number of seconds and resume. Do not simply retry at the same rate.',
          'Set created_at from the source system — if you are importing 6 months of Zendesk tickets, preserve the original ticket creation date so trend charts reflect when the feedback actually happened, not when you imported it.',
          'Monitor the worker queue in the Rereflect UI — under heavy bulk import, the analysis queue will grow. This is expected; items will be analyzed in order as the queue drains.',
        ],
      },
    ],
  },
  {
    slug: 'build-a-custom-feedback-dashboard-with-the-api',
    title: 'Building a Custom Feedback Dashboard with the Rereflect API',
    excerpt:
      'The Rereflect built-in dashboard covers the common cases, but sometimes you need feedback data embedded in an internal tool, a data warehouse report, or a custom view built for a specific team. The read API makes all of that possible without reimplementing the analysis layer.',
    date: '2026-11-28',
    status: 'scheduled',
    readTime: '10 min read',
    author: 'Rereflect Team',
    tags: ['API', 'Developers', 'Dashboard', 'Analytics'],
    seoTitle: 'Build a Custom Feedback Dashboard with the Rereflect API | Rereflect',
    seoDescription:
      'Learn how to use the Rereflect read API to build custom dashboards — sentiment trends, pain point tables, customer health views, and filtered feedback lists.',
    sections: [
      {
        heading: 'Why build a custom dashboard',
        content: [
          'The Rereflect UI is a general-purpose feedback analysis tool. It covers sentiment trends, pain point breakdowns, feature request tracking, and customer health — all in a single interface.',
          'But general-purpose tools sometimes do not fit specific contexts. A support team lead might want a view that shows only tickets from a specific customer segment, sorted by a custom urgency formula. An engineering team might want pain point data embedded in their existing internal ops dashboard. A data team might want feedback metrics flowing into a warehouse alongside product usage data.',
          'The Rereflect API makes all of these possible. The analysis layer — the hard part — runs on your self-hosted instance. The API exposes the results so you can compose them into whatever surface you need.',
        ],
      },
      {
        heading: 'The data surfaces available via API',
        content: [
          'A custom dashboard typically pulls from three endpoint groups:',
        ],
        listItems: [
          'GET /api/v1/feedback — paginated, filterable list of analyzed feedback items. Filter by sentiment, category, urgency, source, customer, and date range. Sort by any field.',
          'GET /api/v1/analytics/sentiment — aggregate sentiment breakdown (positive / neutral / negative counts and percentages) for a time window. Supports grouping by day, week, or month.',
          'GET /api/v1/analytics/pain-points — frequency table of pain point categories for a time window, sorted by count. Useful for a "top issues this week" widget.',
          'GET /api/v1/analytics/feature-requests — same as pain-points but for feature request categories.',
          'GET /api/v1/customers — paginated list of customer records with health scores and churn probabilities. Filter by health score range, plan, or segment.',
          'GET /api/v1/customers/{customer_id} — single customer detail with full feedback history and health timeline.',
        ],
      },
      {
        heading: 'Building a sentiment trend chart',
        content: [
          'A weekly sentiment trend chart is one of the most common custom dashboard elements. Here is the query pattern:',
          'GET /api/v1/analytics/sentiment?group_by=week&created_after=2026-09-01T00:00:00Z&created_before=2026-11-28T00:00:00Z',
          'The response is an array of buckets, each with a period_start, period_end, and counts for positive, neutral, and negative feedback. Map those buckets to your charting library of choice (Recharts, Chart.js, Observable Plot, Grafana — the data shape is simple enough to work with any of them).',
          'To scope the trend to a specific source — say, only Zendesk tickets — add source=zendesk to the query. To scope to a specific customer segment — enterprise plan customers only — filter by passing plan=enterprise in the metadata filter params.',
        ],
      },
      {
        heading: 'Building a pain point table',
        content: [
          'A "top pain points this month" table is another common widget:',
          'GET /api/v1/analytics/pain-points?created_after=2026-11-01T00:00:00Z&created_before=2026-11-28T00:00:00Z&limit=10',
          'The response is a ranked list of pain point categories with their counts and a percentage share of total analyzed feedback. Render this as a table with a sparkline showing the weekly trend for each category — the sparkline data comes from querying /api/v1/feedback?pain_point_category={category}&group_by=week for each row.',
          'For a dashboard consumed by non-technical stakeholders, consider adding a change column that shows the delta from the previous period. That requires two API calls (current period and prior period) and a join on category name, but it turns a static count table into something actionable.',
        ],
      },
      {
        heading: 'Embedding feedback data in other tools',
        content: [
          'A custom dashboard does not have to be a standalone app. Common embedding patterns:',
        ],
        listItems: [
          'Notion or Confluence via API widget — use a scheduled script (cron job or GitHub Action) to fetch the weekly pain point summary from the API and POST it to a Notion database or Confluence page. The page updates automatically every Monday morning.',
          'Data warehouse sync — a nightly job that paginates through feedback.analyzed items from the past 24 hours and loads them into a BigQuery or Snowflake table. The full metadata blob is preserved, and you can join feedback data against product usage or revenue tables.',
          'Internal ops dashboard (Retool, Grafana, Metabase) — configure the Rereflect API as a REST data source in Retool or Metabase. Most low-code dashboard tools can query a JSON API with bearer token auth and render the results directly.',
          'Customer-facing reporting — if you are building a B2B product and want to expose feedback summaries to your own customers, the read API gives you the data to build those views without duplicating the analysis infrastructure.',
        ],
        content2: [
          'The common thread across all of these patterns: Rereflect handles the analysis, you handle the presentation. The API boundary means you can change either side independently — swap out the charting library, move to a different dashboard tool, or extend the Rereflect analysis pipeline — without breaking the integration.',
        ],
      },
    ],
  },
];
