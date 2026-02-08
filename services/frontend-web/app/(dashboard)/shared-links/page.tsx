'use client';

import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import {
  sharedLinksAPI,
  type SharedLink,
  type PaginatedSharedLinks,
  type SharedLinksFilter,
} from '@/lib/api/analytics';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Copy,
  Check,
  Eye,
  Link as LinkIcon,
  Shield,
  Clock,
  XCircle,
  ExternalLink,
  ArrowUpDown,
} from 'lucide-react';
import { DataTable } from '@/components/shared/data-table';
import { ColumnDef, SortingState } from '@tanstack/react-table';

const DATE_RANGES = [
  { value: 'all', label: 'All Time' },
  { value: '7d', label: '7 Days' },
  { value: '30d', label: '30 Days' },
  { value: '90d', label: '90 Days' },
];

function getDateFrom(range: string): string | undefined {
  if (range === 'all') return undefined;
  const days = parseInt(range);
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().split('T')[0];
}

function getLinkStatus(link: SharedLink): { label: string; variant: 'default' | 'secondary' | 'destructive' } {
  if (!link.is_active) return { label: 'Deactivated', variant: 'secondary' };
  if (link.expires_at && new Date(link.expires_at) < new Date()) return { label: 'Expired', variant: 'destructive' };
  return { label: 'Active', variant: 'default' };
}

export default function SharedLinksPage() {
  const [data, setData] = useState<PaginatedSharedLinks | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // Server-side state
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [dateRange, setDateRange] = useState('all');

  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const buildFilters = useCallback((): SharedLinksFilter => {
    const filters: SharedLinksFilter = {
      page: currentPage,
      page_size: pageSize,
    };
    if (searchQuery) filters.search = searchQuery;
    if (statusFilter) filters.status = statusFilter as SharedLinksFilter['status'];
    const dateFrom = getDateFrom(dateRange);
    if (dateFrom) filters.date_from = dateFrom;
    if (sortBy) filters.sort_by = sortBy;
    if (sortOrder) filters.sort_order = sortOrder;
    return filters;
  }, [searchQuery, statusFilter, dateRange, currentPage, pageSize, sortBy, sortOrder]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await sharedLinksAPI.listAll(buildFilters());
      setData(result);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
      setSearching(false);
    }
  }, [buildFilters]);

  // Initial load
  useEffect(() => {
    fetchData();
  }, []);

  // Refetch on filter/page/sort changes
  useEffect(() => {
    fetchData();
  }, [statusFilter, dateRange, currentPage, pageSize, sortBy, sortOrder]);

  // Debounced search
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    setSearching(true);
    searchTimeoutRef.current = setTimeout(() => {
      setCurrentPage(1);
      fetchData();
    }, 300);
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchQuery]);

  const handleDeactivate = async (id: number) => {
    try {
      await sharedLinksAPI.deactivate(id);
      fetchData();
    } catch {
      // handle error
    }
  };

  const handleCopy = async (link: SharedLink) => {
    const url = `${window.location.origin}/shared/${link.token}`;
    await navigator.clipboard.writeText(url);
    setCopiedId(link.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleSortingChange = (sorting: SortingState) => {
    if (sorting.length > 0) {
      setSortBy(sorting[0].id);
      setSortOrder(sorting[0].desc ? 'desc' : 'asc');
    } else {
      setSortBy(undefined);
      setSortOrder('desc');
    }
    setCurrentPage(1);
  };

  const handleFilterChange = (setter: (v: string) => void) => (value: string) => {
    setter(value === 'all' ? '' : value);
    setCurrentPage(1);
  };

  const totalCount = data?.total ?? 0;
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  const columns: ColumnDef<SharedLink>[] = useMemo(() => [
    {
      accessorKey: 'token',
      header: 'Token',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <LinkIcon className="w-4 h-4 text-muted-foreground shrink-0" />
          <span className="font-mono text-sm truncate max-w-[180px]">
            ...{row.original.token.slice(-12)}
          </span>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = getLinkStatus(row.original);
        return (
          <Badge variant={status.variant} className="text-xs">
            {status.label}
          </Badge>
        );
      },
    },
    {
      id: 'protection',
      header: 'Protection',
      cell: ({ row }) => {
        if (!row.original.has_password) {
          return <span className="text-xs text-muted-foreground">None</span>;
        }
        return (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Shield className="w-3 h-3" /> Protected
          </span>
        );
      },
    },
    {
      accessorKey: 'view_count',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          className="h-8 px-2 lg:px-3"
        >
          Views
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="flex items-center gap-1 text-sm text-muted-foreground">
          <Eye className="w-3.5 h-3.5" /> {row.original.view_count}
        </span>
      ),
    },
    {
      accessorKey: 'expires_at',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          className="h-8 px-2 lg:px-3"
        >
          Expires
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="flex items-center gap-1 text-sm text-muted-foreground">
          <Clock className="w-3.5 h-3.5" />
          {row.original.expires_at
            ? new Date(row.original.expires_at).toLocaleDateString()
            : 'Never'}
        </span>
      ),
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          className="h-8 px-2 lg:px-3"
        >
          Created
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {new Date(row.original.created_at).toLocaleDateString()}
        </span>
      ),
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const link = row.original;
        const status = getLinkStatus(link);
        return (
          <div className="flex items-center gap-1">
            {status.label === 'Active' && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={() => window.open(`/shared/${link.token}`, '_blank')}
                title="Open link"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => handleCopy(link)}
              title="Copy link"
            >
              {copiedId === link.id ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
            </Button>
            {link.is_active && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                onClick={() => handleDeactivate(link.id)}
                title="Deactivate link"
              >
                <XCircle className="w-3.5 h-3.5" />
              </Button>
            )}
          </div>
        );
      },
    },
  ], [copiedId]);

  if (loading && !data) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="animate-pulse space-y-4">
            <div className="h-8 w-64 bg-muted rounded"></div>
            <div className="h-12 bg-muted rounded"></div>
            <div className="h-96 bg-muted rounded"></div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Title */}
        <div className="mb-8 animate-fade-in">
          <h2 className="text-4xl font-bold text-foreground mb-2">Shared Links</h2>
          <p className="text-muted-foreground text-lg">Manage your shared analytics dashboard links</p>
        </div>

        {/* Filters */}
        <Card className="mb-6 animate-slide-up stagger-1">
          <div className="p-6">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-4">Filters</h3>
            <div className="flex flex-wrap gap-4 items-center">
              {/* Status Filter */}
              <Select value={statusFilter || 'all'} onValueChange={handleFilterChange(setStatusFilter)}>
                <SelectTrigger className="h-10 w-[180px]">
                  <SelectValue placeholder="All Statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="expired">Expired</SelectItem>
                  <SelectItem value="deactivated">Deactivated</SelectItem>
                </SelectContent>
              </Select>

              {/* Date Range Toggle */}
              <Tabs value={dateRange} onValueChange={(v) => { setDateRange(v); setCurrentPage(1); }}>
                <TabsList className="h-10">
                  {DATE_RANGES.map((range) => (
                    <TabsTrigger key={range.value} value={range.value} className="text-xs px-3">
                      {range.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
            </div>
          </div>
        </Card>

        {/* Data Table */}
        <Card className="animate-slide-up stagger-2 p-6">
          <DataTable
            columns={columns}
            data={data?.items ?? []}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            isSearching={searching}
            searchPlaceholder="Search by token..."
            totalCount={totalCount}
            emptyIcon={LinkIcon}
            emptyTitle="No shared links"
            emptyDescription="Create shared links from the Analytics page to share your dashboard with others."
            serverSide
            pageCount={totalPages}
            currentPage={currentPage}
            pageSize={pageSize}
            onPageChange={handlePageChange}
            onPageSizeChange={handlePageSizeChange}
            onSortingChange={handleSortingChange}
          />
        </Card>
      </main>
    </div>
  );
}
