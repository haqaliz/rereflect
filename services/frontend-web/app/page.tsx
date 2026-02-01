'use client';

import { useEffect, useRef } from 'react';
import { BarChart3, Brain, MessageSquare, TrendingUp, Zap, Shield, ArrowRight, Sparkles, Target, Bell, ChevronRight, Check } from 'lucide-react';
import Link from 'next/link';
import { Logo } from '@/components/Logo';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

export default function Home() {
  const heroRef = useRef<HTMLDivElement>(null);
  const featuresRef = useRef<HTMLDivElement>(null);
  const statsRef = useRef<HTMLDivElement>(null);
  const pricingRef = useRef<HTMLDivElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);

  // Smooth scroll handler
  const scrollToSection = (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => {
    e.preventDefault();
    const element = document.getElementById(targetId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  useEffect(() => {
    const ctx = gsap.context(() => {
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

      // Feature cards - set initial state then animate on scroll
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

    }, heroRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={heroRef} className="min-h-screen bg-background overflow-hidden">
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
            <a
              href="#features"
              onClick={(e) => scrollToSection(e, 'features')}
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              Features
            </a>
            <a
              href="#pricing"
              onClick={(e) => scrollToSection(e, 'pricing')}
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              Pricing
            </a>
          </div>

          <div className="flex items-center gap-3">
            <Link href="/login">
              <button className="px-4 py-2.5 text-sm font-medium text-foreground/80 hover:text-foreground transition-colors">
                Sign In
              </button>
            </Link>
            <Link href="/signup">
              <button className="group relative px-5 py-2.5 text-sm font-semibold text-primary-foreground rounded-xl overflow-hidden transition-all duration-300 hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02]">
                <div className="absolute inset-0 bg-gradient-to-r from-primary via-chart-5 to-primary bg-[length:200%_100%] animate-[shimmer_3s_ease-in-out_infinite]" />
                <span className="relative flex items-center gap-1.5">
                  Get Started
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </span>
              </button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative z-10 pt-12 pb-24 md:pt-20 md:pb-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-8 items-center">
            {/* Left Content */}
            <div className="text-center lg:text-left">
              <div className="hero-badge inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-8">
                <Sparkles className="w-4 h-4 text-primary" />
                <span className="text-sm font-semibold text-primary">AI-Powered Feedback Intelligence</span>
              </div>

              <h1 className="hero-title text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-foreground mb-6 leading-[1.1]">
                Transform Customer
                <span className="block mt-2 bg-gradient-to-r from-primary via-chart-5 to-accent bg-clip-text text-transparent">
                  Feedback into Action
                </span>
              </h1>

              <p className="hero-subtitle text-lg md:text-xl text-muted-foreground mb-10 max-w-xl mx-auto lg:mx-0 leading-relaxed">
                Automatically analyze sentiment, extract pain points, and discover feature requests.
                Turn overwhelming feedback into clear, actionable insights.
              </p>

              <div className="hero-cta flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
                <Link href="/signup">
                  <button className="group relative px-8 py-4 text-base font-semibold text-primary-foreground rounded-2xl overflow-hidden transition-all duration-300 hover:shadow-xl hover:shadow-primary/30 hover:scale-[1.02]">
                    <div className="absolute inset-0 bg-gradient-to-r from-primary to-chart-5" />
                    <div className="absolute inset-0 bg-gradient-to-r from-chart-5 to-primary opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                    <span className="relative flex items-center justify-center gap-2">
                      Start Free Trial
                      <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                    </span>
                  </button>
                </Link>
                <Link href="/login">
                  <button className="hero-cta group px-8 py-4 text-base font-semibold text-foreground bg-card border-2 border-border rounded-2xl transition-all duration-300 hover:border-primary/50 hover:shadow-lg hover:scale-[1.02]">
                    <span className="flex items-center justify-center gap-2">
                      View Demo
                      <ChevronRight className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" />
                    </span>
                  </button>
                </Link>
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

            {/* Right Visual */}
            <div className="hero-visual relative lg:pl-8">
              <div className="hero-visual-float relative">
                {/* Main Dashboard Preview */}
                <div className="relative bg-card rounded-3xl border border-border shadow-2xl shadow-primary/10 p-6 overflow-hidden">
                  {/* Glow effect */}
                  <div className="absolute -top-20 -right-20 w-40 h-40 bg-primary/30 rounded-full blur-3xl" />
                  <div className="absolute -bottom-20 -left-20 w-40 h-40 bg-accent/20 rounded-full blur-3xl" />

                  {/* Header */}
                  <div className="relative flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <Logo size="sm" />
                      <span className="font-semibold text-foreground">Dashboard</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-chart-3" />
                      <div className="w-3 h-3 rounded-full bg-accent" />
                      <div className="w-3 h-3 rounded-full bg-primary" />
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div className="relative grid grid-cols-3 gap-3 mb-6">
                    <div className="bg-background/50 rounded-xl p-4 border border-border/50">
                      <div className="text-2xl font-bold text-foreground">2,847</div>
                      <div className="text-xs text-muted-foreground">Total Feedback</div>
                      <div className="mt-2 h-1 rounded-full bg-muted overflow-hidden">
                        <div className="h-full w-3/4 bg-primary rounded-full" />
                      </div>
                    </div>
                    <div className="bg-background/50 rounded-xl p-4 border border-border/50">
                      <div className="text-2xl font-bold text-success-text">78%</div>
                      <div className="text-xs text-muted-foreground">Positive</div>
                      <div className="mt-2 h-1 rounded-full bg-muted overflow-hidden">
                        <div className="h-full w-[78%] bg-success-border rounded-full" />
                      </div>
                    </div>
                    <div className="bg-background/50 rounded-xl p-4 border border-border/50">
                      <div className="text-2xl font-bold text-warning-text">23</div>
                      <div className="text-xs text-muted-foreground">Urgent</div>
                      <div className="mt-2 h-1 rounded-full bg-muted overflow-hidden">
                        <div className="h-full w-1/4 bg-warning-border rounded-full" />
                      </div>
                    </div>
                  </div>

                  {/* Sample Feedback Items */}
                  <div className="relative space-y-3">
                    <div className="flex items-start gap-3 p-3 rounded-xl bg-success-bg/50 border border-success-border/30">
                      <div className="w-8 h-8 rounded-lg bg-success-bg flex items-center justify-center shrink-0">
                        <span className="text-success-text text-sm">+</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-foreground truncate">&quot;Love the new dashboard!&quot;</div>
                        <div className="text-xs text-muted-foreground">Sentiment: Positive</div>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 p-3 rounded-xl bg-warning-bg/50 border border-warning-border/30">
                      <div className="w-8 h-8 rounded-lg bg-warning-bg flex items-center justify-center shrink-0">
                        <Bell className="w-4 h-4 text-warning-text" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-foreground truncate">&quot;Export feature needs work&quot;</div>
                        <div className="text-xs text-muted-foreground">Pain Point Detected</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Floating Card - Feature Request */}
                <div className="absolute -right-4 top-1/4 bg-card rounded-2xl border border-border shadow-xl p-4 w-48 transform rotate-3 hover:rotate-0 transition-transform duration-300">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-6 h-6 rounded-lg bg-accent/20 flex items-center justify-center">
                      <Target className="w-3.5 h-3.5 text-accent-foreground" />
                    </div>
                    <span className="text-xs font-semibold text-foreground">Feature Request</span>
                  </div>
                  <div className="text-xs text-muted-foreground">Dark mode support requested by 47 users</div>
                </div>

                {/* Floating Card - AI Analysis */}
                <div className="absolute -left-4 bottom-1/4 bg-card rounded-2xl border border-border shadow-xl p-4 w-44 transform -rotate-3 hover:rotate-0 transition-transform duration-300">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-6 h-6 rounded-lg bg-primary/20 flex items-center justify-center">
                      <Brain className="w-3.5 h-3.5 text-primary" />
                    </div>
                    <span className="text-xs font-semibold text-foreground">AI Analysis</span>
                  </div>
                  <div className="text-xs text-muted-foreground">Processing 156 new items...</div>
                  <div className="mt-2 h-1 rounded-full bg-muted overflow-hidden">
                    <div className="h-full w-2/3 bg-gradient-to-r from-primary to-accent rounded-full animate-pulse" />
                  </div>
                </div>
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
              <div className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-primary to-chart-5 bg-clip-text text-transparent">50K+</div>
              <div className="text-sm text-muted-foreground mt-2">Feedback Analyzed Daily</div>
            </div>
            <div className="stat-item text-center">
              <div className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-chart-5 to-accent bg-clip-text text-transparent">98%</div>
              <div className="text-sm text-muted-foreground mt-2">Sentiment Accuracy</div>
            </div>
            <div className="stat-item text-center">
              <div className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-accent to-chart-3 bg-clip-text text-transparent">500+</div>
              <div className="text-sm text-muted-foreground mt-2">Companies Trust Us</div>
            </div>
            <div className="stat-item text-center">
              <div className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-chart-3 to-primary bg-clip-text text-transparent">4.9</div>
              <div className="text-sm text-muted-foreground mt-2">Average Rating</div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section ref={featuresRef} id="features" className="relative z-10 py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 mb-6">
              <Zap className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">Powerful Features</span>
            </div>
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-foreground mb-6">
              Everything you need to understand
              <span className="block text-primary">your customers</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              From sentiment analysis to churn prediction, our AI-powered platform gives you the tools to make data-driven decisions.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Feature Card 1 */}
            <div className="feature-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl hover:shadow-primary/10 hover:border-primary/30 hover:-translate-y-1">
              <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" />
              <div className="relative">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary to-chart-5 flex items-center justify-center mb-6 shadow-lg shadow-primary/25 group-hover:scale-110 transition-transform duration-300">
                  <MessageSquare className="w-7 h-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-foreground mb-3">Sentiment Analysis</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Automatically detect positive, neutral, and negative sentiment with industry-leading 98% accuracy using advanced NLP models.
                </p>
              </div>
            </div>

            {/* Feature Card 2 */}
            <div className="feature-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl hover:shadow-chart-5/10 hover:border-chart-5/30 hover:-translate-y-1">
              <div className="absolute inset-0 bg-gradient-to-br from-chart-5/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" />
              <div className="relative">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-chart-5 to-accent flex items-center justify-center mb-6 shadow-lg shadow-chart-5/25 group-hover:scale-110 transition-transform duration-300">
                  <Brain className="w-7 h-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-foreground mb-3">Pain Point Detection</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Automatically extract and categorize customer pain points, prioritizing issues that impact user experience the most.
                </p>
              </div>
            </div>

            {/* Feature Card 3 */}
            <div className="feature-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl hover:shadow-accent/10 hover:border-accent/30 hover:-translate-y-1">
              <div className="absolute inset-0 bg-gradient-to-br from-accent/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" />
              <div className="relative">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-accent to-chart-3 flex items-center justify-center mb-6 shadow-lg shadow-accent/25 group-hover:scale-110 transition-transform duration-300">
                  <Target className="w-7 h-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-foreground mb-3">Feature Requests</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Identify and prioritize feature requests from feedback, understanding what your customers want most.
                </p>
              </div>
            </div>

            {/* Feature Card 4 */}
            <div className="feature-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl hover:shadow-destructive/10 hover:border-destructive/30 hover:-translate-y-1">
              <div className="absolute inset-0 bg-gradient-to-br from-destructive/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" />
              <div className="relative">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-destructive to-chart-8 flex items-center justify-center mb-6 shadow-lg shadow-destructive/25 group-hover:scale-110 transition-transform duration-300">
                  <Bell className="w-7 h-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-foreground mb-3">Urgent Alerts</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Get instant notifications for critical feedback that needs immediate attention, preventing customer churn.
                </p>
              </div>
            </div>

            {/* Feature Card 5 */}
            <div className="feature-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl hover:shadow-chart-3/10 hover:border-chart-3/30 hover:-translate-y-1">
              <div className="absolute inset-0 bg-gradient-to-br from-chart-3/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" />
              <div className="relative">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-chart-3 to-chart-9 flex items-center justify-center mb-6 shadow-lg shadow-chart-3/25 group-hover:scale-110 transition-transform duration-300">
                  <BarChart3 className="w-7 h-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-foreground mb-3">Visual Analytics</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Beautiful, interactive dashboards that make it easy to understand trends and share insights with your team.
                </p>
              </div>
            </div>

            {/* Feature Card 6 */}
            <div className="feature-card group relative bg-card rounded-3xl border border-border p-8 transition-all duration-500 hover:shadow-xl hover:shadow-accent/10 hover:border-accent/30 hover:-translate-y-1">
              <div className="absolute inset-0 bg-gradient-to-br from-accent/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-3xl" />
              <div className="relative">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-accent via-chart-5 to-primary flex items-center justify-center mb-6 shadow-lg shadow-accent/25 group-hover:scale-110 transition-transform duration-300">
                  <TrendingUp className="w-7 h-7 text-white" />
                </div>
                <h3 className="text-xl font-bold text-foreground mb-3">Trend Analysis</h3>
                <p className="text-muted-foreground leading-relaxed">
                  Track sentiment over time, identify emerging patterns, and measure the impact of your product changes.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section ref={pricingRef} id="pricing" className="relative z-10 py-24 md:py-32 bg-card/30">
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
              <Link href="/signup" className="block">
                <button className="w-full py-3 px-6 rounded-xl border-2 border-border text-foreground font-semibold hover:border-primary/50 hover:bg-primary/5 transition-all duration-300">
                  Get Started Free
                </button>
              </Link>
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
                  <span>Slack integration</span>
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
              <Link href="/signup" className="block">
                <button className="w-full py-3 px-6 rounded-xl bg-gradient-to-r from-primary to-chart-5 text-white font-semibold hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02] transition-all duration-300">
                  Start 14-Day Trial
                </button>
              </Link>
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
              <Link href="/signup" className="block">
                <button className="w-full py-3 px-6 rounded-xl border-2 border-border text-foreground font-semibold hover:border-primary/50 hover:bg-primary/5 transition-all duration-300">
                  Start 14-Day Trial
                </button>
              </Link>
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
                Ready to transform your feedback?
              </h2>
              <p className="text-xl text-white/80 mb-10 max-w-2xl mx-auto">
                Join 500+ companies already making better decisions with AI-powered customer insights.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Link href="/signup">
                  <button className="group px-8 py-4 text-base font-semibold text-primary bg-white rounded-2xl transition-all duration-300 hover:shadow-2xl hover:shadow-white/25 hover:scale-[1.02]">
                    <span className="flex items-center justify-center gap-2">
                      Start Your Free Trial
                      <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                    </span>
                  </button>
                </Link>
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
                  <a
                    href="#features"
                    onClick={(e) => scrollToSection(e, 'features')}
                    className="hover:text-foreground transition-colors cursor-pointer"
                  >
                    Features
                  </a>
                </li>
                <li>
                  <a
                    href="#pricing"
                    onClick={(e) => scrollToSection(e, 'pricing')}
                    className="hover:text-foreground transition-colors cursor-pointer"
                  >
                    Pricing
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="pt-8 border-t border-border flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-muted-foreground">
            <p>2025 Rereflect. All rights reserved.</p>
            <div className="flex gap-6">
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
