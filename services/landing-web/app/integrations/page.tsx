'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { Logo } from '@rereflect/ui';
import { ArrowRight, Puzzle, Zap, Clock } from 'lucide-react';
import { SlackIcon } from '@/components/icons/SlackIcon';
import { IntercomIcon } from '@/components/icons/IntercomIcon';
import { EmailIcon } from '@/components/icons/EmailIcon';
import { ZendeskIcon } from '@/components/icons/ZendeskIcon';
import { HubSpotIcon } from '@/components/icons/HubSpotIcon';
import { getAvailableIntegrations, getComingSoonIntegrations } from '@/lib/integrations';

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? (process.env.NODE_ENV === 'development' ? 'http://localhost:3000' : 'https://app.rereflect.ca');

export default function IntegrationsPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const availableRef = useRef<HTMLDivElement>(null);
  const comingSoonRef = useRef<HTMLDivElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);

  const availableIntegrations = getAvailableIntegrations();
  const comingSoonIntegrations = getComingSoonIntegrations();

  const iconMap: Record<string, React.ReactNode> = {
    slack: <SlackIcon size={40} />,
    intercom: <IntercomIcon size={40} />,
    email: <EmailIcon size={40} />,
    zendesk: <ZendeskIcon size={40} />,
    hubspot: <HubSpotIcon size={40} />,
  };

  useEffect(() => {
    let ctx: any;

    (async () => {
      const [{ default: gsap }, { ScrollTrigger }] = await Promise.all([
        import('gsap'),
        import('gsap/ScrollTrigger')
      ]);

      gsap.registerPlugin(ScrollTrigger);

      ctx = gsap.context(() => {
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
            duration: 1,
            stagger: 0.2
          }, '-=0.4')
          .from('.hero-subtitle', {
            y: 30,
            opacity: 0,
            duration: 0.8
          }, '-=0.6');

        gsap.to('.particle', {
          y: -20,
          x: 'random(-10, 10)',
          duration: 'random(2, 4)',
          repeat: -1,
          yoyo: true,
          ease: 'sine.inOut',
          stagger: {
            each: 0.3,
            from: 'random'
          }
        });

        gsap.set('.integration-card', { opacity: 1, y: 0 });

        ScrollTrigger.batch('.integration-card', {
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

        gsap.set('.coming-soon-card', { opacity: 1, y: 0 });

        ScrollTrigger.create({
          trigger: comingSoonRef.current,
          start: 'top 85%',
          once: true,
          onEnter: () => {
            gsap.fromTo('.coming-soon-card',
              { opacity: 0, y: 50 },
              {
                opacity: 1,
                y: 0,
                duration: 0.8,
                stagger: 0.15,
                ease: 'power3.out',
                overwrite: true
              }
            );
          }
        });

        ScrollTrigger.create({
          trigger: ctaRef.current,
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
      if (ctx) {
        ctx.revert();
      }
    };
  }, []);

  return (
    <div ref={containerRef} className="min-h-screen bg-background overflow-hidden">
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,var(--accent)_0%,transparent_50%)] opacity-[0.08]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,var(--primary)_0%,transparent_50%)] opacity-[0.06]" />
        <div className="absolute inset-0 pattern-bg opacity-30" />
        <div className="particle absolute top-[20%] left-[15%] w-2 h-2 rounded-full bg-primary/30" />
        <div className="particle absolute top-[40%] left-[80%] w-3 h-3 rounded-full bg-accent/40" />
        <div className="particle absolute top-[60%] left-[25%] w-2.5 h-2.5 rounded-full bg-chart-3/30" />
        <div className="particle absolute top-[75%] left-[70%] w-2 h-2 rounded-full bg-primary/25" />
        <div className="particle absolute top-[30%] left-[60%] w-1.5 h-1.5 rounded-full bg-accent/35" />
      </div>

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

      <section className="relative z-10 pt-12 pb-24 md:pt-20 md:pb-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center">
            <div className="hero-badge inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-8">
              <Puzzle className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">Connect Your Tools</span>
            </div>

            <h1 className="hero-title text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-foreground mb-6 leading-[1.1]">
              Automatically analyze feedback
              <span className="block mt-2 bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">
                from every channel
              </span>
            </h1>

            <p className="hero-subtitle text-lg md:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed">
              Connect Slack, Intercom, email, and more. Rereflect pulls in customer feedback from your existing tools and turns it into actionable insights.
            </p>
          </div>
        </div>
      </section>

      <section ref={availableRef} className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <Zap className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">Available Now</span>
            </div>
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Ready to connect
              <span className="block mt-2 bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">
                today
              </span>
            </h2>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {availableIntegrations.map((integration) => (
              <Link
                key={integration.slug}
                href={`/integrations/${integration.slug}`}
                className={`integration-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl ${integration.hoverShadow} ${integration.hoverBorder} hover:-translate-y-1`}
              >
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" />
                <div className="relative">
                  <div className="mb-6 group-hover:scale-110 transition-transform duration-300">
                    {iconMap[integration.slug]}
                  </div>
                  <h3 className="text-xl font-bold text-foreground mb-3">{integration.name}</h3>
                  <p className="text-muted-foreground leading-relaxed mb-6">
                    {integration.tagline}
                  </p>
                  <div className="flex items-center gap-2 text-primary font-semibold group-hover:gap-3 transition-all">
                    Learn more
                    <ArrowRight className="w-4 h-4" />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section ref={comingSoonRef} className="relative z-10 py-24 md:py-32 border-t border-border bg-card/30">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <Clock className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">Coming Soon</span>
            </div>
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              More integrations
              <span className="block mt-2 bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">
                on the way
              </span>
            </h2>
          </div>

          <div className="grid md:grid-cols-2 gap-6 max-w-2xl mx-auto">
            {comingSoonIntegrations.map((integration) => (
              <a
                key={integration.slug}
                href={`${APP_URL}/signup`}
                className="coming-soon-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-300 hover:shadow-lg"
              >
                <div className="relative">
                  <div className="mb-6 group-hover:scale-110 transition-transform duration-300">
                    {iconMap[integration.slug]}
                  </div>
                  <h3 className="text-xl font-bold text-foreground mb-3">{integration.name}</h3>
                  <p className="text-muted-foreground leading-relaxed mb-6">
                    {integration.tagline}
                  </p>
                  <div className="flex items-center gap-2 text-primary font-semibold group-hover:gap-3 transition-all">
                    Get notified
                    <ArrowRight className="w-4 h-4" />
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section ref={ctaRef} className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="cta-content relative overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-primary via-chart-5 to-accent p-12 md:p-16 lg:p-20">
            <div className="absolute inset-0 opacity-10">
              <div className="absolute inset-0" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'0.4\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")' }} />
            </div>

            <div className="absolute -top-20 -right-20 w-60 h-60 bg-white/20 rounded-full blur-3xl" />
            <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-white/10 rounded-full blur-3xl" />

            <div className="relative text-center">
              <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-6">
                Ready to connect your tools?
              </h2>
              <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
                Start analyzing feedback from every channel in minutes.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <a href={`${APP_URL}/signup`}>
                  <button className="group px-8 py-4 text-base font-semibold text-primary bg-white rounded-2xl transition-all duration-300 hover:shadow-2xl hover:shadow-white/25 hover:scale-[1.02]">
                    <span className="flex items-center justify-center gap-2">
                      Start Your Free Trial
                      <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                    </span>
                  </button>
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

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
              <Link href="/changelog" className="hover:text-foreground transition-colors">Changelog</Link>
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
