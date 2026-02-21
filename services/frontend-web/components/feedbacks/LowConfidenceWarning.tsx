'use client';

import { AlertTriangle } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

interface LowConfidenceWarningProps {
  confidenceScore: number | null | undefined;
}

export function LowConfidenceWarning({ confidenceScore }: LowConfidenceWarningProps) {
  const { user } = useAuth();

  const isPro =
    user?.plan === 'pro' ||
    user?.plan === 'business' ||
    user?.plan === 'enterprise';

  if (!isPro) return null;

  if (confidenceScore === null || confidenceScore === undefined || confidenceScore >= 30) {
    return null;
  }

  return (
    <span className="relative inline-block group">
      <AlertTriangle
        data-testid="low-confidence-warning"
        className="w-3.5 h-3.5 text-[var(--chart-2)]"
        aria-label="Low confidence"
      />
      {/* Tooltip for testability */}
      <span
        data-testid="low-confidence-tooltip"
        className="sr-only"
        aria-hidden="true"
      >
        Low confidence — limited data for this customer
      </span>
    </span>
  );
}
