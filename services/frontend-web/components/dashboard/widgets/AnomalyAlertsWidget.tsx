'use client';

import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { SentimentAnomaly } from '@/lib/api/anomalies';

interface AnomalyAlertsWidgetProps {
  anomalies: SentimentAnomaly[];
}

function getRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

export function AnomalyAlertsWidget({ anomalies }: AnomalyAlertsWidgetProps) {
  if (anomalies.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <CheckCircle2 className="w-10 h-10 mb-2 opacity-20" />
        <p className="text-sm font-medium">No anomalies detected</p>
        <p className="text-xs opacity-60 mt-0.5">Sentiment patterns are within normal range</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {anomalies.map((anomaly) => {
        const isCritical = anomaly.severity === 'critical';
        const borderColor = isCritical ? 'var(--destructive)' : 'var(--chart-2)';
        const bgColor = isCritical
          ? 'color-mix(in oklch, var(--destructive) 10%, var(--card))'
          : 'color-mix(in oklch, var(--chart-2) 10%, var(--card))';

        return (
          <div
            key={anomaly.id}
            className="rounded-xl p-4 border-2"
            style={{ backgroundColor: bgColor, borderColor }}
          >
            <div className="flex items-start space-x-3">
              <div
                className="p-2 rounded-lg flex-shrink-0"
                style={{ backgroundColor: `color-mix(in oklch, ${borderColor} 20%, transparent)` }}
              >
                <AlertTriangle className="w-5 h-5" style={{ color: borderColor }} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-foreground">
                    {isCritical ? 'Critical' : 'Warning'}: Negative Sentiment Spike
                  </p>
                  <span className="text-xs text-muted-foreground flex-shrink-0">
                    {getRelativeTime(anomaly.detected_at)}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground mt-0.5">
                  {anomaly.current_negative_pct.toFixed(0)}% negative vs {anomaly.baseline_negative_pct.toFixed(0)}% baseline
                  {' '}(+{anomaly.deviation_pct.toFixed(0)}pp) — {anomaly.feedback_count} items in last {anomaly.time_window_hours}h
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
