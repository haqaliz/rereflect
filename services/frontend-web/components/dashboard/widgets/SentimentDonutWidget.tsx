'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Meh } from 'lucide-react';
import { PieChart, Pie, Cell, Sector } from 'recharts';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartConfig } from '@/components/ui/chart';

interface SentimentDonutWidgetProps {
  sentimentData: {
    positive_count: number;
    neutral_count: number;
    negative_count: number;
  };
  totalFeedback: number;
}

const sentimentChartConfig = {
  count: { label: 'Count' },
  positive: { label: 'Positive', color: 'var(--chart-2)' },
  neutral: { label: 'Neutral', color: 'var(--chart-3)' },
  negative: { label: 'Negative', color: 'var(--destructive)' },
} satisfies ChartConfig;

export function SentimentDonutWidget({ sentimentData, totalFeedback }: SentimentDonutWidgetProps) {
  const router = useRouter();
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const chartData = [
    {
      sentiment: 'positive',
      count: sentimentData.positive_count,
      fill: 'var(--chart-2)',
      percentage: totalFeedback > 0 ? Math.round((sentimentData.positive_count / totalFeedback) * 100) : 0,
    },
    {
      sentiment: 'neutral',
      count: sentimentData.neutral_count,
      fill: 'var(--chart-3)',
      percentage: totalFeedback > 0 ? Math.round((sentimentData.neutral_count / totalFeedback) * 100) : 0,
    },
    {
      sentiment: 'negative',
      count: sentimentData.negative_count,
      fill: 'var(--destructive)',
      percentage: totalFeedback > 0 ? Math.round((sentimentData.negative_count / totalFeedback) * 100) : 0,
    },
  ];

  const renderActiveShape = (props: any) => {
    const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
    return (
      <g>
        <Sector
          cx={cx}
          cy={cy}
          innerRadius={innerRadius - 4}
          outerRadius={outerRadius + 8}
          startAngle={startAngle}
          endAngle={endAngle}
          fill={fill}
          style={{ filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.3))' }}
        />
      </g>
    );
  };

  return chartData.some(d => d.count > 0) ? (
    <div className="flex-1 flex flex-col lg:flex-row items-center gap-6">
            <div className="flex-shrink-0">
              <ChartContainer config={sentimentChartConfig} className="mx-auto w-[240px] h-[240px]">
                <PieChart>
                  <ChartTooltip
                    cursor={false}
                    content={<ChartTooltipContent hideLabel formatter={(value, _name, props) => {
                      const item = props.payload;
                      return `${value} (${item.percentage}%)`;
                    }} />}
                  />
                  <Pie
                    data={chartData}
                    dataKey="count"
                    nameKey="sentiment"
                    innerRadius={70}
                    outerRadius={110}
                    strokeWidth={2}
                    stroke="hsl(var(--background))"
                    activeIndex={activeIndex !== null ? activeIndex : undefined}
                    activeShape={renderActiveShape}
                    onMouseEnter={(_, index) => setActiveIndex(index)}
                    onMouseLeave={() => setActiveIndex(null)}
                  >
                    {chartData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.fill}
                        opacity={activeIndex === null || activeIndex === index ? 1 : 0.4}
                        style={{ transition: 'opacity 0.2s ease-in-out' }}
                      />
                    ))}
                  </Pie>
                </PieChart>
              </ChartContainer>
            </div>

            <div className="flex-1 space-y-3 min-w-0">
              <div className="mb-4">
                <p className="text-2xl font-bold font-mono text-text-primary">{totalFeedback}</p>
                <p className="text-xs text-text-tertiary uppercase tracking-wide">Total Feedback</p>
              </div>

              {chartData.map((item, index) => {
                const chartColor =
                  item.sentiment === 'positive' ? 'var(--chart-2)' :
                  item.sentiment === 'negative' ? 'var(--destructive)' :
                  'var(--chart-3)';
                const isActive = activeIndex === index;
                const isInactive = activeIndex !== null && activeIndex !== index;

                return (
                  <div
                    key={item.sentiment}
                    className={`group flex justify-between items-center p-4 rounded-xl transition-all duration-200 cursor-pointer border ${
                      isActive ? 'scale-[1.02] shadow-md' : isInactive ? 'opacity-50' : ''
                    }`}
                    style={{
                      backgroundColor: isActive
                        ? `color-mix(in oklch, ${chartColor} 15%, var(--muted))`
                        : 'color-mix(in oklch, var(--muted) 50%, transparent)',
                      borderColor: isActive ? chartColor : 'var(--border)',
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                    onMouseLeave={() => setActiveIndex(null)}
                    onClick={() => router.push(`/feedbacks?sentiment=${item.sentiment}`)}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: chartColor }}
                      />
                      <span className="text-foreground font-medium text-sm capitalize truncate">
                        {item.sentiment}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 ml-3 flex-shrink-0">
                      <span
                        className="text-xs font-semibold px-2 py-0.5 rounded-md"
                        style={{
                          backgroundColor: `color-mix(in oklch, ${chartColor} 20%, transparent)`,
                          color: chartColor,
                        }}
                      >
                        {item.percentage}%
                      </span>
                      <span
                        className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono"
                        style={{
                          backgroundColor: `color-mix(in oklch, ${chartColor} 20%, transparent)`,
                          color: chartColor,
                        }}
                      >
                        {item.count}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
    </div>
  ) : (
    <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary">
      <Meh className="w-16 h-16 mb-3 opacity-30" />
      <p className="text-sm">No sentiment data available yet</p>
    </div>
  );
}
