'use client';

import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';

const faqs = [
  {
    q: 'Is it really free?',
    a: 'Yes, completely. Rereflect is MIT-licensed open-source software. There are no plans, seats, usage caps, or fees of any kind. You clone the repo, deploy it on your own infrastructure, and run it forever at no cost.',
  },
  {
    q: 'How do I self-host it?',
    a: 'Clone the repository from GitHub and follow the self-hosting guide in the README. The stack is Docker-friendly: you will need a PostgreSQL database, a Redis instance, and optionally an LLM API key. Most setups are running in under 30 minutes.',
  },
  {
    q: 'Do I need an LLM API key?',
    a: 'No. Rereflect ships with VADER sentiment analysis, which runs entirely locally with no external API calls and no cost. If you want richer AI features — the Copilot, LLM-powered categorization, or churn insights — you can add an OpenAI, Anthropic, or Google API key. Your key, your cost, no markup.',
  },
  {
    q: 'Can I use it without sending any data to an external LLM?',
    a: 'Yes. With the VADER-only configuration, all processing happens on your own server. No feedback data leaves your infrastructure. You can also run a local LLM (e.g. via Ollama) and point Rereflect at it — see the README for BYOK/local model configuration.',
  },
  {
    q: 'What is the license?',
    a: 'MIT. You can use it, fork it, modify it, and redistribute it — commercially or otherwise — with no restrictions. The only requirement is to retain the copyright notice.',
  },
  {
    q: 'What integrations are included?',
    a: 'Slack (OAuth), Intercom (OAuth + webhooks), email forwarding, CSV import, webhooks for custom sources, and Linear. Zendesk and HubSpot integrations are planned. All integrations are configured in your self-hosted instance — no hosted service required.',
  },
  {
    q: 'Does it support single sign-on (SSO)?',
    a: 'Yes — OIDC and SAML 2.0 single sign-on, alongside email/password and Google login. Point it at your own identity provider (Okta, Azure AD, Google Workspace, Keycloak, or any conformant OIDC/SAML provider), configure it in Settings → SSO, and restrict access by email domain. First-time users are provisioned automatically. Like everything else, it is fully unlocked — there is no enterprise tier or SSO tax. SAML is SP-initiated only in this release — IdP-initiated login, Single Logout, and SCIM are not yet supported.',
  },
  {
    q: 'Who owns my data?',
    a: 'You do, entirely. Because Rereflect runs on your infrastructure, your feedback data never leaves your servers (unless you configure an external LLM key). There is no cloud service, no analytics pipeline, and no third party with access to your data.',
  },
  {
    q: 'Can I contribute or request features?',
    a: 'Absolutely. Open an issue or pull request on GitHub. The project welcomes bug reports, feature ideas, and code contributions. Check CONTRIBUTING.md in the repository for guidelines.',
  },
  {
    q: 'How does churn prediction work without sending data to a hosted service?',
    a: 'Churn prediction uses a calibrated model trained on your own labeled outcomes — customers you have marked as churned. The model runs in your instance. Each prediction includes a confidence interval so you can see how certain the model is. Org-specific models activate once you have labeled at least 20 customers; before that a global baseline model is used.',
  },
  {
    q: 'Can Rereflect pull churn labels from my CRM?',
    a: 'Yes, if you connect HubSpot or Salesforce — and it is opt-in and off by default. Rereflect reads closed-lost deals from the renewal pipelines (or opportunity types) you name and proposes them as churn suggestions; an optional on-demand backfill can cover your closed-lost history. Nothing is applied automatically: every suggestion waits in a review queue for a person to confirm or reject it, because a lost renewal is not always a churn — deals close lost for renegotiations, contract merges, and mis-staging too. Until you name your renewal pipelines, nothing is suggested at all.',
  },
  {
    q: 'Can I automate actions based on feedback events?',
    a: 'Yes. Create IF/THEN automation rules that trigger when specific conditions are met — like a health score dropping below a threshold or multiple negative feedbacks arriving. Rules can auto-assign team members, change workflow status, send Slack notifications, and draft AI responses. Pre-built templates are included.',
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
