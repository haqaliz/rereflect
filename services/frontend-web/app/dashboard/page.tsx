'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { dashboardAPI, DashboardData } from '@/lib/api/dashboard';
import { StatCard } from '@/components/StatCard';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Header } from '@/components/Header';
import {
  MessageSquare,
  Smile,
  Meh,
  Frown,
  AlertTriangle,
  CircleAlert,
  Lightbulb,
  TrendingUp,
  Tag,
  ArrowRight,
  Clock
} from 'lucide-react';
import Link from 'next/link';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, Pie, PieChart } from 'recharts';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartConfig } from '@/components/ui/chart';

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
          return;
        }

        const dashboardData = await dashboardAPI.get(30);
        setData(dashboardData);
      } catch (err: any) {
        setError('Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router]);

  const sentimentChartData = data ? [
    { sentiment: 'positive', count: data.sentiment.positive_count, fill: '#10b981' },
    { sentiment: 'neutral', count: data.sentiment.neutral_count, fill: '#64748b' },
    { sentiment: 'negative', count: data.sentiment.negative_count, fill: '#ef4444' }
  ] : [];

  const sentimentChartConfig = {
    count: {
      label: "Count",
    },
    positive: {
      label: "Positive",
      color: "#059669",
    },
    neutral: {
      label: "Neutral",
      color: "#64748b",
    },
    negative: {
      label: "Negative",
      color: "#dc2626",
    },
  } satisfies ChartConfig;

  const painPointsChartData = data?.pain_points.slice(0, 5).map(point => ({
    issue: point.issue.length > 30 ? point.issue.substring(0, 30) + '...' : point.issue,
    count: point.count
  })) || [];

  const painPointsChartConfig = {
    count: {
      label: "Count",
      color: "#ea580c",
    },
  } satisfies ChartConfig;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-accent-amber-200 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-accent-amber-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-text-secondary font-medium">Loading your dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="surface-raised rounded-2xl p-8 max-w-md shadow-lg">
          <div className="flex items-start space-x-4">
            <div className="p-3 bg-error-bg rounded-xl">
              <AlertTriangle className="w-6 h-6 text-error-text" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-text-primary mb-1">Error Loading Dashboard</h3>
              <p className="text-text-secondary">{error}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <Header />

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Page Title */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-4xl font-bold text-text-primary">Dashboard</h2>
            <div className="flex items-center space-x-2 text-text-tertiary text-sm font-mono">
              <Clock className="w-4 h-4" />
              <span>{data?.date_range}</span>
            </div>
          </div>
          <p className="text-text-secondary text-lg">Real-time customer feedback analytics and insights</p>
        </div>

        {/* Stats Overview */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="animate-slide-up stagger-1">
            <StatCard
              title="Total Feedback"
              value={data?.total_feedback || 0}
              icon={MessageSquare}
              color="blue"
            />
          </div>
          <div className="animate-slide-up stagger-2">
            <StatCard
              title="Positive"
              value={data?.sentiment.positive_count || 0}
              icon={Smile}
              color="green"
            />
          </div>
          <div className="animate-slide-up stagger-3">
            <StatCard
              title="Neutral"
              value={data?.sentiment.neutral_count || 0}
              icon={Meh}
              color="yellow"
            />
          </div>
          <div className="animate-slide-up stagger-4">
            <StatCard
              title="Negative"
              value={data?.sentiment.negative_count || 0}
              icon={Frown}
              color="red"
            />
          </div>
        </div>

        {/* Charts Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Sentiment Distribution */}
          <div className="animate-slide-up stagger-5">
            <Card className="h-full flex flex-col">
              <CardHeader className="border-b border-border">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 bg-blue-100 dark:bg-blue-900/30 rounded-xl">
                    <TrendingUp className="w-5 h-5 text-blue-700 dark:text-blue-400" />
                  </div>
                  <div>
                    <CardTitle>Sentiment Distribution</CardTitle>
                    <p className="text-xs text-text-tertiary mt-0.5">Customer satisfaction overview</p>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col p-4">
                {sentimentChartData.some(d => d.count > 0) ? (
                  <div className="flex-1 flex flex-col lg:flex-row items-center gap-6">
                    {/* Chart */}
                    <div className="flex-shrink-0">
                      <ChartContainer config={sentimentChartConfig} className="mx-auto w-[240px] h-[240px]">
                        <PieChart>
                          <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
                          <Pie
                            data={sentimentChartData}
                            dataKey="count"
                            nameKey="sentiment"
                            innerRadius={70}
                            outerRadius={110}
                            strokeWidth={2}
                            stroke="hsl(var(--background))"
                          >
                            {sentimentChartData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.fill} />
                            ))}
                          </Pie>
                        </PieChart>
                      </ChartContainer>
                    </div>

                    {/* Legend with Stats */}
                    <div className="flex-1 space-y-3 min-w-0">
                      <div className="mb-4">
                        <p className="text-2xl font-bold font-mono text-text-primary">
                          {sentimentChartData.reduce((acc, d) => acc + d.count, 0)}
                        </p>
                        <p className="text-xs text-text-tertiary uppercase tracking-wide">Total Feedback</p>
                      </div>

                      {sentimentChartData.map((item) => {
                        const colorClass = item.sentiment === 'positive' ? 'text-emerald-700 dark:text-emerald-400' :
                                          item.sentiment === 'negative' ? 'text-red-700 dark:text-red-400' :
                                          'text-slate-600 dark:text-slate-400';
                        const badgeBg = item.sentiment === 'positive' ? 'bg-emerald-100 dark:bg-emerald-900/40 group-hover:bg-emerald-200 dark:group-hover:bg-emerald-800/50' :
                                       item.sentiment === 'negative' ? 'bg-red-100 dark:bg-red-900/40 group-hover:bg-red-200 dark:group-hover:bg-red-800/50' :
                                       'bg-slate-500/20 dark:bg-slate-500/30 group-hover:bg-slate-500/30 dark:group-hover:bg-slate-500/40';
                        const hoverBg = item.sentiment === 'positive' ? 'hover:bg-emerald-50 dark:hover:bg-emerald-900/20' :
                                       item.sentiment === 'negative' ? 'hover:bg-red-50 dark:hover:bg-red-900/20' :
                                       'hover:bg-slate-50 dark:hover:bg-slate-900/20';
                        const borderHover = item.sentiment === 'positive' ? 'hover:border-emerald-300 dark:hover:border-emerald-700' :
                                           item.sentiment === 'negative' ? 'hover:border-red-300 dark:hover:border-red-700' :
                                           'hover:border-slate-300 dark:hover:border-slate-700';

                        return (
                          <div key={item.sentiment} className={`group flex justify-between items-center p-4 bg-muted/50 dark:bg-muted/20 rounded-xl ${hoverBg} transition-all duration-200 cursor-pointer border border-border ${borderHover}`}>
                            <span className="text-text-primary font-medium text-sm capitalize truncate">
                              {item.sentiment}
                            </span>
                            <span className={`px-3 py-1.5 ${badgeBg} ${colorClass} text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0`}>
                              {item.count}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary min-h-[450px]">
                    <Meh className="w-16 h-16 mb-3 opacity-30" />
                    <p className="text-sm">No sentiment data available yet</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Top Pain Points Chart */}
          <div className="animate-slide-up stagger-6">
            <Card className="h-full flex flex-col">
              <CardHeader className="border-b border-border">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 bg-orange-100 dark:bg-orange-900/30 rounded-xl">
                    <AlertTriangle className="w-5 h-5 text-orange-700 dark:text-orange-400" />
                  </div>
                  <div>
                    <CardTitle>Top Pain Points</CardTitle>
                    <p className="text-xs text-text-tertiary mt-0.5">Most reported issues</p>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col p-4">
                {painPointsChartData.length > 0 ? (
                  <ChartContainer config={painPointsChartConfig} className="h-full min-h-[450px]">
                    <BarChart
                      data={painPointsChartData}
                      margin={{ top: 20, right: 10, left: 10, bottom: 100 }}
                    >
                      <CartesianGrid vertical={false} strokeDasharray="3 3" />
                      <XAxis
                        dataKey="issue"
                        angle={-45}
                        textAnchor="end"
                        height={100}
                        interval={0}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 10 }}
                        tickFormatter={(value) => {
                          // Truncate long labels
                          if (value.length > 20) {
                            return value.substring(0, 17) + '...';
                          }
                          return value;
                        }}
                      />
                      <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                      <ChartTooltip
                        content={<ChartTooltipContent />}
                        cursor={{ fill: 'hsl(var(--muted))', opacity: 0.3 }}
                      />
                      <Bar
                        dataKey="count"
                        fill="#ea580c"
                        radius={[8, 8, 0, 0]}
                        maxBarSize={60}
                      />
                    </BarChart>
                  </ChartContainer>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary min-h-[450px]">
                    <AlertTriangle className="w-16 h-16 mb-3 opacity-30" />
                    <p className="text-sm">No pain points identified yet</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Pain Points and Feature Requests */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Pain Points List */}
          <Card>
            <CardHeader className="border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 bg-orange-100 dark:bg-orange-900/30 rounded-xl">
                    <AlertTriangle className="w-5 h-5 text-orange-700 dark:text-orange-400" />
                  </div>
                  <div>
                    <CardTitle>Pain Points</CardTitle>
                    <p className="text-xs text-text-tertiary mt-0.5">Critical customer issues</p>
                  </div>
                </div>
                {data?.pain_points && data.pain_points.length > 0 && (
                  <Link
                    href="/pain-points"
                    className="flex items-center space-x-1 text-sm text-orange-600 dark:text-orange-400 hover:text-orange-700 dark:hover:text-orange-300 font-medium transition-colors group"
                  >
                    <span>View All</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </Link>
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-6">
              {data?.pain_points && data.pain_points.length > 0 ? (
                <ul className="space-y-2">
                  {data.pain_points.slice(0, 5).map((point, index) => (
                    <li
                      key={index}
                      className="group flex justify-between items-center p-4 bg-muted/50 dark:bg-muted/20 rounded-xl hover:bg-orange-50 dark:hover:bg-orange-900/20 transition-all duration-200 cursor-pointer border border-border hover:border-orange-300 dark:hover:border-orange-700"
                    >
                      <span className="text-text-primary font-medium text-sm line-clamp-1">{point.issue}</span>
                      <span className="px-3 py-1.5 bg-orange-100 dark:bg-orange-900/40 group-hover:bg-orange-200 dark:group-hover:bg-orange-800/50 text-orange-700 dark:text-orange-400 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0">
                        {point.count}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-center py-12 text-text-tertiary">
                  <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-20" />
                  <p className="text-sm">No pain points identified yet</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Feature Requests List */}
          <Card>
            <CardHeader className="border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 bg-emerald-100 dark:bg-emerald-900/30 rounded-xl">
                    <Lightbulb className="w-5 h-5 text-emerald-700 dark:text-emerald-400" />
                  </div>
                  <div>
                    <CardTitle>Feature Requests</CardTitle>
                    <p className="text-xs text-text-tertiary mt-0.5">Customer suggestions</p>
                  </div>
                </div>
                {data?.feature_requests && data.feature_requests.length > 0 && (
                  <Link
                    href="/feature-requests"
                    className="flex items-center space-x-1 text-sm text-success-text hover:opacity-80 font-medium transition-opacity group"
                  >
                    <span>View All</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </Link>
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-6">
              {data?.feature_requests && data.feature_requests.length > 0 ? (
                <ul className="space-y-2">
                  {data.feature_requests.slice(0, 5).map((request, index) => (
                    <li
                      key={index}
                      className="group flex justify-between items-center p-4 bg-muted/50 dark:bg-muted/20 rounded-xl hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-all duration-200 cursor-pointer border border-border hover:border-emerald-300 dark:hover:border-emerald-700"
                    >
                      <span className="text-text-primary font-medium text-sm line-clamp-1">{request.feature}</span>
                      <span className="px-3 py-1.5 bg-emerald-100 dark:bg-emerald-900/40 group-hover:bg-emerald-200 dark:group-hover:bg-emerald-800/50 text-emerald-700 dark:text-emerald-400 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0">
                        {request.count}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-center py-12 text-text-tertiary">
                  <Lightbulb className="w-12 h-12 mx-auto mb-3 opacity-20" />
                  <p className="text-sm">No feature requests identified yet</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Top Categories */}
        <Card>
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 bg-purple-100 dark:bg-purple-900/30 rounded-xl">
                <Tag className="w-5 h-5 text-purple-700 dark:text-purple-400" />
              </div>
              <div>
                <CardTitle>Top Categories</CardTitle>
                <p className="text-xs text-text-tertiary mt-0.5">Most common feedback tags</p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {data?.top_categories && data.top_categories.length > 0 ? (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                {data.top_categories.map((category) => {
                  const getTagStyles = (tag: string): { color: string; displayName: string } => {
                    const tagMap: Record<string, { color: string; displayName: string }> = {
                      'bug': { color: '#ef4444', displayName: 'Bug' },
                      'performance': { color: '#f97316', displayName: 'Performance' },
                      'ui-ux': { color: '#a855f7', displayName: 'UI/UX' },
                      'feature-request': { color: '#3b82f6', displayName: 'Feature Request' },
                      'mobile': { color: '#10b981', displayName: 'Mobile' },
                      'web': { color: '#6366f1', displayName: 'Web' },
                      'security': { color: '#eab308', displayName: 'Security' },
                      'pricing': { color: '#ec4899', displayName: 'Pricing' },
                      'support': { color: '#06b6d4', displayName: 'Support' },
                      'documentation': { color: '#6b7280', displayName: 'Documentation' },
                      'integration': { color: '#14b8a6', displayName: 'Integration' },
                      'data': { color: '#8b5cf6', displayName: 'Data' },
                      'notification': { color: '#f59e0b', displayName: 'Notification' },
                      'search': { color: '#84cc16', displayName: 'Search' },
                      'accessibility': { color: '#059669', displayName: 'Accessibility' },
                    };
                    return tagMap[tag] || { color: '#6b7280', displayName: tag };
                  };

                  const styles = getTagStyles(category.tag);

                  return (
                    <Link
                      key={category.tag}
                      href={`/categories/${category.tag}`}
                      className="group relative p-5 rounded-2xl surface-raised border-2 border-border hover:shadow-xl hover:scale-105 transition-all duration-300 cursor-pointer block overflow-hidden"
                      style={{
                        '--category-color': styles.color,
                      } as React.CSSProperties}
                    >
                      <div
                        className="absolute inset-0 opacity-0 group-hover:opacity-10 transition-opacity"
                        style={{ backgroundColor: styles.color }}
                      />
                      <div
                        className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl"
                        style={{ backgroundColor: styles.color }}
                      />
                      <div className="relative">
                        <div
                          className="text-3xl font-bold mb-1 font-mono"
                          style={{ color: styles.color }}
                        >
                          {category.count}
                        </div>
                        <div className="text-sm font-semibold text-text-secondary uppercase tracking-wide">
                          {styles.displayName}
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-12 text-text-tertiary">
                <Tag className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">No categories found yet</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Urgent Feedback */}
        <Card>
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 bg-red-100 dark:bg-red-900/30 rounded-xl">
                  <CircleAlert className="w-5 h-5 text-red-700 dark:text-red-400" />
                </div>
                <div>
                  <CardTitle>Urgent Feedback</CardTitle>
                  <p className="text-xs text-text-tertiary mt-0.5">Requires immediate attention</p>
                </div>
              </div>
              {data?.urgent_items && data.urgent_items.length > 0 && (
                <Link
                  href="/urgent-feedback"
                  className="flex items-center space-x-1 text-sm text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 font-medium transition-colors group"
                >
                  <span>View All</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </Link>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {data?.urgent_items && data.urgent_items.length > 0 ? (
              <ul className="space-y-2">
                {data.urgent_items.map((item) => (
                  <li
                    key={item.id}
                    className="group flex justify-between items-center p-4 bg-muted/50 dark:bg-muted/20 rounded-xl hover:bg-red-50 dark:hover:bg-red-900/20 transition-all duration-200 cursor-pointer border border-border hover:border-red-300 dark:hover:border-red-700"
                  >
                    <span className="text-text-primary font-medium text-sm line-clamp-1">{item.text}</span>
                    <span className="px-3 py-1.5 bg-red-100 dark:bg-red-900/40 group-hover:bg-red-200 dark:group-hover:bg-red-800/50 text-red-700 dark:text-red-400 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0">
                      {item.id}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-center py-12 text-text-tertiary">
                <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">No urgent feedback at the moment</p>
                <p className="text-xs mt-1">Great job keeping up!</p>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
