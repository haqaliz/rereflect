'use client';

import { useRef } from 'react';
import { ArrowRight, Github } from 'lucide-react';
import { gsap, useGSAP } from '@/lib/landing/gsap';
import { EASE, countUp } from '@/lib/landing/motion';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';
const SELFHOST_URL = 'https://github.com/haqaliz/rereflect#self-hosting';

/** The specimen record shown in FIG. 01 — one feedback item, fully classified. */
const RECORD = [
  ['source', 'intercom', ''],
  ['customer', 'maya.chen@acme.io', ''],
  ['sentiment', 'negative · −0.82', 'is-red'],
  ['pain_point', 'billing · conf 0.94', 'is-amber'],
  ['feature_req', 'invoice_export', 'is-accent'],
  ['churn_risk', 'high · 92%', 'is-red'],
  ['playbook', 'save_the_customer', 'is-accent'],
] as const;

const SPECS = [
  { label: 'License', value: 'MIT', note: 'Fork it, ship it, sell it.', count: null },
  { label: 'Feature gates', value: 0, note: 'No tiers, no seats, no SSO tax.', count: 0 },
  { label: 'Integrations', value: 10, note: 'Slack, Intercom, Zendesk, Jira…', count: 10 },
  { label: 'Data leaving your box', value: 'NONE', note: 'VADER runs fully offline.', count: null },
];

export default function Hero() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (!reduced) {
        gsap
          .timeline({ defaults: { ease: EASE } })
          .fromTo(
            '[data-hero]',
            { y: 12, autoAlpha: 0 },
            { y: 0, autoAlpha: 1, duration: 0.8, stagger: 0.06 },
            0,
          )
          .fromTo(
            '[data-hero-panel]',
            { y: 16, autoAlpha: 0 },
            { y: 0, autoAlpha: 1, duration: 0.9 },
            0.24,
          )
          .fromTo(
            '.lp-kv dd',
            { autoAlpha: 0, x: -6 },
            { autoAlpha: 1, x: 0, duration: 0.4, stagger: 0.07 },
            0.55,
          );
      }

      gsap.utils.toArray<HTMLElement>('[data-count]').forEach((el) => {
        countUp(el, Number(el.dataset.count));
      });
    },
    { scope: sectionRef },
  );

  return (
    <section ref={sectionRef} className="lp-hero">
      <div className="lp-hero-mesh" aria-hidden="true" />

      <div className="lp-hero-body lp-grid">
        <div className="col-span-12 lg:col-span-7">
          <span data-hero className="lp-fig lp-fig--accent">
            Fig. 01 — Feedback analysis pipeline
          </span>

          <h1 data-hero className="lp-display-1 lp-hero-title">
            Your customers are already telling you <span className="lp-accent">what to build</span>.
          </h1>

          <p data-hero className="lp-lede mt-7">
            Rereflect reads every review, ticket and chat you receive and returns structured
            signal: sentiment, pain points, ranked feature requests and churn risk. Self-hosted,
            MIT licensed, every feature unlocked.
          </p>

          <div data-hero className="lp-hero-actions">
            <a
              href={SELFHOST_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="lp-btn lp-btn-primary"
            >
              Self-host guide
              <ArrowRight className="h-3.5 w-3.5" />
            </a>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="lp-btn lp-btn-ghost"
            >
              <Github className="h-3.5 w-3.5" />
              View source
            </a>
          </div>
        </div>

        <div data-hero-panel className="col-span-12 mt-4 lg:col-span-5 lg:mt-0">
          <div className="lp-panel">
            <div className="lp-panel-bar">
              <span className="lp-dot" />
              <span className="lp-mono-10">analysis · 48,213</span>
              <span className="lp-mono-10 ml-auto">0.4s</span>
            </div>
            <div className="lp-panel-body">
              <p className="lp-quote">
                “The new billing page is confusing — I was charged twice and couldn&rsquo;t find my
                invoices anywhere. If this happens again next month we&rsquo;re switching.”
              </p>
              <dl className="lp-kv">
                {RECORD.map(([k, v, tone]) => (
                  <div key={k} className="contents">
                    <dt>{k}</dt>
                    <dd className={tone}>{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </div>
      </div>

      <div className="lp-spec">
        {SPECS.map((spec) => (
          <div key={spec.label} className="lp-spec-cell">
            <span className="lp-label">{spec.label}</span>
            <span className="lp-spec-value">
              {spec.count === null ? (
                spec.value
              ) : (
                <span data-count={spec.count}>0</span>
              )}
            </span>
            <span className="lp-spec-note">{spec.note}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
