'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  ChevronDown,
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
import { gsap, useGSAP } from '@/lib/landing/gsap';
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
      gsap.fromTo(
        '[data-ih]',
        { y: 30, autoAlpha: 0, filter: 'blur(8px)' },
        { y: 0, autoAlpha: 1, filter: 'blur(0px)', duration: 1, ease: 'power3.out', stagger: 0.07 },
      );

      gsap.utils.toArray<HTMLElement>('[data-reveal]').forEach((el) => {
        gsap.fromTo(
          el,
          { y: 36, autoAlpha: 0 },
          {
            y: 0,
            autoAlpha: 1,
            duration: 0.9,
            ease: 'power3.out',
            immediateRender: false,
            scrollTrigger: { trigger: el, start: 'top 88%', toggleActions: 'play none none reverse' },
          },
        );
      });
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
            <span data-ih className="lp-section-eyebrow">
              {integration.name} integration
            </span>
            <h1 data-ih className="lp-page-hero-title font-display">
              {integration.name} + <span className="lp-gradient-text">Rereflect</span>
            </h1>
            <p data-ih className="lp-page-hero-sub">
              {integration.heroMessage}
            </p>
            <div data-ih className="mt-9 flex flex-wrap justify-center gap-4">
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="lp-btn lp-btn-primary"
              >
                <Github className="h-4 w-4" />
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
                Learn more
                <ArrowRight className="h-4 w-4" />
              </a>
            </div>
          </div>

          <div className="lp-section-block pt-6" id="how-it-works">
            <div className="lp-section-head">
              <span className="lp-section-eyebrow">How it works</span>
              <h2 className="lp-section-title font-display">Up and running in minutes.</h2>
            </div>
            <div className="lp-steps-grid">
              {integration.howItWorks.map((step) => (
                <div key={step.step} data-reveal className="lp-step-card">
                  <span className="lp-step-num">STEP {step.step}</span>
                  <h3 className="lp-step-title">{step.title}</h3>
                  <p className="lp-step-desc">{step.description}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="lp-section-block">
            <div className="lp-section-head">
              <span className="lp-section-eyebrow">What you get</span>
              <h2 className="lp-section-title font-display">Built for this channel.</h2>
            </div>
            <div className="lp-tile-grid">
              {integration.features.map((feature) => {
                const FeatureIcon = ICONS[feature.icon];
                return (
                  <div key={feature.title} data-reveal className="lp-feature-tile">
                    {FeatureIcon ? (
                      <div className="lp-feature-icon">
                        <FeatureIcon className="h-5 w-5" />
                      </div>
                    ) : null}
                    <h3 className="lp-feature-title">{feature.title}</h3>
                    <p className="lp-feature-desc">{feature.description}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {integration.useCases.length > 0 && (
            <div className="lp-section-block">
              <div className="lp-section-head">
                <span className="lp-section-eyebrow">Use cases</span>
                <h2 className="lp-section-title font-display">Who it helps.</h2>
              </div>
              <div className="lp-tile-grid">
                {integration.useCases.map((useCase) => (
                  <div key={useCase.persona} data-reveal className="lp-use-case">
                    <p className="lp-use-case-quote">“{useCase.quote}”</p>
                    <div className="lp-use-case-who">
                      <div className="lp-use-case-avatar">
                        {useCase.persona.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div className="lp-use-case-name">{useCase.persona}</div>
                        <div className="lp-use-case-role">{useCase.role}</div>
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
                <span className="lp-section-eyebrow">Setup</span>
                <h2 className="lp-section-title font-display">Connect in four steps.</h2>
              </div>
              <div className="lp-setup-list">
                {integration.setupSteps.map((step) => (
                  <div key={step.step} data-reveal className="lp-setup-step">
                    <span className="lp-setup-num">{step.step}</span>
                    <div>
                      <div className="lp-setup-title">{step.title}</div>
                      <p className="lp-setup-desc">{step.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {integration.faqs.length > 0 && (
            <div className="lp-faq">
              <div className="mx-auto max-w-3xl">
                <div className="mb-12 text-center">
                  <span className="lp-section-eyebrow">FAQ</span>
                  <h2 className="lp-faq-title font-display mt-4">Questions, answered.</h2>
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
                          <span>{faq.question}</span>
                          <ChevronDown
                            className="h-4 w-4 shrink-0 transition-transform duration-300"
                            style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}
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
            </div>
          )}

          <div className="lp-section-block pt-0">
            <Link href="/integrations" className="lp-back-link">
              <ChevronLeft className="h-4 w-4" />
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