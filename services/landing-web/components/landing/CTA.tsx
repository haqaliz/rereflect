'use client';

import { useRef } from 'react';
import { Github, ArrowRight } from 'lucide-react';
import { useGSAP } from '@/lib/landing/gsap';
import { revealOnScroll } from '@/lib/landing/motion';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';
const SELFHOST_URL = 'https://github.com/haqaliz/rereflect#self-hosting';

const STEPS = [
  ['01', 'git clone', 'Pull the monorepo and copy .env.example.'],
  ['02', 'docker compose up', 'Postgres, Redis, API, worker and web.'],
  ['03', 'alembic upgrade head', 'Schema applied; the console is live on :3000.'],
];

export default function CTA() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(() => revealOnScroll(), { scope: sectionRef });

  return (
    <section ref={sectionRef} className="lp-cta">
      <div className="lp-cta-mesh" aria-hidden="true" />

      <div className="relative z-10">
        <span data-reveal className="lp-fig lp-fig--accent">
          Fig. 08 — Deployment
        </span>

        <h2 data-reveal className="lp-display-2 lp-cta-title">
          Stop guessing. Run it yourself.
        </h2>

        <p data-reveal className="lp-lede mt-5">
          Three commands and roughly thirty minutes. No account, no trial, no sales call — the
          whole thing is MIT licensed and runs on infrastructure you already have.
        </p>

        <div data-reveal className="mt-9 flex flex-wrap items-center gap-3">
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
            View on GitHub
          </a>
        </div>

        <div data-reveal className="lp-steps">
          {STEPS.map(([n, cmd, note]) => (
            <div key={n}>
              <span className="lp-mono-10 text-[var(--content-quaternary)]">{n}</span>
              <code className="lp-mono-value mt-1.5 block text-[0.8125rem] text-[var(--content-accent)]">
                {cmd}
              </code>
              <span className="mt-1.5 block text-[0.75rem] leading-relaxed text-[var(--content-tertiary)]">
                {note}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
