'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from 'recharts';
import type { CohortBucket } from '@/lib/api/churn-analytics';
import { getRiskBandColor, RISK_BAND_COLOR } from '@/lib/constants/churn';
import { formatPercent } from '@/lib/api/churn-analytics';

interface ChurnCohortBarChartProps {
  cohorts: CohortBucket[];
}

/** Horizontal bar chart showing churn rate per cohort. */
export function ChurnCohortBarChart({ cohorts }: ChurnCohortBarChartProps) {
  if (cohorts.length === 0) {
    return (
      <div className="text-sm text-muted-foreground text-center py-8">
        No cohort data available.
      </div>
    );
  }

  const data = cohorts.map((c) => ({
    name: c.label,
    churn_rate: Math.round(c.churn_rate * 100),
    raw_rate: c.churn_rate,
  }));

  return (
    <div data-testid="cohort-bar-chart">
      <ResponsiveContainer width="100%" height={Math.max(180, cohorts.length * 48)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(v) => `${v}%`}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={110}
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            formatter={(value: number, _name: string, props: { payload?: { raw_rate: number } }) => [
              formatPercent(props?.payload?.raw_rate ?? value / 100),
              'Churn Rate',
            ]}
          />
          <Bar dataKey="churn_rate" radius={[0, 4, 4, 0]}>
            {data.map(({ raw_rate }, index) => (
              <Cell
                key={index}
                fill={RISK_BAND_COLOR[getRiskBandColor(raw_rate)]}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
