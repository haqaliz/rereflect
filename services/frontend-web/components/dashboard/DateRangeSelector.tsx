'use client';

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
    <Tabs value={dateRange} onValueChange={(v) => setDateRange(v as DateRange)}>
      <TabsList className="h-8">
        {presets.map((preset) => (
          <TabsTrigger
            key={preset.value}
            value={preset.value}
            className="text-xs px-2 h-6"
          >
            {preset.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
