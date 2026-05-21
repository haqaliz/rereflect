'use client';

import { useMemo } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import type { CohortBucket } from '@/lib/api/churn-analytics';
import { CHURN_REASON_LABELS } from '@/lib/constants/churn';
import type { ChurnReasonCode } from '@/lib/api/churn-events';

interface ReasonCodeBreakdownProps {
  cohorts: CohortBucket[];
}

const REASON_COLORS: Record<ChurnReasonCode, string> = {
  price: 'var(--chart-1)',
  competitor: 'var(--chart-2)',
  product_quality: 'var(--chart-3)',
  no_longer_needed: 'var(--chart-4)',
  silent_churn: 'var(--chart-5)',
  other: 'var(--muted-foreground)',
};

/** Donut chart of aggregated churn reason codes across all cohorts. */
export function ReasonCodeBreakdown({ cohorts }: ReasonCodeBreakdownProps) {
  const aggregated = useMemo(() => {
    const totals = new Map<ChurnReasonCode, number>();
    for (const cohort of cohorts) {
      for (const rc of cohort.top_reason_codes) {
        totals.set(rc.code, (totals.get(rc.code) ?? 0) + rc.count);
      }
    }
    return Array.from(totals.entries()).map(([code, count]) => ({ code, count }));
  }, [cohorts]);

  if (aggregated.length === 0) return null;

  return (
    <div data-testid="reason-code-breakdown" className="flex flex-col gap-4">
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={aggregated}
            dataKey="count"
            nameKey="code"
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={85}
            strokeWidth={2}
            stroke="hsl(var(--background))"
          >
            {aggregated.map(({ code }) => (
              <Cell key={code} fill={REASON_COLORS[code] ?? 'var(--muted-foreground)'} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number, name: string) => [
              value,
              CHURN_REASON_LABELS[name as ChurnReasonCode] ?? name,
            ]}
          />
        </PieChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {aggregated.map(({ code, count }) => (
          <div
            key={code}
            data-testid={`reason-segment-${code}`}
            className="flex items-center gap-2 text-sm"
          >
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ backgroundColor: REASON_COLORS[code] ?? 'var(--muted-foreground)' }}
            />
            <span data-testid={`reason-label-${code}`} className="flex-1 truncate text-muted-foreground">
              {CHURN_REASON_LABELS[code] ?? code}
            </span>
            <span data-testid={`reason-count-${code}`} className="font-mono font-medium tabular-nums">
              {count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
