'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { billingAPI, Subscription } from '@/lib/api/billing';
import { Crown, X, Sparkles } from 'lucide-react';

interface TrialBannerProps {
  className?: string;
}

export function TrialBanner({ className = '' }: TrialBannerProps) {
  const router = useRouter();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if banner was dismissed in this session
    const wasDismissed = sessionStorage.getItem('trial_banner_dismissed');
    if (wasDismissed) {
      setDismissed(true);
      setLoading(false);
      return;
    }

    const fetchSubscription = async () => {
      try {
        const response = await billingAPI.getSubscription();
        setSubscription(response.subscription);
      } catch (err) {
        console.error('Failed to fetch subscription:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchSubscription();
  }, []);

  const handleDismiss = () => {
    setDismissed(true);
    sessionStorage.setItem('trial_banner_dismissed', 'true');
  };

  // Don't show if loading, dismissed, or not on trial
  if (loading || dismissed || !subscription?.is_trial) {
    return null;
  }

  const daysLeft = subscription.trial_days_remaining ?? 0;
  const isUrgent = daysLeft <= 3;

  return (
    <div
      className={`relative overflow-hidden ${
        isUrgent
          ? 'bg-gradient-to-r from-amber-500/10 to-orange-500/10 border-amber-500/30'
          : 'bg-gradient-to-r from-primary/10 to-primary/5 border-primary/30'
      } border rounded-lg px-4 py-3 ${className}`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${isUrgent ? 'bg-amber-500/20' : 'bg-primary/20'}`}>
            {isUrgent ? (
              <Sparkles className="w-5 h-5 text-amber-600" />
            ) : (
              <Crown className="w-5 h-5 text-primary" />
            )}
          </div>
          <div>
            <p className="font-medium text-foreground">
              {daysLeft === 0 ? (
                'Your Pro trial ends today!'
              ) : daysLeft === 1 ? (
                'Your Pro trial ends tomorrow!'
              ) : (
                <>
                  <span className="font-bold">{daysLeft} days</span> left in your Pro trial
                </>
              )}
            </p>
            <p className="text-sm text-muted-foreground">
              Upgrade now to keep your Pro features and avoid losing access.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            onClick={() => router.push('/settings/billing')}
            size="sm"
            className={isUrgent ? 'bg-amber-600 hover:bg-amber-700' : ''}
          >
            Upgrade Now
          </Button>
          <button
            onClick={handleDismiss}
            className="p-1 hover:bg-secondary rounded-md transition-colors"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      {/* Progress indicator */}
      <div className="absolute bottom-0 left-0 h-1 bg-primary/20 w-full">
        <div
          className={`h-full transition-all ${isUrgent ? 'bg-amber-500' : 'bg-primary'}`}
          style={{ width: `${Math.max(0, ((14 - daysLeft) / 14) * 100)}%` }}
        />
      </div>
    </div>
  );
}
