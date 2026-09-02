'use client';

import { useRef } from 'react';
import { useGSAP } from '@/lib/landing/gsap';
import { revealOnScroll, revealGroup } from '@/lib/landing/motion';

type Tone = 'accent' | 'amber' | 'red' | 'muted';

const ROWS: Array<{
  id: string;
  customer: string;
  source: string;
  sentiment: string;
  tone: Tone;
  topic: string;
  churn: string;
  churnTone: Tone;
}> = [
  { id: 'fb_9f21c4', customer: 'Acme Inc.', source: 'intercom', sentiment: '−0.82', tone: 'red', topic: 'billing', churn: '92%', churnTone: 'red' },
  { id: 'fb_9f21c1', customer: 'Northwind', source: 'zendesk', sentiment: '−0.41', tone: 'amber', topic: 'onboarding', churn: '48%', churnTone: 'amber' },
  { id: 'fb_9f21be', customer: 'Globex', source: 'slack', sentiment: '+0.66', tone: 'accent', topic: 'reporting', churn: '07%', churnTone: 'muted' },
  { id: 'fb_9f21bb', customer: 'Initech', source: 'email', sentiment: '−0.12', tone: 'amber', topic: 'performance', churn: '31%', churnTone: 'muted' },
  { id: 'fb_9f21b7', customer: 'Umbrella', source: 'csv', sentiment: '+0.88', tone: 'accent', topic: 'support', churn: '04%', churnTone: 'muted' },
  { id: 'fb_9f21b2', customer: 'Soylent', source: 'webhook', sentiment: '−0.74', tone: 'red', topic: 'billing', churn: '77%', churnTone: 'red' },
  { id: 'fb_9f21ae', customer: 'Hooli', source: 'intercom', sentiment: '+0.23', tone: 'accent', topic: 'integrations', churn: '12%', churnTone: 'muted' },
];

const TONE_CLASS: Record<Tone, string> = {
  accent: 'text-[var(--content-accent)]',
  amber: 'text-[var(--content-amber)]',
  red: 'text-[var(--content-red)]',
  muted: 'text-[var(--content-tertiary)]',
};

const SUMMARY = [
  ['Analysed today', '1,284'],
  ['Open pain points', '17'],
  ['At-risk accounts', '4'],
  ['Median latency', '0.4s'],
];

export default function Console() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealOnScroll();
      revealGroup('[data-row]', '[data-console]', 0.035);
    },
    { scope: sectionRef },
  );

  return (
    <section ref={sectionRef} className="lp-band">
      <div className="lp-section-head">
        <span data-reveal className="lp-fig">
          Fig. 06 — Rereflect console
        </span>
        <h2 data-reveal className="lp-display-2 mt-6 max-w-[22ch] text-raise">
          Everything the model concluded, in one table you can argue with.
        </h2>
        <p data-reveal className="lp-lede mt-5">
          No score is a black box. Every row links back to the original message, the confidence
          the model assigned, and the rule that fired because of it.
        </p>
      </div>

      <div data-console className="px-[var(--gutter-width)] pb-[clamp(2.5rem,5vw,4rem)]">
        <div className="lp-panel">
          <div className="lp-panel-bar">
            <span className="lp-dot" />
            <span className="lp-mono-10">feedback / all</span>
            <span className="lp-mono-10 ml-auto hidden sm:inline">
              org: acme · 1,284 records
            </span>
          </div>

          <div className="lp-table-wrap">
            <table className="lp-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Customer</th>
                  <th>Source</th>
                  <th className="text-right">Sentiment</th>
                  <th>Pain point</th>
                  <th className="text-right">Churn</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.id} data-row>
                    <td className="lp-td-name">{row.id}</td>
                    <td className="text-[var(--content-default)]">{row.customer}</td>
                    <td>
                      <span className="lp-badge">{row.source}</span>
                    </td>
                    <td className={`lp-td-num ${TONE_CLASS[row.tone]}`}>{row.sentiment}</td>
                    <td>{row.topic}</td>
                    <td className={`lp-td-num ${TONE_CLASS[row.churnTone]}`}>{row.churn}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-2 border-t border-[var(--stroke-secondary)] md:grid-cols-4">
            {SUMMARY.map(([label, value], i) => (
              <div
                key={label}
                className={`px-4 py-3 ${
                  i < SUMMARY.length - 1
                    ? 'border-b border-r border-[var(--stroke-secondary)] md:border-b-0'
                    : ''
                }`}
              >
                <span className="lp-mono-10 text-[var(--content-quaternary)]">{label}</span>
                <span className="lp-mono-value mt-1 block text-[1.05rem] text-raise">{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
