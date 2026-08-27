'use client';

import { useRef, type ReactNode } from 'react';
import { gsap, useGSAP } from '@/lib/landing/gsap';

export default function RevealGrid({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      gsap.fromTo(
        '.lp-tile',
        { y: 40, autoAlpha: 0 },
        {
          y: 0,
          autoAlpha: 1,
          duration: 0.8,
          stagger: 0.08,
          ease: 'power3.out',
          immediateRender: false,
          scrollTrigger: { trigger: '.lp-tile-grid', start: 'top 88%', toggleActions: 'play none none reverse' },
        },
      );
    },
    { scope: ref },
  );

  return <div ref={ref}>{children}</div>;
}