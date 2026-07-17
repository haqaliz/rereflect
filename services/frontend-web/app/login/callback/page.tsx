'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { Loader2, AlertCircle } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function LoginCallbackPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [status, setStatus] = useState<'processing' | 'error'>('processing');

  useEffect(() => {
    const rawHash = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash;
    const hashParams = new URLSearchParams(rawHash);
    const queryParams = new URLSearchParams(window.location.search);
    const token = hashParams.get('token');
    const ssoError = hashParams.get('sso_error') || queryParams.get('sso_error');

    if (token && !ssoError) {
      login(token);
      // Scrub the token from the URL immediately so it never lingers in
      // browser history, referrer headers, or gets logged anywhere.
      window.history.replaceState(null, '', window.location.pathname);
      router.replace('/dashboard');
    } else {
      setStatus('error');
    }
    // Intentionally runs once on mount to consume the fragment exactly one time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (status === 'error') {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <div className="mb-6">
            <div className="w-16 h-16 mx-auto bg-destructive/10 rounded-full flex items-center justify-center">
              <AlertCircle className="w-8 h-8 text-destructive" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-foreground mb-2">Single sign-on didn&apos;t complete</h1>
          <p className="text-muted-foreground mb-6">
            We couldn&apos;t finish signing you in. Please try again.
          </p>
          <Link href="/login">
            <Button variant="outline">Back to login</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-muted-foreground">Signing you in...</p>
      </div>
    </div>
  );
}
