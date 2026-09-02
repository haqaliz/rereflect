'use client';

import { useRef } from 'react';
import { useGSAP } from '@/lib/landing/gsap';
import { revealOnScroll } from '@/lib/landing/motion';

const MANUAL = [
  'Someone reads tickets on Friday afternoon and writes a summary nobody trusts',
  'The same complaint gets counted twice, or not at all',
  'Feedback lives in six tools and gets reconciled in a spreadsheet',
  'By the time a churn signal is spotted, the renewal has already lapsed',
];

const SAAS = [
  'Per-seat pricing, so the people closest to customers never get a login',
  'Your customers’ words sitting on a vendor’s infrastructure, indefinitely',
  'SSO, audit logs and the API held back for the enterprise tier',
  'Export is a support ticket, and the model behind the scores is a black box',
];

export default function Comparison() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(() => revealOnScroll(), { scope: sectionRef });

  return (
    <section ref={sectionRef} className="lp-band">
      <div className="lp-section-head">
        <span data-reveal className="lp-fig">
          Fig. 03 — Prior art
        </span>
        <h2 data-reveal className="lp-display-2 mt-6 max-w-[26ch] text-raise">
          For years, teams had two ways to understand their customers. Both cost you something.
        </h2>
      </div>

      <div className="lp-compare">
        <div className="lp-compare-col" data-reveal>
          <span className="lp-label">Manual triage</span>
          <h3 className="lp-display-3 lp-compare-title">Control, at the cost of coverage</h3>
          <div className="lp-compare-list">
            {MANUAL.map((item) => (
              <p key={item} className="lp-compare-item">
                <span>{item}</span>
              </p>
            ))}
          </div>
        </div>

        <div className="lp-compare-col" data-reveal>
          <span className="lp-label">Hosted feedback SaaS</span>
          <h3 className="lp-display-3 lp-compare-title">Coverage, at the cost of control</h3>
          <div className="lp-compare-list">
            {SAAS.map((item) => (
              <p key={item} className="lp-compare-item">
                <span>{item}</span>
              </p>
            ))}
          </div>
        </div>
      </div>

      <div className="lp-compare-col lp-compare-col--ours border-t border-[var(--stroke-secondary)]" data-reveal>
        <span className="lp-label text-accent">Rereflect</span>
        <h3 className="lp-display-3 lp-compare-title">Both, on hardware you own</h3>
        <div className="lp-compare-list max-w-[80ch]">
          <p className="lp-compare-item">
            <span>
              Runs on your own Postgres and Redis. The feedback never leaves your network unless
              you point it at an LLM yourself.
            </span>
          </p>
          <p className="lp-compare-item">
            <span>
              MIT licensed with no plan checks in the code path — SSO, the API, automations and
              churn prediction are all simply on.
            </span>
          </p>
          <p className="lp-compare-item">
            <span>
              Bring your own key, or run entirely offline on VADER for free. Swap the model
              whenever you like; the scores stay in your database either way.
            </span>
          </p>
        </div>
      </div>
    </section>
  );
}
