'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { billingAPI, Usage } from '@/lib/api/billing';
import { AlertTriangle, X, TrendingUp } from 'lucide-react';

interface UsageWarningProps {
  className?: string;
  threshold?: number; // Percentage threshold to show warning (default: 80)
}

export function UsageWarning({ className = '', threshold = 80 }: UsageWarningProps) {
  const router = useRouter();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if warning was dismissed in this session
    const wasDismissed = sessionStorage.getItem('usage_warning_dismissed');
    if (wasDismissed) {
      setDismissed(true);
      setLoading(false);
      return;
    }

    const fetchUsage = async () => {
      try {
        const response = await billingAPI.getUsage();
        setUsage(response);
      } catch (err) {
        console.error('Failed to fetch usage:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchUsage();
  }, []);

  const handleDismiss = () => {
    setDismissed(true);
    sessionStorage.setItem('usage_warning_dismissed', 'true');
  };

  // Don't show if loading, dismissed, or usage under threshold
  if (loading || dismissed || !usage) {
    return null;
  }

  // Check if feedback or seats are approaching limit
  const feedbackPercentage = usage.feedback_percentage;
  const seatsPercentage = usage.seats_percentage;

  // Only show if above threshold and there's a limit
  const showFeedbackWarning = usage.feedback_limit !== null && feedbackPercentage >= threshold;
  const showSeatsWarning = usage.seats_limit !== null && seatsPercentage >= threshold;

  if (!showFeedbackWarning && !showSeatsWarning) {
    return null;
  }

  const isOverLimit = feedbackPercentage >= 100 || seatsPercentage >= 100;
  const isCritical = feedbackPercentage >= 90 || seatsPercentage >= 90;

  return (
    <div
      className={`relative overflow-hidden ${
        isOverLimit
          ? 'bg-gradient-to-r from-red-500/10 to-red-500/5 border-red-500/30'
          : isCritical
          ? 'bg-gradient-to-r from-amber-500/10 to-amber-500/5 border-amber-500/30'
          : 'bg-gradient-to-r from-yellow-500/10 to-yellow-500/5 border-yellow-500/30'
      } border rounded-lg px-4 py-3 ${className}`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded-lg ${
              isOverLimit
                ? 'bg-red-500/20'
                : isCritical
                ? 'bg-amber-500/20'
                : 'bg-yellow-500/20'
            }`}
          >
            {isOverLimit ? (
              <AlertTriangle className="w-5 h-5 text-red-600" />
            ) : (
              <TrendingUp className="w-5 h-5 text-amber-600" />
            )}
          </div>
          <div>
            <p className="font-medium text-foreground">
              {isOverLimit ? (
                'Usage limit reached'
              ) : (
                'Approaching usage limit'
              )}
            </p>
            <p className="text-sm text-muted-foreground">
              {showFeedbackWarning && (
                <span>
                  Feedback: {usage.feedback_used.toLocaleString()}/{usage.feedback_limit?.toLocaleString()} ({feedbackPercentage.toFixed(0)}%)
                  {usage.overage_count > 0 && ` - ${usage.overage_count} overage items`}
                </span>
              )}
              {showFeedbackWarning && showSeatsWarning && ' | '}
              {showSeatsWarning && (
                <span>
                  Seats: {usage.seats_used}/{usage.seats_limit} ({seatsPercentage.toFixed(0)}%)
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            onClick={() => router.push('/settings/billing')}
            size="sm"
            variant={isOverLimit ? 'destructive' : 'default'}
          >
            Upgrade Plan
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
    </div>
  );
}
