'use client';

import { useEffect, type ReactNode } from 'react';
import Lenis from 'lenis';
import { gsap, ScrollTrigger } from '@/lib/landing/gsap';
import { lenisStore } from '@/lib/landing/lenis';

export default function LandingSmoothScroll({ children }: { children: ReactNode }) {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const lenis = new Lenis({
      lerp: 0.09,
      wheelMultiplier: 0.95,
      smoothWheel: true,
    });
    lenisStore.lenis = lenis;

    lenis.on('scroll', ScrollTrigger.update);
    const raf = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(raf);
      lenis.destroy();
      lenisStore.lenis = null;
    };
  }, []);

  return <>{children}</>;
}