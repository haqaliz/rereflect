'use client';

import { Suspense, useEffect, useState } from 'react';
import { CheckCircle2, Loader2, MailX } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Logo } from '@/components/Logo';
import { unsubscribe } from '@/lib/api/outreach';

export default function UnsubscribePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-background flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
            <p className="text-muted-foreground">Loading...</p>
          </div>
        </div>
      }
    >
      <UnsubscribePageContent />
    </Suspense>
  );
}

type UnsubscribeState = 'loading' | 'success' | 'error';

function UnsubscribePageContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const [state, setState] = useState<UnsubscribeState>(token ? 'loading' : 'error');

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    unsubscribe(token)
      .then(() => {
        if (!cancelled) setState('success');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="min-h-screen bg-background pattern-bg flex items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
          <Logo size="lg" />
          {state === 'loading' && (
            <>
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <p className="text-muted-foreground">Processing your request...</p>
            </>
          )}
          {state === 'success' && (
            <>
              <CheckCircle2 className="w-10 h-10 text-success-text" />
              <h1 className="text-xl font-semibold text-foreground">You&apos;re unsubscribed</h1>
              <p className="text-sm text-muted-foreground max-w-xs">
                You won&apos;t receive any more outreach emails from this organization.
              </p>
            </>
          )}
          {state === 'error' && (
            <>
              <MailX className="w-10 h-10 text-destructive" />
              <h1 className="text-xl font-semibold text-foreground">This link is invalid</h1>
              <p className="text-sm text-muted-foreground max-w-xs">
                The unsubscribe link is invalid or has already been used. Please contact the
                sender if you keep receiving emails.
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
