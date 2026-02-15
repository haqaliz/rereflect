'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { dashboardAPI, DashboardData } from '@/lib/api/dashboard';
import { anomaliesAPI, SentimentAnomaly } from '@/lib/api/anomalies';
import { insightsAPI, WeeklyInsight } from '@/lib/api/insights';
import { analytics } from '@/lib/analytics';
import { StatCard } from '@/components/StatCard';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
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
  Clock,
  UserX,
  ShieldAlert,
  DatabaseZap,
  CreditCard,
  ServerCrash,
  KeyRound,
  CircleX,
  Gauge,
  MousePointerClick,
  Laptop,
  PackageX,
  FileQuestion,
  Paintbrush,
  Boxes,
  Workflow,
  Plug,
  BarChart3,
  Settings2,
  Users,
  ArrowUpDown,
  Smartphone,
  Bell,
  Palette,
  Siren,
  Flame,
  Database,
  Lock,
  Bug,
  Receipt,
  Shield,
  Star,
  HeartPulse,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import Link from 'next/link';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, Pie, PieChart, Sector } from 'recharts';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartConfig } from '@/components/ui/chart';
import {
  getPainPointLabel,
  getFeatureRequestLabel,
  getUrgentLabel
} from '@/lib/category-utils';
import { DashboardSkeleton } from '@/components/shared/page-skeletons';

export default function DashboardPage() {
  const router = useRouter();
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [dismissingAnomaly, setDismissingAnomaly] = useState<number | null>(null);
  const [expandedCustomer, setExpandedCustomer] = useState<string | null>(null);

  // Fetch dashboard data with React Query
  const {
    data,
    isLoading: loading,
    error: queryError,
  } = useQuery({
    queryKey: ['dashboard', 30],
    queryFn: async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        router.push('/login');
        throw new Error('No token');
      }
      analytics.dashboardViewed();
      return await dashboardAPI.get(30);
    },
    staleTime: 5 * 60 * 1000, // 5 min
    gcTime: 30 * 60 * 1000, // 30 min
  });

  // Fetch anomalies with React Query
  const { data: anomalyData } = useQuery({
    queryKey: ['anomalies', false],
    queryFn: () => anomaliesAPI.list(false).catch(() => ({ items: [], total: 0 })),
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
  });

  // Fetch weekly insights with React Query
  const { data: weeklyInsight } = useQuery({
    queryKey: ['insights', 'weekly'],
    queryFn: () => insightsAPI.getLatest().catch(() => null),
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
  });

  const anomalies = anomalyData?.items || [];
  const error = queryError ? 'Failed to load dashboard data' : '';

  // Theme-aligned chart colors (Sunset Horizon palette)
  // chart-2: warm amber/gold, chart-3: soft peach, destructive: coral red
  const totalFeedback = data ? data.sentiment.positive_count + data.sentiment.neutral_count + data.sentiment.negative_count : 0;
  const sentimentChartData = data ? [
    {
      sentiment: 'positive',
      count: data.sentiment.positive_count,
      fill: 'var(--chart-2)',
      percentage: totalFeedback > 0 ? Math.round((data.sentiment.positive_count / totalFeedback) * 100) : 0
    },
    {
      sentiment: 'neutral',
      count: data.sentiment.neutral_count,
      fill: 'var(--chart-3)',
      percentage: totalFeedback > 0 ? Math.round((data.sentiment.neutral_count / totalFeedback) * 100) : 0
    },
    {
      sentiment: 'negative',
      count: data.sentiment.negative_count,
      fill: 'var(--destructive)',
      percentage: totalFeedback > 0 ? Math.round((data.sentiment.negative_count / totalFeedback) * 100) : 0
    }
  ] : [];

  // Custom active shape for pie chart when a slice is selected
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

  const sentimentChartConfig = {
    count: {
      label: "Count",
    },
    positive: {
      label: "Positive",
      color: "var(--chart-2)",
    },
    neutral: {
      label: "Neutral",
      color: "var(--chart-3)",
    },
    negative: {
      label: "Negative",
      color: "var(--destructive)",
    },
  } satisfies ChartConfig;

  // Aggregate pain point categories for the chart
  const painPointCategoriesChartData = data?.pain_point_categories?.slice(0, 6).map(cat => ({
    category: getPainPointLabel(cat.category),
    count: cat.count,
    severity: cat.severity
  })) || [];

  // Using chart-1 (primary coral) for pain points bar chart
  const painPointsChartConfig = {
    count: {
      label: "Count",
      color: "var(--chart-1)",
    },
  } satisfies ChartConfig;

  // Helper function to get pain point category icon
  const getPainPointCategoryIcon = (category: string) => {
    const iconMap: Record<string, React.ReactNode> = {
      'security_breach': <ShieldAlert className="w-3.5 h-3.5" />,
      'data_loss': <DatabaseZap className="w-3.5 h-3.5" />,
      'payment_issue': <CreditCard className="w-3.5 h-3.5" />,
      'system_crash': <ServerCrash className="w-3.5 h-3.5" />,
      'authentication': <KeyRound className="w-3.5 h-3.5" />,
      'functionality_broken': <CircleX className="w-3.5 h-3.5" />,
      'performance': <Gauge className="w-3.5 h-3.5" />,
      'usability': <MousePointerClick className="w-3.5 h-3.5" />,
      'compatibility': <Laptop className="w-3.5 h-3.5" />,
      'missing_feature': <PackageX className="w-3.5 h-3.5" />,
      'documentation': <FileQuestion className="w-3.5 h-3.5" />,
      'cosmetic': <Paintbrush className="w-3.5 h-3.5" />,
    };
    return iconMap[category] || <AlertTriangle className="w-3.5 h-3.5" />;
  };

  // Helper function to get feature request category icon
  const getFeatureRequestCategoryIcon = (category: string) => {
    const iconMap: Record<string, React.ReactNode> = {
      'core_functionality': <Boxes className="w-3.5 h-3.5" />,
      'automation': <Workflow className="w-3.5 h-3.5" />,
      'integration': <Plug className="w-3.5 h-3.5" />,
      'reporting': <BarChart3 className="w-3.5 h-3.5" />,
      'customization': <Settings2 className="w-3.5 h-3.5" />,
      'collaboration': <Users className="w-3.5 h-3.5" />,
      'export_import': <ArrowUpDown className="w-3.5 h-3.5" />,
      'mobile': <Smartphone className="w-3.5 h-3.5" />,
      'notifications': <Bell className="w-3.5 h-3.5" />,
      'ui_enhancement': <Palette className="w-3.5 h-3.5" />,
    };
    return iconMap[category] || <Lightbulb className="w-3.5 h-3.5" />;
  };

  // Helper function to get urgent category icon
  const getUrgentCategoryIcon = (category: string) => {
    const iconMap: Record<string, React.ReactNode> = {
      'service_outage': <Siren className="w-3.5 h-3.5" />,
      'data_breach': <ShieldAlert className="w-3.5 h-3.5" />,
      'payment_failure': <CreditCard className="w-3.5 h-3.5" />,
      'data_corruption': <Database className="w-3.5 h-3.5" />,
      'account_locked': <Lock className="w-3.5 h-3.5" />,
      'critical_bug': <Bug className="w-3.5 h-3.5" />,
      'billing_dispute': <Receipt className="w-3.5 h-3.5" />,
      'churn_risk': <UserX className="w-3.5 h-3.5" />,
      'compliance': <Shield className="w-3.5 h-3.5" />,
      'reputation_risk': <Star className="w-3.5 h-3.5" />,
    };
    return iconMap[category] || <CircleAlert className="w-3.5 h-3.5" />;
  };

  if (loading) {
    return <DashboardSkeleton />;
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

  const handleDismissAnomaly = async (anomalyId: number) => {
    setDismissingAnomaly(anomalyId);
    try {
      await anomaliesAPI.resolve(anomalyId);
      // Note: React Query will auto-refetch when window regains focus
      // Could also use queryClient.invalidateQueries(['anomalies']) for immediate update
    } catch (err) {
      console.error('Failed to dismiss anomaly:', err);
    } finally {
      setDismissingAnomaly(null);
    }
  };

  return (
    <div className="min-h-screen pattern-bg">
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

        {/* Anomaly Alert Banners */}
        {anomalies.length > 0 && (
          <div className="space-y-3 animate-fade-in">
            {anomalies.map((anomaly) => {
              const isCritical = anomaly.severity === 'critical';
              const borderColor = isCritical ? 'var(--destructive)' : 'var(--chart-2)';
              const bgColor = isCritical
                ? 'color-mix(in oklch, var(--destructive) 10%, var(--card))'
                : 'color-mix(in oklch, var(--chart-2) 10%, var(--card))';

              return (
                <div
                  key={anomaly.id}
                  className="rounded-xl p-4 border-2 flex items-center justify-between"
                  style={{ backgroundColor: bgColor, borderColor }}
                >
                  <div className="flex items-center space-x-3">
                    <div
                      className="p-2 rounded-lg"
                      style={{ backgroundColor: `color-mix(in oklch, ${borderColor} 20%, transparent)` }}
                    >
                      <AlertTriangle className="w-5 h-5" style={{ color: borderColor }} />
                    </div>
                    <div>
                      <p className="font-semibold text-foreground">
                        {isCritical ? 'Critical' : 'Warning'}: Negative Sentiment Spike Detected
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {anomaly.current_negative_pct.toFixed(0)}% negative sentiment vs {anomaly.baseline_negative_pct.toFixed(0)}% baseline
                        {' '}(+{anomaly.deviation_pct.toFixed(0)}pp) — based on {anomaly.feedback_count} feedback items in the last {anomaly.time_window_hours}h
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDismissAnomaly(anomaly.id)}
                    disabled={dismissingAnomaly === anomaly.id}
                    className="ml-4 px-3 py-1.5 text-sm font-medium rounded-lg border transition-colors hover:bg-secondary flex-shrink-0"
                    style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
                  >
                    {dismissingAnomaly === anomaly.id ? 'Dismissing...' : 'Dismiss'}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Stats Overview */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="animate-slide-up stagger-1">
            <StatCard
              title="Total Feedback"
              value={data?.total_feedback || 0}
              icon={MessageSquare}
              color="blue"
              href="/feedbacks"
            />
          </div>
          <div className="animate-slide-up stagger-2">
            <StatCard
              title="Positive"
              value={data?.sentiment.positive_count || 0}
              icon={Smile}
              color="green"
              href="/feedbacks?sentiment=positive"
            />
          </div>
          <div className="animate-slide-up stagger-3">
            <StatCard
              title="Neutral"
              value={data?.sentiment.neutral_count || 0}
              icon={Meh}
              color="yellow"
              href="/feedbacks?sentiment=neutral"
            />
          </div>
          <div className="animate-slide-up stagger-4">
            <StatCard
              title="Negative"
              value={data?.sentiment.negative_count || 0}
              icon={Frown}
              color="red"
              href="/feedbacks?sentiment=negative"
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
                  <div className="p-2.5 bg-secondary rounded-xl">
                    <TrendingUp className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle>Sentiment Distribution</CardTitle>
                    <p className="text-xs text-muted-foreground mt-0.5">Customer satisfaction overview</p>
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
                          <ChartTooltip
                            cursor={false}
                            content={<ChartTooltipContent hideLabel formatter={(value, name, props) => {
                              const item = props.payload;
                              return `${value} (${item.percentage}%)`;
                            }} />}
                          />
                          <Pie
                            data={sentimentChartData}
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
                            {sentimentChartData.map((entry, index) => (
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

                    {/* Legend with Stats */}
                    <div className="flex-1 space-y-3 min-w-0">
                      <div className="mb-4">
                        <p className="text-2xl font-bold font-mono text-text-primary">
                          {totalFeedback}
                        </p>
                        <p className="text-xs text-text-tertiary uppercase tracking-wide">Total Feedback</p>
                      </div>

                      {sentimentChartData.map((item, index) => {
                        // Use inline styles with CSS variables for consistent colors across light/dark modes
                        const chartColor = item.sentiment === 'positive' ? 'var(--chart-2)' :
                                          item.sentiment === 'negative' ? 'var(--destructive)' :
                                          'var(--chart-3)';
                        const isActive = activeIndex === index;
                        const isInactive = activeIndex !== null && activeIndex !== index;

                        return (
                          <div
                            key={item.sentiment}
                            className={`group flex justify-between items-center p-4 rounded-xl transition-all duration-200 cursor-pointer border ${
                              isActive
                                ? 'scale-[1.02] shadow-md'
                                : isInactive
                                ? 'opacity-50'
                                : ''
                            }`}
                            style={{
                              backgroundColor: isActive
                                ? `color-mix(in oklch, ${chartColor} 15%, var(--muted))`
                                : 'color-mix(in oklch, var(--muted) 50%, transparent)',
                              borderColor: isActive ? chartColor : 'var(--border)',
                            }}
                            onMouseEnter={() => setActiveIndex(index)}
                            onMouseLeave={() => setActiveIndex(null)}
                            onClick={() => {
                              const sentimentMap: Record<string, string> = {
                                positive: 'positive',
                                neutral: 'neutral',
                                negative: 'negative',
                              };
                              router.push(`/feedbacks?sentiment=${sentimentMap[item.sentiment]}`);
                            }}
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
                  <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary min-h-[450px]">
                    <Meh className="w-16 h-16 mb-3 opacity-30" />
                    <p className="text-sm">No sentiment data available yet</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Top Pain Points Chart - By Category */}
          <div className="animate-slide-up stagger-6">
            <Card className="h-full flex flex-col">
              <CardHeader className="border-b border-border">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 bg-secondary rounded-xl">
                    <AlertTriangle className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle>Pain Points by Category</CardTitle>
                    <p className="text-xs text-muted-foreground mt-0.5">Issues grouped by type</p>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col p-4">
                {painPointCategoriesChartData.length > 0 ? (
                  <ChartContainer config={painPointsChartConfig} className="h-full min-h-[450px]">
                    <BarChart
                      data={painPointCategoriesChartData}
                      margin={{ top: 20, right: 10, left: 10, bottom: 80 }}
                    >
                      <CartesianGrid vertical={false} strokeDasharray="3 3" />
                      <XAxis
                        dataKey="category"
                        angle={-45}
                        textAnchor="end"
                        height={80}
                        interval={0}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 11 }}
                      />
                      <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                      <ChartTooltip
                        content={<ChartTooltipContent />}
                        cursor={{ fill: 'var(--muted)', opacity: 0.3 }}
                      />
                      <Bar
                        dataKey="count"
                        fill="var(--chart-1)"
                        radius={[8, 8, 0, 0]}
                        maxBarSize={60}
                      />
                    </BarChart>
                  </ChartContainer>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-text-tertiary min-h-[450px]">
                    <AlertTriangle className="w-16 h-16 mb-3 opacity-30" />
                    <p className="text-sm">No pain point categories identified yet</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Pain Points and Feature Requests */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Pain Points List - By Category */}
          <Card>
            <CardHeader className="border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 bg-secondary rounded-xl">
                    <AlertTriangle className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle>Pain Points</CardTitle>
                    <p className="text-xs text-muted-foreground mt-0.5">Issues by category</p>
                  </div>
                </div>
                {data?.pain_point_categories && data.pain_point_categories.length > 0 && (
                  <Link
                    href="/pain-points"
                    className="flex items-center space-x-1 text-sm text-primary hover:text-primary/80 font-medium transition-colors group"
                  >
                    <span>View All</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </Link>
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-6">
              {data?.pain_point_categories && data.pain_point_categories.length > 0 ? (
                <ul className="space-y-3">
                  {data.pain_point_categories.slice(0, 5).map((cat, index) => {
                    const chartColor = 'var(--chart-1)';
                    return (
                      <li
                        key={index}
                        className="group flex justify-between items-center p-4 rounded-xl transition-all duration-200 cursor-pointer border hover:scale-[1.02] hover:shadow-md"
                        style={{
                          backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                          borderColor: 'var(--border)',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = `color-mix(in oklch, ${chartColor} 15%, var(--muted))`;
                          e.currentTarget.style.borderColor = chartColor;
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = 'color-mix(in oklch, var(--muted) 50%, transparent)';
                          e.currentTarget.style.borderColor = 'var(--border)';
                        }}
                        onClick={() => router.push('/pain-points')}
                      >
                        <div className="flex items-center gap-3">
                          <span style={{ color: chartColor }}>
                            {getPainPointCategoryIcon(cat.category)}
                          </span>
                          <span className="text-foreground font-medium text-sm">
                            {getPainPointLabel(cat.category)}
                          </span>
                        </div>
                        <span
                          className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0"
                          style={{
                            backgroundColor: 'color-mix(in oklch, var(--chart-1) 20%, transparent)',
                            color: 'var(--chart-1)',
                          }}
                        >
                          {cat.count}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-20" />
                  <p className="text-sm">No pain points identified yet</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Feature Requests List - By Category */}
          <Card>
            <CardHeader className="border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 bg-secondary rounded-xl">
                    <Lightbulb className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle>Feature Requests</CardTitle>
                    <p className="text-xs text-muted-foreground mt-0.5">Requests by category</p>
                  </div>
                </div>
                {data?.feature_request_categories && data.feature_request_categories.length > 0 && (
                  <Link
                    href="/feature-requests"
                    className="flex items-center space-x-1 text-sm text-primary hover:text-primary/80 font-medium transition-colors group"
                  >
                    <span>View All</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </Link>
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-6">
              {data?.feature_request_categories && data.feature_request_categories.length > 0 ? (
                <ul className="space-y-3">
                  {data.feature_request_categories.slice(0, 5).map((cat, index) => {
                    const chartColor = 'var(--chart-2)';
                    return (
                      <li
                        key={index}
                        className="group flex justify-between items-center p-4 rounded-xl transition-all duration-200 cursor-pointer border hover:scale-[1.02] hover:shadow-md"
                        style={{
                          backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                          borderColor: 'var(--border)',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = `color-mix(in oklch, ${chartColor} 15%, var(--muted))`;
                          e.currentTarget.style.borderColor = chartColor;
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = 'color-mix(in oklch, var(--muted) 50%, transparent)';
                          e.currentTarget.style.borderColor = 'var(--border)';
                        }}
                        onClick={() => router.push('/feature-requests')}
                      >
                        <div className="flex items-center gap-3">
                          <span style={{ color: chartColor }}>
                            {getFeatureRequestCategoryIcon(cat.category)}
                          </span>
                          <span className="text-foreground font-medium text-sm">
                            {getFeatureRequestLabel(cat.category)}
                          </span>
                        </div>
                        <span
                          className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0"
                          style={{
                            backgroundColor: 'color-mix(in oklch, var(--chart-2) 20%, transparent)',
                            color: 'var(--chart-2)',
                          }}
                        >
                          {cat.count}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
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
              <div className="p-2.5 bg-secondary rounded-xl">
                <Tag className="w-5 h-5 text-secondary-foreground" />
              </div>
              <div>
                <CardTitle>Top Categories</CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">Most common feedback tags</p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {data?.top_categories && data.top_categories.length > 0 ? (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                {data.top_categories.map((category, index) => {
                  // Use all 10 chart colors from theme for variety
                  const chartColors = [
                    'var(--chart-1)',
                    'var(--chart-2)',
                    'var(--chart-3)',
                    'var(--chart-4)',
                    'var(--chart-5)',
                    'var(--chart-6)',
                    'var(--chart-7)',
                    'var(--chart-8)',
                    'var(--chart-9)',
                    'var(--chart-10)',
                  ];
                  const color = chartColors[index % chartColors.length];

                  const getDisplayName = (tag: string): string => {
                    const displayNames: Record<string, string> = {
                      'bug': 'Bug',
                      'performance': 'Performance',
                      'ui-ux': 'UI/UX',
                      'feature-request': 'Feature Request',
                      'mobile': 'Mobile',
                      'web': 'Web',
                      'security': 'Security',
                      'pricing': 'Pricing',
                      'support': 'Support',
                      'documentation': 'Documentation',
                      'integration': 'Integration',
                      'data': 'Data',
                      'notification': 'Notification',
                      'search': 'Search',
                      'accessibility': 'Accessibility',
                    };
                    return displayNames[tag] || tag;
                  };

                  return (
                    <Link
                      key={category.tag}
                      href={`/categories/${category.tag}`}
                      className="group relative p-5 rounded-2xl surface-raised border-2 border-border hover:shadow-md hover:scale-[1.02] transition-all duration-200 cursor-pointer block overflow-hidden"
                      style={{
                        '--category-color': color,
                      } as React.CSSProperties}
                    >
                      <div
                        className="absolute inset-0 opacity-0 group-hover:opacity-10 transition-opacity"
                        style={{ backgroundColor: color }}
                      />
                      <div
                        className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl"
                        style={{ backgroundColor: color }}
                      />
                      <div className="relative">
                        <div
                          className="text-3xl font-bold mb-1 font-mono"
                          style={{ color: color }}
                        >
                          {category.count}
                        </div>
                        <div className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                          {getDisplayName(category.tag)}
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                <Tag className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">No categories found yet</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Urgent Feedback - By Category */}
        <Card>
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 bg-secondary rounded-xl">
                  <CircleAlert className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Urgent Feedback</CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">Urgent issues by category</p>
                </div>
              </div>
              {data?.urgent_categories && data.urgent_categories.length > 0 && (
                <Link
                  href="/urgent-feedbacks"
                  className="flex items-center space-x-1 text-sm text-primary hover:text-primary/80 font-medium transition-colors group"
                >
                  <span>View All</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </Link>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {data?.urgent_categories && data.urgent_categories.length > 0 ? (
              <ul className="space-y-3">
                {data.urgent_categories.slice(0, 5).map((cat, index) => {
                  const chartColor = 'var(--destructive)';
                  return (
                    <li
                      key={index}
                      className="group flex justify-between items-center p-4 rounded-xl transition-all duration-200 cursor-pointer border hover:scale-[1.02] hover:shadow-md"
                      style={{
                        backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                        borderColor: 'var(--border)',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = `color-mix(in oklch, ${chartColor} 15%, var(--muted))`;
                        e.currentTarget.style.borderColor = chartColor;
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'color-mix(in oklch, var(--muted) 50%, transparent)';
                        e.currentTarget.style.borderColor = 'var(--border)';
                      }}
                      onClick={() => router.push('/urgent-feedbacks')}
                    >
                      <div className="flex items-center gap-3">
                        <span style={{ color: chartColor }}>
                          {getUrgentCategoryIcon(cat.category)}
                        </span>
                        <span className="text-foreground font-medium text-sm">
                          {getUrgentLabel(cat.category)}
                        </span>
                      </div>
                      <span
                        className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono transition-colors ml-3 flex-shrink-0"
                        style={{
                          backgroundColor: 'color-mix(in oklch, var(--destructive) 20%, transparent)',
                          color: 'var(--destructive)',
                        }}
                      >
                        {cat.count}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">No urgent feedback at the moment</p>
                <p className="text-xs mt-1">Great job keeping up!</p>
              </div>
            )}
          </CardContent>
        </Card>
        {/* Churn Risk Summary */}
        <Card>
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 bg-secondary rounded-xl">
                  <UserX className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Churn Risk</CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">Customers at risk of leaving</p>
                </div>
              </div>
              {data?.churn_risk_summary && data.churn_risk_summary.total_at_risk > 0 && (
                <Link
                  href="/churn-risks"
                  className="flex items-center space-x-1 text-sm text-primary hover:text-primary/80 font-medium transition-colors group"
                >
                  <span>View All</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </Link>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {data?.churn_risk_summary && (data.churn_risk_summary.high_count > 0 || data.churn_risk_summary.medium_count > 0) ? (
              <div className="space-y-6">
                {/* Risk Level Counts */}
                <div className="grid grid-cols-3 gap-4">
                  <div
                    className="rounded-xl p-5 text-center border-2"
                    style={{
                      backgroundColor: 'color-mix(in oklch, var(--destructive) 10%, transparent)',
                      borderColor: 'color-mix(in oklch, var(--destructive) 25%, transparent)',
                    }}
                  >
                    <p className="text-3xl font-bold font-mono text-destructive">{data.churn_risk_summary.high_count}</p>
                    <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">High Risk</p>
                  </div>
                  <div
                    className="rounded-xl p-5 text-center border-2"
                    style={{
                      backgroundColor: 'color-mix(in oklch, var(--chart-2) 10%, transparent)',
                      borderColor: 'color-mix(in oklch, var(--chart-2) 25%, transparent)',
                    }}
                  >
                    <p className="text-3xl font-bold font-mono" style={{ color: 'var(--chart-2)' }}>{data.churn_risk_summary.medium_count}</p>
                    <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">Medium Risk</p>
                  </div>
                  <div
                    className="rounded-xl p-5 text-center border-2"
                    style={{
                      backgroundColor: 'color-mix(in oklch, var(--chart-5) 10%, transparent)',
                      borderColor: 'color-mix(in oklch, var(--chart-5) 25%, transparent)',
                    }}
                  >
                    <p className="text-3xl font-bold font-mono" style={{ color: 'var(--chart-5)' }}>{data.churn_risk_summary.low_count}</p>
                    <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">Low Risk</p>
                  </div>
                </div>

                {/* Top Churn Risks */}
                {data.top_churn_risks && data.top_churn_risks.length > 0 && (
                  <ul className="space-y-3">
                    {data.top_churn_risks.map((item) => {
                      const riskColor = item.churn_risk_score > 70 ? 'var(--destructive)' :
                                        item.churn_risk_score >= 40 ? 'var(--chart-2)' :
                                        'var(--chart-5)';
                      return (
                        <li
                          key={item.id}
                          className="group flex justify-between items-start p-4 rounded-xl transition-all duration-200 cursor-pointer border hover:scale-[1.01] hover:shadow-md"
                          style={{
                            backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                            borderColor: 'var(--border)',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.backgroundColor = `color-mix(in oklch, ${riskColor} 10%, var(--muted))`;
                            e.currentTarget.style.borderColor = riskColor;
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.backgroundColor = 'color-mix(in oklch, var(--muted) 50%, transparent)';
                            e.currentTarget.style.borderColor = 'var(--border)';
                          }}
                          onClick={() => router.push(`/feedbacks/${item.id}`)}
                        >
                          <div className="flex-1 min-w-0 mr-4">
                            <p className="text-sm text-foreground line-clamp-2 leading-relaxed">{item.text}</p>
                            {item.suggested_action && (
                              <p className="text-xs text-muted-foreground mt-1.5 flex items-start gap-1.5">
                                <Lightbulb className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color: 'var(--chart-2)' }} />
                                <span className="line-clamp-1">{item.suggested_action}</span>
                              </p>
                            )}
                          </div>
                          <span
                            className="px-3 py-1.5 text-sm font-bold rounded-lg font-mono flex-shrink-0"
                            style={{
                              backgroundColor: `color-mix(in oklch, ${riskColor} 20%, transparent)`,
                              color: riskColor,
                            }}
                          >
                            {item.churn_risk_score}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                <UserX className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">No churn risk data available yet</p>
                <p className="text-xs mt-1">Churn risk scores are generated during feedback analysis</p>
              </div>
            )}
          </CardContent>
        </Card>
        {/* At-Risk Customers */}
        {data?.at_risk_customers && data.at_risk_customers.length > 0 && (
          <Card>
            <CardHeader className="border-b border-border">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 bg-secondary rounded-xl">
                  <HeartPulse className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>At-Risk Customers</CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">Customers with lowest health scores</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="space-y-3">
                {data.at_risk_customers.map((customer) => {
                  const healthColor = customer.health_score >= 70 ? 'var(--chart-5)' :
                                     customer.health_score >= 50 ? 'var(--chart-2)' :
                                     customer.health_score >= 30 ? 'var(--chart-1)' :
                                     'var(--destructive)';
                  const isExpanded = expandedCustomer === customer.customer_email;

                  return (
                    <div
                      key={customer.customer_email}
                      className="rounded-xl border transition-all duration-200"
                      style={{
                        backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                        borderColor: isExpanded ? healthColor : 'var(--border)',
                      }}
                    >
                      <div
                        className="flex items-center justify-between p-4 cursor-pointer hover:scale-[1.01] transition-transform"
                        onClick={() => setExpandedCustomer(isExpanded ? null : customer.customer_email)}
                      >
                        <div className="flex items-center gap-3 min-w-0 flex-1">
                          <span
                            className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold font-mono flex-shrink-0"
                            style={{
                              backgroundColor: `color-mix(in oklch, ${healthColor} 20%, transparent)`,
                              color: healthColor,
                            }}
                          >
                            {customer.health_score}
                          </span>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-foreground truncate">
                              {customer.customer_name || customer.customer_email}
                            </p>
                            {customer.customer_name && (
                              <p className="text-xs text-muted-foreground truncate">{customer.customer_email}</p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-3 flex-shrink-0 ml-3">
                          <span
                            className="px-2 py-0.5 text-xs font-semibold rounded-md capitalize"
                            style={{
                              backgroundColor: `color-mix(in oklch, ${healthColor} 15%, transparent)`,
                              color: healthColor,
                            }}
                          >
                            {customer.risk_level.replace('_', ' ')}
                          </span>
                          <span className="text-xs text-muted-foreground font-mono">
                            {customer.feedback_count} feedback{customer.feedback_count !== 1 ? 's' : ''}
                          </span>
                          {isExpanded ? (
                            <ChevronUp className="w-4 h-4 text-muted-foreground" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-muted-foreground" />
                          )}
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="px-4 pb-4 border-t" style={{ borderColor: 'var(--border)' }}>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
                            <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--muted) 70%, transparent)' }}>
                              <p className="text-xs text-muted-foreground">Churn Risk</p>
                              <p className="text-sm font-bold font-mono text-foreground">{customer.churn_risk_component}</p>
                            </div>
                            <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--muted) 70%, transparent)' }}>
                              <p className="text-xs text-muted-foreground">Sentiment</p>
                              <p className="text-sm font-bold font-mono text-foreground">{customer.sentiment_component}</p>
                            </div>
                            <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--muted) 70%, transparent)' }}>
                              <p className="text-xs text-muted-foreground">Resolution</p>
                              <p className="text-sm font-bold font-mono text-foreground">{customer.resolution_component}</p>
                            </div>
                            <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--muted) 70%, transparent)' }}>
                              <p className="text-xs text-muted-foreground">Frequency</p>
                              <p className="text-sm font-bold font-mono text-foreground">{customer.frequency_component}</p>
                            </div>
                          </div>
                          {customer.llm_analysis && (
                            <div className="mt-3 p-3 rounded-lg" style={{ backgroundColor: 'color-mix(in oklch, var(--chart-4) 10%, transparent)' }}>
                              <p className="text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1.5">
                                <Lightbulb className="w-3.5 h-3.5" style={{ color: 'var(--chart-4)' }} />
                                AI Analysis
                              </p>
                              <p className="text-sm text-foreground leading-relaxed">{customer.llm_analysis}</p>
                            </div>
                          )}
                          <button
                            className="mt-3 text-sm font-medium flex items-center gap-1.5 transition-colors"
                            style={{ color: 'var(--primary)' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              router.push(`/feedbacks?search=${encodeURIComponent(customer.customer_email)}`);
                            }}
                          >
                            View feedback
                            <ArrowRight className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* AI Insights This Week */}
        <Card>
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 bg-secondary rounded-xl">
                <Lightbulb className="w-5 h-5 text-primary" />
              </div>
              <div>
                <CardTitle>AI Insights This Week</CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">AI-generated patterns and recommendations</p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {weeklyInsight && weeklyInsight.insights.length > 0 ? (
              <ul className="space-y-3">
                {weeklyInsight.insights.map((insight, index) => {
                  const categoryColorMap: Record<string, string> = {
                    pain_point: 'var(--destructive)',
                    churn_risk: 'var(--destructive)',
                    feature_request: 'var(--chart-2)',
                    positive_trend: 'var(--chart-5)',
                    opportunity: 'var(--chart-4)',
                  };
                  const priorityColorMap: Record<string, string> = {
                    high: 'var(--destructive)',
                    medium: 'var(--chart-2)',
                    low: 'var(--chart-5)',
                  };
                  const categoryColor = categoryColorMap[insight.category] || 'var(--chart-4)';
                  const priorityColor = priorityColorMap[insight.priority] || 'var(--chart-3)';
                  const categoryLabel = insight.category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

                  return (
                    <li
                      key={index}
                      className="p-4 rounded-xl border transition-all duration-200 hover:shadow-md"
                      style={{
                        backgroundColor: 'color-mix(in oklch, var(--muted) 50%, transparent)',
                        borderColor: 'var(--border)',
                      }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1.5">
                            <Lightbulb className="w-4 h-4 flex-shrink-0" style={{ color: categoryColor }} />
                            <p className="font-semibold text-sm text-foreground">{insight.title}</p>
                          </div>
                          <p className="text-sm text-muted-foreground leading-relaxed">{insight.description}</p>
                        </div>
                        <div className="flex flex-col gap-1.5 flex-shrink-0">
                          <span
                            className="px-2 py-0.5 text-xs font-semibold rounded-md text-center"
                            style={{
                              backgroundColor: `color-mix(in oklch, ${categoryColor} 15%, transparent)`,
                              color: categoryColor,
                            }}
                          >
                            {categoryLabel}
                          </span>
                          <span
                            className="px-2 py-0.5 text-xs font-semibold rounded-md text-center capitalize"
                            style={{
                              backgroundColor: `color-mix(in oklch, ${priorityColor} 15%, transparent)`,
                              color: priorityColor,
                            }}
                          >
                            {insight.priority}
                          </span>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                <Lightbulb className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">No AI insights available yet</p>
                <p className="text-xs mt-1">Insights are generated weekly from your feedback data</p>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
