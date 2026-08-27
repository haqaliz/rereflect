'use client';

import { useRef } from 'react';
import { gsap, useGSAP } from '@/lib/landing/gsap';

const INTEGRATIONS = [
  'Intercom',
  'Zendesk',
  'Jira',
  'Linear',
  'Salesforce',
  'Asana',
  'Slack',
  'Webhooks',
  'CSV import',
  'REST API',
];

const PAIN_CHIPS = [
  ['Billing', '214'],
  ['Onboarding', '96'],
  ['Performance', '41'],
  ['Mobile app', '23'],
  ['Integrations', '17'],
];

const REQUESTS = [
  ['Invoice export', '412', 92],
  ['Team workspaces', '267', 61],
  ['SAML / SSO', '189', 43],
  ['API rate alerts', '121', 28],
];

function countUp(el: HTMLElement, target: number) {
  const obj = { v: 0 };
  gsap.to(obj, {
    v: target,
    duration: 1.5,
    ease: 'power2.out',
    scrollTrigger: { trigger: el, start: 'top 90%', once: true },
    onUpdate: () => {
      el.textContent = String(Math.round(obj.v));
    },
  });
}

export default function Features() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      gsap.utils.toArray<HTMLElement>('[data-reveal]').forEach((el) => {
        gsap.fromTo(
          el,
          { y: 40, autoAlpha: 0 },
          {
            y: 0,
            autoAlpha: 1,
            duration: 1,
            ease: 'power3.out',
            immediateRender: false,
            scrollTrigger: { trigger: el, start: 'top 88%', toggleActions: 'play none none reverse' },
          },
        );
      });

      gsap.fromTo(
        '.lp-bar',
        { scaleY: 0 },
        {
          scaleY: 1,
          duration: 1.2,
          ease: 'power3.out',
          stagger: 0.18,
          scrollTrigger: { trigger: '.lp-bars', start: 'top 82%', once: true },
        },
      );
      gsap.utils.toArray<HTMLElement>('.lp-bar-value').forEach((el) => {
        countUp(el, Number(el.dataset.count ?? 0));
      });

      gsap.utils.toArray<HTMLElement>('.lp-pain-chip').forEach((el, i) => {
        gsap.fromTo(
          el,
          { y: 18, autoAlpha: 0, scale: 0.9 },
          {
            y: 0,
            autoAlpha: 1,
            scale: 1,
            duration: 0.6,
            delay: i * 0.09,
            ease: 'power3.out',
            immediateRender: false,
            scrollTrigger: { trigger: '.lp-chip-cloud', start: 'top 85%', once: true },
          },
        );
      });

      gsap.fromTo(
        '.lp-req-row',
        { y: 24, autoAlpha: 0 },
        {
          y: 0,
          autoAlpha: 1,
          duration: 0.6,
          stagger: 0.12,
          immediateRender: false,
          scrollTrigger: { trigger: '.lp-req-list', start: 'top 85%', once: true },
        },
      );
      gsap.fromTo(
        '.lp-req-bar-fill',
        { scaleX: 0 },
        {
          scaleX: 1,
          duration: 1,
          ease: 'power3.out',
          stagger: 0.15,
          scrollTrigger: { trigger: '.lp-req-list', start: 'top 85%', once: true },
        },
      );

      gsap.fromTo(
        '.lp-alert-card',
        { y: 30, autoAlpha: 0 },
        {
          y: 0,
          autoAlpha: 1,
          duration: 0.9,
          ease: 'power3.out',
          immediateRender: false,
          scrollTrigger: { trigger: '.lp-alert-card', start: 'top 85%', once: true },
        },
      );
    },
    { scope: sectionRef },
  );

  return (
    <section ref={sectionRef} id="features" className="relative">
      <div className="mx-auto max-w-6xl px-6 pt-28 lg:pt-40">
        <div data-reveal className="max-w-2xl">
          <span className="lp-section-eyebrow">What you get</span>
          <h2 className="lp-feature-title font-display mt-4">
            Four signals. <span className="lp-gradient-text">Zero guesswork.</span>
          </h2>
          <p className="lp-feature-copy">
            Every piece of feedback passes through the same pipeline and comes out as
            structured, actionable signals you can build on.
          </p>
        </div>

        {/* Sentiment */}
        <div className="lp-feature-row lg:grid-cols-[1fr_1fr]">
          <div>
            <span className="lp-section-eyebrow">01 · Sentiment</span>
            <h3 className="lp-feature-title font-display">Every word, scored.</h3>
            <p className="lp-feature-copy">
              Reviews, chats, and tickets are scored positive, neutral, or negative — with a
              confidence value, not a vibe. No more skimming hundreds of tickets to find out
              how customers actually feel.
            </p>
          </div>
          <div className="lp-visual">
            <div className="lp-bars">
              {[
                ['Positive', 64, 'coral'],
                ['Neutral', 23, 'amber'],
                ['Negative', 13, 'red'],
              ].map(([label, count, tone]) => (
                <div key={label as string} className="lp-bar-col">
                  <span className="lp-bar-value" data-count={count}>
                    0
                  </span>
                  <span
                    className={`lp-bar lp-bar--${tone}`}
                    style={{ height: `${(count as number) * 1.7}%` }}
                  />
                  <span className="lp-bar-label">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Pain points */}
        <div className="lp-feature-row lg:grid-cols-[1fr_1fr]">
          <div>
            <span className="lp-section-eyebrow">02 · Pain points</span>
            <h3 className="lp-feature-title font-display">The top complaints, surfaced.</h3>
            <p className="lp-feature-copy">
              Pain points are extracted and bucketed automatically — billing, onboarding,
              performance — so the issues customers keep hitting rise to the top on their own.
            </p>
          </div>
          <div className="lp-visual">
            <div className="lp-chip-cloud">
              {PAIN_CHIPS.map(([name, count]) => (
                <span key={name} className="lp-pain-chip">
                  {name} <span>×{count}</span>
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Feature requests */}
        <div className="lp-feature-row lg:grid-cols-[1fr_1fr]">
          <div>
            <span className="lp-section-eyebrow">03 · Feature requests</span>
            <h3 className="lp-feature-title font-display">What to build next, ranked.</h3>
            <p className="lp-feature-copy">
              Feature requests are pulled out of the noise, deduplicated, and ranked by how
              many customers actually asked. Your roadmap writes itself.
            </p>
          </div>
          <div className="lp-visual">
            <div className="mb-4 flex items-center justify-between text-[0.72rem]">
              <span className="lp-section-eyebrow">Requests · last 90 days</span>
              <span className="font-mono text-white/40">share of all requests</span>
            </div>
            <div className="lp-req-list">
              {REQUESTS.map(([name, count, pct], i) => (
                <div key={name} className="lp-req-row">
                  <span className="lp-req-rank">#{(i + 1).toString().padStart(2, '0')}</span>
                  <span className="lp-req-name">{name}</span>
                  <span className="lp-req-bar">
                    <span className="lp-req-bar-fill" style={{ width: `${pct}%` }} />
                  </span>
                  <span className="lp-req-count">{count}</span>
                  <span className="lp-req-pct">{pct}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Urgent / churn */}
        <div className="lp-feature-row lg:grid-cols-[1fr_1fr] border-b-0">
          <div>
            <span className="lp-section-eyebrow">04 · Urgent & churn</span>
            <h3 className="lp-feature-title font-display">Save the customer first.</h3>
            <p className="lp-feature-copy">
              When sentiment sours or someone mentions leaving, Rereflect flags the account
              and suggests a playbook — while there is still time to act.
            </p>
          </div>
          <div className="lp-visual">
            <div className="lp-alert-card">
              <span className="lp-alert-pulse" />
              <div>
                <div className="lp-alert-title">Churn risk · high</div>
                <div className="lp-alert-meta">Maya Chen · Acme Inc. · 92% match</div>
              </div>
              <span className="lp-playbook">Playbook: save_the_customer</span>
            </div>
          </div>
        </div>
      </div>

      {/* Integrations */}
      <div className="mt-20 lg:mt-28">
        <div className="mx-auto max-w-6xl px-6">
          <span data-reveal className="lp-section-eyebrow">
            Works where your feedback lives
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
      </div>
    </section>
  );
}