'use client';

import Link from 'next/link';
import {
  AlertTriangle,
  Workflow,
  Tags,
  Bell,
  Lightbulb,
  BarChart3,
  TrendingUp,
  TrendingDown,
  Layers,
  Bot,
  Users,
  Brain,
  Sparkles,
  ShieldCheck,
  Zap,
  type LucideIcon,
} from 'lucide-react';

/* ── Animated icon wrapper ── */
function AnimatedIcon({
  icon: Icon,
  variant = 'spin',
}: {
  icon: LucideIcon;
  variant?: 'spin' | 'pulse';
}) {
  return (
    <span className="relative p-2.5 rounded-xl bg-primary/10 text-primary w-fit block">
      <svg
        className="absolute inset-0 w-full h-full overflow-visible"
        viewBox="0 0 48 48"
        fill="none"
        aria-hidden="true"
      >
        {variant === 'spin' ? (
          <circle
            cx="24"
            cy="24"
            r="22"
            stroke="currentColor"
            strokeWidth="0.75"
            strokeDasharray="5 5"
            opacity={0.25}
          >
            <animateTransform
              attributeName="transform"
              type="rotate"
              from="0 24 24"
              to="360 24 24"
              dur="20s"
              repeatCount="indefinite"
            />
          </circle>
        ) : (
          <circle
            cx="24"
            cy="24"
            r="20"
            stroke="currentColor"
            strokeWidth="0.75"
            fill="none"
            opacity={0.3}
          >
            <animate attributeName="r" values="20;24;20" dur="2.5s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.3;0.05;0.3" dur="2.5s" repeatCount="indefinite" />
          </circle>
        )}
      </svg>
      <Icon className="w-5 h-5 relative" />
    </span>
  );
}

/* ── Data ── */
const copilotBullets = [
  'Cmd+K command bar with smart suggestions',
  'Natural language queries: "What are the top pain points this week?"',
  'SQL generation with safety guardrails',
  'Charts and tables in responses, with deep links',
];

const customer360Bullets = [
  'Health score dashboard',
  '9-factor churn risk',
  'Automated recovery alerts',
];

const multiModelBullets = [
  'OpenAI, Anthropic, Google support',
  'Automatic fallback chains',
  'Per-org budget tracking',
];

const smallCards: {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  animation: 'spin' | 'pulse';
}[] = [
  {
    id: 'card-ai-churn-detection',
    icon: AlertTriangle,
    title: 'AI Churn Detection',
    description:
      'Catch at-risk customers before they leave with real-time frustration pattern scanning',
    animation: 'pulse',
  },
  {
    id: 'card-feedback-workflow',
    icon: Workflow,
    title: 'Feedback Workflow',
    description:
      'Route feedback, track status, assign to team members, close the loop',
    animation: 'spin',
  },
  {
    id: 'card-smart-categorization',
    icon: Tags,
    title: 'Smart Categorization',
    description:
      'AI auto-tags feedback by topic and type — no manual sorting needed',
    animation: 'spin',
  },
  {
    id: 'card-real-time-alerts',
    icon: Bell,
    title: 'Real-Time Alerts',
    description:
      'Slack, email, and in-app notifications when urgent feedback or sentiment spikes occur',
    animation: 'pulse',
  },
  {
    id: 'card-weekly-ai-insights',
    icon: Lightbulb,
    title: 'Weekly AI Insights',
    description:
      'Friday email digest with emerging pain points, feature requests, and action items',
    animation: 'pulse',
  },
  {
    id: 'card-dashboard-sharing',
    icon: BarChart3,
    title: 'Dashboard Sharing',
    description:
      'Public links with password protection and one-click PDF export',
    animation: 'spin',
  },
  {
    id: 'card-trend-analytics',
    icon: TrendingUp,
    title: 'Trend Analytics',
    description:
      'Sentiment, volume, and topic trends over 7d/30d/90d with saved views',
    animation: 'spin',
  },
  {
    id: 'card-integrations',
    icon: Layers,
    title: 'Integrations',
    description:
      'Slack, Intercom, email, webhooks — connect your feedback sources in 2 minutes',
    animation: 'spin',
  },
  {
    id: 'card-data-privacy',
    icon: ShieldCheck,
    title: 'Data Privacy & GDPR',
    description:
      'Export your data anytime. Request account deletion with a 30-day grace period. Full GDPR compliance with data portability and right to erasure.',
    animation: 'pulse',
  },
  {
    id: 'card-ai-workflow-automation',
    icon: Zap,
    title: 'AI Workflow Automation',
    description:
      'Create IF/THEN rules that auto-assign, escalate, notify, and draft responses when churn risk spikes, bugs are reported, or sentiment drops.',
    animation: 'pulse',
  },
  {
    id: 'card-churn-prediction',
    icon: TrendingDown,
    title: '30-Day Churn Probability',
    description:
      'Predict 30-60 days out which customers will churn — with calibrated probabilities, factor breakdowns, and prevention playbooks. Honest accuracy tracking included.',
    animation: 'pulse',
  },
];

/* ── Copilot chat mockup ── */
function CopilotChatMockup() {
  return (
    <div
      data-testid="copilot-demo-area"
      className="flex-1 rounded-xl border border-border bg-background/50 overflow-hidden flex flex-col min-h-[200px] md:min-h-0"
    >
      {/* Header */}
      <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
        <span className="text-[10px] font-medium text-muted-foreground">
          AI Copilot
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 p-3 space-y-2.5">
        {/* User */}
        <div className="flex justify-end">
          <div className="bg-primary/10 rounded-lg px-2.5 py-1.5 text-[11px] text-foreground max-w-[85%]">
            Top pain points this week?
          </div>
        </div>

        {/* AI */}
        <div className="flex justify-start">
          <div className="bg-muted/50 rounded-lg px-2.5 py-2 max-w-[90%]">
            <div className="flex items-center gap-1 mb-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-primary" />
              <span className="text-[10px] font-semibold text-foreground">
                Based on 847 items:
              </span>
            </div>
            <div className="space-y-0.5 text-[10px] text-muted-foreground">
              <div>1. Export failing (23 mentions)</div>
              <div>2. Slow page loads (18 mentions)</div>
              <div>3. Mobile layout (12 mentions)</div>
            </div>
          </div>
        </div>
      </div>

      {/* Input */}
      <div className="px-3 py-2 border-t border-border/50">
        <div className="bg-muted/30 rounded-lg px-2.5 py-1.5 text-[10px] text-muted-foreground/60">
          Ask anything...
        </div>
      </div>
    </div>
  );
}

/* ── Main component ── */
export default function BentoFeatures() {
  return (
    <section
      data-testid="bento-section"
      className="pt-32 pb-28 px-6 md:px-8 lg:px-16"
    >
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center" style={{ marginBottom: '4rem', marginTop: '3rem' }}>
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20" style={{ marginBottom: '1.5rem' }}>
            <Sparkles className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-primary">Powerful Features</span>
          </div>
          <h2 className="text-4xl md:text-5xl font-bold tracking-tight">
            Analyze feedback.{' '}
            <span className="text-primary">Act faster.</span>
          </h2>
        </div>

        {/* ── Large card: AI Copilot (full width) ── */}
        <div
          data-testid="card-ai-copilot"
          data-size="large"
          className="rounded-2xl border border-border bg-card p-8 md:p-10 min-h-[340px] flex flex-col md:flex-row gap-8 mb-6"
          style={{
            boxShadow: '0 0 0 1px hsl(var(--primary) / 0.2), 0 8px 32px -8px hsl(var(--primary) / 0.1)',
          }}
        >
          {/* Left: Content */}
          <div className="flex-1 flex flex-col justify-center">
            <div className="flex items-center gap-3 mb-4">
              <AnimatedIcon icon={Bot} variant="pulse" />
              <h3 className="text-2xl font-bold">AI Copilot</h3>
            </div>
            <p className="text-muted-foreground text-lg mb-6">
              Ask your feedback data anything
            </p>
            <ul className="space-y-2.5 mb-8">
              {copilotBullets.map((bullet) => (
                <li key={bullet} className="flex items-center gap-2.5 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0" />
                  {bullet}
                </li>
              ))}
            </ul>
            <Link
              href="/signup"
              className="text-primary hover:underline text-sm font-medium w-fit"
            >
              Try it free &rarr;
            </Link>
          </div>

          {/* Right: Chat mockup */}
          <CopilotChatMockup />
        </div>

        {/* ── Medium cards row ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Customer 360 */}
          <div
            data-testid="card-customer-360"
            data-size="medium"
            className="rounded-2xl border border-border bg-card p-8 min-h-[280px] flex flex-col"
          >
            <div className="flex items-center gap-3 mb-4">
              <AnimatedIcon icon={Users} variant="pulse" />
              <h3 className="text-xl font-bold">Customer 360</h3>
            </div>
            <p className="text-muted-foreground text-sm mb-5">
              Health scores, churn prediction, and proactive alerts for every
              customer
            </p>
            <ul className="space-y-2.5">
              {customer360Bullets.map((point) => (
                <li
                  key={point}
                  className="flex items-center gap-2.5 text-sm"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0" />
                  {point}
                </li>
              ))}
            </ul>
          </div>

          {/* Multi-Model AI */}
          <div
            data-testid="card-multi-model"
            data-size="medium"
            className="rounded-2xl border border-border bg-card p-8 min-h-[280px] flex flex-col"
          >
            <div className="flex items-center gap-3 mb-4">
              <AnimatedIcon icon={Brain} variant="spin" />
              <h3 className="text-xl font-bold">Choose Your AI</h3>
            </div>
            <p className="text-muted-foreground text-sm mb-5">
              Bring your own keys (BYOK). Pick the model that fits your needs
              and budget.
            </p>
            <ul className="space-y-2.5">
              {multiModelBullets.map((point) => (
                <li
                  key={point}
                  className="flex items-center gap-2.5 text-sm"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0" />
                  {point}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* ── Small cards grid: 4 columns ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {smallCards.map(({ id, icon, title, description, animation }) => (
            <div
              key={id}
              data-testid={id}
              data-size="small"
              className="rounded-2xl border border-border bg-card p-6 min-h-[220px] flex flex-col gap-4 hover:shadow-lg hover:-translate-y-1 transition-all duration-200 group relative overflow-hidden"
            >
              <AnimatedIcon icon={icon} variant={animation} />
              <h4 className="font-semibold text-sm">{title}</h4>
              <p className="text-muted-foreground text-xs leading-relaxed">
                {description}
              </p>
              {/* Gradient overlay on hover */}
              <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none rounded-2xl" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
