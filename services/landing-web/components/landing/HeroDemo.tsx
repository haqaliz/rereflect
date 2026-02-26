'use client';

import { useEffect, useRef } from 'react';

export default function HeroDemo() {
  const containerRef = useRef<HTMLDivElement>(null);
  const hasAnimated = useRef(false);

  useEffect(() => {
    if (hasAnimated.current) return;
    hasAnimated.current = true;

    const mql = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (mql?.matches) return;

    let ctx: ReturnType<typeof import('gsap')['default']['context']>;

    (async () => {
      const [{ default: gsap }, { MotionPathPlugin }] = await Promise.all([
        import('gsap'),
        import('gsap/MotionPathPlugin'),
      ]);
      gsap.registerPlugin(MotionPathPlugin);

      const el = containerRef.current;
      if (!el) return;

      ctx = gsap.context(() => {
        /* ── Entrance animations ── */
        const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });

        // Source nodes stagger in
        tl.from('.source-node', {
          opacity: 0,
          y: -20,
          scale: 0.8,
          duration: 0.6,
          stagger: 0.15,
        });

        // Paths draw in (input)
        tl.fromTo(
          '.path-in',
          { strokeDashoffset: 1 },
          {
            strokeDashoffset: 0,
            duration: 0.8,
            stagger: 0.1,
            ease: 'power2.inOut',
            onComplete() {
              el.querySelectorAll<SVGPathElement>('.path-in').forEach((p) => {
                p.removeAttribute('stroke-dasharray');
                p.removeAttribute('stroke-dashoffset');
                p.style.strokeDasharray = '';
                p.style.strokeDashoffset = '';
              });
            },
          },
          '-=0.2'
        );

        // AI node
        tl.from('.ai-node', {
          opacity: 0,
          scale: 0.5,
          duration: 0.6,
          ease: 'back.out(1.7)',
          transformOrigin: 'center center',
        }, '-=0.4');

        // Paths draw in (output)
        tl.fromTo(
          '.path-out',
          { strokeDashoffset: 1 },
          {
            strokeDashoffset: 0,
            duration: 0.8,
            stagger: 0.1,
            ease: 'power2.inOut',
            onComplete() {
              el.querySelectorAll<SVGPathElement>('.path-out').forEach((p) => {
                p.removeAttribute('stroke-dasharray');
                p.removeAttribute('stroke-dashoffset');
                p.style.strokeDasharray = '';
                p.style.strokeDashoffset = '';
              });
            },
          },
          '-=0.3'
        );

        // Output nodes stagger in
        tl.from('.output-node', {
          opacity: 0,
          y: 20,
          scale: 0.8,
          duration: 0.6,
          stagger: 0.15,
        }, '-=0.4');

        /* ── Looping ambient animations ── */

        // AI node pulse
        gsap.to('.ai-glow', {
          scale: 1.3,
          opacity: 0,
          duration: 1.5,
          repeat: -1,
          ease: 'power1.out',
          transformOrigin: 'center center',
        });

        gsap.to('.ai-glow-2', {
          scale: 1.3,
          opacity: 0,
          duration: 1.5,
          delay: 0.75,
          repeat: -1,
          ease: 'power1.out',
          transformOrigin: 'center center',
        });

        // AI node breathing
        gsap.to('.ai-body', {
          scale: 1.05,
          duration: 2,
          repeat: -1,
          yoyo: true,
          ease: 'sine.inOut',
          transformOrigin: 'center center',
        });

        // Particles along input paths
        const inputPaths = ['#pathIn1', '#pathIn2', '#pathIn3'];
        const inputColors = ['#f97316', '#f97316', '#f97316'];
        inputPaths.forEach((path, i) => {
          for (let p = 0; p < 2; p++) {
            const particle = el.querySelector(`.particle-in-${i}-${p}`);
            if (!particle) return;
            gsap.to(particle, {
              motionPath: {
                path: path,
                align: path,
                alignOrigin: [0.5, 0.5],
              },
              duration: 2,
              repeat: -1,
              delay: p * 1,
              ease: 'none',
              opacity: 1,
            });
            // Fade out at end
            gsap.to(particle, {
              opacity: 0,
              duration: 0.3,
              repeat: -1,
              delay: p * 1 + 1.7,
              repeatDelay: 1.7,
            });
          }
        });

        // Particles along output paths
        const outputPaths = ['#pathOut1', '#pathOut2', '#pathOut3', '#pathOut4'];
        const outputColors = ['#22c55e', '#f59e0b', '#3b82f6', '#ef4444'];
        outputPaths.forEach((path, i) => {
          for (let p = 0; p < 2; p++) {
            const particle = el.querySelector(`.particle-out-${i}-${p}`);
            if (!particle) return;
            gsap.set(particle, { attr: { fill: outputColors[i] } });
            gsap.to(particle, {
              motionPath: {
                path: path,
                align: path,
                alignOrigin: [0.5, 0.5],
              },
              duration: 2,
              repeat: -1,
              delay: p * 1 + 0.5,
              ease: 'none',
              opacity: 1,
            });
            gsap.to(particle, {
              opacity: 0,
              duration: 0.3,
              repeat: -1,
              delay: p * 1 + 0.5 + 1.7,
              repeatDelay: 1.7,
            });
          }
        });

      }, el);
    })();

    return () => {
      ctx?.revert();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="hero-demo relative rounded-3xl overflow-hidden bg-card border border-border shadow-2xl shadow-primary/10 p-4 sm:p-6"
      aria-label="Product demo animation"
      data-testid="hero-demo"
    >
      <svg
        viewBox="0 0 520 400"
        width="100%"
        height="100%"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label="AI feedback analysis flow"
      >
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="glow-soft" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          {/* Gradients */}
          <linearGradient id="grad-green" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#22c55e" />
          </linearGradient>
          <linearGradient id="grad-amber" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#f59e0b" />
          </linearGradient>
          <linearGradient id="grad-blue" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#3b82f6" />
          </linearGradient>
          <linearGradient id="grad-red" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>

          {/* Input paths */}
          <path id="pathIn1" d="M 100 80 C 130 130, 200 145, 230 170" fill="none" />
          <path id="pathIn2" d="M 260 80 L 260 165" fill="none" />
          <path id="pathIn3" d="M 420 80 C 390 130, 320 145, 290 170" fill="none" />

          {/* Output paths */}
          <path id="pathOut1" d="M 230 230 C 190 260, 100 275, 70 320" fill="none" />
          <path id="pathOut2" d="M 245 238 C 220 270, 210 295, 200 322" fill="none" />
          <path id="pathOut3" d="M 275 238 C 300 270, 310 295, 320 322" fill="none" />
          <path id="pathOut4" d="M 290 230 C 330 260, 420 275, 450 320" fill="none" />
        </defs>

        {/* ── Input Paths (visible) ── */}
        <path
          className="path-in"
          d="M 100 80 C 130 130, 200 145, 230 170"
          stroke="#f97316"
          strokeWidth="1.5"
          strokeDasharray="1"
          pathLength={1}
          strokeDashoffset={1}
          fill="none"
          opacity={0.3}
        />
        <path
          className="path-in"
          d="M 260 80 L 260 165"
          stroke="#f97316"
          strokeWidth="1.5"
          strokeDasharray="1"
          pathLength={1}
          strokeDashoffset={1}
          fill="none"
          opacity={0.3}
        />
        <path
          className="path-in"
          d="M 420 80 C 390 130, 320 145, 290 170"
          stroke="#f97316"
          strokeWidth="1.5"
          strokeDasharray="1"
          pathLength={1}
          strokeDashoffset={1}
          fill="none"
          opacity={0.3}
        />

        {/* ── Output Paths (visible) ── */}
        <path
          className="path-out"
          d="M 230 230 C 190 260, 100 275, 70 320"
          stroke="url(#grad-green)"
          strokeWidth="1.5"
          strokeDasharray="1"
          pathLength={1}
          strokeDashoffset={1}
          fill="none"
          opacity={0.4}
        />
        <path
          className="path-out"
          d="M 245 238 C 220 270, 210 295, 200 322"
          stroke="url(#grad-amber)"
          strokeWidth="1.5"
          strokeDasharray="1"
          pathLength={1}
          strokeDashoffset={1}
          fill="none"
          opacity={0.4}
        />
        <path
          className="path-out"
          d="M 275 238 C 300 270, 310 295, 320 322"
          stroke="url(#grad-blue)"
          strokeWidth="1.5"
          strokeDasharray="1"
          pathLength={1}
          strokeDashoffset={1}
          fill="none"
          opacity={0.4}
        />
        <path
          className="path-out"
          d="M 290 230 C 330 260, 420 275, 450 320"
          stroke="url(#grad-red)"
          strokeWidth="1.5"
          strokeDasharray="1"
          pathLength={1}
          strokeDashoffset={1}
          fill="none"
          opacity={0.4}
        />

        {/* ── Input Particles ── */}
        {[0, 1, 2].map((i) =>
          [0, 1].map((p) => (
            <circle
              key={`in-${i}-${p}`}
              className={`flow-particle particle-in-${i}-${p}`}
              r="3"
              fill="#f97316"
              opacity={0}
              filter="url(#glow)"
            />
          ))
        )}

        {/* ── Output Particles ── */}
        {[0, 1, 2, 3].map((i) =>
          [0, 1].map((p) => (
            <circle
              key={`out-${i}-${p}`}
              className={`flow-particle particle-out-${i}-${p}`}
              r="3"
              fill="#f97316"
              opacity={0}
              filter="url(#glow)"
            />
          ))
        )}

        {/* ── Source Nodes ── */}
        <g className="source-node" data-testid="source-slack">
          <rect x="60" y="45" width="80" height="36" rx="18" style={{ fill: 'var(--card)', stroke: 'var(--border)' }} strokeWidth="1.5" />
          <rect x="60" y="45" width="80" height="36" rx="18" fill="#f97316" fillOpacity={0.08} />
          <text x="100" y="63" textAnchor="middle" dominantBaseline="central" style={{ fill: 'var(--foreground)' }} fontFamily="var(--font-sans), system-ui, sans-serif" fontSize="13" fontWeight="500">Slack</text>
        </g>

        <g className="source-node" data-testid="source-email">
          <rect x="220" y="45" width="80" height="36" rx="18" style={{ fill: 'var(--card)', stroke: 'var(--border)' }} strokeWidth="1.5" />
          <rect x="220" y="45" width="80" height="36" rx="18" fill="#f97316" fillOpacity={0.08} />
          <text x="260" y="63" textAnchor="middle" dominantBaseline="central" style={{ fill: 'var(--foreground)' }} fontFamily="var(--font-sans), system-ui, sans-serif" fontSize="13" fontWeight="500">Email</text>
        </g>

        <g className="source-node" data-testid="source-intercom">
          <rect x="375" y="45" width="90" height="36" rx="18" style={{ fill: 'var(--card)', stroke: 'var(--border)' }} strokeWidth="1.5" />
          <rect x="375" y="45" width="90" height="36" rx="18" fill="#f97316" fillOpacity={0.08} />
          <text x="420" y="63" textAnchor="middle" dominantBaseline="central" style={{ fill: 'var(--foreground)' }} fontFamily="var(--font-sans), system-ui, sans-serif" fontSize="13" fontWeight="500">Intercom</text>
        </g>

        {/* ── AI Center Node ── */}
        <g data-testid="ai-brain">
          {/* Pulse rings */}
          <circle className="ai-glow pulse-ring" cx="260" cy="200" r="38" fill="none" stroke="#f97316" strokeWidth="2" opacity={0.5} />
          <circle className="ai-glow-2 pulse-ring" cx="260" cy="200" r="38" fill="none" stroke="#f97316" strokeWidth="2" opacity={0.5} />

          {/* Main circle */}
          <g className="ai-node ai-body">
            <circle cx="260" cy="200" r="38" style={{ fill: 'var(--card)' }} stroke="#f97316" strokeWidth="2" strokeOpacity={0.5} />
            <circle cx="260" cy="200" r="36" fill="#f97316" fillOpacity={0.1} />
            <text x="260" y="200" textAnchor="middle" dominantBaseline="central" fill="#f97316" fontFamily="var(--font-sans), system-ui, sans-serif" fontSize="20" fontWeight="700" letterSpacing="2">AI</text>
          </g>
        </g>

        {/* ── Output Nodes ── */}
        <g className="output-node" data-testid="output-positive">
          <rect x="25" y="322" width="90" height="36" rx="18" style={{ fill: 'var(--card)', stroke: 'var(--border)' }} strokeWidth="1.5" />
          <rect x="25" y="322" width="90" height="36" rx="18" fill="#22c55e" fillOpacity={0.08} />
          <text x="70" y="340" textAnchor="middle" dominantBaseline="central" fill="#22c55e" fontFamily="var(--font-sans), system-ui, sans-serif" fontSize="12" fontWeight="500">Positive</text>
        </g>

        <g className="output-node" data-testid="output-pain-point">
          <rect x="150" y="322" width="100" height="36" rx="18" style={{ fill: 'var(--card)', stroke: 'var(--border)' }} strokeWidth="1.5" />
          <rect x="150" y="322" width="100" height="36" rx="18" fill="#f59e0b" fillOpacity={0.08} />
          <text x="200" y="340" textAnchor="middle" dominantBaseline="central" fill="#f59e0b" fontFamily="var(--font-sans), system-ui, sans-serif" fontSize="12" fontWeight="500">Pain Point</text>
        </g>

        <g className="output-node" data-testid="output-feature">
          <rect x="275" y="322" width="90" height="36" rx="18" style={{ fill: 'var(--card)', stroke: 'var(--border)' }} strokeWidth="1.5" />
          <rect x="275" y="322" width="90" height="36" rx="18" fill="#3b82f6" fillOpacity={0.08} />
          <text x="320" y="340" textAnchor="middle" dominantBaseline="central" fill="#3b82f6" fontFamily="var(--font-sans), system-ui, sans-serif" fontSize="12" fontWeight="500">Feature</text>
        </g>

        <g className="output-node" data-testid="output-churn-risk">
          <rect x="395" y="322" width="110" height="36" rx="18" style={{ fill: 'var(--card)', stroke: 'var(--border)' }} strokeWidth="1.5" />
          <rect x="395" y="322" width="110" height="36" rx="18" fill="#ef4444" fillOpacity={0.08} />
          <text x="450" y="340" textAnchor="middle" dominantBaseline="central" fill="#ef4444" fontFamily="var(--font-sans), system-ui, sans-serif" fontSize="12" fontWeight="500">Churn Risk</text>
        </g>
      </svg>
    </div>
  );
}
