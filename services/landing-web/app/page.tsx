'use client';

import { useEffect, useRef, useState } from 'react';
import { TrendingUp, Zap, Shield, ArrowRight, Sparkles, ChevronRight, Check } from 'lucide-react';
import { Navigation } from '@/components/landing/Navigation';
import { Footer } from '@/components/landing/Footer';
import { IntegrationBar } from '@/components/landing/IntegrationBar';
import BentoFeatures from '@/components/landing/BentoFeatures';
import HeroDemo from '@/components/landing/HeroDemo';
import ImpactMetrics from '@/components/landing/ImpactMetrics';
import FAQ from '@/components/landing/FAQ';

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? (process.env.NODE_ENV === 'development' ? 'http://localhost:3000' : 'https://app.rereflect.ca');


export default function Home() {
  const pageRef = useRef<HTMLDivElement>(null);
  const heroSectionRef = useRef<HTMLDivElement>(null);
  const statsRef = useRef<HTMLDivElement>(null);
  const pricingRef = useRef<HTMLDivElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);
  const [isSticky, setIsSticky] = useState(false);

  // Smooth scroll handler
  const scrollToSection = (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => {
    e.preventDefault();
    const element = document.getElementById(targetId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Sticky nav via IntersectionObserver on hero section
  useEffect(() => {
    const hero = heroSectionRef.current;
    if (!hero) return;
    const observer = new IntersectionObserver(
      ([entry]) => setIsSticky(!entry.isIntersecting),
      { threshold: 0 }
    );
    observer.observe(hero);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    // Lazy load GSAP for better initial page load performance
    let ctx: any;

    (async () => {
      const [{ default: gsap }, { ScrollTrigger }] = await Promise.all([
        import('gsap'),
        import('gsap/ScrollTrigger')
      ]);

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
          duration: 0.6,
          stagger: 0.15
        }, '-=0.4')
        .from('.hero-trust', {
          y: 20,
          opacity: 0,
          duration: 0.6
        }, '-=0.3')
        .from('.hero-visual', {
          scale: 0.9,
          opacity: 0,
          duration: 1.2,
          ease: 'power2.out'
        }, '-=1');

      // Floating animation for hero visual
      gsap.to('.hero-visual-float', {
        y: -15,
        duration: 3,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut'
      });

      // Particle animations
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

      // Stats counter animation
      ScrollTrigger.create({
        trigger: statsRef.current,
        start: 'top 80%',
        once: true,
        onEnter: () => {
          gsap.from('.stat-item', {
            y: 40,
            opacity: 0,
            duration: 0.7,
            stagger: 0.1,
            ease: 'power3.out'
          });
        }
      });

      // Bento feature cards — stagger in on scroll
      gsap.set('[data-testid="bento-section"] [data-size]', { opacity: 1, y: 0 });

      ScrollTrigger.batch('[data-testid="bento-section"] [data-size]', {
        onEnter: (elements) => {
          gsap.fromTo(elements,
            { opacity: 0, y: 60 },
            {
              opacity: 1,
              y: 0,
              duration: 0.8,
              stagger: 0.12,
              ease: 'power3.out',
              overwrite: true
            }
          );
        },
        start: 'top 90%',
        once: true
      });

      // Impact metrics — slide up on scroll
      ScrollTrigger.create({
        trigger: '[data-testid="impact-section"]',
        start: 'top 80%',
        once: true,
        onEnter: () => {
          gsap.from('[data-testid^="metric-card"]', {
            y: 40,
            opacity: 0,
            duration: 0.7,
            stagger: 0.15,
            ease: 'power3.out'
          });
        }
      });

      // Pricing cards - set initial state then animate on scroll
      gsap.set('.pricing-card', { opacity: 1, y: 0 });

      ScrollTrigger.create({
        trigger: pricingRef.current,
        start: 'top 85%',
        once: true,
        onEnter: () => {
          gsap.fromTo('.pricing-card',
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

      // FAQ — fade in on scroll
      ScrollTrigger.create({
        trigger: '[data-testid="faq-section"]',
        start: 'top 80%',
        once: true,
        onEnter: () => {
          gsap.from('[data-testid="faq-section"]', {
            y: 30,
            opacity: 0,
            duration: 0.8,
            ease: 'power3.out'
          });
        }
      });

      // CTA section animation
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

      }, pageRef);
    })(); // End async IIFE

    return () => {
      // Cleanup: revert GSAP context if it was initialized
      if (ctx) {
        ctx.revert();
      }
    };
  }, []);

  return (
    <div ref={pageRef} className="min-h-screen bg-background overflow-hidden">
      {/* Ambient Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,var(--accent)_0%,transparent_50%)] opacity-[0.08]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,var(--primary)_0%,transparent_50%)] opacity-[0.06]" />
        <div className="absolute inset-0 pattern-bg opacity-30" />
        {/* Floating particles */}
        <div className="particle absolute top-[20%] left-[15%] w-2 h-2 rounded-full bg-primary/30" />
        <div className="particle absolute top-[40%] left-[80%] w-3 h-3 rounded-full bg-accent/40" />
        <div className="particle absolute top-[60%] left-[25%] w-2.5 h-2.5 rounded-full bg-chart-3/30" />
        <div className="particle absolute top-[75%] left-[70%] w-2 h-2 rounded-full bg-primary/25" />
        <div className="particle absolute top-[30%] left-[60%] w-1.5 h-1.5 rounded-full bg-accent/35" />
      </div>

      {/* Navigation */}
      <Navigation isSticky={isSticky} onScrollToSection={scrollToSection} />
      {isSticky && <div className="h-[73px]" aria-hidden="true" />}

      {/* Hero Section */}
      <section ref={heroSectionRef} className="relative z-10 pt-12 pb-24 md:pt-20 md:pb-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-8 items-center">
            {/* Left Content */}
            <div className="text-center lg:text-left">
              <div className="hero-badge inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-8">
                <Sparkles className="w-4 h-4 text-primary" />
                <span className="text-sm font-semibold text-primary">AI-Powered Feedback Intelligence</span>
              </div>

              <h1 className="hero-title text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-foreground mb-6 leading-[1.1]">
                Turn Customer Feedback
                <span className="block mt-2 bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">
                  Into Features That Ship
                </span>
              </h1>

              <p className="hero-subtitle text-lg md:text-xl text-muted-foreground mb-10 max-w-xl mx-auto lg:mx-0 leading-relaxed">
                Don&apos;t just analyze feedback — act on it. Automatically detect churn risk, assign work to your team, and track every insight from submission to resolution.
              </p>

              <div className="hero-cta flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
                <a href={`${APP_URL}/signup`}>
                  <button className="group relative px-8 py-4 text-base font-semibold text-primary-foreground rounded-2xl overflow-hidden transition-all duration-300 hover:shadow-xl hover:shadow-primary/30 hover:scale-[1.02]">
                    <div className="absolute inset-0 bg-gradient-to-r from-primary to-chart-5" />
                    <div className="absolute inset-0 bg-gradient-to-r from-chart-5 to-primary opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                    <span className="relative flex items-center justify-center gap-2">
                      Start Free Trial
                      <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                    </span>
                  </button>
                </a>
                <a href={`${APP_URL}/login`}>
                  <button className="group px-8 py-4 text-base font-semibold text-foreground bg-transparent border-2 border-foreground/20 rounded-2xl transition-all duration-300 hover:border-primary/50 hover:bg-card hover:shadow-lg hover:scale-[1.02]">
                    <span className="flex items-center justify-center gap-2">
                      View Demo
                      <ChevronRight className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" />
                    </span>
                  </button>
                </a>
              </div>

              <div className="hero-trust mt-12 flex flex-wrap items-center justify-center lg:justify-start gap-6 text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded-full bg-success-bg flex items-center justify-center">
                    <Shield className="w-3 h-3 text-success-text" />
                  </div>
                  <span>SOC 2 Compliant</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center">
                    <Zap className="w-3 h-3 text-primary" />
                  </div>
                  <span>Real-time Analysis</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded-full bg-accent/10 flex items-center justify-center">
                    <TrendingUp className="w-3 h-3 text-accent-foreground" />
                  </div>
                  <span>98% Accuracy</span>
                </div>
              </div>
            </div>

            {/* Right Visual — Animated Product Demo */}
            <div className="hero-visual relative lg:pl-8">
              <div className="hero-visual-float relative">
                <HeroDemo />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section ref={statsRef} className="relative z-10 py-16 border-y border-border bg-card/50">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            <div className="stat-item text-center">
              <div className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-primary to-chart-5 bg-clip-text text-transparent">10K+</div>
              <div className="text-sm text-muted-foreground mt-2">Insights Generated</div>
            </div>
            <div className="stat-item text-center">
              <div className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-chart-5 to-accent bg-clip-text text-transparent">120+</div>
              <div className="text-sm text-muted-foreground mt-2">Features Shipped</div>
            </div>
            <div className="stat-item text-center">
              <div className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-accent to-chart-3 bg-clip-text text-transparent">60%</div>
              <div className="text-sm text-muted-foreground mt-2">Avg Churn Reduction</div>
            </div>
            <div className="stat-item text-center">
              <div className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-chart-3 to-primary bg-clip-text text-transparent">4.2</div>
              <div className="text-sm text-muted-foreground mt-2">Hours Saved Per Week</div>
            </div>
          </div>
        </div>
      </section>

      {/* Integration Logo Bar */}
      <IntegrationBar />

      {/* Features — Bento Grid */}
      <div id="features">
        <BentoFeatures />
      </div>

      {/* Impact Metrics — Before vs After */}
      <ImpactMetrics />

      {/* Pricing Section */}
      <section ref={pricingRef} id="pricing" className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <Sparkles className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">Simple Pricing</span>
            </div>
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Choose the plan that&apos;s
              <span className="block text-primary">right for you</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Start free and scale as you grow. No hidden fees, no surprises.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
            {/* Free Plan */}
            <div className="pricing-card relative bg-card rounded-3xl border border-border p-6 transition-all duration-300 hover:shadow-lg hover:border-border/80">
              <div className="mb-5">
                <h3 className="text-xl font-bold text-foreground mb-2">Free</h3>
                <p className="text-muted-foreground text-sm">For individuals getting started</p>
              </div>
              <div className="mb-5">
                <span className="text-4xl font-bold text-foreground">$0</span>
                <span className="text-muted-foreground">/month</span>
              </div>
              <ul className="space-y-2.5 mb-6">
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>250 feedback/month</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>2 team members</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Basic sentiment analysis</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>CSV import</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Email support</span>
                </li>
              </ul>
              <a href={`${APP_URL}/signup`} className="block">
                <button className="w-full py-3 px-6 rounded-xl border-2 border-border text-foreground font-semibold hover:border-primary/50 hover:bg-primary/5 transition-all duration-300">
                  Get Started Free
                </button>
              </a>
            </div>

            {/* Pro Plan */}
            <div className="pricing-card relative bg-card rounded-3xl border-2 border-primary p-6 transition-all duration-300 hover:shadow-xl hover:shadow-primary/20 scale-[1.02]">
              <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1 bg-gradient-to-r from-primary to-chart-5 rounded-full">
                <span className="text-xs font-semibold text-white">Most Popular</span>
              </div>
              <div className="mb-5">
                <h3 className="text-xl font-bold text-foreground mb-2">Pro</h3>
                <p className="text-muted-foreground text-sm">For growing teams</p>
              </div>
              <div className="mb-5">
                <span className="text-4xl font-bold text-foreground">$29</span>
                <span className="text-muted-foreground">/month</span>
              </div>
              <ul className="space-y-2.5 mb-6">
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>2,500 feedback/month</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>10 team members</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Slack, Intercom & more</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Webhooks</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Priority support</span>
                </li>
              </ul>
              <a href={`${APP_URL}/signup`} className="block">
                <button className="w-full py-3 px-6 rounded-xl bg-gradient-to-r from-primary to-chart-5 text-white font-semibold hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02] transition-all duration-300">
                  Start 14-Day Trial
                </button>
              </a>
            </div>

            {/* Business Plan */}
            <div className="pricing-card relative bg-card rounded-3xl border border-border p-6 transition-all duration-300 hover:shadow-lg hover:border-border/80">
              <div className="mb-5">
                <h3 className="text-xl font-bold text-foreground mb-2">Business</h3>
                <p className="text-muted-foreground text-sm">For scaling companies</p>
              </div>
              <div className="mb-5">
                <span className="text-4xl font-bold text-foreground">$99</span>
                <span className="text-muted-foreground">/month</span>
              </div>
              <ul className="space-y-2.5 mb-6">
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>25,000 feedback/month</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>25 team members</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>API access</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Advanced analytics</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Custom categories</span>
                </li>
              </ul>
              <a href={`${APP_URL}/signup`} className="block">
                <button className="w-full py-3 px-6 rounded-xl border-2 border-border text-foreground font-semibold hover:border-primary/50 hover:bg-primary/5 transition-all duration-300">
                  Start 14-Day Trial
                </button>
              </a>
            </div>

            {/* Enterprise Plan */}
            <div className="pricing-card relative bg-card rounded-3xl border border-border p-6 transition-all duration-300 hover:shadow-lg hover:border-border/80">
              <div className="mb-5">
                <h3 className="text-xl font-bold text-foreground mb-2">Enterprise</h3>
                <p className="text-muted-foreground text-sm">Custom solutions</p>
              </div>
              <div className="mb-5">
                <span className="text-4xl font-bold text-foreground">Custom</span>
              </div>
              <ul className="space-y-2.5 mb-6">
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Unlimited feedback</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Unlimited team members</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>SSO / SAML</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>Dedicated support</span>
                </li>
                <li className="flex items-center gap-2.5 text-sm text-muted-foreground">
                  <Check className="w-4 h-4 text-success-text shrink-0" />
                  <span>SLA guarantee</span>
                </li>
              </ul>
              <a href="mailto:sales@rereflect.com" className="block">
                <button className="w-full py-3 px-6 rounded-xl border-2 border-border text-foreground font-semibold hover:border-primary/50 hover:bg-primary/5 transition-all duration-300">
                  Contact Sales
                </button>
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <FAQ />

      {/* CTA Section */}
      <section ref={ctaRef} className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="cta-content relative overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-primary via-chart-5 to-accent p-8 sm:p-12 md:p-16 lg:p-20">
            {/* Background Pattern */}
            <div className="absolute inset-0 opacity-10">
              <div className="absolute inset-0" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'0.4\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")' }} />
            </div>

            {/* Glow Effects */}
            <div className="absolute -top-20 -right-20 w-60 h-60 bg-white/20 rounded-full blur-3xl" />
            <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-white/10 rounded-full blur-3xl" />

            <div className="relative text-center">
              <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-6">
                Ready to transform your feedback?
              </h2>
              <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
                Join 500+ companies already making better decisions with AI-powered customer insights.
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

      {/* Footer */}
      <Footer onScrollToSection={scrollToSection} />

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
