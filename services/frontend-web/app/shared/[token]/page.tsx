'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { sharedLinksAPI, type PublicAnalyticsData, type TopItem } from '@/lib/api/analytics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Lock, TrendingUp, TrendingDown, Minus, AlertCircle, ChevronDown } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
} from '@/components/ui/dropdown-menu';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
import {
  LineChart, Line, BarChart, Bar,
  PieChart, Pie, Cell, Sector,
  XAxis, YAxis, CartesianGrid,
} from 'recharts';

// ─── Constants (matching analytics page) ──────────────────────

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

// ─── Component ────────────────────────────────────────────────

export default function SharedAnalyticsPage() {
  const params = useParams();
  const token = params.token as string;

  const [result, setResult] = useState<PublicAnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [activeMetrics, setActiveMetrics] = useState<MetricKey[]>(['sentiment', 'volume']);
  const [donutTab, setDonutTab] = useState<'sentiment' | 'source'>('sentiment');
  const [activeDonutIndex, setActiveDonutIndex] = useState<number | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const data = await sharedLinksAPI.getPublic(token);
        setResult(data);
      } catch (err: unknown) {
        const axiosErr = err as { response?: { status: number; data?: { detail?: string } } };
        if (axiosErr.response?.status === 410) {
          setError('This link has expired or been deactivated.');
        } else {
          setError('Failed to load shared analytics.');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [token]);

  const handleVerify = async () => {
    if (!password.trim()) return;
    setVerifying(true);
    setPasswordError(null);
    try {
      const data = await sharedLinksAPI.verifyPassword(token, password);
      setResult(data);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status: number } };
      if (axiosErr.response?.status === 401) {
        setPasswordError('Incorrect password');
      } else {
        setPasswordError('Failed to verify password');
      }
    } finally {
      setVerifying(false);
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

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-6xl mx-auto p-6 space-y-6">
          <Skeleton className="h-10 w-64" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Skeleton className="h-[370px]" />
            <Skeleton className="h-[370px]" />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Skeleton className="h-[370px]" />
            <Skeleton className="h-[370px]" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 mx-auto rounded-full bg-muted flex items-center justify-center">
            <AlertCircle className="w-8 h-8 text-muted-foreground" />
          </div>
          <h1 className="text-xl font-semibold">Link Unavailable</h1>
          <p className="text-muted-foreground max-w-md">{error}</p>
          <a
            href="https://rereflect.ca"
            className="inline-block text-sm text-primary hover:underline mt-4"
          >
            Learn more about Rereflect
          </a>
        </div>
      </div>
    );
  }

  // Password prompt
  if (result?.requires_password) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="w-full max-w-sm space-y-6 text-center">
          <div className="w-16 h-16 mx-auto rounded-full bg-muted flex items-center justify-center">
            <Lock className="w-8 h-8 text-muted-foreground" />
          </div>
          <div>
            <h1 className="text-xl font-semibold mb-1">Protected Dashboard</h1>
            {result.org_name && (
              <p className="text-sm text-muted-foreground">Shared by {result.org_name}</p>
            )}
          </div>
          <div className="space-y-3">
            <Input
              type="password"
              placeholder="Enter password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleVerify()}
            />
            {passwordError && (
              <p className="text-sm text-destructive">{passwordError}</p>
            )}
            <Button onClick={handleVerify} disabled={verifying || !password.trim()} className="w-full">
              {verifying ? 'Verifying...' : 'View Dashboard'}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const analyticsData = result?.data;
  if (!analyticsData) return null;

  // Build donut data
  const sentimentDonutData = [
    { name: 'Positive', value: analyticsData.sentiment_distribution.positive, fill: SENTIMENT_COLORS.positive },
    { name: 'Neutral', value: analyticsData.sentiment_distribution.neutral, fill: SENTIMENT_COLORS.neutral },
    { name: 'Negative', value: analyticsData.sentiment_distribution.negative, fill: SENTIMENT_COLORS.negative },
  ].filter(d => d.value > 0);

  const sourceDonutData = analyticsData.source_distribution.map((s, i) => ({
    name: s.source,
    value: s.count,
    fill: SOURCE_COLORS[i % SOURCE_COLORS.length],
  }));

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <TrendingUp className="w-6 h-6" />
              Analytics
            </h1>
            {result?.org_name && (
              <p className="text-sm text-muted-foreground mt-1">{result.org_name}</p>
            )}
          </div>
          <span className="text-xs text-muted-foreground">{analyticsData.date_range}</span>
        </div>

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
                <LineChart data={analyticsData.data_points}>
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
                <BarChart data={analyticsData.data_points}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} className="text-muted-foreground" />
                  <YAxis tick={{ fontSize: 12 }} className="text-muted-foreground" />
                  <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
                  <Bar dataKey="feedback_count" name="Feedback" fill="var(--chart-1)" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ChartContainer>
            </CardContent>
          </Card>
        </div>

        {/* Charts row 2: Distribution (tabbed) + Top Insights */}
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
                  {(analyticsData.top_pain_points?.length ?? 0) > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 px-2">Pain Points</h4>
                      <div className="space-y-0.5">
                        {analyticsData.top_pain_points.map((item, i) => (
                          <TopItemRow key={i} item={item} />
                        ))}
                      </div>
                    </div>
                  )}
                  {(analyticsData.top_feature_requests?.length ?? 0) > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 px-2">Feature Requests</h4>
                      <div className="space-y-0.5">
                        {analyticsData.top_feature_requests.map((item, i) => (
                          <TopItemRow key={i} item={item} />
                        ))}
                      </div>
                    </div>
                  )}
                  {(!analyticsData.top_pain_points?.length && !analyticsData.top_feature_requests?.length) && (
                    <p className="text-sm text-muted-foreground text-center py-8">No categorized items in this period</p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Summary stats */}
        <div className="text-xs text-muted-foreground text-center">
          {analyticsData.total_feedback} total feedback items &middot; {analyticsData.date_range}
        </div>

        {/* Footer */}
        <div className="text-center py-6 border-t border-border">
          <p className="text-xs text-muted-foreground">
            Powered by{' '}
            <a href="https://rereflect.ca" className="text-primary hover:underline" target="_blank" rel="noopener noreferrer">
              Rereflect
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────

function TopItemRow({ item }: { item: TopItem }) {
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
