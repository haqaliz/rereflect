'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { authAPI } from '@/lib/api/auth';
import { useAuth } from '@/contexts/AuthContext';
import { Mail, Lock, ArrowRight, MessageSquare, Brain, TrendingUp, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Logo } from '@/components/Logo';
import { GoogleSignInButton } from '@/components/GoogleSignInButton';
import gsap from 'gsap';

export default function LoginPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Redirect to dashboard if already authenticated
  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      router.push('/dashboard');
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    // Only run animations if not authenticated and not loading
    if (authLoading || isAuthenticated) return;

    const ctx = gsap.context(() => {
      // Set initial visible state for all animated elements
      gsap.set(['.brand-logo', '.brand-title', '.brand-subtitle', '.brand-feature', '.brand-footer'], { opacity: 1, y: 0, x: 0 });
      gsap.set(['.form-logo', '.form-title', '.form-subtitle', '.form-field', '.form-button', '.form-footer'], { opacity: 1, y: 0, scale: 1 });

      // Branding side animations
      const brandTl = gsap.timeline({ defaults: { ease: 'power3.out' } });
      brandTl
        .fromTo('.brand-logo', { y: -20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 })
        .fromTo('.brand-title', { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.8 }, '-=0.3')
        .fromTo('.brand-subtitle', { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 }, '-=0.4')
        .fromTo('.brand-feature', { x: -30, opacity: 0 }, { x: 0, opacity: 1, duration: 0.5, stagger: 0.1 }, '-=0.3')
        .fromTo('.brand-footer', { opacity: 0 }, { opacity: 1, duration: 0.4 }, '-=0.2');

      // Form side animations
      const formTl = gsap.timeline({ defaults: { ease: 'power3.out' }, delay: 0.2 });
      formTl
        .fromTo('.form-logo', { scale: 0.8, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.5 })
        .fromTo('.form-title', { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 }, '-=0.2')
        .fromTo('.form-subtitle', { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5 }, '-=0.3')
        .fromTo('.form-field', { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, stagger: 0.1 }, '-=0.2')
        .fromTo('.form-button', { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4 }, '-=0.1')
        .fromTo('.form-footer', { opacity: 0 }, { opacity: 1, duration: 0.3 }, '-=0.1');

      // Floating shapes animation
      gsap.to('.float-shape', {
        y: -20,
        rotation: 5,
        duration: 4,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
        stagger: { each: 0.5, from: 'random' }
      });

    }, containerRef);

    return () => ctx.revert();
  }, [authLoading, isAuthenticated]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await authAPI.login({ email, password });
      localStorage.setItem('access_token', response.access_token);
      router.push('/dashboard');
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSuccess = async (accessToken: string) => {
    setError('');
    setLoading(true);

    try {
      const response = await authAPI.googleLogin({ access_token: accessToken });
      localStorage.setItem('access_token', response.access_token);
      router.push('/dashboard');
    } catch (err: unknown) {
      const error = err as { response?: { status?: number; data?: { detail?: string } } };
      const detail = error.response?.data?.detail;

      // Handle specific error: user needs to sign up
      if (error.response?.status === 404) {
        setError('No account found with this email. Please sign up first.');
      } else {
        setError(detail || 'Google sign-in failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Show loading state while checking authentication
  if (authLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  // Don't render the page if authenticated (will redirect)
  if (isAuthenticated) {
    return null;
  }

  return (
    <div ref={containerRef} className="min-h-screen bg-background flex">
      {/* Left Side - Branding */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden">
        {/* Gradient Background */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary via-chart-5 to-accent" />

        {/* Pattern Overlay */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute inset-0" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'0.4\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")' }} />
        </div>

        {/* Floating Shapes */}
        <div className="float-shape absolute top-20 right-20 w-32 h-32 bg-white/10 rounded-3xl backdrop-blur-sm" />
        <div className="float-shape absolute bottom-32 left-16 w-24 h-24 bg-white/10 rounded-2xl backdrop-blur-sm" />
        <div className="float-shape absolute top-1/2 right-32 w-16 h-16 bg-white/15 rounded-xl backdrop-blur-sm" />

        {/* Glow Effects */}
        <div className="absolute -top-20 -left-20 w-60 h-60 bg-white/20 rounded-full blur-3xl" />
        <div className="absolute -bottom-20 -right-20 w-60 h-60 bg-white/10 rounded-full blur-3xl" />

        {/* Content */}
        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          <Link href="/" className="brand-logo flex items-center gap-3">
            <div className="w-12 h-12 bg-white/20 backdrop-blur rounded-xl flex items-center justify-center">
              <Logo size="md" className="text-white [&_path]:fill-white" />
            </div>
            <span className="text-2xl font-bold text-white">
              <span className="text-white/70">Re</span>reflect
            </span>
          </Link>

          <div className="text-white max-w-md">
            <h1 className="brand-title text-4xl xl:text-5xl font-bold mb-6 leading-tight">
              Welcome back to your
              <span className="block text-white/90">feedback insights</span>
            </h1>
            <p className="brand-subtitle text-xl text-white/80 mb-10">
              Continue analyzing customer feedback and making data-driven decisions.
            </p>

            <div className="space-y-4">
              <div className="brand-feature flex items-center gap-4 p-4 bg-white/10 backdrop-blur rounded-2xl">
                <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center shrink-0">
                  <MessageSquare className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Real-time Analysis</h3>
                  <p className="text-sm text-white/70">Instant sentiment detection</p>
                </div>
              </div>

              <div className="brand-feature flex items-center gap-4 p-4 bg-white/10 backdrop-blur rounded-2xl">
                <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center shrink-0">
                  <Brain className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">AI-Powered Insights</h3>
                  <p className="text-sm text-white/70">Smart pain point detection</p>
                </div>
              </div>

              <div className="brand-feature flex items-center gap-4 p-4 bg-white/10 backdrop-blur rounded-2xl">
                <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center shrink-0">
                  <TrendingUp className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Actionable Dashboard</h3>
                  <p className="text-sm text-white/70">Track trends over time</p>
                </div>
              </div>
            </div>
          </div>

          <p className="brand-footer text-white/60 text-sm">
            2025 Rereflect. All rights reserved.
          </p>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="flex-1 flex items-center justify-center p-8 relative">
        {/* Subtle Background */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,var(--primary)_0%,transparent_50%)] opacity-[0.03]" />
        <div className="absolute inset-0 pattern-bg opacity-20" />

        <div className="w-full max-w-md relative z-10">
          {/* Mobile Logo */}
          <div className="form-logo lg:hidden flex items-center justify-center gap-3 mb-10">
            <div className="w-12 h-12 bg-gradient-to-br from-primary to-chart-5 rounded-xl flex items-center justify-center shadow-lg shadow-primary/25">
              <Logo size="md" className="text-white [&_path]:fill-white" />
            </div>
            <span className="text-2xl font-bold">
              <span className="text-muted-foreground">Re</span>
              <span className="text-foreground">reflect</span>
            </span>
          </div>

          <div className="text-center mb-10">
            <h2 className="form-title text-3xl font-bold text-foreground mb-3">
              Sign in to your account
            </h2>
            <p className="form-subtitle text-muted-foreground">
              Don&apos;t have an account?{' '}
              <Link href="/signup" className="text-primary hover:text-chart-5 font-semibold transition-colors">
                Sign up for free
              </Link>
            </p>
          </div>

          {error && (
            <Alert variant="destructive" className="mb-6 animate-fade-in">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="form-field space-y-2">
              <Label htmlFor="email" className="text-foreground font-medium">Email address</Label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Mail className="h-5 w-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                </div>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="pl-12 h-12 text-base bg-background border-border focus:border-primary focus:ring-primary/20 rounded-xl transition-all"
                  placeholder="you@example.com"
                />
              </div>
            </div>

            <div className="form-field space-y-2">
              <Label htmlFor="password" className="text-foreground font-medium">Password</Label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                </div>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-12 h-12 text-base bg-background border-border focus:border-primary focus:ring-primary/20 rounded-xl transition-all"
                  placeholder="Enter your password"
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="form-button w-full h-12 text-base font-semibold bg-gradient-to-r from-primary to-chart-5 hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02] transition-all duration-300 rounded-xl"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Signing in...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  Sign in
                  <ArrowRight className="w-5 h-5" />
                </span>
              )}
            </Button>

            {/* Divider */}
            <div className="form-field relative my-6">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-3 text-muted-foreground">Or continue with</span>
              </div>
            </div>

            {/* Google Sign-In */}
            <div className="form-field">
              <GoogleSignInButton
                mode="login"
                onSuccess={handleGoogleSuccess}
                onError={(err) => setError(err)}
                disabled={loading}
              />
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
