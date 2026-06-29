'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { customersAPI } from '@/lib/api/customers';
import { Skeleton } from '@/components/ui/skeleton';

interface UsageTimelineProps {
  email: string;
}

const PERIODS = [30, 60, 90] as const;
type Period = (typeof PERIODS)[number];

export function UsageTimeline({ email }: UsageTimelineProps) {
  const [days, setDays] = useState<Period>(30);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['customer-usage', email, days],
    queryFn: () => customersAPI.getUsage(email, days),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const chartData = data?.time_series ?? [];

  const isEmpty = !isLoading && (isError || chartData.length === 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">
          Product Usage Over Time
        </span>
        <div className="flex gap-1">
          {PERIODS.map((period) => (
            <button
              key={period}
              onClick={() => setDays(period)}
              className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                days === period
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
            >
              {period}d
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="h-48 space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : isEmpty ? (
        <div className="h-48 flex items-center justify-center text-center px-4">
          <p className="text-muted-foreground text-sm">
            No usage events recorded yet. Send product-usage events via{' '}
            <code className="text-xs bg-muted px-1 py-0.5 rounded">
              POST /api/v1/webhooks/usage
            </code>{' '}
            to start tracking engagement.
          </p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              stroke="var(--muted-foreground)"
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 11 }}
              stroke="var(--muted-foreground)"
            />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="event_count"
              stroke="var(--chart-2)"
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
