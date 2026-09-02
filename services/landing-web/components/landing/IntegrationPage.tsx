'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  ChevronLeft,
  ClipboardCheck,
  DollarSign,
  FileText,
  Github,
  Hash,
  Headphones,
  Heart,
  KeyRound,
  Layers,
  Mail,
  MessageCircle,
  MessageSquare,
  Plus,
  RefreshCw,
  Rocket,
  Search,
  Shield,
  Star,
  Tags,
  Target,
  TrendingUp,
  UserCheck,
  Users,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { getIntegration } from '@/lib/integrations';
import { useGSAP } from '@/lib/landing/gsap';
import { gsap } from '@/lib/landing/gsap';
import { EASE, revealOnScroll } from '@/lib/landing/motion';
import Nav from '@/components/landing/Nav';
import Footer from '@/components/landing/Footer';
import SubpageCTA from '@/components/landing/SubpageCTA';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';

const ICONS: Record<string, LucideIcon> = {
  AlertTriangle,
  Bell,
  ClipboardCheck,
  DollarSign,
  FileText,
  Hash,
  Headphones,
  Heart,
  KeyRound,
  Layers,
  Mail,
  MessageCircle,
  MessageSquare,
  RefreshCw,
  Rocket,
  Search,
  Shield,
  Star,
  Tags,
  Target,
  TrendingUp,
  UserCheck,
  Users,
  Zap,
};

export default function IntegrationPage({ slug }: { slug: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [openFAQ, setOpenFAQ] = useState<number | null>(0);

  const integration = getIntegration(slug);

  useGSAP(
    () => {
      if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        gsap.fromTo(
          '[data-ih]',
          { y: 12, autoAlpha: 0 },
          { y: 0, autoAlpha: 1, duration: 0.8, ease: EASE, stagger: 0.06 },
        );
      }
      revealOnScroll();
    },
    { scope: containerRef },
  );

  if (!integration) {
    return null;
  }

  return (
    <div ref={containerRef}>
      <Nav />
      <main>
        <div className="lp-page">
          <div className="lp-page-hero">
            <span data-ih className="lp-fig">
              {integration.name} integration
            </span>
            <h1 data-ih className="lp-display-1 lp-page-hero-title">
              {integration.name} <span className="text-accent">+</span> Rereflect
            </h1>
            <p data-ih className="lp-lede lp-page-hero-sub">
              {integration.heroMessage}
            </p>
            <div data-ih className="mt-9 flex flex-wrap gap-3">
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="lp-btn lp-btn-primary"
              >
                <Github className="h-3.5 w-3.5" />
                View on GitHub
              </a>
              <a
                href="#how-it-works"
                className="lp-btn lp-btn-ghost"
                onClick={(e) => {
                  e.preventDefault();
                  document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                How it works
                <ArrowRight className="h-3.5 w-3.5" />
              </a>
            </div>
          </div>

          <div className="lp-section-block" id="how-it-works">
            <div className="lp-section-head">
              <span data-reveal className="lp-fig">
                Fig. 01 — How it works
              </span>
              <h2 data-reveal className="lp-display-2 mt-6 max-w-[20ch] text-raise">
                Up and running in minutes.
              </h2>
            </div>
            <div className="lp-cells md:grid-cols-3">
              {integration.howItWorks.map((step, i) => (
                <div key={step.step} data-reveal className="lp-cell">
                  <span className="lp-mono-sm text-accent">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <h3 className="lp-display-3 mt-3 text-raise">{step.title}</h3>
                  <p className="lp-body mt-2.5 text-[0.875rem]">{step.description}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="lp-section-block">
            <div className="lp-section-head">
              <span data-reveal className="lp-fig">
                Fig. 02 — Capabilities
              </span>
              <h2 data-reveal className="lp-display-2 mt-6 max-w-[20ch] text-raise">
                Built for this channel.
              </h2>
            </div>
            <div className="lp-tile-grid">
              {integration.features.map((feature) => {
                const FeatureIcon = ICONS[feature.icon];
                return (
                  <div key={feature.title} data-reveal className="lp-tile">
                    {FeatureIcon ? (
                      <div className="lp-tile-icon">
                        <FeatureIcon className="h-4 w-4 text-[var(--content-secondary)]" />
                      </div>
                    ) : null}
                    <h3 className="lp-tile-name">{feature.title}</h3>
                    <p className="lp-tile-tagline">{feature.description}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {integration.useCases.length > 0 && (
            <div className="lp-section-block">
              <div className="lp-section-head">
                <span data-reveal className="lp-fig">
                  Fig. 03 — Use cases
                </span>
                <h2 data-reveal className="lp-display-2 mt-6 max-w-[20ch] text-raise">
                  Who it helps.
                </h2>
              </div>
              <div className="lp-tile-grid">
                {integration.useCases.map((useCase) => (
                  <div key={useCase.persona} data-reveal className="lp-tile">
                    <p className="lp-quote mb-0 text-[0.875rem]">{useCase.quote}</p>
                    <div className="mt-auto pt-4">
                      <div className="lp-mono-sm text-raise">{useCase.persona}</div>
                      <div className="lp-mono-10 mt-1 text-[var(--content-quaternary)]">
                        {useCase.role}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {integration.setupSteps.length > 0 && (
            <div className="lp-section-block">
              <div className="lp-section-head">
                <span data-reveal className="lp-fig">
                  Fig. 04 — Setup
                </span>
                <h2 data-reveal className="lp-display-2 mt-6 max-w-[20ch] text-raise">
                  Connect in four steps.
                </h2>
              </div>
              <div className="border-t border-[var(--stroke-secondary)]">
                {integration.setupSteps.map((step) => (
                  <div key={step.step} data-reveal className="lp-setup-step">
                    <span className="lp-setup-num">{String(step.step).padStart(2, '0')}</span>
                    <div>
                      <div className="text-[0.9375rem] text-[var(--content-raise)]">
                        {step.title}
                      </div>
                      <p className="lp-body mt-1.5 text-[0.875rem]">{step.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {integration.faqs.length > 0 && (
            <div className="lp-section-block">
              <div className="lp-section-head">
                <span data-reveal className="lp-fig">
                  Fig. 05 — Common questions
                </span>
                <h2 data-reveal className="lp-display-2 mt-6 max-w-[18ch] text-raise">
                  Questions, answered.
                </h2>
              </div>
              <div className="lp-faq-list">
                {integration.faqs.map((faq, i) => {
                  const isOpen = openFAQ === i;
                  return (
                    <div key={i} className={`lp-faq-item${isOpen ? ' lp-faq-item--open' : ''}`}>
                      <button
                        onClick={() => setOpenFAQ(openFAQ === i ? null : i)}
                        aria-expanded={isOpen}
                        className="lp-faq-q"
                      >
                        <span className="flex items-baseline">
                          <span className="lp-faq-index">{String(i + 1).padStart(2, '0')}</span>
                          <span>{faq.question}</span>
                        </span>
                        <Plus
                          className="h-3.5 w-3.5 shrink-0 text-[var(--content-tertiary)] transition-transform duration-300"
                          style={{ transform: isOpen ? 'rotate(45deg)' : 'rotate(0deg)' }}
                        />
                      </button>
                      <div hidden={!isOpen} className="lp-faq-a">
                        {faq.answer}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="lp-section-block px-[var(--gutter-width)] py-6">
            <Link href="/integrations" className="lp-back-link">
              <ChevronLeft className="h-3.5 w-3.5" />
              All integrations
            </Link>
          </div>

          <SubpageCTA />
        </div>
      </main>
      <Footer />
    </div>
  );
}
