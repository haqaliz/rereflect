'use client';

import { useRef } from 'react';
import { Github, ArrowRight } from 'lucide-react';
import { gsap, useGSAP } from '@/lib/landing/gsap';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';
const SELFHOST_URL = 'https://github.com/haqaliz/rereflect#self-hosting';

export default function SubpageCTA() {
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
          scrollTrigger: { trigger: sectionRef.current, start: 'top 80%', toggleActions: 'play none none reverse' },
        },
      );
    },
    { scope: sectionRef },
  );

  return (
    <section ref={sectionRef} className="lp-cta">
      <div className="lp-cta-glow" />
      <div className="relative z-10">
        <h2 data-cta className="lp-cta-title font-display">
          Self-host and <span className="lp-gradient-text">connect your tools.</span>
        </h2>
        <p data-cta className="lp-cta-sub">
          Deploy Rereflect on your own infrastructure and connect every feedback channel in
          minutes.
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