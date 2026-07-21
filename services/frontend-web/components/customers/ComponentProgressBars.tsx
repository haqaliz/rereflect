'use client';

import { useQuery } from '@tanstack/react-query';
import { categoriesAPI } from '@/lib/api/categories';
import { getHealthColor } from './HealthScoreCircle';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface ComponentProgressBarsProps {
  churn_risk_component: number;
  sentiment_component: number;
  resolution_component: number;
  frequency_component: number;
  /** 0-100 usage component; defaults to 50 (neutral) when omitted */
  usage_component?: number;
}

const components = [
  { key: 'churn_risk', label: 'Churn Risk' },
  { key: 'sentiment', label: 'Sentiment' },
  { key: 'resolution', label: 'Resolution' },
  { key: 'frequency', label: 'Frequency' },
  { key: 'usage', label: 'Usage Activity' },
] as const;

/** Documented fallback weights used until org weights have loaded.
 *  Mirrors the backend defaults: churn 35 / sentiment 25 / resolution 25 / frequency 15 / usage 0.
 *  Usage is 0 until an operator opts in via Settings → AI → Health Score Weights. */
const DEFAULT_WEIGHTS: Record<string, number> = {
  churn_risk: 35,
  sentiment: 25,
  resolution: 25,
  frequency: 15,
  usage: 0,
};

const tooltips: Record<string, string> = {
  churn_risk: 'Based on negative sentiment patterns and feedback urgency signals indicating potential customer churn.',
  sentiment: 'Based on the average sentiment score across all feedback from this customer.',
  resolution: 'Based on average time to resolve this customer\'s feedback items.',
  frequency: 'Based on the rate and recency of feedback submissions from this customer.',
  usage: 'Based on login recency, frequency, and feature breadth from product-usage events.',
};

const descriptions: Record<string, (score: number) => string> = {
  churn_risk: (score) => {
    if (score < 30) return 'High likelihood of churning based on recent feedback patterns and keywords.';
    if (score < 50) return 'Some warning signals detected in recent feedback. Worth monitoring.';
    if (score < 70) return 'Moderate risk level. No strong warning signs currently.';
    return 'Low risk. Customer appears satisfied and engaged.';
  },
  sentiment: (score) => {
    if (score < 30) return 'Overall mood is very negative based on the last 30 days of feedback.';
    if (score < 50) return 'Feedback tone leans negative. Customer may be frustrated.';
    if (score < 70) return 'Mixed signals — some positive, some negative feedback.';
    return 'Feedback tone is positive. Customer is generally happy.';
  },
  resolution: (score) => {
    if (score < 30) return 'Open issues take a very long time to close for this customer.';
    if (score < 50) return 'Ticket close times are slower than ideal for this customer.';
    if (score < 70) return 'Average close time. Room for improvement.';
    return 'Open issues are closed quickly for this customer.';
  },
  frequency: (score) => {
    if (score < 30) return 'Complaint cadence is spiking — significantly above normal.';
    if (score < 50) return 'Submission rate is increasing compared to their average.';
    if (score < 70) return 'Submission cadence is stable and within normal range.';
    return 'Submission rate is low or declining — a healthy sign.';
  },
  usage: (score) => {
    if (score < 30) return 'Customer shows very low product engagement recently.';
    if (score < 50) return 'Product engagement is below average for this customer.';
    if (score < 70) return 'Moderate product activity detected.';
    return 'Customer is actively engaging with the product.';
  },
};

export function ComponentProgressBars({
  churn_risk_component,
  sentiment_component,
  resolution_component,
  frequency_component,
  usage_component = 50,
}: ComponentProgressBarsProps) {
  // Fetch the org's live health-score weights. Shared cache key with HealthWeightsEditor
  // so a single network request is reused across the page.
  const { data: healthWeights } = useQuery({
    queryKey: ['health-weights'],
    queryFn: () => categoriesAPI.getHealthWeights(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Map backend field names (churn/sentiment/resolution/frequency/usage) to component keys.
  // Fall back to documented defaults until the query resolves or if the fetch fails.
  const liveWeights: Record<string, number> = {
    churn_risk: healthWeights?.churn ?? DEFAULT_WEIGHTS.churn_risk,
    sentiment: healthWeights?.sentiment ?? DEFAULT_WEIGHTS.sentiment,
    resolution: healthWeights?.resolution ?? DEFAULT_WEIGHTS.resolution,
    frequency: healthWeights?.frequency ?? DEFAULT_WEIGHTS.frequency,
    usage: healthWeights?.usage ?? DEFAULT_WEIGHTS.usage,
  };

  const values: Record<string, number> = {
    churn_risk: churn_risk_component,
    sentiment: sentiment_component,
    resolution: resolution_component,
    frequency: frequency_component,
    usage: usage_component,
  };

  return (
    <TooltipProvider>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {components.map(({ key, label }) => {
          const score = values[key];
          const weight = liveWeights[key];
          const color = getHealthColor(score);
          const description = descriptions[key](score);
          return (
            <div key={key} data-testid={`progress-bar-${key}`} className="space-y-1.5">
              <div className="flex items-center justify-between text-sm">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="font-medium text-foreground cursor-help">
                      {label}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p className="max-w-xs">{tooltips[key]}</p>
                  </TooltipContent>
                </Tooltip>
                <span className="font-mono text-sm font-medium text-muted-foreground">
                  <span style={{ color }}>{score}/100</span>
                  <span className="ml-1 text-xs">· {weight}%</span>
                </span>
              </div>
              <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
                <div
                  data-testid={`progress-fill-${key}`}
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${score}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
              <p className="text-xs text-muted-foreground">{description}</p>
            </div>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
