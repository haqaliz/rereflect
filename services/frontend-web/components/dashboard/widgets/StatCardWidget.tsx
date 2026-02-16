'use client';

import { LucideIcon, TrendingUp, TrendingDown } from 'lucide-react';
import Link from 'next/link';
import { Area, AreaChart, ResponsiveContainer } from 'recharts';

interface StatCardWidgetProps {
  title: string;
  subtitle?: string;
  value: string | number;
  icon: LucideIcon;
  color: 'blue' | 'green' | 'yellow' | 'red' | 'purple';
  href?: string;
  deltaPct?: number;
  sparklineData?: number[];
  invertDelta?: boolean;
}

const colorMap = {
  blue: 'var(--chart-1)',
  green: 'var(--chart-2)',
  yellow: 'var(--chart-3)',
  red: 'var(--destructive)',
  purple: 'var(--chart-5)',
};

export function StatCardWidget({
  title,
  subtitle,
  value,
  icon: Icon,
  color,
  href,
  deltaPct,
  sparklineData,
  invertDelta = false,
}: StatCardWidgetProps) {
  const themeColor = colorMap[color];

  const hasDelta = deltaPct !== undefined && deltaPct !== null;
  const isPositiveChange = hasDelta && deltaPct! > 0;
  const isNegativeChange = hasDelta && deltaPct! < 0;

  // For metrics like "negative", an increase is bad (invert logic)
  const isGoodChange = invertDelta ? isNegativeChange : isPositiveChange;
  const deltaColor = isGoodChange ? 'var(--chart-5)' : 'var(--destructive)';

  const sparkData = sparklineData?.map((v, i) => ({ value: v, index: i })) || [];

  const cardContent = (
    <div className="relative h-full bg-card rounded-2xl shadow-md overflow-hidden transition-all duration-200 hover:shadow-md hover:scale-[1.02] border border-border cursor-pointer">
      {/* Gradient top bar */}
      <div
        className="h-1"
        style={{
          background: `linear-gradient(to right, ${themeColor}, color-mix(in oklch, ${themeColor} 80%, transparent))`,
        }}
      />

      {/* Decorative corner accent */}
      <div
        className="absolute bottom-0 right-0 w-24 h-24 opacity-[0.03] rounded-tl-full z-0"
        style={{ backgroundColor: themeColor }}
      />

      <div className="relative z-10 p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              {title}
            </p>
            {subtitle && (
              <p className="text-xs text-muted-foreground/60 mt-0.5 mb-1">{subtitle}</p>
            )}
            <div className="flex items-end gap-3">
              <p className="text-4xl font-bold text-foreground font-mono">{value}</p>
              {hasDelta && (
                <div
                  className="inline-flex items-center gap-1 mb-1 px-2 py-0.5 rounded-md text-xs font-semibold"
                  style={{
                    backgroundColor: `color-mix(in oklch, ${deltaColor} 15%, transparent)`,
                    color: deltaColor,
                  }}
                >
                  {isPositiveChange ? (
                    <TrendingUp className="w-3 h-3" />
                  ) : isNegativeChange ? (
                    <TrendingDown className="w-3 h-3" />
                  ) : null}
                  <span>{Math.abs(deltaPct!).toFixed(1)}%</span>
                </div>
              )}
            </div>

            {/* Sparkline */}
            {sparkData.length > 1 && (
              <div className="mt-3 h-8 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={sparkData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id={`sparkGrad-${title.replace(/\s/g, '')}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={themeColor} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={themeColor} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke={themeColor}
                      strokeWidth={1.5}
                      fill={`url(#sparkGrad-${title.replace(/\s/g, '')})`}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="relative z-10 flex-shrink-0 ml-3">
            <div
              className="absolute inset-0 blur-lg opacity-30"
              style={{ backgroundColor: themeColor }}
            />
            <div
              className="relative p-3.5 rounded-2xl shadow-sm"
              style={{
                backgroundColor: `color-mix(in oklch, ${themeColor} 15%, var(--secondary))`,
                color: themeColor,
              }}
            >
              <Icon className="w-7 h-7" strokeWidth={2.5} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  if (href) {
    return <Link href={href} className="block h-full">{cardContent}</Link>;
  }

  return cardContent;
}
