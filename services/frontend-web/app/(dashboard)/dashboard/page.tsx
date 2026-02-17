'use client';

import { Suspense, useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Clock, Gift } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DashboardGrid } from '@/components/dashboard/DashboardGrid';
import { DateRangeSelector } from '@/components/dashboard/DateRangeSelector';
import { useDateRange } from '@/components/dashboard/hooks/useDateRange';
import { DashboardSkeleton } from '@/components/shared/page-skeletons';
import { useAuth } from '@/contexts/AuthContext';

function PromoBanner() {
  const router = useRouter();
  const { user } = useAuth();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const promo = localStorage.getItem('rereflect_promo');
    const dismissed = localStorage.getItem('rereflect_promo_dismissed');
    if (promo && user?.plan === 'free' && !dismissed) {
      setVisible(true);
    }
  }, [user?.plan]);

  if (!visible) return null;

  return (
    <div className="bg-gradient-to-r from-primary/10 to-chart-5/10 border border-primary/20 rounded-xl p-4 animate-fade-in">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Gift className="w-5 h-5 text-primary" />
          </div>
          <div>
            <p className="font-semibold text-foreground">You have 3 months of Pro waiting!</p>
            <p className="text-sm text-muted-foreground">Get 2,500 feedback/mo, Slack integration, and more.</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => {
              localStorage.setItem('rereflect_promo_dismissed', 'true');
              setVisible(false);
            }}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors px-2 py-1"
          >
            Later
          </button>
          <Button onClick={() => router.push('/settings/billing')} size="sm">
            Activate Pro
          </Button>
        </div>
      </div>
    </div>
  );
}

function DashboardContent() {
  const { days } = useDateRange();

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Promo Activation Banner */}
        <PromoBanner />

        {/* Page Title + Date Range */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              <h2 className="text-4xl font-bold text-text-primary">Dashboard</h2>
              <div className="flex items-center space-x-2 text-text-tertiary text-sm font-mono">
                <Clock className="w-4 h-4" />
                <span>Last {days}d</span>
              </div>
            </div>
            <DateRangeSelector />
          </div>
          <p className="text-text-secondary text-lg">Real-time customer feedback analytics and insights</p>
        </div>

        {/* Dashboard Grid */}
        <DashboardGrid days={days} />
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardContent />
    </Suspense>
  );
}
