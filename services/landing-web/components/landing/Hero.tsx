'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { gsap, useGSAP } from '@/lib/landing/gsap';
import { galaxyState } from '@/lib/landing/scrollState';
import Galaxy from './Galaxy';

const HEADLINE = {
  plain: ['Your', 'customers', 'are'],
  gradient: ['already', 'telling', 'you'],
  rest: ['what', 'to', 'build.'],
};

function SignalTicker() {
  const [n, setN] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setN((v) => v + 1 + Math.floor(Math.random() * 4)), 2200);
    return () => clearInterval(id);
  }, []);
  return <span className="lp-ticker">live · +{n} signals this session</span>;
}

export default function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
      tl.to(galaxyState, { intro: 1, duration: 1.8 }, 0).fromTo(
        '[data-hero]',
        { y: 28, autoAlpha: 0, filter: 'blur(10px)' },
        { y: 0, autoAlpha: 1, filter: 'blur(0px)', duration: 1, stagger: 0.05 },
        0.1,
      );

      gsap.to(contentRef.current, {
        y: -90,
        autoAlpha: 0,
        ease: 'none',
        scrollTrigger: {
          trigger: sectionRef.current,
          start: 'top top',
          end: '72% top',
          scrub: 1,
        },
      });

      gsap.to(galaxyState, {
        t: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: sectionRef.current,
          start: 'top top',
          end: 'bottom top',
          scrub: 1.2,
        },
      });
    },
    { scope: sectionRef },
  );

  return (
    <section ref={sectionRef} className="relative h-[100svh] min-h-[620px] overflow-hidden">
      <div className="lp-hero-glow absolute inset-0" />
      <Galaxy />

      <div className="lp-hero-rings" aria-hidden="true">
        <div className="lp-hero-ring lp-hero-ring--3" />
        <div className="lp-hero-ring lp-hero-ring--1" />
        <div className="lp-hero-ring lp-hero-ring--2" />
      </div>

      <div className="relative z-10 mx-auto flex h-full max-w-5xl flex-col items-center justify-center px-6 text-center">
        <span data-hero className="lp-eyebrow">
          <span className="dot" />
          AI-powered feedback analysis · free & self-hosted
        </span>

        <h1 data-hero className="lp-hero-title font-display mt-8" aria-label="Your customers are already telling you what to build.">
          <span className="block">
            {HEADLINE.plain.map((w) => (
              <span key={w} className="lp-word">
                {w}{' '}
              </span>
            ))}
          </span>
          <span className="block">
            {HEADLINE.gradient.map((w) => (
              <span key={w} className="lp-word lp-gradient-text">
                {w}{' '}
              </span>
            ))}
          </span>
          <span className="block">
            {HEADLINE.rest.map((w) => (
              <span key={w} className="lp-word">
                {w}{' '}
              </span>
            ))}
          </span>
        </h1>

        <p data-hero className="lp-hero-sub mt-7">
          Rereflect reads every review, chat, and support ticket — then shows you the
          sentiment, the pain points, and the features people actually want. Before a
          problem becomes a churn.
        </p>

        <div data-hero className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link href="/integrations" className="lp-btn lp-btn-primary">
            Browse integrations
          </Link>
          <Link href="/blog" className="lp-btn lp-btn-ghost">
            Read the blog
          </Link>
        </div>

        <div data-hero className="lp-legend mt-12">
          <span className="lp-legend-item">
            <span className="lp-legend-dot lp-legend-dot--coral" /> positive
          </span>
          <span className="lp-legend-item">
            <span className="lp-legend-dot lp-legend-dot--amber" /> neutral
          </span>
          <span className="lp-legend-item">
            <span className="lp-legend-dot lp-legend-dot--red" /> at risk
          </span>
          <span className="hidden text-white/30 sm:inline">·</span>
          <span className="hidden sm:inline">each dot is a piece of feedback</span>
        </div>

        <div data-hero className="mt-5">
          <SignalTicker />
        </div>

        <div data-hero className="lp-scroll-cue">
          Scroll
        </div>
      </div>
    </section>
  );
}