export interface IntegrationStep {
  step: string;
  title: string;
  description: string;
}

export interface IntegrationFeature {
  title: string;
  description: string;
  icon: string; // lucide-react icon name
}

export interface IntegrationUseCase {
  persona: string;
  role: string;
  quote: string;
  icon: string; // lucide-react icon name
}

export interface IntegrationFAQ {
  question: string;
  answer: string;
}

export interface IntegrationSetupStep {
  step: number;
  title: string;
  description: string;
}

export interface Integration {
  slug: string;
  name: string;
  tagline: string;
  description: string;
  status: 'available' | 'coming_soon';
  color: string;
  gradient: string;
  hoverShadow: string;
  hoverBorder: string;
  heroMessage: string;
  howItWorks: IntegrationStep[];
  features: IntegrationFeature[];
  useCases: IntegrationUseCase[];
  faqs: IntegrationFAQ[];
  setupSteps: IntegrationSetupStep[];
}

const SHARED_FAQS: IntegrationFAQ[] = [
  {
    question: 'How long does setup take?',
    answer: 'Usually a couple of minutes. Connect the integration, choose which channels or conversations to monitor, and Rereflect starts analyzing feedback immediately.',
  },
  {
    question: 'Is my data secure?',
    answer: 'Rereflect is self-hosted — it runs on your own infrastructure, so your data never leaves it. Connection credentials are encrypted at rest, and Rereflect only reads the data you authorize.',
  },
  {
    question: 'Which plan includes integrations?',
    answer: 'All of them. Rereflect is open-source and self-hosted, so every integration is included with no plans, seats, or paywalls — you run it on your own infrastructure.',
  },
  {
    question: 'Can I use multiple integrations at once?',
    answer: 'Yes. Connect as many sources as you need — Slack, Intercom, email, and CSV all feed into the same dashboard, and Rereflect automatically deduplicates and categorizes everything. (Note: only one CRM, HubSpot or Salesforce, can be connected per organization at a time.)',
  },
  {
    question: 'What if I need an integration you don\'t support yet?',
    answer: 'Because Rereflect is open-source, you can build it yourself or request it on GitHub. You can also use the webhook API to connect any tool that can send an HTTP request.',
  },
];

const JIRA_FAQS: IntegrationFAQ[] = [
  ...SHARED_FAQS,
  {
    question: 'Does this support Jira Server, Data Center, or OAuth?',
    answer: 'This release supports Jira Cloud only — any *.atlassian.net site, connected with a personal Atlassian API token. Jira Server, Data Center, and native OAuth (3LO) app installation are planned for a future release.',
  },
];

export const integrations: Integration[] = [
  {
    slug: 'slack',
    name: 'Slack',
    tagline: 'Capture customer feedback from Slack channels automatically',
    description: 'Connect your Slack workspace and let Rereflect monitor customer-facing channels for feedback, feature requests, and pain points — all analyzed by AI in real-time.',
    status: 'available',
    color: 'chart-4',
    gradient: 'from-[#4A154B] to-[#36C5F0]',
    hoverShadow: 'hover:shadow-[#4A154B]/10',
    hoverBorder: 'hover:border-[#4A154B]/30',
    heroMessage: 'Stop losing feedback in Slack threads. Rereflect automatically detects customer sentiment, flags urgent issues, and routes feedback to the right team members — all from your existing Slack channels.',
    howItWorks: [
      { step: '1', title: 'Connect Slack', description: 'Authorize Rereflect with one click. Choose which channels to monitor for customer feedback.' },
      { step: '2', title: 'AI Analyzes Messages', description: 'Our AI reads new messages in real-time, detecting sentiment, pain points, feature requests, and churn risk.' },
      { step: '3', title: 'Get Actionable Insights', description: 'View categorized feedback on your dashboard. Get alerts for urgent issues. Export reports for stakeholders.' },
    ],
    features: [
      { title: 'Channel Monitoring', description: 'Select specific Slack channels to monitor. Rereflect only reads channels you authorize — nothing else.', icon: 'Hash' },
      { title: 'Real-Time Analysis', description: 'Every message is analyzed as it arrives. No batch processing, no delays — instant sentiment detection.', icon: 'Zap' },
      { title: 'Urgent Alerts', description: 'Get notified immediately when a customer expresses frustration or churn risk. Respond before it escalates.', icon: 'Bell' },
      { title: 'Keyword Triggers', description: 'Set up custom keywords to filter which messages are captured as feedback. Focus on what matters.', icon: 'Search' },
      { title: 'Slack Notifications', description: 'Receive AI-generated alerts back in Slack when anomalies are detected — sentiment spikes, volume changes, and more.', icon: 'MessageSquare' },
      { title: 'Auto-Categorization', description: 'AI automatically tags feedback as bug reports, feature requests, praise, or complaints. No manual sorting.', icon: 'Tags' },
    ],
    useCases: [
      { persona: 'SaaS Founder', role: 'Early-stage, 10-person team', quote: 'Our support channel was a goldmine of feedback we were ignoring. Now Rereflect surfaces the top pain points every week — we shipped 3 fixes last month based on Slack feedback alone.', icon: 'Rocket' },
      { persona: 'Community Manager', role: 'Developer tools company', quote: 'I manage 5 Slack communities with 2,000+ members. Rereflect catches the feature requests I used to miss and shows me sentiment trends I never could have tracked manually.', icon: 'Users' },
      { persona: 'Product Manager', role: 'B2B SaaS, 50K users', quote: 'Instead of scrolling through Slack all day, I check Rereflect\'s dashboard once in the morning. The AI-generated insights are better than what I used to produce from hours of manual review.', icon: 'Layers' },
    ],
    faqs: SHARED_FAQS,
    setupSteps: [
      { step: 1, title: 'Go to Settings → Integrations', description: 'Navigate to your Rereflect dashboard and open the Integrations page.' },
      { step: 2, title: 'Click "Connect Slack"', description: 'You\'ll be redirected to Slack to authorize Rereflect. Choose the workspace you want to connect.' },
      { step: 3, title: 'Select channels to monitor', description: 'Pick which Slack channels contain customer feedback. You can add or remove channels anytime.' },
      { step: 4, title: 'Set up feedback triggers', description: 'Optionally configure keywords or message filters to focus on specific types of feedback.' },
      { step: 5, title: 'Start receiving insights', description: 'That\'s it! Feedback will appear in your dashboard within minutes as messages come in.' },
    ],
  },
  {
    slug: 'intercom',
    name: 'Intercom',
    tagline: 'Analyze support conversations for hidden feedback patterns',
    description: 'Pull customer conversations from Intercom and let AI uncover the patterns your support team misses — recurring complaints, feature requests buried in tickets, and early churn signals.',
    status: 'available',
    color: 'chart-5',
    gradient: 'from-[#286EFA] to-[#6B8AFF]',
    hoverShadow: 'hover:shadow-[#286EFA]/10',
    hoverBorder: 'hover:border-[#286EFA]/30',
    heroMessage: 'Your support conversations contain the most honest customer feedback. Rereflect connects to Intercom and automatically extracts sentiment, pain points, and feature requests from every conversation — so nothing falls through the cracks.',
    howItWorks: [
      { step: '1', title: 'Connect Intercom', description: 'Authorize via OAuth in one click. Rereflect connects to your Intercom workspace securely.' },
      { step: '2', title: 'Conversations Flow In', description: 'New conversations, replies, and ratings are automatically sent to Rereflect via webhooks.' },
      { step: '3', title: 'AI Extracts Insights', description: 'Our AI analyzes each conversation for sentiment, categorizes feedback, and flags churn risks on your dashboard.' },
    ],
    features: [
      { title: 'Conversation Sync', description: 'New conversations, customer replies, and satisfaction ratings are automatically imported as they happen.', icon: 'MessageCircle' },
      { title: 'Two-Way Sync', description: 'Add notes back to Intercom conversations and close resolved tickets — all from Rereflect.', icon: 'RefreshCw' },
      { title: 'Rating Analysis', description: 'Customer satisfaction ratings are correlated with conversation content to understand what drives good and bad scores.', icon: 'Star' },
      { title: 'Support Patterns', description: 'Discover recurring themes across hundreds of conversations. See which issues generate the most tickets.', icon: 'TrendingUp' },
      { title: 'Churn Risk Detection', description: 'AI identifies frustrated customers from conversation tone and content before they cancel.', icon: 'AlertTriangle' },
      { title: 'Webhook Integration', description: 'Real-time data flow via Intercom webhooks with HMAC-SHA1 signature verification for security.', icon: 'Shield' },
    ],
    useCases: [
      { persona: 'Head of Support', role: 'SaaS company, 100+ tickets/day', quote: 'We were drowning in tickets but had no way to see the big picture. Rereflect showed us that 40% of our tickets were about the same 3 issues — we fixed them and ticket volume dropped 30%.', icon: 'Headphones' },
      { persona: 'Product Manager', role: 'B2B platform, Series B', quote: 'I used to ask support to tag tickets manually. Now Rereflect auto-categorizes everything and shows me exactly which features customers are requesting most — with sentiment context.', icon: 'Layers' },
      { persona: 'Customer Success Manager', role: 'Enterprise SaaS', quote: 'The churn detection caught a key account\'s frustration before I even knew about it. We jumped on it, resolved their issue, and they renewed their contract the next month.', icon: 'Heart' },
    ],
    faqs: SHARED_FAQS,
    setupSteps: [
      { step: 1, title: 'Go to Settings → Integrations', description: 'Navigate to your Rereflect dashboard and open the Integrations page.' },
      { step: 2, title: 'Click "Connect Intercom"', description: 'You\'ll be redirected to Intercom to authorize Rereflect via OAuth.' },
      { step: 3, title: 'Configure conversation triggers', description: 'Choose which conversation types to monitor: new conversations, replies, ratings, or all of the above.' },
      { step: 4, title: 'Set up a feedback source', description: 'Create an Intercom feedback source to start receiving conversations in your dashboard.' },
      { step: 5, title: 'Start analyzing conversations', description: 'Conversations flow in automatically. View insights on your dashboard within minutes.' },
    ],
  },
  {
    slug: 'email',
    name: 'Email Forwarding',
    tagline: 'Forward customer emails and let AI extract the insights',
    description: 'Simply forward customer feedback emails to your Rereflect inbox. Our AI strips headers, identifies the original sender, and analyzes the content — from any email client.',
    status: 'available',
    color: 'accent',
    gradient: 'from-accent to-chart-3',
    hoverShadow: 'hover:shadow-accent/10',
    hoverBorder: 'hover:border-accent/30',
    heroMessage: 'No API integration needed. Just forward any customer email to your Rereflect inbox address and our AI does the rest — extracts the feedback, identifies the sender, detects sentiment, and categorizes it automatically.',
    howItWorks: [
      { step: '1', title: 'Get Your Inbox Address', description: 'Every Rereflect workspace gets a unique email address for receiving forwarded feedback.' },
      { step: '2', title: 'Forward Customer Emails', description: 'Forward feedback emails from Gmail, Outlook, Apple Mail, or any client. We strip forwarding headers automatically.' },
      { step: '3', title: 'AI Analyzes Content', description: 'The original message is extracted, sender identified, and content analyzed for sentiment, pain points, and feature requests.' },
    ],
    features: [
      { title: 'Universal Compatibility', description: 'Works with Gmail, Outlook, Apple Mail, Thunderbird, and any email client. We parse forwarding headers from all major providers.', icon: 'Mail' },
      { title: 'Smart Header Parsing', description: 'Our parser strips "Begin forwarded message", "From:", "Date:", and other forwarding artifacts. Only the real content is analyzed.', icon: 'FileText' },
      { title: 'Sender Detection', description: 'Original sender email and name are automatically extracted from forwarding headers, so you know who the feedback is from.', icon: 'UserCheck' },
      { title: 'Keyword Matching', description: 'Set up keyword triggers to only capture emails containing specific terms — or monitor all forwarded emails.', icon: 'Search' },
      { title: 'No Setup Required', description: 'No API keys, no OAuth, no webhooks to configure. Just forward an email and it works instantly.', icon: 'Zap' },
      { title: 'Bulk Forwarding', description: 'Set up email rules in your client to auto-forward specific emails to Rereflect. Hands-free feedback collection.', icon: 'Layers' },
    ],
    useCases: [
      { persona: 'Solo Founder', role: 'Bootstrapped SaaS', quote: 'I get customer emails all day. Now I just forward them to Rereflect and check the dashboard once a week. It\'s like having a customer research team for free.', icon: 'Rocket' },
      { persona: 'Sales Team Lead', role: 'B2B startup, 20 reps', quote: 'I asked my sales team to forward any "lost deal" emails to Rereflect. Within a month, we had a clear picture of why prospects were churning — pricing confusion was #1.', icon: 'Target' },
      { persona: 'Customer Support Lead', role: 'E-commerce, 500+ emails/day', quote: 'We set up an Outlook rule to auto-forward all complaint emails. Rereflect\'s AI categorizes them way better than our manual tagging — and it catches things we missed.', icon: 'Headphones' },
    ],
    faqs: SHARED_FAQS,
    setupSteps: [
      { step: 1, title: 'Go to Settings → Integrations', description: 'Navigate to your Rereflect dashboard and open the Integrations page.' },
      { step: 2, title: 'Find your unique inbox address', description: 'Your workspace has a dedicated email address for receiving forwarded feedback.' },
      { step: 3, title: 'Create an email feedback source', description: 'Set up a feedback source with email type and configure keyword triggers if needed.' },
      { step: 4, title: 'Forward your first email', description: 'Forward a customer email from any client. Rereflect processes it within seconds.' },
      { step: 5, title: 'Optional: Set up auto-forwarding', description: 'Create email rules in Gmail/Outlook to automatically forward specific emails to Rereflect.' },
    ],
  },
  {
    slug: 'linear',
    name: 'Linear',
    tagline: 'Turn issue tracker comments into actionable product feedback',
    description: 'Connect Linear and let Rereflect analyze issue comments, bug reports, and feature requests — surfacing customer sentiment and product patterns your team would otherwise miss.',
    status: 'available',
    color: 'chart-5',
    gradient: 'from-[#5E6AD2] to-[#8B94E8]',
    hoverShadow: 'hover:shadow-[#5E6AD2]/10',
    hoverBorder: 'hover:border-[#5E6AD2]/30',
    heroMessage: 'Your Linear issues are full of customer feedback hiding in comments and descriptions. Rereflect connects to Linear and automatically extracts sentiment, pain points, and feature requests — giving your product team a clear signal from the noise.',
    howItWorks: [
      { step: '1', title: 'Connect Linear', description: 'Authorize Rereflect via OAuth in one click. We securely connect to your Linear workspace.' },
      { step: '2', title: 'Issues Flow In', description: 'New issue comments, status changes, and labels are sent to Rereflect via webhooks in real-time.' },
      { step: '3', title: 'AI Finds Patterns', description: 'Our AI analyzes every comment for sentiment, categorizes feedback, and surfaces the most impactful product insights.' },
    ],
    features: [
      { title: 'Issue Comment Analysis', description: 'Every comment on Linear issues is analyzed for customer sentiment, pain points, and feature requests — automatically.', icon: 'MessageSquare' },
      { title: 'Label-Based Filtering', description: 'Choose which issues to monitor by label. Only capture feedback from customer-facing issues, bug reports, or specific projects.', icon: 'Tags' },
      { title: 'Team Mapping', description: 'Map Linear teams to Rereflect categories. Route feedback from different teams to the right dashboard views.', icon: 'Users' },
      { title: 'Status Tracking', description: 'Track how feedback correlates with issue status. See which customer pain points are being addressed and which are stuck.', icon: 'TrendingUp' },
      { title: 'Issue Templates', description: 'Create issues back in Linear from Rereflect with customizable templates — including sentiment data and customer context.', icon: 'FileText' },
      { title: 'Real-Time Webhooks', description: 'Instant data flow via Linear webhooks with signature verification. No polling, no delays — feedback appears in seconds.', icon: 'Zap' },
    ],
    useCases: [
      { persona: 'Product Manager', role: 'B2B SaaS, 200+ issues/week', quote: 'We had feature requests scattered across hundreds of Linear issues. Rereflect now surfaces the top requests with sentiment context — we prioritize based on data, not gut feeling.', icon: 'Layers' },
      { persona: 'Engineering Lead', role: 'Developer tools startup', quote: 'Bug reports from customers often have valuable product feedback buried in the comments. Rereflect catches patterns we never would have seen — like 3 different customers hitting the same workflow issue.', icon: 'Rocket' },
      { persona: 'Customer Success Manager', role: 'Enterprise SaaS', quote: 'I used to manually scan Linear for customer-reported issues. Now I check Rereflect\'s dashboard and instantly see which accounts are frustrated and what they need fixed.', icon: 'Heart' },
    ],
    faqs: SHARED_FAQS,
    setupSteps: [
      { step: 1, title: 'Go to Settings → Integrations', description: 'Navigate to your Rereflect dashboard and open the Integrations page.' },
      { step: 2, title: 'Click "Connect Linear"', description: 'You\'ll be redirected to Linear to authorize Rereflect via OAuth. Approve the connection.' },
      { step: 3, title: 'Configure team mappings', description: 'Map your Linear teams to Rereflect categories so feedback is automatically organized.' },
      { step: 4, title: 'Set up a feedback source', description: 'Create a Linear feedback source and configure which labels or keywords to monitor.' },
      { step: 5, title: 'Start analyzing issues', description: 'Issue comments flow in automatically. View insights on your dashboard within minutes.' },
    ],
  },
  {
    slug: 'jira',
    name: 'Jira',
    tagline: 'Push feedback straight into Jira issues your team already tracks',
    description: 'Connect Jira Cloud and create issues directly from feedback items — with sentiment, customer context, and a link back to the original feedback included automatically.',
    status: 'available',
    color: 'chart-2',
    gradient: 'from-[#0052CC] to-[#2684FF]',
    hoverShadow: 'hover:shadow-[#0052CC]/10',
    hoverBorder: 'hover:border-[#0052CC]/30',
    heroMessage: 'Stop copy-pasting customer feedback into Jira by hand. Rereflect connects to Jira Cloud with a personal API token and lets you create fully-linked issues — with sentiment and customer context attached — straight from any feedback item.',
    howItWorks: [
      { step: '1', title: 'Connect Jira', description: 'Paste your Jira site URL, account email, and a personal API token to authorize Rereflect — no OAuth redirect required.' },
      { step: '2', title: 'Create Issues from Feedback', description: 'Pick a project and issue type, then create a Jira issue directly from any feedback item — pre-filled with the feedback content and AI context.' },
      { step: '3', title: 'Track the Link', description: 'Rereflect keeps a link between the feedback item and the Jira issue, so your team can jump straight to the ticket that came from a customer.' },
    ],
    features: [
      { title: 'Token-Based Connection', description: 'Connect with a personal Atlassian API token — no OAuth app to register, no admin approval workflow required.', icon: 'KeyRound' },
      { title: 'One-Click Issue Creation', description: 'Turn any feedback item into a Jira issue in a couple of clicks, pre-filled with title, description, and customer context.', icon: 'FileText' },
      { title: 'Project & Issue-Type Picker', description: 'Choose which Jira project and issue type (Bug, Task, Story) each issue is created in — no hardcoded defaults.', icon: 'Tags' },
      { title: 'Feedback-to-Issue Linking', description: 'Every created issue is linked back to the originating feedback item, so context is never lost.', icon: 'RefreshCw' },
      { title: 'Cloud-Native', description: 'Built for Jira Cloud (*.atlassian.net) using the official REST API v3 with Basic auth.', icon: 'Zap' },
    ],
    useCases: [
      { persona: 'Product Manager', role: 'B2B SaaS, Jira-based roadmap', quote: 'We used to manually re-type customer complaints into Jira tickets. Now I create the issue right from the feedback card and the customer context comes with it.', icon: 'Layers' },
      { persona: 'Engineering Lead', role: 'Platform team', quote: 'Every bug report that turns into a Jira ticket keeps a link back to the original feedback, so nobody has to ask "wait, who reported this?"', icon: 'Rocket' },
    ],
    faqs: JIRA_FAQS,
    setupSteps: [
      { step: 1, title: 'Go to Settings → Integrations', description: 'Navigate to your Rereflect dashboard and open the Integrations page.' },
      { step: 2, title: 'Mint an Atlassian API token', description: 'Go to id.atlassian.com → Security → API tokens, and create a new API token for your Atlassian account.' },
      { step: 3, title: 'Paste your credentials into Rereflect', description: 'In Rereflect, go to Settings → Integrations → Jira and paste your Jira site URL (e.g. your-company.atlassian.net), your Atlassian account email, and the API token you just created.' },
      { step: 4, title: 'Rereflect validates the connection', description: 'Rereflect verifies the token against your Jira site and encrypts it at rest. You\'ll see a connected status once it succeeds.' },
      { step: 5, title: 'Create your first issue', description: 'Open any feedback item, choose "Create Jira Issue," pick a project and issue type, and Rereflect creates a linked Jira issue for you.' },
    ],
  },
  {
    slug: 'zendesk',
    name: 'Zendesk',
    tagline: 'Pull support tickets and discover feedback patterns at scale',
    description: 'Connect Zendesk to automatically analyze support tickets, discover recurring issues, and surface the most impactful feedback — powered by AI.',
    status: 'coming_soon',
    color: 'chart-3',
    gradient: 'from-[#03363D] to-[#17494D]',
    hoverShadow: 'hover:shadow-[#03363D]/10',
    hoverBorder: 'hover:border-[#03363D]/30',
    heroMessage: 'Zendesk integration is coming soon. Connect your helpdesk and let AI find the patterns hidden in thousands of support tickets.',
    howItWorks: [
      { step: '1', title: 'Connect Zendesk', description: 'Authorize Rereflect to access your Zendesk account via API.' },
      { step: '2', title: 'Tickets Sync Automatically', description: 'New and updated tickets flow into Rereflect in real-time.' },
      { step: '3', title: 'AI Finds Patterns', description: 'Discover recurring issues, trending topics, and customer sentiment across all tickets.' },
    ],
    features: [
      { title: 'Ticket Analysis', description: 'Every support ticket is analyzed for sentiment, category, and urgency — automatically.', icon: 'FileText' },
      { title: 'Trend Detection', description: 'Spot emerging issues before they become ticket storms. AI detects unusual patterns in real-time.', icon: 'TrendingUp' },
      { title: 'Priority Scoring', description: 'AI scores tickets by impact and urgency, helping your team focus on what matters most.', icon: 'Target' },
      { title: 'Custom Fields', description: 'Map Zendesk custom fields to Rereflect categories for seamless data flow.', icon: 'Settings' },
    ],
    useCases: [],
    faqs: SHARED_FAQS,
    setupSteps: [],
  },
  {
    slug: 'hubspot',
    name: 'HubSpot',
    tagline: 'Sync CRM data with feedback — and push health scores back to HubSpot',
    description: 'Connect HubSpot to enrich your feedback data with CRM context — see which customers are giving feedback, their account value, and how sentiment correlates with revenue. Opt in to push each customer\'s health score back into HubSpot automatically.',
    status: 'available',
    color: 'destructive',
    gradient: 'from-[#FF7A59] to-[#FF957A]',
    hoverShadow: 'hover:shadow-[#FF7A59]/10',
    hoverBorder: 'hover:border-[#FF7A59]/30',
    heroMessage: 'Combine CRM intelligence with feedback analysis for a complete view of your customer relationships — and optionally push Rereflect\'s health score straight back into a HubSpot contact property, so your CRM stays in sync automatically.',
    howItWorks: [
      { step: '1', title: 'Connect HubSpot', description: 'Paste a HubSpot private-app access token to authorize Rereflect — no OAuth redirect required.' },
      { step: '2', title: 'Enrich Feedback Data', description: 'Customer feedback is automatically linked to HubSpot contacts and deals by email address.' },
      { step: '3', title: 'Push Health Scores Back (optional)', description: 'Opt in to writeback and Rereflect pushes each customer\'s health score into a HubSpot contact property you choose.' },
    ],
    features: [
      { title: 'Contact Matching', description: 'Feedback is automatically matched to HubSpot contacts by email address.', icon: 'Users' },
      { title: 'Deal Context', description: 'See deal stage, value, and history alongside customer feedback.', icon: 'DollarSign' },
      { title: 'Revenue Impact', description: 'Prioritize feedback from high-value accounts. Know which pain points affect your biggest customers.', icon: 'TrendingUp' },
      { title: 'Lifecycle Tracking', description: 'Track how customer sentiment evolves across their lifecycle — from prospect to long-term customer.', icon: 'BarChart3' },
      { title: 'Health-Score Writeback', description: 'Opt-in bidirectional sync pushes Rereflect\'s calculated health score back into a HubSpot contact property you choose — kept in sync automatically as scores change.', icon: 'RefreshCw' },
    ],
    useCases: [
      { persona: 'Customer Success Manager', role: 'B2B SaaS, HubSpot CRM', quote: 'Our reps live in HubSpot. Now the health score shows up right on the contact record, so nobody has to context-switch to Rereflect to know an account is at risk.', icon: 'Heart' },
      { persona: 'RevOps Lead', role: 'Series A SaaS', quote: 'Deal value and feedback sentiment used to live in two different tools. Rereflect ties them together in HubSpot, so we prioritize fixes by revenue impact, not gut feel.', icon: 'TrendingUp' },
    ],
    faqs: SHARED_FAQS,
    setupSteps: [
      { step: 1, title: 'Go to Settings → Integrations', description: 'Navigate to your Rereflect dashboard and open the Integrations page.' },
      { step: 2, title: 'Create a HubSpot private app', description: 'In HubSpot, create a private app and copy its access token. Grant crm.objects.contacts.read (and crm.objects.deals.read) scopes.' },
      { step: 3, title: 'Paste the token into Rereflect', description: 'Connect HubSpot from Settings → Integrations by pasting the private-app token. Rereflect validates and encrypts it immediately.' },
      { step: 4, title: 'Optional: enable health-score writeback', description: 'Create a number-type custom contact property in HubSpot, grant crm.objects.contacts.write on your private-app token, then enter the property name in Rereflect to turn on writeback.' },
      { step: 5, title: 'Start syncing', description: 'Feedback is enriched with CRM context automatically. If writeback is enabled, each customer\'s health score pushes to HubSpot as it updates.' },
    ],
  },
  {
    slug: 'salesforce',
    name: 'Salesforce',
    tagline: 'Sync CRM data and feedback for a complete customer picture',
    description: 'Connect Salesforce to enrich your feedback data with CRM context — see which customers are giving feedback, their account ARR, renewal timing, and open opportunities alongside sentiment.',
    status: 'available',
    color: 'chart-2',
    gradient: 'from-[#00A1E0] to-[#1798C1]',
    hoverShadow: 'hover:shadow-[#00A1E0]/10',
    hoverBorder: 'hover:border-[#00A1E0]/30',
    heroMessage: 'Combine Salesforce CRM intelligence with feedback analysis for a complete view of your customer relationships — company, ARR, renewal date, and open opportunities, all alongside sentiment.',
    howItWorks: [
      { step: '1', title: 'Connect Salesforce', description: 'Authorize Rereflect via Salesforce OAuth in one click. We securely connect to your Salesforce org.' },
      { step: '2', title: 'Enrich Feedback Data', description: 'Customer feedback is automatically linked to Salesforce accounts and opportunities by email address.' },
      { step: '3', title: 'Revenue-Weighted Insights', description: 'See ARR, renewal timing, and the highest-value open opportunity alongside feedback, and prioritize accordingly.' },
    ],
    features: [
      { title: 'Account Matching', description: 'Feedback is automatically matched to Salesforce contacts and accounts by email address.', icon: 'Users' },
      { title: 'Opportunity Context', description: 'See deal stage, amount, and close date alongside customer feedback.', icon: 'DollarSign' },
      { title: 'ARR & Renewal Tracking', description: 'Annual revenue and a renewal-date proxy (the highest-amount open opportunity) are pulled in for every account.', icon: 'TrendingUp' },
      { title: 'Revenue Impact', description: 'Prioritize feedback from high-value accounts. Know which pain points affect your biggest customers.', icon: 'BarChart3' },
    ],
    useCases: [
      { persona: 'Customer Success Manager', role: 'Enterprise SaaS, Salesforce CRM', quote: 'I can finally see churn-risk feedback next to the account\'s ARR and renewal date without leaving Rereflect. It changes which fires I fight first.', icon: 'Heart' },
      { persona: 'Product Manager', role: 'B2B SaaS, Series B', quote: 'We route feature requests by opportunity size now. Rereflect pulls the Salesforce deal amount right onto the feedback card.', icon: 'Layers' },
    ],
    faqs: SHARED_FAQS,
    setupSteps: [
      { step: 1, title: 'Go to Settings → Integrations', description: 'Navigate to your Rereflect dashboard and open the Integrations page.' },
      { step: 2, title: 'Click "Connect Salesforce"', description: 'You\'ll be redirected to Salesforce to authorize Rereflect via OAuth. Note: only one CRM (HubSpot or Salesforce) can be active per organization at a time.' },
      { step: 3, title: 'Approve the requested scopes', description: 'Grant Rereflect read access to accounts, contacts, and opportunities.' },
      { step: 4, title: 'Rereflect syncs accounts & opportunities', description: 'Company, ARR, renewal date, and opportunity stage/amount are pulled in automatically.' },
      { step: 5, title: 'View enriched feedback', description: 'Feedback is enriched with CRM context automatically. Segment and prioritize by account value on your dashboard.' },
    ],
  },
];

export function getIntegration(slug: string): Integration | undefined {
  return integrations.find((i) => i.slug === slug);
}

export function getAvailableIntegrations(): Integration[] {
  return integrations.filter((i) => i.status === 'available');
}

export function getComingSoonIntegrations(): Integration[] {
  return integrations.filter((i) => i.status === 'coming_soon');
}
