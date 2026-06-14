'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Logo } from '@rereflect/ui';
import { ArrowRight, ChevronRight, ChevronDown, MessageCircle, RefreshCw, Star, TrendingUp, AlertTriangle, Github } from 'lucide-react';
import { IntercomIcon } from '@/components/icons/IntercomIcon';
import { getIntegration } from '@/lib/integrations';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';
const SELFHOST_URL = 'https://github.com/haqaliz/rereflect#self-hosting';

export default function IntercomIntegrationPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [openFAQ, setOpenFAQ] = useState<number | null>(null);

  const integration = getIntegration('intercom');

  const featureIconMap: Record<string, React.ComponentType<{className?: string}>> = {
    MessageCircle,
    RefreshCw,
    Star,
    TrendingUp,
    AlertTriangle,
  };

  useEffect(() => {
    let ctx: any;
    let mounted = true;

    (async () => {
      const [{ default: gsap }, { ScrollTrigger }] = await Promise.all([
        import('gsap'),
        import('gsap/ScrollTrigger')
      ]);

      if (!mounted) return;

      gsap.registerPlugin(ScrollTrigger);

      ctx = gsap.context(() => {
        // Hero animations
        const heroTl = gsap.timeline({ defaults: { ease: 'power3.out' } });

        heroTl
          .from('.hero-badge', {
            y: 30,
            opacity: 0,
            duration: 0.8
          })
          .from('.hero-title', {
            y: 50,
            opacity: 0,
            duration: 1
          }, '-=0.4')
          .from('.hero-subtitle', {
            y: 30,
            opacity: 0,
            duration: 0.8
          }, '-=0.6')
          .from('.hero-cta', {
            y: 30,
            opacity: 0,
            duration: 0.6,
            stagger: 0.15
          }, '-=0.4');

        // Steps, features, use cases: ScrollTrigger batch
        gsap.set('.step-item', { opacity: 1, y: 0 });
        ScrollTrigger.batch('.step-item', {
          onEnter: (elements) => {
            gsap.fromTo(elements,
              { opacity: 0, y: 40 },
              {
                opacity: 1,
                y: 0,
                duration: 0.7,
                stagger: 0.15,
                ease: 'power3.out',
                overwrite: true
              }
            );
          },
          start: 'top 90%',
          once: true
        });

        gsap.set('.feature-card', { opacity: 1, y: 0 });
        ScrollTrigger.batch('.feature-card', {
          onEnter: (elements) => {
            gsap.fromTo(elements,
              { opacity: 0, y: 60 },
              {
                opacity: 1,
                y: 0,
                duration: 0.8,
                stagger: 0.15,
                ease: 'power3.out',
                overwrite: true
              }
            );
          },
          start: 'top 90%',
          once: true
        });

        gsap.set('.setup-step', { opacity: 1, y: 0 });
        ScrollTrigger.batch('.setup-step', {
          onEnter: (elements) => {
            gsap.fromTo(elements,
              { opacity: 0, x: -40 },
              {
                opacity: 1,
                x: 0,
                duration: 0.7,
                stagger: 0.1,
                ease: 'power3.out',
                overwrite: true
              }
            );
          },
          start: 'top 90%',
          once: true
        });

        // CTA fade-in
        ScrollTrigger.create({
          trigger: '.cta-section',
          start: 'top 80%',
          once: true,
          onEnter: () => {
            gsap.from('.cta-content', {
              y: 50,
              opacity: 0,
              duration: 1,
              ease: 'power3.out'
            });
          }
        });

      }, containerRef);
    })();

    return () => {
      mounted = false;
      if (ctx) {
        ctx.revert();
      }
    };
  }, []);

  if (!integration) {
    return null;
  }

  return (
    <div ref={containerRef} className="min-h-screen bg-background overflow-hidden">
      {/* Ambient Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,var(--accent)_0%,transparent_50%)] opacity-[0.08]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,var(--primary)_0%,transparent_50%)] opacity-[0.06]" />
        <div className="absolute inset-0 pattern-bg opacity-30" />
      </div>

      {/* Navigation */}
      <nav className="relative z-50 px-6 py-5">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="relative">
              <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full scale-150 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <Logo size="lg" className="relative" />
            </div>
            <span className="text-xl font-bold tracking-tight">
              <span className="text-muted-foreground">Re</span>
              <span className="text-foreground">reflect</span>
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <Link
              href="/#features"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Features
            </Link>
            <Link
              href="/#pricing"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Open source
            </Link>
            <Link
              href="/integrations"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Integrations
            </Link>
          </div>

          <div className="flex items-center gap-3">
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              <button className="group relative px-5 py-2.5 text-sm font-semibold text-primary-foreground rounded-xl overflow-hidden transition-all duration-300 hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02]">
                <div className="absolute inset-0 bg-gradient-to-r from-primary via-chart-5 to-primary bg-[length:200%_100%] animate-[shimmer_3s_ease-in-out_infinite]" />
                <span className="relative flex items-center gap-1.5">
                  <Github className="w-4 h-4" />
                  View on GitHub
                </span>
              </button>
            </a>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative z-10 pt-12 pb-24 md:pt-20 md:pb-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center">
            <div className="hero-badge inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-8">
              <IntercomIcon size={16} />
              <span className="text-sm font-semibold text-primary">Intercom Integration</span>
            </div>

            <h1 className="hero-title text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-foreground mb-6 leading-[1.1]">
              Intercom + <span className="bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">Rereflect</span>
            </h1>

            <p className="hero-subtitle text-lg md:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed">
              {integration.heroMessage}
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="hero-cta">
                <button className="group relative px-8 py-4 text-base font-semibold text-primary-foreground rounded-2xl overflow-hidden transition-all duration-300 hover:shadow-xl hover:shadow-primary/30 hover:scale-[1.02]">
                  <div className="absolute inset-0 bg-gradient-to-r from-primary to-chart-5" />
                  <div className="absolute inset-0 bg-gradient-to-r from-chart-5 to-primary opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                  <span className="relative flex items-center justify-center gap-2">
                    <Github className="w-5 h-5" />
                    View on GitHub
                  </span>
                </button>
              </a>
              <a href="#how-it-works" className="hero-cta">
                <button
                  className="group px-8 py-4 text-base font-semibold text-foreground bg-background border-2 border-border rounded-2xl transition-all duration-300 hover:border-primary/50 hover:shadow-lg hover:scale-[1.02]"
                  onClick={(e) => {
                    e.preventDefault();
                    document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' });
                  }}
                >
                  <span className="flex items-center justify-center gap-2">
                    Learn more
                    <ChevronRight className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" />
                  </span>
                </button>
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="relative z-10 py-24 md:py-32 border-y border-border bg-card/30">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              How it works
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Get up and running in minutes. No complex setup required.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {integration.howItWorks.map((step, index) => (
              <div key={index} className="step-item relative">
                <div className="flex flex-col items-center text-center">
                  <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-chart-5 flex items-center justify-center mb-6 shadow-lg shadow-primary/25">
                    <span className="text-2xl font-bold text-white">{step.step}</span>
                  </div>
                  <h3 className="text-xl font-bold text-foreground mb-3">{step.title}</h3>
                  <p className="text-muted-foreground leading-relaxed">
                    {step.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Powerful features
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Everything you need to turn support conversations into actionable insights.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {integration.features.map((feature, index) => {
              const IconComponent = featureIconMap[feature.icon];
              const gradients = [
                { bg: 'from-chart-1 to-chart-2', shadow: 'shadow-chart-1/25', hover: 'hover:shadow-chart-1/10 hover:border-chart-1/30', overlay: 'from-chart-1/5' },
                { bg: 'from-chart-4 to-chart-5', shadow: 'shadow-chart-4/25', hover: 'hover:shadow-chart-4/10 hover:border-chart-4/30', overlay: 'from-chart-4/5' },
                { bg: 'from-chart-3 to-chart-4', shadow: 'shadow-chart-3/25', hover: 'hover:shadow-chart-3/10 hover:border-chart-3/30', overlay: 'from-chart-3/5' },
                { bg: 'from-chart-5 to-accent', shadow: 'shadow-chart-5/25', hover: 'hover:shadow-chart-5/10 hover:border-chart-5/30', overlay: 'from-chart-5/5' },
                { bg: 'from-destructive to-chart-8', shadow: 'shadow-destructive/25', hover: 'hover:shadow-destructive/10 hover:border-destructive/30', overlay: 'from-destructive/5' },
                { bg: 'from-primary to-chart-5', shadow: 'shadow-primary/25', hover: 'hover:shadow-primary/10 hover:border-primary/30', overlay: 'from-primary/5' },
              ];
              const g = gradients[index % gradients.length];
              return (
                <div key={index} className={`feature-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl ${g.hover} hover:-translate-y-1`}>
                  <div className={`absolute inset-0 bg-gradient-to-br ${g.overlay} to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl`} />
                  <div className="relative">
                    <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${g.bg} flex items-center justify-center mb-6 shadow-lg ${g.shadow} group-hover:scale-110 transition-transform duration-300`}>
                      {IconComponent && <IconComponent className="w-7 h-7 text-white" />}
                    </div>
                    <h3 className="text-xl font-bold text-foreground mb-3">{feature.title}</h3>
                    <p className="text-muted-foreground leading-relaxed">
                      {feature.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Setup Steps */}
      <section className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <ArrowRight className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">Get Started</span>
            </div>
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Set up in{' '}
              <span className="bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">
                {integration.setupSteps.length} simple steps
              </span>
            </h2>
          </div>

          <div className="max-w-2xl mx-auto space-y-8">
            {integration.setupSteps.map((step, index) => (
              <div key={step.step} className="setup-step flex gap-6">
                <div className="flex flex-col items-center">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-chart-5 flex items-center justify-center text-white font-bold shrink-0">
                    {step.step}
                  </div>
                  {index < integration.setupSteps.length - 1 && (
                    <div className="w-px flex-1 bg-border mt-3" />
                  )}
                </div>
                <div className="pb-8">
                  <h3 className="text-lg font-bold text-foreground mb-2">{step.title}</h3>
                  <p className="text-muted-foreground leading-relaxed">{step.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="relative z-10 py-24 md:py-32 border-y border-border bg-card/30">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Frequently asked questions
            </h2>
          </div>

          <div className="max-w-3xl mx-auto space-y-4">
            {integration.faqs.map((faq, index) => (
              <div key={index} className="bg-card rounded-2xl border border-border overflow-hidden transition-all duration-300 hover:shadow-lg">
                <button
                  onClick={() => setOpenFAQ(openFAQ === index ? null : index)}
                  className="w-full flex items-center justify-between p-6 text-left"
                >
                  <span className="text-lg font-semibold text-foreground pr-4">
                    {faq.question}
                  </span>
                  <ChevronDown
                    className={`w-5 h-5 text-muted-foreground shrink-0 transition-transform duration-300 ${
                      openFAQ === index ? 'rotate-180' : ''
                    }`}
                  />
                </button>
                {openFAQ === index && (
                  <div className="px-6 pb-6">
                    <p className="text-muted-foreground leading-relaxed">
                      {faq.answer}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-section relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="cta-content relative overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-primary via-chart-5 to-accent p-12 md:p-16 lg:p-20">
            {/* Background Pattern */}
            <div className="absolute inset-0 opacity-10">
              <div className="absolute inset-0" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'0.4\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")' }} />
            </div>

            {/* Glow Effects */}
            <div className="absolute -top-20 -right-20 w-60 h-60 bg-white/20 rounded-full blur-3xl" />
            <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-white/10 rounded-full blur-3xl" />

            <div className="relative text-center">
              <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-6">
                Self-host and connect Intercom.
              </h2>
              <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
                Deploy Rereflect on your own infrastructure and start analyzing support conversations in minutes.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
                  <button className="group px-8 py-4 text-base font-semibold text-primary bg-white rounded-2xl transition-all duration-300 hover:shadow-2xl hover:shadow-white/25 hover:scale-[1.02]">
                    <span className="flex items-center justify-center gap-2">
                      <Github className="w-5 h-5" />
                      View on GitHub
                    </span>
                  </button>
                </a>
                <a href={SELFHOST_URL} target="_blank" rel="noopener noreferrer">
                  <button className="group px-8 py-4 text-base font-semibold text-white bg-white/10 border-2 border-white/30 rounded-2xl transition-all duration-300 hover:bg-white/20 hover:scale-[1.02]">
                    <span className="flex items-center justify-center gap-2">
                      Self-host guide
                      <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                    </span>
                  </button>
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border bg-card/50 py-16">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-3 gap-12 mb-12">
            <div className="md:col-span-2">
              <Link href="/" className="flex items-center gap-3 mb-4">
                <Logo size="lg" />
                <span className="text-xl font-bold">
                  <span className="text-muted-foreground">Re</span>
                  <span className="text-foreground">reflect</span>
                </span>
              </Link>
              <p className="text-muted-foreground max-w-sm mb-6">
                Transform overwhelming customer feedback into clear, actionable insights with AI-powered analysis.
              </p>
            </div>
            <div>
              <h4 className="font-semibold text-foreground mb-4">Product</h4>
              <ul className="space-y-3 text-muted-foreground">
                <li>
                  <Link href="/#features" className="hover:text-foreground transition-colors">
                    Features
                  </Link>
                </li>
                <li>
                  <Link href="/#pricing" className="hover:text-foreground transition-colors">
                    Pricing
                  </Link>
                </li>
                <li>
                  <Link href="/integrations" className="hover:text-foreground transition-colors">
                    Integrations
                  </Link>
                </li>
              </ul>
            </div>
          </div>

          {/* Footer Bottom */}
          <div className="pt-8 border-t border-border flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-muted-foreground">
            <p>© 2026 Rereflect. All rights reserved.</p>
            <div className="flex gap-6">
              <Link href="/integrations" className="hover:text-foreground transition-colors">Integrations</Link>
              <Link href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link>
              <Link href="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link>
            </div>
          </div>
        </div>
      </footer>

      {/* Custom Styles */}
      <style jsx>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  );
}
