'use client';

import { ChevronsUpDown } from 'lucide-react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { useAuth } from '@/contexts/AuthContext';
import Link from 'next/link';

export interface ChurnFactor {
  score: number;
  max: number;
  label: string;
}

export interface ChurnRiskFactors {
  [key: string]: ChurnFactor;
}

const FACTOR_DISPLAY_NAMES: Record<string, string> = {
  sentiment: 'Sentiment',
  churn_keywords: 'Churn Keywords',
  frustration_keywords: 'Frustration Keywords',
  urgency: 'Urgency',
  sentiment_trend: 'Sentiment Trend',
  feedback_frequency: 'Feedback Frequency',
  resolution_time: 'Resolution Time',
  pain_severity: 'Pain Severity',
  feature_density: 'Feature Density',
};

function getFactorColor(score: number, max: number): 'red' | 'orange' | 'green' {
  if (max === 0) return 'green';
  const pct = score / max;
  if (pct > 0.75) return 'red';
  if (pct >= 0.4) return 'orange';
  return 'green';
}

const COLOR_STYLES: Record<'red' | 'orange' | 'green', string> = {
  red: 'var(--destructive)',
  orange: 'var(--chart-2)',
  green: 'var(--chart-5)',
};

interface ChurnFactorBreakdownProps {
  churnRiskFactors: ChurnRiskFactors | null;
}

export function ChurnFactorBreakdown({ churnRiskFactors }: ChurnFactorBreakdownProps) {
  const { user } = useAuth();

  const isPro =
    user?.plan === 'pro' ||
    user?.plan === 'business' ||
    user?.plan === 'enterprise';

  if (!isPro) {
    return (
      <div className="mt-3 pt-3 border-t border-border">
        <p className="text-sm text-muted-foreground">
          <Link href="/settings/billing" className="text-primary underline underline-offset-2">
            Upgrade to Pro
          </Link>{' '}
          to see factor breakdown
        </p>
      </div>
    );
  }

  if (churnRiskFactors === null) {
    return (
      <div className="mt-3 pt-3 border-t border-border">
        <p className="text-sm text-muted-foreground italic">Factor breakdown not available</p>
      </div>
    );
  }

  const sortedFactors = Object.entries(churnRiskFactors).sort(
    ([, a], [, b]) => b.score - a.score
  );

  return (
    <Collapsible className="mt-3 pt-3 border-t border-border">
      <CollapsibleTrigger className="flex w-full items-center justify-between py-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <span className="font-medium">Factor breakdown</span>
        <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="pt-3 space-y-3">
          {sortedFactors.map(([key, factor]) => {
            const color = getFactorColor(factor.score, factor.max);
            const colorValue = COLOR_STYLES[color];
            const widthPct = factor.max > 0 ? (factor.score / factor.max) * 100 : 0;
            const isMuted = factor.score === 0;

            return (
              <div key={key} className={isMuted ? 'opacity-50' : ''}>
                <div className="flex items-center justify-between mb-1">
                  <span
                    className="text-xs font-medium"
                    data-testid="factor-label"
                  >
                    {factor.label || FACTOR_DISPLAY_NAMES[key] || key}
                  </span>
                  <span className="text-xs text-muted-foreground font-mono">
                    {factor.score}/{factor.max}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    data-testid="factor-progress-bar"
                    data-color={color}
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${widthPct}%`,
                      backgroundColor: colorValue,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
