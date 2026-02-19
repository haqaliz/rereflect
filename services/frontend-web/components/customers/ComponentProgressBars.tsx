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
}

const components = [
  { key: 'churn_risk', label: 'Churn Risk' },
  { key: 'sentiment', label: 'Sentiment' },
  { key: 'resolution', label: 'Resolution' },
  { key: 'frequency', label: 'Frequency' },
] as const;

const tooltips: Record<string, string> = {
  churn_risk: 'Based on negative sentiment patterns and feedback urgency signals indicating potential customer churn.',
  sentiment: 'Based on the average sentiment score across all feedback from this customer.',
  resolution: 'Based on average time to resolve this customer\'s feedback items.',
  frequency: 'Based on the rate and recency of feedback submissions from this customer.',
};

function getRatingLabel(score: number): string {
  if (score < 30) return 'Critical';
  if (score < 50) return 'Poor';
  if (score < 70) return 'Fair';
  if (score < 85) return 'Good';
  return 'Excellent';
}

const descriptions: Record<string, (score: number) => string> = {
  churn_risk: (score) => {
    if (score < 30) return 'High likelihood of churning based on recent feedback patterns and keywords.';
    if (score < 50) return 'Some churn signals detected in recent feedback. Worth monitoring.';
    if (score < 70) return 'Moderate churn risk. No strong warning signs currently.';
    return 'Low churn risk. Customer appears satisfied and engaged.';
  },
  sentiment: (score) => {
    if (score < 30) return 'Overall feedback sentiment is very negative over the last 30 days.';
    if (score < 50) return 'Feedback sentiment leans negative. Customer may be frustrated.';
    if (score < 70) return 'Mixed sentiment — some positive, some negative feedback.';
    return 'Feedback sentiment is positive. Customer is generally happy.';
  },
  resolution: (score) => {
    if (score < 30) return 'Issues take a very long time to resolve for this customer.';
    if (score < 50) return 'Resolution times are slower than ideal for this customer.';
    if (score < 70) return 'Average resolution time. Room for improvement.';
    return 'Issues are resolved quickly for this customer.';
  },
  frequency: (score) => {
    if (score < 30) return 'Complaint frequency is spiking — significantly above normal.';
    if (score < 50) return 'Feedback frequency is increasing compared to their average.';
    if (score < 70) return 'Feedback frequency is stable and within normal range.';
    return 'Feedback frequency is low or declining — a healthy sign.';
  },
};

export function ComponentProgressBars({
  churn_risk_component,
  sentiment_component,
  resolution_component,
  frequency_component,
}: ComponentProgressBarsProps) {
  const values: Record<string, number> = {
    churn_risk: churn_risk_component,
    sentiment: sentiment_component,
    resolution: resolution_component,
    frequency: frequency_component,
  };

  return (
    <TooltipProvider>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {components.map(({ key, label }) => {
          const score = values[key];
          const color = getHealthColor(score);
          const ratingLabel = getRatingLabel(score);
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
                <span className="font-mono text-sm font-medium" style={{ color }}>
                  {ratingLabel} · {score}
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
