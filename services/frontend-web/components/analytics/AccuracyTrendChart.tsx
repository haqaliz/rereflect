'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { BacktestRunSummary } from '@/lib/api/churn-accuracy';
import { formatMetricPercent } from '@/lib/api/churn-accuracy';

interface AccuracyTrendChartProps {
  runs: BacktestRunSummary[];
  width?: number;
  height?: number;
}

interface ChartDataPoint {
  date: string;
  f1: number | null;
  precision: number | null;
  recall: number | null;
}

function formatRunDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

interface TooltipPayloadEntry {
  name: string;
  value: number | null;
  color: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="bg-background border border-border rounded-md p-3 shadow-md text-sm">
      <p className="font-medium mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }}>
          {entry.name}: {entry.value !== null ? formatMetricPercent(entry.value) : '—'}
        </p>
      ))}
    </div>
  );
}

export function AccuracyTrendChart({ runs, height = 280 }: AccuracyTrendChartProps) {
  if (runs.length === 0) {
    return (
      <div
        data-testid="accuracy-trend-empty"
        className="flex items-center justify-center h-40 text-sm text-muted-foreground"
      >
        No backtest runs yet. Accuracy data will appear after the weekly refit.
      </div>
    );
  }

  const data: ChartDataPoint[] = runs.map((run) => ({
    date: formatRunDate(run.run_at),
    f1: run.f1,
    precision: run.precision,
    recall: run.recall,
  }));

  return (
    <div data-testid="accuracy-trend-chart" style={{ width: '100%', height }}>
      {/* Metric labels rendered in DOM for testability (Recharts SVG legend is not accessible in jsdom) */}
      <div className="sr-only" aria-hidden="true">
        <span>F1</span>
        <span>Precision</span>
        <span>Recall</span>
      </div>
      <div aria-label="Accuracy trend legend" className="flex gap-4 text-xs text-muted-foreground mb-2">
        <span style={{ color: 'var(--chart-1)' }}>F1</span>
        <span style={{ color: 'var(--chart-2)' }}>Precision</span>
        <span style={{ color: 'var(--chart-5)' }}>Recall</span>
      </div>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11 }}
            className="text-muted-foreground"
          />
          <YAxis
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            domain={[0, 1]}
            tick={{ fontSize: 11 }}
            className="text-muted-foreground"
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Line
            type="monotone"
            dataKey="f1"
            name="F1"
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="precision"
            name="Precision"
            stroke="var(--chart-2)"
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="recall"
            name="Recall"
            stroke="var(--chart-5)"
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
