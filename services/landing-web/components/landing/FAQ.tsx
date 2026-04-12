'use client';

import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';

const faqs = [
  {
    q: 'How accurate is the AI analysis?',
    a: "Rereflect achieves 85-95% accuracy on sentiment classification and 80-90% on topic categorization. The system improves over time as it processes more of your data. For edge cases, you can manually adjust categories.",
  },
  {
    q: 'Is my data secure?',
    a: "Yes. All data is encrypted in transit (TLS) and at rest. We use SOC 2 compliant infrastructure. Each organization's data is fully isolated — no cross-tenant access. We never use your data to train AI models.",
  },
  {
    q: 'Can I use my own AI provider?',
    a: 'Absolutely. Pro plans can use any OpenAI model. Business and Enterprise plans support Anthropic (Claude) and Google (Gemini) as well. Bring your own API keys for full control over model selection and costs.',
  },
  {
    q: 'How long does setup take?',
    a: 'Under 5 minutes. Sign up, connect your feedback sources (Slack, Intercom, or email), and upload a CSV of existing feedback. AI analysis starts immediately.',
  },
  {
    q: "What happens when I hit my plan's feedback limit?",
    a: 'Pro and Business plans allow overage at a small per-item cost ($0.02 and $0.01 respectively). You\'ll see a usage warning before you hit the limit. Free plans stop processing new feedback at the cap — upgrade anytime to continue.',
  },
  {
    q: 'Can I cancel anytime?',
    a: "Yes, all plans are month-to-month with no annual commitment required. Cancel from the billing settings page and you'll retain access until the end of your billing period.",
  },
  {
    q: 'Do you offer a free trial?',
    a: 'Yes. All paid plans include a 14-day free trial with full feature access. No credit card required to start.',
  },
  {
    q: 'What integrations do you support?',
    a: 'Currently: Slack (OAuth), Intercom (OAuth + webhooks), email forwarding, CSV import, and webhooks for custom sources. Zendesk and HubSpot integrations are coming soon.',
  },
  {
    q: 'How do I download my data?',
    a: "You can export all your personal data at any time from Settings > Preferences. Click 'Export My Data' to download a ZIP file containing your profile information, feedback items, AI conversations, notes, and preferences in both JSON and CSV formats.",
  },
  {
    q: 'Can I delete my account?',
    a: "Yes. Go to Settings > Preferences and click 'Delete My Account.' Your account will be deactivated immediately and all data permanently deleted after a 30-day grace period. During this window, you can cancel the deletion by simply logging back in. This complies with GDPR's right to erasure.",
  },
  {
    q: 'Can I automate actions based on feedback events?',
    a: "Yes. Create automation rules that trigger when specific conditions are met — like a customer's health score dropping below a threshold or receiving multiple negative feedbacks. Rules can auto-assign team members, change workflow status, send notifications, and even draft AI responses. Choose from 5 pre-built templates or create custom rules.",
  },
];

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const toggle = (i: number) => setOpenIndex(openIndex === i ? null : i);

  return (
    <section data-testid="faq-section" className="py-24">
      <div className="max-w-3xl mx-auto px-6">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Frequently Asked Questions
          </h2>
        </div>

        <div className="divide-y divide-border">
          {faqs.map((faq, i) => {
            const isOpen = openIndex === i;
            return (
              <div key={i} className="py-4">
                <button
                  data-testid={`faq-question-${i}`}
                  onClick={() => toggle(i)}
                  aria-expanded={isOpen}
                  aria-controls={`faq-answer-${i}`}
                  className="flex w-full items-center justify-between text-left font-semibold"
                >
                  <span>{faq.q}</span>
                  <ChevronDown
                    className="w-5 h-5 shrink-0 transition-transform duration-200"
                    style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}
                  />
                </button>

                <div
                  data-testid={`faq-answer-${i}`}
                  id={`faq-answer-${i}`}
                  data-state={isOpen ? 'open' : 'closed'}
                  hidden={!isOpen}
                  className="pt-2 text-muted-foreground text-sm"
                >
                  {faq.a}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
