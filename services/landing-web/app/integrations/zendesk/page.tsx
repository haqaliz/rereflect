'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { Logo } from '@rereflect/ui';
import { ArrowRight, Clock, FileText, TrendingUp, Target, Settings as SettingsIcon, Sparkles, X, Github } from 'lucide-react';
import { ZendeskIcon } from '@/components/icons/ZendeskIcon';
import { getIntegration } from '@/lib/integrations';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';
const SELFHOST_URL = 'https://github.com/haqaliz/rereflect#self-hosting';

export default function ZendeskIntegrationPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const featuresRef = useRef<HTMLDivElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);

  const integration = getIntegration('zendesk');

  if (!integration) {
    return null;
  }

  const featureIconMap: Record<string, React.ReactNode> = {
    FileText: <FileText className="w-7 h-7 text-white" />,
    TrendingUp: <TrendingUp className="w-7 h-7 text-white" />,
    Target: <Target className="w-7 h-7 text-white" />,
    Settings: <SettingsIcon className="w-7 h-7 text-white" />,
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
          }, '-=0.6')
          .from('.hero-cta', {
            y: 30,
            opacity: 0,
            duration: 0.6
          }, '-=0.4');

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
        <div className="absolute inset-0 pattern-bg opacity-30" />
        <div className="particle absolute top-[20%] left-[15%] w-2 h-2 rounded-full bg-primary/30" />
        <div className="particle absolute top-[40%] left-[80%] w-3 h-3 rounded-full bg-accent/40" />
        <div className="particle absolute top-[60%] left-[25%] w-2.5 h-2.5 rounded-full bg-chart-3/30" />
        <div className="particle absolute top-[75%] left-[70%] w-2 h-2 rounded-full bg-primary/25" />
        <div className="particle absolute top-[30%] left-[60%] w-1.5 h-1.5 rounded-full bg-accent/35" />
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
              <Clock className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">Coming Soon</span>
            </div>

            <h1 className="hero-title text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-foreground mb-6 leading-[1.1]">
              Zendesk +
              <span className="block mt-2 bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">
                Rereflect
              </span>
            </h1>

            <p className="hero-subtitle text-lg md:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed">
              {integration.heroMessage}
            </p>

            <div className="hero-cta">
              <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
                <button className="group relative px-8 py-4 text-base font-semibold text-primary-foreground rounded-2xl overflow-hidden transition-all duration-300 hover:shadow-xl hover:shadow-primary/30 hover:scale-[1.02]">
                  <div className="absolute inset-0 bg-gradient-to-r from-primary to-chart-5" />
                  <div className="absolute inset-0 bg-gradient-to-r from-chart-5 to-primary opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                  <span className="relative flex items-center justify-center gap-2">
                    <Github className="w-5 h-5" />
                    View on GitHub
                  </span>
                </button>
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Preview Section */}
      <section ref={featuresRef} className="relative z-10 py-24 md:py-32 border-t border-border bg-card/30">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <Sparkles className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">What to Expect</span>
            </div>
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Planned features
              <span className="block mt-2 bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">
                for Zendesk
              </span>
            </h2>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {integration.features.map((feature, index) => {
              const gradients = [
                { bg: 'from-chart-1 to-chart-2', shadow: 'shadow-chart-1/25', hover: 'hover:shadow-chart-1/10 hover:border-chart-1/30', overlay: 'from-chart-1/5' },
                { bg: 'from-chart-4 to-chart-5', shadow: 'shadow-chart-4/25', hover: 'hover:shadow-chart-4/10 hover:border-chart-4/30', overlay: 'from-chart-4/5' },
                { bg: 'from-chart-3 to-chart-4', shadow: 'shadow-chart-3/25', hover: 'hover:shadow-chart-3/10 hover:border-chart-3/30', overlay: 'from-chart-3/5' },
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
                    <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${g.bg} flex items-center justify-center mb-6 shadow-lg ${g.shadow} group-hover:scale-110 transition-transform duration-300`}>
                      {featureIconMap[feature.icon]}
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

      {/* CTA Section */}
      <section ref={ctaRef} className="relative z-10 py-24 md:py-32">
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
                Follow along on GitHub.
              </h2>
              <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
                Star the repo or open an issue to track progress on the Zendesk integration.
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
              <div className="flex flex-col gap-4">
                <a
                  href="https://twitter.com/rereflectapp"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors w-fit"
                >
                  <X className="w-5 h-5" />
                  <span className="text-sm">Follow us on X</span>
                </a>
                <a
                  href="https://www.producthunt.com/products/rereflect?embed=true&utm_source=badge-featured&utm_medium=badge&utm_campaign=badge-rereflect"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    alt="Rereflect - AI-powered customer feedback analysis for SaaS teams | Product Hunt"
                    width="250"
                    height="54"
                    src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1073104&theme=dark&t=1770240628252"
                  />
                </a>
              </div>
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
