'use client';

import { useRef } from 'react';
import { useGSAP } from '@/lib/landing/gsap';
import { revealOnScroll, drawRules } from '@/lib/landing/motion';

const STAGES = [
  {
    id: '01',
    name: 'Ingest',
    body: 'Slack, Intercom, Zendesk, email, CSV or webhook. Everything lands in one queue with its source, customer and timestamp intact.',
    io: 'in: raw text',
  },
  {
    id: '02',
    name: 'Analyse',
    body: 'VADER scores sentiment locally at zero cost. Add an LLM key and the same pass extracts pain points, requests and urgency.',
    io: 'out: scored record',
  },
  {
    id: '03',
    name: 'Cluster',
    body: 'Records are deduplicated and grouped by topic, so five hundred tickets about billing become one ranked pain point.',
    io: 'out: topics',
  },
  {
    id: '04',
    name: 'Act',
    body: 'Automation rules fire on thresholds: assign an owner, open a Jira issue, alert Slack, or run a churn playbook.',
    io: 'out: side effects',
  },
];

export default function Pipeline() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealOnScroll();
      drawRules('[data-rule]', '[data-stages]', 0.09);
    },
    { scope: sectionRef },
  );

  return (
    <section ref={sectionRef} className="lp-band" id="pipeline">
      <div className="lp-section-head">
        <span data-reveal className="lp-fig">
          Fig. 02 — Processing stages
        </span>
        <h2 data-reveal className="lp-display-2 mt-6 max-w-[20ch] text-raise">
          Four stages, from raw text to something you can act on.
        </h2>
        <p data-reveal className="lp-lede mt-5">
          Every item takes the same path. Nothing is sampled, nothing is thrown away, and each
          stage writes back to the record so you can audit exactly how a conclusion was reached.
        </p>
      </div>

      <div data-stages className="lp-cells md:grid-cols-2 lg:grid-cols-4">
        {STAGES.map((stage) => (
          <div key={stage.id} className="lp-cell" data-reveal>
            <div className="flex items-baseline justify-between gap-3">
              <span className="lp-mono-sm text-accent">{stage.id}</span>
              <span className="lp-mono-10 text-[var(--content-quaternary)]">{stage.io}</span>
            </div>

            <span
              data-rule
              className="mt-3 block h-px w-full bg-[var(--stroke-default)]"
              aria-hidden="true"
            />

            <h3 className="lp-display-3 mt-4 text-raise">{stage.name}</h3>
            <p className="lp-body mt-2.5 text-[0.875rem]">{stage.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
