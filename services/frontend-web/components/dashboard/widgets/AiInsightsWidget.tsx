'use client';

import { Lightbulb } from 'lucide-react';
import { WeeklyInsight } from '@/lib/api/insights';

interface AiInsightsWidgetProps {
  insights: WeeklyInsight | null;
}

const categoryColorMap: Record<string, string> = {
  pain_point: 'var(--destructive)',
  churn_risk: 'var(--destructive)',
  feature_request: 'var(--chart-2)',
  positive_trend: 'var(--chart-5)',
  opportunity: 'var(--chart-4)',
};

const priorityColorMap: Record<string, string> = {
  high: 'var(--destructive)',
  medium: 'var(--chart-2)',
  low: 'var(--chart-5)',
};

export function AiInsightsWidget({ insights }: AiInsightsWidgetProps) {
  const hasInsights = insights && insights.insights.length > 0;

  return hasInsights ? (
          <ul className="space-y-3">
            {insights.insights.map((insight, index) => {
              const categoryColor = categoryColorMap[insight.category] || 'var(--chart-4)';
              const priorityColor = priorityColorMap[insight.priority] || 'var(--chart-3)';
              const categoryLabel = insight.category
                .replace(/_/g, ' ')
                .replace(/\b\w/g, c => c.toUpperCase());

              return (
                <li
                  key={index}
                  className="p-4 rounded-xl border transition-all duration-200 hover:shadow-md"
                  style={{
                    backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                    borderColor: 'var(--border)',
                  }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <Lightbulb className="w-4 h-4 flex-shrink-0" style={{ color: categoryColor }} />
                        <p className="font-semibold text-sm text-foreground">{insight.title}</p>
                      </div>
                      <p className="text-sm text-muted-foreground leading-relaxed">{insight.description}</p>
                    </div>
                    <div className="flex flex-col gap-1.5 flex-shrink-0">
                      <span
                        className="px-2 py-0.5 text-xs font-semibold rounded-md text-center"
                        style={{
                          backgroundColor: `color-mix(in oklch, ${categoryColor} 15%, transparent)`,
                          color: categoryColor,
                        }}
                      >
                        {categoryLabel}
                      </span>
                      <span
                        className="px-2 py-0.5 text-xs font-semibold rounded-md text-center capitalize"
                        style={{
                          backgroundColor: `color-mix(in oklch, ${priorityColor} 15%, transparent)`,
                          color: priorityColor,
                        }}
                      >
                        {insight.priority}
                      </span>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
  ) : (
    <div className="text-center py-12 text-muted-foreground">
      <Lightbulb className="w-12 h-12 mx-auto mb-3 opacity-20" />
      <p className="text-sm">No AI insights available yet</p>
      <p className="text-xs mt-1">Insights are generated weekly from your feedback data</p>
    </div>
  );
}
