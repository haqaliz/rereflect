'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { aiSettingsAPI, type AIUsage, type AIUsageDaily } from '@/lib/api/ai-settings';
import { Zap, DollarSign, Hash, GitBranch } from 'lucide-react';

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatNumber(n: number): string {
  return n.toLocaleString();
}

interface StatCardProps {
  title: string;
  value: string;
  icon: React.ReactNode;
}

function StatCard({ title, value, icon }: StatCardProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold text-foreground mt-1">{value}</p>
          </div>
          <div className="p-3 bg-secondary rounded-xl">
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function AISettingsUsage() {
  const [usage, setUsage] = useState<AIUsage | null>(null);
  const [daily, setDaily] = useState<AIUsageDaily | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      aiSettingsAPI.getUsage(),
      aiSettingsAPI.getUsageDaily(),
    ])
      .then(([usageData, dailyData]) => {
        setUsage(usageData);
        setDaily(dailyData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-32 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    );
  }

  if (!usage) return null;

  const chartData = daily?.days.map(d => ({
    date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    tokens: d.tokens,
    requests: d.requests,
  })) ?? [];

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Tokens"
          value={formatNumber(usage.total_tokens)}
          icon={<Zap className="w-5 h-5 text-primary" />}
        />
        <StatCard
          title="Estimated Cost"
          value={formatCents(usage.estimated_cost_cents)}
          icon={<DollarSign className="w-5 h-5 text-primary" />}
        />
        <StatCard
          title="Total Requests"
          value={formatNumber(usage.total_requests)}
          icon={<Hash className="w-5 h-5 text-primary" />}
        />
        <StatCard
          title={`${usage.fallback_count} fallback${usage.fallback_count !== 1 ? 's' : ''} this month`}
          value={String(usage.fallback_count)}
          icon={<GitBranch className="w-5 h-5 text-primary" />}
        />
      </div>

      {/* Daily Chart */}
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Daily Token Usage</CardTitle>
        </CardHeader>
        <CardContent className="pt-6">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12, fill: 'var(--muted-foreground)' }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 12, fill: 'var(--muted-foreground)' }}
                tickLine={false}
                axisLine={false}
                width={50}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--popover)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  color: 'var(--foreground)',
                }}
              />
              <Legend />
              <Bar dataKey="tokens" fill="var(--chart-1)" radius={[3, 3, 0, 0]} name="Tokens" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Provider Breakdown Table */}
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Provider Breakdown</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">Requests</TableHead>
                <TableHead className="text-right">Est. Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {usage.by_provider.map(p => (
                <TableRow key={p.provider}>
                  <TableCell className="font-medium capitalize">{p.provider}</TableCell>
                  <TableCell className="text-right">{formatNumber(p.tokens)}</TableCell>
                  <TableCell className="text-right">{formatNumber(p.requests)}</TableCell>
                  <TableCell className="text-right">{formatCents(p.cost_cents)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
