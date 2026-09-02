'use client';

import { useRef } from 'react';
import { gsap, useGSAP } from '@/lib/landing/gsap';
import { EASE } from '@/lib/landing/motion';

interface PageHeroProps {
  eyebrow: string;
  title: string;
  /** Trailing fragment of the headline, rendered in the accent colour. */
  gradient?: string;
  sub?: string;
}

export default function PageHero({ eyebrow, title, gradient, sub }: PageHeroProps) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      gsap.fromTo(
        '[data-page-hero]',
        { y: 12, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: 0.8, ease: EASE, stagger: 0.06 },
      );
    },
    { scope: ref },
  );

  return (
    <div ref={ref} className="lp-page-hero">
      <span data-page-hero className="lp-fig">
        {eyebrow}
      </span>
      <h1 data-page-hero className="lp-display-1 lp-page-hero-title">
        {title}
        {gradient ? (
          <>
            {' '}
            <span className="text-accent">{gradient}</span>
          </>
        ) : null}
      </h1>
      {sub ? (
        <p data-page-hero className="lp-lede lp-page-hero-sub">
          {sub}
        </p>
      ) : null}
    </div>
  );
}
