import { LucideIcon } from 'lucide-react';
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
}

const colorClasses = {
  blue: {
    gradient: 'from-blue-500 to-blue-600',
    bg: 'bg-blue-50',
    icon: 'bg-blue-100 text-blue-600',
    border: 'border-blue-200'
  },
  green: {
    gradient: 'from-emerald-500 to-green-600',
    bg: 'bg-emerald-50',
    icon: 'bg-emerald-100 text-emerald-700',
    border: 'border-emerald-200'
  },
  yellow: {
    gradient: 'from-amber-400 to-yellow-500',
    bg: 'bg-amber-50',
    icon: 'bg-amber-100 text-amber-700',
    border: 'border-amber-200'
  },
  red: {
    gradient: 'from-red-500 to-rose-600',
    bg: 'bg-red-50',
    icon: 'bg-red-100 text-red-700',
    border: 'border-red-200'
  },
  purple: {
    gradient: 'from-purple-500 to-indigo-600',
    bg: 'bg-purple-50',
    icon: 'bg-purple-100 text-purple-700',
    border: 'border-purple-200'
  }
};

export function StatCard({ title, value, icon: Icon, trend, color }: StatCardProps) {
  const colors = colorClasses[color];

  return (
    <div className={cn(
      "relative surface rounded-2xl shadow-md overflow-hidden transition-all duration-300 hover:shadow-xl hover:scale-[1.02] border-2",
      colors.border
    )}>
      {/* Gradient top bar */}
      <div className={cn("h-1 bg-gradient-to-r", colors.gradient)} />

      <div className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-sm font-medium text-text-secondary mb-2 uppercase tracking-wide">{title}</p>
            <p className="text-4xl font-bold text-text-primary font-mono">{value}</p>
            {trend && (
              <div className={cn(
                "inline-flex items-center space-x-1 mt-3 px-2 py-1 rounded-lg text-xs font-semibold",
                trend.isPositive ? 'bg-success-bg text-success-text' : 'bg-error-bg text-error-text'
              )}>
                <span>{trend.isPositive ? '↑' : '↓'}</span>
                <span>{Math.abs(trend.value)}%</span>
              </div>
            )}
          </div>
          <div className="relative">
            <div className={cn("absolute inset-0 blur-lg opacity-30", colors.bg)}></div>
            <div className={cn("relative p-3.5 rounded-2xl shadow-sm", colors.icon)}>
              <Icon className="w-7 h-7" strokeWidth={2.5} />
            </div>
          </div>
        </div>
      </div>

      {/* Decorative corner accent */}
      <div className={cn(
        "absolute bottom-0 right-0 w-24 h-24 opacity-5 rounded-tl-full",
        colors.bg
      )} />
    </div>
  );
}
