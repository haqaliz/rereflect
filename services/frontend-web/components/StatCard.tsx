import { LucideIcon } from 'lucide-react';
import Link from 'next/link';
import { cn } from '@/lib/utils';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  color: 'blue' | 'green' | 'yellow' | 'red' | 'purple';
  href?: string;
}

// Map color names to CSS variable names from Sunset Horizon palette
const colorMap = {
  blue: 'var(--chart-1)',      // Primary coral - for total/main metrics
  green: 'var(--chart-2)',     // Warm amber/gold - for positive metrics
  yellow: 'var(--chart-3)',    // Soft peach - for neutral metrics
  red: 'var(--destructive)',   // Destructive coral - for negative/urgent metrics
  purple: 'var(--chart-5)',    // Deep coral - for special metrics
};

export function StatCard({ title, value, icon: Icon, trend, color, href }: StatCardProps) {
  const themeColor = colorMap[color];

  const cardContent = (
    <div className={cn(
      "relative bg-card rounded-2xl shadow-md overflow-hidden transition-all duration-200 hover:shadow-md hover:scale-[1.02] border border-border",
      href && "cursor-pointer"
    )}>
      {/* Gradient top bar */}
      <div
        className="h-1"
        style={{
          background: `linear-gradient(to right, ${themeColor}, color-mix(in oklch, ${themeColor} 80%, transparent))`,
        }}
      />

      {/* Decorative corner accent - behind content */}
      <div
        className="absolute bottom-0 right-0 w-24 h-24 opacity-[0.03] rounded-tl-full z-0"
        style={{ backgroundColor: themeColor }}
      />

      <div className="relative z-10 p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-sm font-medium text-muted-foreground mb-2 uppercase tracking-wide">{title}</p>
            <p className="text-4xl font-bold text-foreground font-mono">{value}</p>
            {trend && (
              <div className={cn(
                "inline-flex items-center space-x-1 mt-3 px-2 py-1 rounded-lg text-xs font-semibold",
                trend.isPositive ? 'bg-accent/20 text-accent-foreground' : 'bg-destructive/20 text-destructive'
              )}>
                <span>{trend.isPositive ? '↑' : '↓'}</span>
                <span>{Math.abs(trend.value)}%</span>
              </div>
            )}
          </div>
          <div className="relative z-10">
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
    return <Link href={href}>{cardContent}</Link>;
  }

  return cardContent;
}
