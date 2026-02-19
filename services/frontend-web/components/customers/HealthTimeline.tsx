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
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import { customersAPI } from '@/lib/api/customers';

interface HealthTimelineProps {
  email: string;
}

const PERIODS = [30, 60, 90] as const;
type Period = (typeof PERIODS)[number];

export function HealthTimeline({ email }: HealthTimelineProps) {
  const [days, setDays] = useState<Period>(30);

  const { data, isLoading } = useQuery({
    queryKey: ['customer-history', email, days],
    queryFn: () => customersAPI.getHistory(email, days),
    staleTime: 5 * 60 * 1000,
  });

  const chartData =
    data?.history.map((entry) => ({
      date: new Date(entry.recorded_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      score: entry.health_score,
    })) ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">Health Score Over Time</span>
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
        <div className="h-48 flex items-center justify-center text-muted-foreground text-sm">
          Loading...
        </div>
      ) : chartData.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-center px-4">
          <p className="text-muted-foreground text-sm">
            Not enough history yet. Score history builds as feedback is analyzed.
          </p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" />
            <Tooltip />
            <ReferenceLine y={70} stroke="var(--chart-5)" strokeDasharray="4 4" />
            <ReferenceLine y={30} stroke="var(--destructive)" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="score"
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
