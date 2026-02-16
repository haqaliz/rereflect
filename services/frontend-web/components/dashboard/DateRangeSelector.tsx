'use client';

import { cn } from '@/lib/utils';
import { type DateRange, useDateRange } from './hooks/useDateRange';

const presets: { label: string; value: DateRange }[] = [
  { label: '7d', value: '7d' },
  { label: '14d', value: '14d' },
  { label: '30d', value: '30d' },
  { label: '90d', value: '90d' },
  { label: 'YTD', value: 'ytd' },
];

export function DateRangeSelector() {
  const { dateRange, setDateRange } = useDateRange();

  return (
    <div className="flex items-center gap-1 p-1 rounded-lg bg-muted/50 border border-border">
      {presets.map((preset) => {
        const isActive = dateRange === preset.value;
        return (
          <button
            key={preset.value}
            onClick={() => setDateRange(preset.value)}
            className={cn(
              'px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200',
              isActive
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            )}
          >
            {preset.label}
          </button>
        );
      })}
    </div>
  );
}
