'use client';

import { useRef } from 'react';
import { Github, ArrowRight } from 'lucide-react';
import { useGSAP } from '@/lib/landing/gsap';
import { revealOnScroll } from '@/lib/landing/motion';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';
const SELFHOST_URL = 'https://github.com/haqaliz/rereflect#self-hosting';

export default function SubpageCTA() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(() => revealOnScroll(), { scope: sectionRef });

  return (
    <section ref={sectionRef} className="lp-cta">
      <div className="lp-cta-mesh" aria-hidden="true" />

      <div className="relative z-10">
        <span data-reveal className="lp-fig lp-fig--accent">
          Deployment
        </span>
        <h2 data-reveal className="lp-display-2 lp-cta-title">
          Self-host it and connect your tools.
        </h2>
        <p data-reveal className="lp-lede mt-5">
          Deploy Rereflect on your own infrastructure and wire up every feedback channel you
          already use. MIT licensed, every feature unlocked.
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
      </div>
    </section>
  );
}
