'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Logo } from '@rereflect/ui';
import { ArrowRight, ChevronRight, ChevronDown, Mail, FileText, UserCheck, Search, Zap, Layers, Sparkles, Settings as SettingsIcon } from 'lucide-react';
import { EmailIcon } from '@/components/icons/EmailIcon';
import { getIntegration } from '@/lib/integrations';

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? (process.env.NODE_ENV === 'development' ? 'http://localhost:3000' : 'https://app.rereflect.ca');

const featureIconMap: Record<string, React.ComponentType<{className?: string}>> = {
  Mail,
  FileText,
  UserCheck,
  Search,
  Zap,
  Layers,
};


export default function EmailIntegrationPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const integration = getIntegration('email');

  if (!integration) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Integration not found</p>
      </div>
    );
  }

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

        // Step items animation
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

        // Feature cards animation
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

        // CTA section animation
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

  return (
    <div ref={containerRef} className="min-h-screen bg-background overflow-hidden">
      {/* Ambient Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,var(--accent)_0%,transparent_50%)] opacity-[0.08]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,var(--primary)_0%,transparent_50%)] opacity-[0.06]" />
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
              Pricing
            </Link>
            <Link
              href="/integrations"
              className="text-sm font-medium text-foreground transition-colors"
            >
              Integrations
            </Link>
          </div>

          <div className="flex items-center gap-3">
            <a href={`${APP_URL}/login`}>
              <button className="px-4 py-2.5 text-sm font-medium text-foreground/80 hover:text-foreground transition-colors">
                Sign In
              </button>
            </a>
            <a href={`${APP_URL}/signup`}>
              <button className="group relative px-5 py-2.5 text-sm font-semibold text-primary-foreground rounded-xl overflow-hidden transition-all duration-300 hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02]">
                <div className="absolute inset-0 bg-gradient-to-r from-primary via-chart-5 to-primary bg-[length:200%_100%] animate-[shimmer_3s_ease-in-out_infinite]" />
                <span className="relative flex items-center gap-1.5">
                  Get Started
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
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
              <EmailIcon size={16} />
              <span className="text-sm font-semibold text-primary">Email Integration</span>
            </div>

            <h1 className="hero-title text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-foreground mb-6 leading-[1.1]">
              Email Forwarding +
              <span className="block mt-2 bg-gradient-to-r from-accent via-chart-3 to-accent bg-clip-text text-transparent">
                Rereflect
              </span>
            </h1>

            <p className="hero-subtitle text-lg md:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed">
              {integration.heroMessage}
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <a href={`${APP_URL}/settings/integrations`} className="hero-cta">
                <button className="group px-8 py-4 text-base font-semibold text-primary-foreground bg-gradient-to-r from-accent to-chart-3 rounded-2xl transition-all duration-300 hover:shadow-xl hover:shadow-accent/25 hover:scale-[1.02]">
                  <span className="flex items-center justify-center gap-2">
                    Set Up Email Forwarding
                    <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
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

      {/* How It Works Section */}
      <section id="how-it-works" className="relative z-10 py-24 md:py-32 bg-card/30 border-t border-border">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <Sparkles className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">Simple Setup</span>
            </div>
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              How it works
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Three simple steps to start analyzing customer emails with AI
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {integration.howItWorks.map((step, index) => (
              <div key={index} className="step-item text-center">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-chart-5 text-white text-2xl font-bold mb-6 shadow-lg shadow-primary/25">
                  {step.step}
                </div>
                <h3 className="text-xl font-bold text-foreground mb-3">{step.title}</h3>
                <p className="text-muted-foreground leading-relaxed">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Grid Section */}
      <section className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Powerful features
              <span className="block mt-2 bg-gradient-to-r from-accent via-chart-3 to-accent bg-clip-text text-transparent">
                built for email
              </span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Everything you need to turn forwarded emails into actionable insights
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
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
                <div
                  key={index}
                  className={`feature-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl ${g.hover} hover:-translate-y-1`}
                >
                  <div className={`absolute inset-0 bg-gradient-to-br ${g.overlay} to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl`} />
                  <div className="relative">
                    <div className={`inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br ${g.bg} text-white mb-6 shadow-lg ${g.shadow} group-hover:scale-110 transition-transform duration-300`}>
                      {IconComponent && <IconComponent className="w-6 h-6" />}
                    </div>
                    <h3 className="text-xl font-bold text-foreground mb-3">{feature.title}</h3>
                    <p className="text-muted-foreground leading-relaxed">{feature.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Setup Steps Section */}
      <section className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <SettingsIcon className="w-4 h-4 text-primary" />
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
              <div key={step.step} className="flex gap-6">
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

      {/* FAQ Section */}
      <section className="relative z-10 py-24 md:py-32 bg-card/30 border-t border-border">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Frequently asked questions
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Everything you need to know about email forwarding integration
            </p>
          </div>

          <div className="max-w-3xl mx-auto space-y-4">
            {integration.faqs.map((faq, index) => (
              <div
                key={index}
                className="bg-card rounded-2xl border border-border overflow-hidden transition-all duration-300 hover:shadow-lg"
              >
                <button
                  onClick={() => setOpenFaq(openFaq === index ? null : index)}
                  className="w-full flex items-center justify-between p-6 text-left"
                >
                  <span className="text-lg font-semibold text-foreground pr-4">
                    {faq.question}
                  </span>
                  {openFaq === index ? (
                    <ChevronDown className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                  ) : (
                    <ChevronRight className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                  )}
                </button>
                {openFaq === index && (
                  <div className="px-6 pb-6 text-muted-foreground leading-relaxed border-t border-border pt-4">
                    {faq.answer}
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
          <div className="cta-content relative overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-accent via-chart-3 to-accent p-12 md:p-16 lg:p-20">
            <div className="absolute inset-0 opacity-10">
              <div className="absolute inset-0" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'0.4\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")' }} />
            </div>

            <div className="absolute -top-20 -right-20 w-60 h-60 bg-white/20 rounded-full blur-3xl" />
            <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-white/10 rounded-full blur-3xl" />

            <div className="relative text-center">
              <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-6">
                Ready to analyze your emails?
              </h2>
              <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
                Start forwarding customer feedback emails and get AI-powered insights in minutes.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <a href={`${APP_URL}/signup`}>
                  <button className="group px-8 py-4 text-base font-semibold text-accent bg-white rounded-2xl transition-all duration-300 hover:shadow-2xl hover:shadow-white/25 hover:scale-[1.02]">
                    <span className="flex items-center justify-center gap-2">
                      Start Your Free Trial
                      <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                    </span>
                  </button>
                </a>
                <a href="/integrations">
                  <button className="px-8 py-4 text-base font-semibold text-white border-2 border-white/30 rounded-2xl transition-all duration-300 hover:bg-white/10 hover:border-white/50">
                    View All Integrations
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

          <div className="pt-8 border-t border-border flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-muted-foreground">
            <p>2025 Rereflect. All rights reserved.</p>
            <div className="flex gap-6">
              <Link href="/integrations" className="hover:text-foreground transition-colors">Integrations</Link>
              <Link href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link>
              <Link href="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link>
            </div>
          </div>
        </div>
      </footer>

      <style jsx>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  );
}
