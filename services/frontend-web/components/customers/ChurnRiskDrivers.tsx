'use client';

import { useQuery } from '@tanstack/react-query';
import { customersAPI } from '@/lib/api/customers';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

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

interface ChurnRiskDriversProps {
  email: string;
}

export function ChurnRiskDrivers({ email }: ChurnRiskDriversProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['churn-factors', email],
    queryFn: () => customersAPI.getChurnFactors(email),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Churn Risk Drivers</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Loading...</p>
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return null;
  }

  const sortedFactors = Object.entries(data.aggregated_factors).sort(
    ([, a], [, b]) => b.avg_score - a.avg_score
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Churn Risk Drivers</CardTitle>
        <p className="text-xs text-muted-foreground">
          Based on {data.feedback_count} feedbacks in the last {data.period_days} days
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {data.top_risk_drivers.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {data.top_risk_drivers.map((driver) => (
              <Badge
                key={driver}
                variant="outline"
                data-testid={`top-driver-${driver}`}
                style={{
                  color: 'var(--destructive)',
                  borderColor: 'color-mix(in oklch, var(--destructive) 30%, transparent)',
                  backgroundColor: 'color-mix(in oklch, var(--destructive) 8%, transparent)',
                }}
              >
                {FACTOR_DISPLAY_NAMES[driver] || driver}
              </Badge>
            ))}
          </div>
        )}

        <div className="space-y-2.5">
          {sortedFactors.map(([key, factor]) => {
            const widthPct = factor.max > 0 ? (factor.avg_score / factor.max) * 100 : 0;
            const isTopDriver = data.top_risk_drivers.includes(key);

            return (
              <div key={key}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium">
                    {FACTOR_DISPLAY_NAMES[key] || key}
                  </span>
                  <span className="text-xs text-muted-foreground font-mono">
                    {factor.avg_score.toFixed(1)}/{factor.max}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${widthPct}%`,
                      backgroundColor: isTopDriver ? 'var(--destructive)' : 'var(--chart-2)',
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
