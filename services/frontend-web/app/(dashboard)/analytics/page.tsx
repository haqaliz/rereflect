'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import {
  analyticsAPI,
  type AnalyticsTrendsData,
  type DateRange,
} from '@/lib/api/analytics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Lock, TrendingUp, TrendingDown, Minus, ArrowRight, Download, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
} from '@/components/ui/dropdown-menu';
import Link from 'next/link';
import { SavedViewsBar } from '@/components/SavedViewsBar';
import { ShareAnalyticsDialog } from '@/components/ShareAnalyticsDialog';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
import {
  LineChart, Line, BarChart, Bar,
  PieChart, Pie, Cell, Sector,
  XAxis, YAxis, CartesianGrid,
} from 'recharts';

// ─── Constants ─────────────────────────────────────────────────

const METRIC_KEYS = ['sentiment', 'volume', 'urgency', 'painPoints', 'featureRequests'] as const;
type MetricKey = typeof METRIC_KEYS[number];

const METRIC_CONFIG: Record<MetricKey, { label: string; dataKey: string; color: string }> = {
  sentiment:       { label: 'Avg Sentiment',   dataKey: 'avg_sentiment_score', color: 'var(--chart-1)' },
  volume:          { label: 'Volume',           dataKey: 'feedback_count',      color: 'var(--chart-2)' },
  urgency:         { label: 'Urgent',           dataKey: 'urgent_count',        color: 'var(--chart-5)' },
  painPoints:      { label: 'Pain Points',      dataKey: 'pain_points_count',   color: 'var(--destructive)' },
  featureRequests: { label: 'Feature Requests', dataKey: 'feature_requests_count', color: 'var(--chart-3)' },
};

const SENTIMENT_COLORS = {
  positive: 'var(--chart-2)',
  neutral:  'var(--chart-3)',
  negative: 'var(--destructive)',
};

const SOURCE_COLORS = [
  'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)',
  'var(--chart-4)', 'var(--chart-5)',
];

const sentimentChartConfig = {
  value: { label: 'Count' },
  Positive: { label: 'Positive', color: 'var(--chart-2)' },
  Neutral: { label: 'Neutral', color: 'var(--chart-3)' },
  Negative: { label: 'Negative', color: 'var(--destructive)' },
} satisfies ChartConfig;

const sourceChartConfig = {
  value: { label: 'Count' },
} satisfies ChartConfig;

const volumeChartConfig = {
  feedback_count: { label: 'Feedback', color: 'var(--chart-1)' },
} satisfies ChartConfig;

const metricTrendsChartConfig = {
  avg_sentiment_score: { label: 'Avg Sentiment', color: 'var(--chart-1)' },
  feedback_count: { label: 'Volume', color: 'var(--chart-2)' },
  urgent_count: { label: 'Urgent', color: 'var(--chart-5)' },
  pain_points_count: { label: 'Pain Points', color: 'var(--destructive)' },
  feature_requests_count: { label: 'Feature Requests', color: 'var(--chart-3)' },
} satisfies ChartConfig;

// ─── Component ─────────────────────────────────────────────────

export default function AnalyticsPage() {
  const { user } = useAuth();
  const plan = user?.plan || 'free';

  const [dateRange, setDateRange] = useState<DateRange>('7d');
  const [data, setData] = useState<AnalyticsTrendsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeMetrics, setActiveMetrics] = useState<MetricKey[]>(['sentiment', 'volume']);
  const [donutTab, setDonutTab] = useState<'sentiment' | 'source'>('sentiment');
  const [exporting, setExporting] = useState(false);
  const [activeDonutIndex, setActiveDonutIndex] = useState<number | null>(null);
  const chartsRef = useRef<HTMLDivElement>(null);

  const canAccessRange = useCallback((range: DateRange) => {
    if (range === '7d') return true;
    return plan !== 'free';
  }, [plan]);

  const fetchData = useCallback(async (range: DateRange) => {
    if (!canAccessRange(range)) return;
    setLoading(true);
    setError(null);
    try {
      const result = await analyticsAPI.getTrends(range);
      setData(result);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status: number; data?: { detail?: { message?: string } } } };
      if (axiosErr.response?.status === 403) {
        setError(axiosErr.response.data?.detail?.message || 'Upgrade required');
      } else {
        setError('Failed to load analytics data');
      }
    } finally {
      setLoading(false);
    }
  }, [canAccessRange]);

  useEffect(() => { fetchData(dateRange); }, [dateRange, fetchData]);

  const handleRangeChange = (value: string) => {
    if (value && (value === '7d' || value === '30d' || value === '90d')) {
      setDateRange(value as DateRange);
    }
  };

  const handleExportPDF = async () => {
    if (!chartsRef.current || plan === 'free') return;
    setExporting(true);
    try {
      const { exportAnalyticsPDF } = await import('@/lib/pdf-export');
      await exportAnalyticsPDF(chartsRef.current, {
        title: 'Analytics Report',
        dateRange: data?.date_range || dateRange,
      });
    } catch (err) {
      console.error('PDF export failed:', err);
    } finally {
      setExporting(false);
    }
  };

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

  // ── Empty state ──
  if (!loading && data && data.total_feedback === 0) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Analytics</h1>
        </div>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-24 h-24 mb-6 rounded-full bg-muted flex items-center justify-center">
            <TrendingUp className="w-12 h-12 text-muted-foreground" />
          </div>
          <h2 className="text-xl font-semibold mb-2">No feedback data yet</h2>
          <p className="text-muted-foreground mb-6 max-w-md">
            Import feedback to start seeing analytics trends, sentiment breakdowns, and top insights.
          </p>
          <Link
            href="/feedbacks"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            Import Feedback <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    );
  }

  // Build donut data
  const sentimentDonutData = data ? [
    { name: 'Positive', value: data.sentiment_distribution.positive, fill: SENTIMENT_COLORS.positive },
    { name: 'Neutral', value: data.sentiment_distribution.neutral, fill: SENTIMENT_COLORS.neutral },
    { name: 'Negative', value: data.sentiment_distribution.negative, fill: SENTIMENT_COLORS.negative },
  ].filter(d => d.value > 0) : [];

  const sourceDonutData = data ? data.source_distribution.map((s, i) => ({
    name: s.source,
    value: s.count,
    fill: SOURCE_COLORS[i % SOURCE_COLORS.length],
  })) : [];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-2xl font-bold">Analytics</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportPDF}
            disabled={exporting || plan === 'free' || !data}
            title={plan === 'free' ? 'Upgrade to Pro to export PDF' : 'Export as PDF'}
          >
            <Download className="w-4 h-4 mr-1.5" />
            {exporting ? 'Exporting...' : 'Export PDF'}
            {plan === 'free' && <Lock className="w-3 h-3 ml-1 opacity-50" />}
          </Button>
          <ShareAnalyticsDialog
            disabled={plan === 'free'}
            disabledReason={plan === 'free' ? 'Upgrade to Pro to share dashboards' : undefined}
          />
          <Tabs value={dateRange} onValueChange={handleRangeChange}>
            <TabsList className="h-8">
              <TabsTrigger value="7d" className="text-xs px-2 h-6">7d</TabsTrigger>
              <TabsTrigger value="30d" disabled={!canAccessRange('30d')} className="text-xs px-2 h-6">
                30d {!canAccessRange('30d') && <Lock className="w-3 h-3 ml-0.5 opacity-50" />}
              </TabsTrigger>
              <TabsTrigger value="90d" disabled={!canAccessRange('90d')} className="text-xs px-2 h-6">
                90d {!canAccessRange('90d') && <Lock className="w-3 h-3 ml-0.5 opacity-50" />}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {/* Saved views bar */}
      <SavedViewsBar
        page="analytics"
        currentConfig={{ dateRange, activeMetrics, donutTab }}
        onApplyView={(config) => {
          if (config.dateRange) setDateRange(config.dateRange as DateRange);
          if (config.activeMetrics) setActiveMetrics(config.activeMetrics as MetricKey[]);
          if (config.donutTab) setDonutTab(config.donutTab as 'sentiment' | 'source');
        }}
      />

      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm">
          {error}
          {plan === 'free' && (
            <Link href="/settings/billing" className="ml-2 underline font-medium">
              Upgrade to Pro
            </Link>
          )}
        </div>
      )}

      {loading ? <LoadingSkeleton /> : data && (
        <>
          {/* Charts container (ref for PDF export) */}
          <div ref={chartsRef} className="space-y-6 pb-1">
          {/* Charts row 1: Line + Bar */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-medium">Metric Trends</CardTitle>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" size="sm" className="h-7 text-xs gap-1">
                        Metrics
                        <ChevronDown className="w-3 h-3 opacity-50" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-48">
                      {METRIC_KEYS.map(key => (
                        <DropdownMenuCheckboxItem
                          key={key}
                          checked={activeMetrics.includes(key)}
                          onCheckedChange={(checked) => {
                            if (checked) {
                              setActiveMetrics(prev => [...prev, key]);
                            } else {
                              setActiveMetrics(prev => prev.filter(k => k !== key));
                            }
                          }}
                          onSelect={(e) => e.preventDefault()}
                        >
                          <span className="w-2 h-2 rounded-full mr-1.5 shrink-0" style={{ backgroundColor: METRIC_CONFIG[key].color }} />
                          {METRIC_CONFIG[key].label}
                        </DropdownMenuCheckboxItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </CardHeader>
              <CardContent>
                <ChartContainer config={metricTrendsChartConfig} className="h-[300px] w-full">
                  <LineChart data={data.data_points}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} className="text-muted-foreground" />
                    <YAxis tick={{ fontSize: 12 }} className="text-muted-foreground" />
                    <ChartTooltip
                      cursor={false}
                      content={<ChartTooltipContent />}
                    />
                    {activeMetrics.map(key => (
                      <Line
                        key={key}
                        type="monotone"
                        dataKey={METRIC_CONFIG[key].dataKey}
                        name={METRIC_CONFIG[key].label}
                        stroke={METRIC_CONFIG[key].color}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                    ))}
                  </LineChart>
                </ChartContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-medium">Feedback Volume</CardTitle>
              </CardHeader>
              <CardContent>
                <ChartContainer config={volumeChartConfig} className="h-[300px] w-full">
                  <BarChart data={data.data_points}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} className="text-muted-foreground" />
                    <YAxis tick={{ fontSize: 12 }} className="text-muted-foreground" />
                    <ChartTooltip
                      cursor={false}
                      content={<ChartTooltipContent />}
                    />
                    <Bar dataKey="feedback_count" name="Feedback" fill="var(--chart-1)" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>
          </div>

          {/* Charts row 2: Donut + Table */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-medium">Distribution</CardTitle>
                  <Tabs value={donutTab} onValueChange={(v) => { setDonutTab(v as 'sentiment' | 'source'); setActiveDonutIndex(null); }}>
                    <TabsList className="h-8">
                      <TabsTrigger value="sentiment" className="text-xs px-2 h-6">Sentiment</TabsTrigger>
                      <TabsTrigger value="source" className="text-xs px-2 h-6">Source</TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>
              </CardHeader>
              <CardContent>
                <ChartContainer config={donutTab === 'sentiment' ? sentimentChartConfig : sourceChartConfig} className="h-[300px] w-full">
                  <PieChart>
                    <ChartTooltip
                      cursor={false}
                      content={<ChartTooltipContent hideLabel />}
                    />
                    <Pie
                      data={donutTab === 'sentiment' ? sentimentDonutData : sourceDonutData}
                      cx="50%" cy="50%"
                      innerRadius={70} outerRadius={110}
                      strokeWidth={2}
                      stroke="hsl(var(--background))"
                      dataKey="value"
                      nameKey="name"
                      activeIndex={activeDonutIndex !== null ? activeDonutIndex : undefined}
                      activeShape={renderActiveShape}
                      onMouseEnter={(_, index) => setActiveDonutIndex(index)}
                      onMouseLeave={() => setActiveDonutIndex(null)}
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {(donutTab === 'sentiment' ? sentimentDonutData : sourceDonutData).map((entry, index) => (
                        <Cell
                          key={index}
                          fill={entry.fill}
                          opacity={activeDonutIndex === null || activeDonutIndex === index ? 1 : 0.4}
                          style={{ transition: 'opacity 0.2s ease-in-out' }}
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ChartContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-medium">Top Insights</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="max-h-[300px] overflow-y-auto overflow-x-hidden">
                  {/* Column headers */}
                  <div className="flex items-center py-1.5 px-2 mb-1 border-b border-border text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                    <span className="flex-1 min-w-0">Name</span>
                    <span className="w-10 text-center shrink-0">Count</span>
                    <span className="w-8 text-center shrink-0">Trend</span>
                    <span className="w-14 text-center shrink-0">Sentiment</span>
                  </div>
                  <div className="space-y-3">
                    {data.top_pain_points.length > 0 && (
                      <div>
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 px-2">Pain Points</h4>
                        <div className="space-y-0.5">
                          {data.top_pain_points.map((item, i) => (
                            <TopItemRow key={i} item={item} />
                          ))}
                        </div>
                      </div>
                    )}
                    {data.top_feature_requests.length > 0 && (
                      <div>
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 px-2">Feature Requests</h4>
                        <div className="space-y-0.5">
                          {data.top_feature_requests.map((item, i) => (
                            <TopItemRow key={i} item={item} />
                          ))}
                        </div>
                      </div>
                    )}
                    {data.top_pain_points.length === 0 && data.top_feature_requests.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-8">No categorized items in this period</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          </div>
          {/* End charts container */}

          {/* Summary stats */}
          <div className="text-xs text-muted-foreground text-center">
            {data.total_feedback} total feedback items &middot; {data.date_range} &middot; {data.granularity} granularity
          </div>
        </>
      )}
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────

function TopItemRow({ item }: { item: { name: string; count: number; trend: string; avg_sentiment: number | null } }) {
  return (
    <div className="flex items-center py-1.5 px-2 rounded-md hover:bg-muted/50">
      <span className="flex-1 min-w-0 text-sm truncate capitalize">{item.name.replace(/_/g, ' ')}</span>
      <span className="w-10 text-center shrink-0">
        <Badge variant="secondary" className="text-xs tabular-nums">{item.count}</Badge>
      </span>
      <span className="w-8 flex justify-center shrink-0">
        <TrendIcon trend={item.trend} />
      </span>
      <span className="w-14 text-center shrink-0">
        {item.avg_sentiment !== null ? (
          <Badge variant={item.avg_sentiment > 0.3 ? 'default' : item.avg_sentiment < -0.3 ? 'destructive' : 'secondary'} className="text-xs tabular-nums">
            {item.avg_sentiment.toFixed(2)}
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground">--</span>
        )}
      </span>
    </div>
  );
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === 'up') return <TrendingUp className="w-3.5 h-3.5 text-destructive" />;
  if (trend === 'down') return <TrendingDown className="w-3.5 h-3.5 text-chart-3" />;
  return <Minus className="w-3.5 h-3.5 text-muted-foreground" />;
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Skeleton className="h-[370px]" />
        <Skeleton className="h-[370px]" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Skeleton className="h-[370px]" />
        <Skeleton className="h-[370px]" />
      </div>
    </div>
  );
}
