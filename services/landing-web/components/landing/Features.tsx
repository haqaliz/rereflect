'use client';

import { useRef } from 'react';
import { useGSAP } from '@/lib/landing/gsap';
import { revealOnScroll, fillMeters, countUp, revealGroup } from '@/lib/landing/motion';
import { gsap } from '@/lib/landing/gsap';

const INTEGRATIONS = [
  'Intercom',
  'Zendesk',
  'Jira',
  'Linear',
  'Salesforce',
  'HubSpot',
  'Asana',
  'Slack',
  'Teams',
  'Webhooks',
  'CSV import',
  'REST API',
];

const SENTIMENT = [
  { label: 'Positive', value: 64, tone: '' },
  { label: 'Neutral', value: 23, tone: 'lp-column-bar--amber' },
  { label: 'Negative', value: 13, tone: 'lp-column-bar--red' },
];

const PAIN_POINTS = [
  ['Billing & invoicing', 214, 100],
  ['Onboarding flow', 96, 45],
  ['Dashboard performance', 41, 19],
  ['Mobile app', 23, 11],
  ['Integrations', 17, 8],
] as const;

const REQUESTS = [
  ['Invoice export', 412, 92],
  ['Team workspaces', 267, 61],
  ['SAML / SSO', 189, 43],
  ['API rate alerts', 121, 28],
] as const;

export default function Features() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      revealOnScroll();
      fillMeters('.lp-column-bar', '.lp-columns', 'y');
      fillMeters('[data-meter]', '[data-pain]', 'x');
      fillMeters('[data-req-meter]', '[data-requests]', 'x');
      revealGroup('.lp-marquee-item', '.lp-marquee', 0.01);

      gsap.utils.toArray<HTMLElement>('[data-count]').forEach((el) => {
        countUp(el, Number(el.dataset.count), el.dataset.suffix ?? '');
      });
    },
    { scope: sectionRef },
  );

  return (
    <section ref={sectionRef} id="features" className="lp-band">
      <div className="lp-section-head">
        <span data-reveal className="lp-fig">
          Fig. 04 — Extracted signals
        </span>
        <h2 data-reveal className="lp-display-2 mt-6 max-w-[20ch] text-raise">
          Four signals. No guesswork.
        </h2>
        <p data-reveal className="lp-lede mt-5">
          Every piece of feedback comes out the far end as structured data — scored, categorised,
          deduplicated and ranked — in your own database, queryable over the API.
        </p>
      </div>

      {/* 01 — Sentiment */}
      <div className="lp-feature">
        <div data-reveal>
          <span className="lp-label">01 / Sentiment</span>
          <h3 className="lp-display-3 lp-feature-title">Every word, scored.</h3>
          <p className="lp-body">
            Reviews, chats and tickets are scored positive, neutral or negative with a confidence
            value attached — not a vibe. VADER runs locally for free; an LLM key sharpens the
            edge cases without changing the schema.
          </p>
        </div>
        <div data-reveal>
          <div className="lp-columns">
            {SENTIMENT.map((s) => (
              <div key={s.label} className="lp-column">
                <div className="lp-column-head">
                  <span className="lp-column-value">
                    <span data-count={s.value} data-suffix="%">
                      0%
                    </span>
                  </span>
                  <span className="lp-column-label">{s.label}</span>
                </div>
                <span
                  className={`lp-column-bar ${s.tone}`}
                  style={{ height: `${s.value * 0.9}%` }}
                />
              </div>
            ))}
          </div>
          <p className="lp-mono-10 mt-3 text-[var(--content-quaternary)]">
            n = 1,284 · last 30 days · conf ≥ 0.7
          </p>
        </div>
      </div>

      {/* 02 — Pain points */}
      <div className="lp-feature lp-feature--flip">
        <div data-reveal>
          <span className="lp-label">02 / Pain points</span>
          <h3 className="lp-display-3 lp-feature-title">The top complaints, surfaced.</h3>
          <p className="lp-body">
            Pain points are extracted and bucketed automatically, then clustered across every
            channel. Five hundred tickets about billing collapse into one row with a count you
            can take to a planning meeting.
          </p>
        </div>
        <div data-reveal data-pain>
          <div className="mb-4 flex items-center justify-between">
            <span className="lp-mono-10 text-[var(--content-quaternary)]">Category</span>
            <span className="lp-mono-10 text-[var(--content-quaternary)]">Mentions</span>
          </div>
          <div className="lp-terms">
            {PAIN_POINTS.map(([name, count, pct]) => (
              <div key={name} className="lp-term lp-term--stacked">
                <div className="lp-term-head">
                  <span>{name}</span>
                  <span className="lp-term-count">{count}</span>
                </div>
                <span className="lp-meter">
                  <span
                    data-meter
                    className="lp-meter-fill lp-meter-fill--amber"
                    style={{ width: `${pct}%` }}
                  />
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 03 — Feature requests */}
      <div className="lp-feature">
        <div data-reveal>
          <span className="lp-label">03 / Feature requests</span>
          <h3 className="lp-display-3 lp-feature-title">What to build next, ranked.</h3>
          <p className="lp-body">
            Requests are pulled out of the noise, deduplicated across phrasings, and ranked by how
            many distinct customers actually asked. The roadmap argument stops being a matter of
            who spoke loudest.
          </p>
        </div>
        <div data-reveal data-requests>
          <div className="mb-3 flex items-center justify-between">
            <span className="lp-mono-10 text-[var(--content-quaternary)]">
              Requests · last 90 days
            </span>
            <span className="lp-mono-10 text-[var(--content-quaternary)]">Share</span>
          </div>
          {REQUESTS.map(([name, count, pct], i) => (
            <div key={name} className="lp-rank-row">
              <span className="lp-rank-idx">#{String(i + 1).padStart(2, '0')}</span>
              <span className="lp-rank-name">{name}</span>
              <span className="lp-meter">
                <span
                  data-req-meter
                  className="lp-meter-fill"
                  style={{ width: `${pct}%` }}
                />
              </span>
              <span className="lp-rank-num">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 04 — Urgent & churn */}
      <div className="lp-feature lp-feature--flip">
        <div data-reveal>
          <span className="lp-label">04 / Urgent &amp; churn</span>
          <h3 className="lp-display-3 lp-feature-title">Save the account first.</h3>
          <p className="lp-body">
            When sentiment sours or someone mentions leaving, the account is flagged and a
            playbook is suggested. Predictions are calibrated against outcomes you labelled
            yourself, and each one carries a confidence interval rather than a single number.
          </p>
        </div>
        <div data-reveal>
          <div className="lp-panel">
            <div className="lp-panel-bar">
              <span className="lp-dot" />
              <span className="lp-mono-10">alert · churn_risk</span>
              <span className="lp-badge lp-badge--red ml-auto">
                <span className="lp-dot" />
                High
              </span>
            </div>
            <div className="lp-panel-body">
              <dl className="lp-kv">
                <div className="contents">
                  <dt>account</dt>
                  <dd>Acme Inc.</dd>
                </div>
                <div className="contents">
                  <dt>probability</dt>
                  <dd className="is-red">0.92 · CI [0.86, 0.96]</dd>
                </div>
                <div className="contents">
                  <dt>drivers</dt>
                  <dd>billing · 3 negatives · 14d</dd>
                </div>
                <div className="contents">
                  <dt>playbook</dt>
                  <dd className="is-accent">save_the_customer</dd>
                </div>
                <div className="contents">
                  <dt>owner</dt>
                  <dd>unassigned → CSM</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      </div>

      {/* Integrations marquee */}
      <div className="px-[var(--gutter-width)] pt-[clamp(2.5rem,5vw,4rem)] pb-6">
        <span data-reveal className="lp-fig">
          Fig. 05 — Connected channels
        </span>
      </div>
      <div className="lp-marquee" aria-hidden="true">
        <div className="lp-marquee-track">
          {[...INTEGRATIONS, ...INTEGRATIONS].map((name, i) => (
            <span key={`${name}-${i}`} className="lp-marquee-item">
              {name}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
