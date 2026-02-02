'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { invitesAPI, InviteDetails } from '@/lib/api/invites';
import { Mail, Lock, ArrowRight, Users, Building2, Clock, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Logo } from '@/components/Logo';
import gsap from 'gsap';

type PageState = 'loading' | 'invite' | 'error' | 'success';

export default function InvitePage() {
  const router = useRouter();
  const params = useParams();
  const token = params.token as string;

  const [pageState, setPageState] = useState<PageState>('loading');
  const [invite, setInvite] = useState<InviteDetails | null>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchInvite = async () => {
      try {
        const details = await invitesAPI.getDetails(token);
        setInvite(details);
        setPageState('invite');
      } catch (err: unknown) {
        const error = err as { response?: { data?: { detail?: string }; status?: number } };
        if (error.response?.status === 410) {
          setError(error.response?.data?.detail || 'This invite is no longer valid');
        } else if (error.response?.status === 404) {
          setError('Invite not found. Please check your invitation link.');
        } else {
          setError('Failed to load invite details. Please try again.');
        }
        setPageState('error');
      }
    };

    if (token) {
      fetchInvite();
    }
  }, [token]);

  useEffect(() => {
    if (pageState !== 'invite' || !containerRef.current) return;

    const ctx = gsap.context(() => {
      gsap.set(['.invite-card', '.invite-header', '.invite-content', '.form-field', '.form-button'], { opacity: 1, y: 0 });

      const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
      tl
        .fromTo('.invite-card', { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 })
        .fromTo('.invite-header', { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5 }, '-=0.3')
        .fromTo('.invite-content', { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4 }, '-=0.2')
        .fromTo('.form-field', { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3, stagger: 0.1 }, '-=0.1')
        .fromTo('.form-button', { y: 10, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3 }, '-=0.1');
    }, containerRef);

    return () => ctx.revert();
  }, [pageState]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);

    try {
      const response = await invitesAPI.accept(token, { password });
      localStorage.setItem('access_token', response.access_token);
      setPageState('success');

      // Redirect to dashboard after a moment
      setTimeout(() => {
        router.push('/dashboard');
      }, 2000);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to accept invite. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  const getRoleBadgeColor = (role: string) => {
    switch (role) {
      case 'owner':
        return 'bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300';
      case 'admin':
        return 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300';
      default:
        return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
    }
  };

  // Loading state
  if (pageState === 'loading') {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-muted-foreground">Loading invitation...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (pageState === 'error') {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <div className="mb-6">
            <div className="w-16 h-16 mx-auto bg-destructive/10 rounded-full flex items-center justify-center">
              <AlertCircle className="w-8 h-8 text-destructive" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-foreground mb-2">Invalid Invitation</h1>
          <p className="text-muted-foreground mb-6">{error}</p>
          <Link href="/login">
            <Button variant="outline">Go to Login</Button>
          </Link>
        </div>
      </div>
    );
  }

  // Success state
  if (pageState === 'success') {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <div className="mb-6">
            <div className="w-16 h-16 mx-auto bg-green-100 dark:bg-green-950 rounded-full flex items-center justify-center">
              <CheckCircle className="w-8 h-8 text-green-600" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-foreground mb-2">Welcome to {invite?.organization_name}!</h1>
          <p className="text-muted-foreground mb-6">Your account has been created. Redirecting to dashboard...</p>
          <Loader2 className="w-6 h-6 animate-spin text-primary mx-auto" />
        </div>
      </div>
    );
  }

  // Invite form
  return (
    <div ref={containerRef} className="min-h-screen bg-background flex items-center justify-center p-4 relative">
      {/* Subtle Background */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,var(--primary)_0%,transparent_50%)] opacity-[0.03]" />
      <div className="absolute inset-0 pattern-bg opacity-20" />

      <div className="invite-card max-w-md w-full bg-card border border-border rounded-2xl shadow-xl overflow-hidden relative z-10">
        {/* Header */}
        <div className="invite-header bg-gradient-to-r from-primary to-chart-5 p-6 text-white">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-white/20 backdrop-blur rounded-xl flex items-center justify-center">
              <Logo size="sm" className="text-white [&_path]:fill-white" />
            </div>
            <span className="text-xl font-bold">
              <span className="opacity-80">Re</span>reflect
            </span>
          </div>
          <h1 className="text-xl font-semibold">You&apos;ve been invited!</h1>
          <p className="text-white/80 text-sm mt-1">Create your account to get started</p>
        </div>

        {/* Invite Details */}
        <div className="invite-content p-6 border-b border-border bg-muted/30">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-secondary rounded-lg flex items-center justify-center">
                <Building2 className="w-5 h-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Organization</p>
                <p className="font-semibold text-foreground">{invite?.organization_name}</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-secondary rounded-lg flex items-center justify-center">
                <Users className="w-5 h-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Your Role</p>
                <Badge className={`${getRoleBadgeColor(invite?.role || '')} capitalize`}>
                  {invite?.role}
                </Badge>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-secondary rounded-lg flex items-center justify-center">
                <Mail className="w-5 h-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Invited by</p>
                <p className="text-foreground">{invite?.invited_by_name}</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-secondary rounded-lg flex items-center justify-center">
                <Clock className="w-5 h-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Expires</p>
                <p className="text-foreground text-sm">{invite?.expires_at && formatDate(invite.expires_at)}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Form */}
        <div className="p-6">
          <p className="text-sm text-muted-foreground mb-4">
            You&apos;ll sign in with <strong className="text-foreground">{invite?.email}</strong>
          </p>

          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="form-field space-y-2">
              <Label htmlFor="password">Create Password</Label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                </div>
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 h-11"
                  placeholder="At least 6 characters"
                />
              </div>
            </div>

            <div className="form-field space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                </div>
                <Input
                  id="confirmPassword"
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="pl-10 h-11"
                  placeholder="Confirm your password"
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="form-button w-full h-11 bg-gradient-to-r from-primary to-chart-5 hover:shadow-lg hover:shadow-primary/25 transition-all"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Creating account...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  Accept & Join
                  <ArrowRight className="w-4 h-4" />
                </span>
              )}
            </Button>
          </form>

          <p className="text-xs text-muted-foreground text-center mt-4">
            By accepting, you agree to our{' '}
            <Link href="/terms" className="text-primary hover:underline">Terms of Service</Link>
            {' '}and{' '}
            <Link href="/privacy" className="text-primary hover:underline">Privacy Policy</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
