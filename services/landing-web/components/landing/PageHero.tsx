'use client';

import { useRef } from 'react';
import { gsap, useGSAP } from '@/lib/landing/gsap';

interface PageHeroProps {
  eyebrow: string;
  title: string;
  gradient?: string;
  sub?: string;
}

export default function PageHero({ eyebrow, title, gradient, sub }: PageHeroProps) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      gsap.fromTo(
        '[data-page-hero]',
        { y: 30, autoAlpha: 0, filter: 'blur(8px)' },
        { y: 0, autoAlpha: 1, filter: 'blur(0px)', duration: 1, ease: 'power3.out', stagger: 0.08 },
      );
    },
    { scope: ref },
  );

  return (
    <div ref={ref} className="lp-page-hero">
      <span data-page-hero className="lp-section-eyebrow">
        {eyebrow}
      </span>
      <h1 data-page-hero className="lp-page-hero-title font-display">
        {title}
        {gradient ? (
          <>
            {' '}
            <span className="lp-gradient-text">{gradient}</span>
          </>
        ) : null}
      </h1>
      {sub ? <p data-page-hero className="lp-page-hero-sub">{sub}</p> : null}
    </div>
  );
}