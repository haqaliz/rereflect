'use client';

import { useRef } from 'react';
import { gsap, useGSAP } from '@/lib/landing/gsap';

const FEEDBACK_LINES = [
  '“The new billing page is confusing — I was charged twice and couldn’t find my invoices anywhere.”',
  '“Support fixed it fast, but the docs still don’t explain how proration works.”',
  '“If this happens again next month, we’re switching to a competitor.”',
];

const STREAM_LINES = [
  ['sentiment', 'negative · -0.82'],
  ['pain_point', 'billing · conf 0.94'],
  ['feature_req', 'invoice export'],
  ['urgency', 'churn_risk · high'],
  ['playbook', 'save_the_customer'],
];

const STATUS_STEPS = [
  'Reading feedback…',
  'Sentiment detected · negative',
  'Pain point found · billing',
  'Feature request extracted',
  'Churn risk flagged — playbook suggested',
];

const STATUS_AT = [0.85, 2.0, 2.4, 2.8, 3.6];

export default function LiveClassification() {
  const sectionRef = useRef<HTMLElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);

  useGSAPScrub(sectionRef, cardRef, progressRef);

  return (
    <section ref={sectionRef} className="relative h-[280vh]" id="live">
      <div className="lp-pin-wrap">
        <div className="lp-pin-glow" />
        <div className="lp-pin-heading">
          <span className="lp-section-eyebrow">The pipeline · live</span>
          <h2 className="lp-pin-title font-display">
            Watch feedback become <span className="lp-gradient-text">answers</span>.
          </h2>
        </div>

        <div ref={cardRef} className="lp-card-wrap relative px-6">
          <div className="lp-card">
            <div className="lp-card-header">
              <div className="lp-avatar">MC</div>
              <div>
                <div className="lp-card-name">Maya Chen</div>
                <div className="lp-card-meta">Acme Inc. · via Intercom</div>
              </div>
              <span className="lp-source-chip">intercom</span>
            </div>

            <div className="lp-fb-body">
              {FEEDBACK_LINES.map((line) => (
                <p key={line} className="lp-fb-line">
                  {line}
                </p>
              ))}
            </div>

            <div className="lp-chips">
              <span className="lp-chip lp-chip--red">
                <span className="dot" /> Sentiment · negative
              </span>
              <span className="lp-chip lp-chip--amber">
                <span className="dot" /> Pain point · billing
              </span>
              <span className="lp-chip lp-chip--coral">
                <span className="dot" /> Feature · invoice export
              </span>
              <span className="lp-chip lp-chip--red">
                <span className="dot" /> Churn risk · high
              </span>
            </div>

            <div className="lp-stream">
              {STREAM_LINES.map(([k, v], i) => (
                <div key={k} className="lp-stream-line">
                  <span className="k">{k}</span>
                  <span className={i === 4 ? 'ok' : 'v'}>{v}</span>
                </div>
              ))}
            </div>

            <div className="mt-4 flex items-center justify-between gap-4">
              {STATUS_STEPS.map((s) => (
                <span key={s} className="lp-status">
                  <span className="dot" />
                  {s}
                </span>
              ))}
              <span className="hidden text-[0.72rem] text-white/25 sm:block">
                analysis #48,213 · 0.4s
              </span>
            </div>
          </div>

          <div className="lp-float lp-float--1">
            Sentiment <b>negative</b> · match 94%
          </div>
          <div className="lp-float lp-float--2">
            <b>3 related signals</b> found this week
          </div>

          <div className="lp-progress-track" aria-hidden="true">
            <div ref={progressRef} className="lp-progress-fill" />
          </div>
        </div>
      </div>
    </section>
  );
}

function useGSAPScrub(
  sectionRef: React.RefObject<HTMLElement | null>,
  cardRef: React.RefObject<HTMLDivElement | null>,
  progressRef: React.RefObject<HTMLDivElement | null>,
) {
  useGSAP(
    () => {
      const tl = gsap.timeline({
        defaults: { ease: 'power2.out' },
        scrollTrigger: {
          trigger: sectionRef.current,
          start: 'top 85%',
          end: 'bottom top',
          scrub: 1,
        },
      });

      tl.fromTo(
        cardRef.current,
        { y: 70, autoAlpha: 0, scale: 0.94 },
        { y: 0, autoAlpha: 1, scale: 1, duration: 0.9 },
        0,
      );

      tl.fromTo(
        '.lp-fb-line',
        { y: 20, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: 0.45, stagger: 0.2 },
        1.0,
      );

      const statuses = gsap.utils.toArray<HTMLElement>('.lp-status');
      statuses.forEach((el, i) => {
        tl.set(el, { autoAlpha: 0 }, 0);
        if (i > 0) tl.set(statuses[i - 1], { autoAlpha: 0 }, STATUS_AT[i]);
        tl.to(el, { autoAlpha: 1, duration: 0.2 }, STATUS_AT[i]);
      });

      const chips = gsap.utils.toArray<HTMLElement>('.lp-chip');
      const chipAt = [2.0, 2.4, 2.8, 3.2];
      chips.forEach((el, i) => {
        tl.fromTo(
          el,
          { scale: 0.6, autoAlpha: 0 },
          { scale: 1, autoAlpha: 1, duration: 0.35 },
          chipAt[i],
        );
      });

      tl.fromTo(
        '.lp-stream-line',
        { x: -16, autoAlpha: 0 },
        { x: 0, autoAlpha: 1, duration: 0.3, stagger: 0.18 },
        3.5,
      );

      tl.fromTo(
        '.lp-float',
        { y: 24, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: 0.4, stagger: 0.15 },
        4.0,
      );

      tl.to(
        progressRef.current,
        { scaleY: 1, ease: 'none', duration: 5.4 },
        0,
      );
    },
    { scope: sectionRef },
  );
}