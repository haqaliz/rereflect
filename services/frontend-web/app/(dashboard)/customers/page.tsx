'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { ColumnDef } from '@tanstack/react-table';
import Link from 'next/link';
import {
  Users,
  TrendingUp,
  TrendingDown,
  Minus,
  UserPlus,
  AlertTriangle,
  Upload,
  Sparkles,
  Brain,
  Loader2,
  UserX,
  FileUp,
  Info,
} from 'lucide-react';
import { customersAPI, CustomerListItem, CustomerListParams } from '@/lib/api/customers';
import { ChurnProbabilityBadge } from '@/components/customers/ChurnProbabilityBadge';
import { SegmentBadge } from '@/components/customers/SegmentBadge';
import { SEGMENT_SLUGS, SEGMENT_LABELS } from '@/lib/constants/segments';
import { useAuth } from '@/contexts/AuthContext';
import { BulkMarkChurnedDialog } from '@/components/customers/BulkMarkChurnedDialog';
import { ChurnCsvImportDialog } from '@/components/customers/ChurnCsvImportDialog';
import { StatCard } from '@/components/StatCard';
import { RiskDistributionBar } from '@/components/customers/RiskDistributionBar';
import { HealthScoreCircle } from '@/components/customers/HealthScoreCircle';
import { DataTable } from '@/components/shared/data-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';

function getRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function getRiskBadgeStyle(riskLevel: string) {
  const map: Record<string, { label: string; color: string }> = {
    healthy: { label: 'Healthy', color: 'var(--chart-5)' },
    moderate: { label: 'Moderate', color: 'var(--chart-2)' },
    at_risk: { label: 'At Risk', color: 'var(--chart-1)' },
    critical: { label: 'Critical', color: 'var(--destructive)' },
  };
  return map[riskLevel] ?? { label: riskLevel, color: 'var(--muted-foreground)' };
}

interface TrendCellProps {
  trend: CustomerListItem['sentiment_trend'];
  isBlurred: boolean;
}

function TrendCell({ trend, isBlurred }: TrendCellProps) {
  const { direction, change_percent } = trend;
  const style = isBlurred ? { filter: 'blur(4px)', userSelect: 'none' as const } : {};

  if (direction === 'improving') {
    return (
      <span
        className="flex items-center gap-1 text-sm font-mono font-medium"
        style={{ color: 'var(--chart-5)', ...style }}
      >
        <TrendingUp className="w-3.5 h-3.5" />
        +{change_percent}%
      </span>
    );
  }
  if (direction === 'declining') {
    return (
      <span
        className="flex items-center gap-1 text-sm font-mono font-medium"
        style={{ color: 'var(--destructive)', ...style }}
      >
        <TrendingDown className="w-3.5 h-3.5" />
        {change_percent}%
      </span>
    );
  }
  return (
    <span
      className="flex items-center gap-1 text-sm font-mono text-muted-foreground"
      style={style}
    >
      <Minus className="w-3.5 h-3.5" />0%
    </span>
  );
}

export default function CustomersPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [segmentFilter, setSegmentFilter] = useState('');
  const [sortBy, setSortBy] = useState<CustomerListParams['sort_by']>('health_score');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [reanalyzing, setReanalyzing] = useState(false);
  const [selectedEmails, setSelectedEmails] = useState<string[]>([]);
  const [bulkChurnOpen, setBulkChurnOpen] = useState(false);
  const [csvImportOpen, setCsvImportOpen] = useState(false);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery), 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  const queryParams: CustomerListParams = {
    page: currentPage,
    page_size: pageSize,
    sort_by: sortBy,
    sort_order: sortOrder,
    ...(debouncedSearch && { search: debouncedSearch }),
    ...(riskFilter && { risk_level: riskFilter }),
    ...(segmentFilter && { segment: segmentFilter }),
  };

  const { data, isLoading } = useQuery({
    queryKey: ['customers', queryParams],
    queryFn: async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        router.push('/login');
        throw new Error('No token');
      }
      return customersAPI.list(queryParams);
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
  });

  const handleRiskFilterFromBar = useCallback((level: string) => {
    setRiskFilter(prev => (prev === level ? '' : level));
    setCurrentPage(1);
  }, []);

  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    setCurrentPage(1);
  }, []);

  const handleRiskFilterChange = useCallback((value: string) => {
    setRiskFilter(value === 'all' ? '' : value);
    setCurrentPage(1);
  }, []);

  const handleSegmentFilterChange = useCallback((value: string) => {
    setSegmentFilter(value === 'all' ? '' : value);
    setCurrentPage(1);
  }, []);

  const handlePageSizeChange = useCallback((size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  }, []);

  const handleRowClick = useCallback(
    (item: CustomerListItem) => {
      router.push(`/customers/${encodeURIComponent(item.customer_email)}`);
    },
    [router]
  );

  const handleBatchAnalyze = useCallback(async () => {
    setReanalyzing(true);
    try {
      const result = await customersAPI.batchAnalyze();
      toast.success(`Analysis queued for ${result.customer_count} customers`);
    } catch {
      toast.error('Failed to queue batch analysis');
    } finally {
      setReanalyzing(false);
    }
  }, []);

  const summary = data?.summary;
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize) || 1;

  const atRiskPercent =
    summary && summary.total_customers > 0
      ? Math.round(
          ((summary.risk_distribution.at_risk + summary.risk_distribution.critical) /
            summary.total_customers) *
            100
        )
      : 0;

  // Column definitions
  const columns: ColumnDef<CustomerListItem>[] = [
    {
      accessorKey: 'customer_email',
      header: 'Customer',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <div>
            <p className="font-medium text-foreground text-sm">{row.original.customer_email}</p>
            {row.original.customer_name && (
              <p className="text-xs text-muted-foreground mt-0.5">{row.original.customer_name}</p>
            )}
          </div>
          {row.original.has_llm_analysis && (
            <span
              className="shrink-0"
              title="AI analysis available"
            >
              <Sparkles className="w-3.5 h-3.5" style={{ color: 'var(--chart-2)' }} />
            </span>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'health_score',
      header: 'Health Score',
      cell: ({ row }) => {
        const blurred = {};
        return (
          <span style={blurred}>
            <HealthScoreCircle score={row.original.health_score} />
          </span>
        );
      },
    },
    {
      accessorKey: 'risk_level',
      header: 'Churn Probability',
      cell: ({ row }) => {
        const blurred = {};
        const { churn_probability, churn_probability_low, churn_probability_high } = row.original;
        // Fall back to risk_level color hint when probability is null (Pro/Free)
        if (churn_probability === null || churn_probability === undefined) {
          const { label, color } = getRiskBadgeStyle(row.original.risk_level);
          return (
            <Badge
              variant="outline"
              style={{
                backgroundColor: `color-mix(in oklch, ${color} 15%, transparent)`,
                color,
                borderColor: `color-mix(in oklch, ${color} 30%, transparent)`,
                ...blurred,
              }}
            >
              {label}
            </Badge>
          );
        }
        return (
          <span style={blurred}>
            <ChurnProbabilityBadge
              probability={churn_probability}
              probabilityLow={churn_probability_low ?? undefined}
              probabilityHigh={churn_probability_high ?? undefined}
              size="sm"
            />
          </span>
        );
      },
    },
    {
      accessorKey: 'confidence_level',
      header: 'Confidence',
      cell: ({ row }) => {
        const level = row.original.confidence_level;
        if (level === 'high') return null;
        const blurred = {};
        const color = level === 'low' ? 'var(--chart-1)' : 'var(--chart-2)';
        return (
          <Badge
            variant="outline"
            style={{
              backgroundColor: `color-mix(in oklch, ${color} 15%, transparent)`,
              color,
              borderColor: `color-mix(in oklch, ${color} 30%, transparent)`,
              ...blurred,
            }}
          >
            {level === 'low' ? 'Low' : 'Medium'}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'feedback_count',
      header: 'Feedbacks',
      cell: ({ row }) => (
        <span className="font-mono text-sm text-foreground">{row.original.feedback_count}</span>
      ),
    },
    {
      accessorKey: 'last_feedback_at',
      header: 'Last Active (feedback)',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {getRelativeTime(row.original.last_feedback_at)}
        </span>
      ),
    },
    {
      accessorKey: 'last_active_at',
      header: 'Last Active (product)',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {row.original.last_active_at != null
            ? getRelativeTime(row.original.last_active_at)
            : '—'}
        </span>
      ),
    },
    {
      accessorKey: 'sentiment_trend',
      header: 'Trend',
      cell: ({ row }) => (
        <TrendCell trend={row.original.sentiment_trend} isBlurred={false} />
      ),
    },
    {
      accessorKey: 'segment',
      header: () => (
        <div className="flex items-center gap-1">
          Segment
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="w-3 h-3 text-muted-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs max-w-xs">
                Segments are rule-based heuristics computed from usage and feedback signals — not
                a guarantee.
              </p>
            </TooltipContent>
          </Tooltip>
        </div>
      ),
      cell: ({ row }) => <SegmentBadge segment={row.original.segment} size="sm" />,
    },
  ];

  // Empty state
  const isEmpty =
    !isLoading && items.length === 0 && !searchQuery && !riskFilter && !segmentFilter;

  if (isLoading) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="animate-pulse space-y-6">
            <div className="h-10 w-48 bg-muted rounded" />
            <div className="grid grid-cols-4 gap-4">
              {[0, 1, 2, 3].map(i => (
                <div key={i} className="h-32 bg-muted rounded-2xl" />
              ))}
            </div>
            <div className="h-16 bg-muted rounded" />
            <div className="h-96 bg-muted rounded" />
          </div>
        </main>
      </div>
    );
  }

  return (
    <TooltipProvider>
    <div className="min-h-screen pattern-bg">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Users className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-foreground">Customers</h1>
                <p className="text-muted-foreground text-lg">
                  Customer health scores and risk analysis
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {selectedEmails.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setBulkChurnOpen(true)}
                  className="flex items-center gap-2"
                >
                  <UserX className="w-4 h-4" />
                  Mark {selectedEmails.length} as churned
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCsvImportOpen(true)}
                className="flex items-center gap-2"
              >
                <FileUp className="w-4 h-4" />
                Import CSV
              </Button>
              {user?.is_system_admin && (
                <Button
                  variant="outline"
                  onClick={handleBatchAnalyze}
                  disabled={reanalyzing}
                  className="flex items-center gap-2"
                >
                  {reanalyzing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Brain className="w-4 h-4" />
                  )}
                  Re-analyze All
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-slide-up stagger-1">
          <StatCard
            title="Total Customers"
            value={summary?.total_customers ?? 0}
            icon={Users}
            color="blue"
          />
          <StatCard
            title="Avg Health Score"
            value={summary?.avg_health_score ?? 0}
            icon={TrendingUp}
            color="green"
          />
          <StatCard
            title="At Risk %"
            value={`${atRiskPercent}%`}
            icon={AlertTriangle}
            color="yellow"
          />
          <StatCard
            title="Critical Count"
            value={summary?.risk_distribution.critical ?? 0}
            icon={UserPlus}
            color="red"
          />
        </div>

        {/* Risk Distribution Bar */}
        {summary && summary.total_customers > 0 && (
          <Card className="p-6 animate-slide-up stagger-2">
            <RiskDistributionBar
              distribution={summary.risk_distribution}
              total={summary.total_customers}
              onFilterChange={handleRiskFilterFromBar}
              activeFilter={riskFilter}
            />
          </Card>
        )}

        {/* Filter Bar */}
        <div className="flex flex-wrap gap-4 items-center animate-slide-up stagger-2">
          <Select
            value={riskFilter || 'all'}
            onValueChange={handleRiskFilterChange}
          >
            <SelectTrigger className="h-10 w-[180px]">
              <SelectValue placeholder="All Risk Levels" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Risk Levels</SelectItem>
              <SelectItem value="healthy">Healthy</SelectItem>
              <SelectItem value="moderate">Moderate</SelectItem>
              <SelectItem value="at_risk">At Risk</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1.5">
            <Select
              value={segmentFilter || 'all'}
              onValueChange={handleSegmentFilterChange}
            >
              <SelectTrigger className="h-10 w-[180px]">
                <SelectValue placeholder="All Segments" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Segments</SelectItem>
                {SEGMENT_SLUGS.map(slug => (
                  <SelectItem key={slug} value={slug}>
                    {SEGMENT_LABELS[slug]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="w-3.5 h-3.5 text-muted-foreground cursor-help shrink-0" />
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs max-w-xs">
                  Segments are rule-based heuristics computed from usage and feedback signals —
                  not a guarantee.
                </p>
              </TooltipContent>
            </Tooltip>
          </div>
        </div>

        {/* Empty state */}
        {isEmpty ? (
          <Card className="p-16 flex flex-col items-center justify-center animate-fade-in">
            <Users className="w-16 h-16 text-muted-foreground opacity-20 mb-4" />
            <h2 className="text-xl font-semibold text-foreground mb-2">No customer data yet</h2>
            <p className="text-muted-foreground text-sm mb-6 text-center max-w-md">
              Import feedback with customer emails to see health scores and risk analysis.
            </p>
            <Link href="/feedbacks">
              <Button className="flex items-center gap-2">
                <Upload className="w-4 h-4" />
                Import Feedback
              </Button>
            </Link>
          </Card>
        ) : (
          /* DataTable */
          <Card className="p-6 animate-slide-up stagger-3">
            <DataTable
              columns={columns}
              data={items}
              searchQuery={searchQuery}
              onSearchChange={handleSearchChange}
              onRowClick={handleRowClick}
              searchPlaceholder="Search customers by email or name..."
              emptyIcon={Users}
              emptyTitle="No customers found"
              emptyDescription="Try adjusting your search or filters"
              serverSide
              totalCount={total}
              pageCount={totalPages}
              currentPage={currentPage}
              pageSize={pageSize}
              onPageChange={setCurrentPage}
              onPageSizeChange={handlePageSizeChange}
              onSortingChange={(sorting) => {
                if (sorting.length > 0) {
                  const s = sorting[0];
                  setSortBy(s.id as CustomerListParams['sort_by']);
                  setSortOrder(s.desc ? 'desc' : 'asc');
                }
              }}
            />
          </Card>
        )}
      </main>

      <BulkMarkChurnedDialog
        open={bulkChurnOpen}
        onOpenChange={setBulkChurnOpen}
        selectedEmails={selectedEmails}
        onSuccess={() => setSelectedEmails([])}
      />

      <ChurnCsvImportDialog
        open={csvImportOpen}
        onOpenChange={setCsvImportOpen}
      />
    </div>
    </TooltipProvider>
  );
}
