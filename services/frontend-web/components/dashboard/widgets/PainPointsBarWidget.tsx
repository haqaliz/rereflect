'use client';

import { AlertTriangle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartConfig } from '@/components/ui/chart';
import { CategoryCount } from '@/lib/api/dashboard';
import { getPainPointLabel } from '@/lib/category-utils';

interface PainPointsBarWidgetProps {
  categories: CategoryCount[];
}

const painPointsChartConfig = {
  count: {
    label: 'Count',
    color: 'var(--chart-1)',
  },
} satisfies ChartConfig;

export function PainPointsBarWidget({ categories }: PainPointsBarWidgetProps) {
  const chartData = categories.slice(0, 6).map(cat => ({
    category: getPainPointLabel(cat.category),
    count: cat.count,
    severity: cat.severity,
  }));

  const useAngle = chartData.length > 4;

  return chartData.length > 0 ? (
    <ChartContainer config={painPointsChartConfig} className="h-full w-full min-h-[250px]">
      <BarChart
              data={chartData}
              margin={{ top: 20, right: 10, left: 10, bottom: useAngle ? 80 : 20 }}
            >
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis
                dataKey="category"
                angle={useAngle ? -45 : 0}
                textAnchor={useAngle ? 'end' : 'middle'}
                height={useAngle ? 80 : 30}
                interval={0}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
              />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
              <ChartTooltip
                content={<ChartTooltipContent />}
                cursor={{ fill: 'var(--muted)', opacity: 0.3 }}
              />
              <Bar
                dataKey="count"
                fill="var(--chart-1)"
                radius={[8, 8, 0, 0]}
                maxBarSize={60}
              />
      </BarChart>
    </ChartContainer>
  ) : (
    <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary">
      <AlertTriangle className="w-16 h-16 mb-3 opacity-30" />
      <p className="text-sm">No pain point categories identified yet</p>
    </div>
  );
}
