'use client';

import { useRef } from 'react';
import { Github, ArrowRight } from 'lucide-react';
import { gsap, useGSAP } from '@/lib/landing/gsap';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';
const SELFHOST_URL = 'https://github.com/haqaliz/rereflect#self-hosting';

export default function CTA() {
  const sectionRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      gsap.fromTo(
        '[data-cta]',
        { y: 40, autoAlpha: 0 },
        {
          y: 0,
          autoAlpha: 1,
          duration: 1,
          ease: 'power3.out',
          stagger: 0.1,
          immediateRender: false,
          scrollTrigger: { trigger: sectionRef.current, start: 'top 75%', toggleActions: 'play none none reverse' },
        },
      );
    },
    { scope: sectionRef },
  );

  return (
    <section ref={sectionRef} className="lp-cta">
      <div className="lp-cta-glow" />
      <div className="relative z-10">
        <span data-cta className="lp-eyebrow">
          <span className="dot" />
          Free · open source · self-hosted
        </span>
        <h2 data-cta className="lp-cta-title font-display mt-8">
          Stop guessing.{' '}
          <span className="lp-gradient-text">Start listening.</span>
        </h2>
        <p data-cta className="lp-cta-sub">
          Self-host Rereflect on your own infrastructure and see what your customers have
          been trying to tell you — every feature unlocked, MIT licensed.
        </p>
        <div data-cta className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="lp-btn lp-btn-primary">
            <Github className="h-4 w-4" />
            View on GitHub
          </a>
          <a href={SELFHOST_URL} target="_blank" rel="noopener noreferrer" className="lp-btn lp-btn-ghost">
            Self-host guide
            <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </div>
    </section>
  );
}