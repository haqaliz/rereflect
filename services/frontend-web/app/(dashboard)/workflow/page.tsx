'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { workflowAPI, WorkflowFeedbackItem, WorkflowOverviewFilters } from '@/lib/api/workflow';
import apiClient from '@/lib/api-client';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { KanbanSquare, Table2 } from 'lucide-react';
import { KanbanView } from './kanban-view';
import { BulkActionsBar } from '@/components/workflow/BulkActionsBar';
import { DataTable } from '@/components/shared/data-table';
import { ColumnDef, RowSelectionState, SortingState } from '@tanstack/react-table';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getStatusColor, getStatusLabel, formatRelativeTime } from '@/lib/workflow-utils';
import { ArrowUpDown, KanbanSquare as KanbanIcon } from 'lucide-react';

interface TeamMember {
  id: number;
  email: string;
  role: string;
}

type ViewMode = 'kanban' | 'table';

export default function WorkflowPage() {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<ViewMode>('kanban');
  const [items, setItems] = useState<WorkflowFeedbackItem[]>([]);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);

  // Server-side state
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Filters (shared between both views)
  const [statusFilter, setStatusFilter] = useState('');
  const [assigneeFilter, setAssigneeFilter] = useState('');
  const [sentimentFilter, setSentimentFilter] = useState('');

  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const buildFilters = useCallback((): WorkflowOverviewFilters => {
    const filters: WorkflowOverviewFilters = {};
    if (searchQuery) filters.search = searchQuery;
    if (statusFilter) filters.workflow_status = statusFilter;
    if (assigneeFilter) filters.assigned_to = parseInt(assigneeFilter, 10);
    if (sentimentFilter) filters.sentiment = sentimentFilter;
    if (sortBy) filters.sort_by = sortBy;
    filters.sort_order = sortOrder;
    return filters;
  }, [searchQuery, statusFilter, assigneeFilter, sentimentFilter, sortBy, sortOrder]);

  const fetchData = useCallback(async (page?: number, size?: number) => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        router.push('/login');
        return;
      }

      const effectivePage = page ?? currentPage;
      const effectiveSize = viewMode === 'kanban' ? 100 : (size ?? pageSize);
      const filters = buildFilters();

      const [overviewResponse, membersResponse] = await Promise.all([
        workflowAPI.getOverview(effectivePage, effectiveSize, filters),
        apiClient.get('/api/v1/team/members'),
      ]);

      setItems(overviewResponse.items);
      setStatusCounts(overviewResponse.status_counts);
      setTotalCount(overviewResponse.total);
      setTotalPages(overviewResponse.total_pages);
      setTeamMembers(membersResponse.data.members || membersResponse.data || []);
    } catch (err) {
      console.error('Failed to load workflow data:', err);
    } finally {
      setLoading(false);
      setSearching(false);
    }
  }, [router, currentPage, pageSize, viewMode, buildFilters]);

  // Initial load
  useEffect(() => {
    fetchData();
  }, []);

  // Refetch when filters, page, sort, or view mode change
  useEffect(() => {
    if (!loading) {
      fetchData();
    }
  }, [statusFilter, assigneeFilter, sentimentFilter, currentPage, pageSize, sortBy, sortOrder, viewMode]);

  // Debounced search
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    setSearching(true);
    searchTimeoutRef.current = setTimeout(() => {
      setCurrentPage(1);
      fetchData(1);
    }, 300);
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchQuery]);

  // Polling for auto-refresh (every 30 seconds)
  useEffect(() => {
    if (loading) return;

    pollingIntervalRef.current = setInterval(async () => {
      await fetchData();
    }, 30000);

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, [loading, fetchData]);

  const handleStatusChange = async (id: number, newStatus: string) => {
    try {
      await workflowAPI.changeStatus([id], newStatus);
      await fetchData();
    } catch (err) {
      console.error('Failed to change status:', err);
    }
  };

  const handleBulkStatusChange = async (status: string) => {
    if (selectedIds.length === 0) return;
    try {
      await workflowAPI.changeStatus(selectedIds, status);
      setSelectedIds([]);
      await fetchData();
    } catch (err) {
      console.error('Failed to bulk change status:', err);
    }
  };

  const handleBulkAssign = async (userId: number | null) => {
    if (selectedIds.length === 0) return;
    try {
      await workflowAPI.assign(selectedIds, userId);
      setSelectedIds([]);
      await fetchData();
    } catch (err) {
      console.error('Failed to bulk assign:', err);
    }
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

  // Controlled row selection: derive from selectedIds
  const tableRowSelection: RowSelectionState = useMemo(() => {
    const selection: RowSelectionState = {};
    items.forEach((item, index) => {
      if (selectedIds.includes(item.id)) {
        selection[String(index)] = true;
      }
    });
    return selection;
  }, [items, selectedIds]);

  const handleRowSelectionChange = useCallback((selection: RowSelectionState) => {
    const newSelectedIds = Object.keys(selection)
      .filter(key => selection[key])
      .map(key => items[parseInt(key)]?.id)
      .filter((id): id is number => id !== undefined);
    setSelectedIds(newSelectedIds);
  }, [items]);

  const getSentimentVariant = (sentiment: string | null): 'success' | 'warning' | 'destructive' | 'secondary' => {
    switch (sentiment?.toLowerCase()) {
      case 'positive': return 'success';
      case 'negative': return 'destructive';
      case 'neutral': return 'warning';
      default: return 'secondary';
    }
  };

  const columns: ColumnDef<WorkflowFeedbackItem>[] = useMemo(() => [
    {
      id: 'select',
      header: ({ table }) => (
        <Checkbox
          checked={
            table.getIsAllPageRowsSelected() ||
            (table.getIsSomePageRowsSelected() && 'indeterminate')
          }
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label="Select row"
        />
      ),
      enableSorting: false,
      enableHiding: false,
    },
    {
      accessorKey: 'id',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          ID
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      ),
      cell: ({ row }) => (
        <div className="font-bold font-mono text-muted-foreground">
          #{row.getValue('id')}
        </div>
      ),
    },
    {
      accessorKey: 'text',
      header: 'Feedback Text',
      cell: ({ row }) => {
        const text = row.getValue('text') as string;
        return (
          <div className="max-w-md">
            <div className="line-clamp-2 leading-relaxed">{text}</div>
          </div>
        );
      },
    },
    {
      accessorKey: 'workflow_status',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Status
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      ),
      cell: ({ row }) => {
        const status = row.getValue('workflow_status') as string;
        const color = getStatusColor(status);
        return (
          <div className="flex items-center gap-1.5">
            <div
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: color }}
            />
            <span className="text-sm font-medium">{getStatusLabel(status)}</span>
          </div>
        );
      },
    },
    {
      id: 'assignee',
      header: 'Assignee',
      cell: ({ row }) => {
        const email = row.original.assigned_to_email;
        if (!email) {
          return <span className="text-muted-foreground text-sm">Unassigned</span>;
        }
        return (
          <div className="flex items-center gap-1.5">
            <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-semibold flex-shrink-0">
              {email.charAt(0).toUpperCase()}
            </div>
            <span className="text-sm truncate max-w-[120px]">{email.split('@')[0]}</span>
          </div>
        );
      },
    },
    {
      accessorKey: 'sentiment_label',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Sentiment
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      ),
      cell: ({ row }) => {
        const sentiment = row.getValue('sentiment_label') as string | null;
        return (
          <Badge variant={getSentimentVariant(sentiment)}>
            {sentiment ? sentiment.charAt(0).toUpperCase() + sentiment.slice(1) : 'Unknown'}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'source',
      header: 'Source',
      cell: ({ row }) => {
        const source = row.getValue('source') as string | null;
        return (
          <span className="text-sm text-muted-foreground">
            {source || 'N/A'}
          </span>
        );
      },
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Created
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      ),
      cell: ({ row }) => {
        const date = row.getValue('created_at') as string;
        return (
          <span className="text-sm text-muted-foreground">
            {formatRelativeTime(date)}
          </span>
        );
      },
    },
  ], [items]);

  if (loading) {
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
        <div className="mb-8 flex justify-between items-start">
          <div className="animate-fade-in">
            <h2 className="text-4xl font-bold text-foreground mb-2">Workflow</h2>
            <p className="text-muted-foreground text-lg">Track, assign, and manage feedback through your workflow</p>
          </div>
          <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as ViewMode)}>
            <TabsList className="h-8">
              <TabsTrigger value="kanban" className="text-xs px-2 h-6">
                <KanbanSquare className="h-3.5 w-3.5 mr-1" /> Board
              </TabsTrigger>
              <TabsTrigger value="table" className="text-xs px-2 h-6">
                <Table2 className="h-3.5 w-3.5 mr-1" /> Table
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* Filters */}
        <Card className="mb-6 animate-slide-up stagger-1">
          <div className="p-6">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-4">Filters</h3>
            <div className="flex flex-wrap gap-4">
              {/* Status Filter */}
              <Select value={statusFilter || 'all'} onValueChange={handleFilterChange(setStatusFilter)}>
                <SelectTrigger className="h-10 w-[180px]">
                  <SelectValue placeholder="All Statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="new">New</SelectItem>
                  <SelectItem value="in_review">In Review</SelectItem>
                  <SelectItem value="resolved">Resolved</SelectItem>
                  <SelectItem value="closed">Closed</SelectItem>
                </SelectContent>
              </Select>

              {/* Assignee Filter */}
              <Select value={assigneeFilter || 'all'} onValueChange={handleFilterChange(setAssigneeFilter)}>
                <SelectTrigger className="h-10 w-[180px]">
                  <SelectValue placeholder="All Assignees" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Assignees</SelectItem>
                  {teamMembers.map((member) => (
                    <SelectItem key={member.id} value={member.id.toString()}>
                      {member.email.split('@')[0]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Sentiment Filter */}
              <Select value={sentimentFilter || 'all'} onValueChange={handleFilterChange(setSentimentFilter)}>
                <SelectTrigger className="h-10 w-[180px]">
                  <SelectValue placeholder="All Sentiments" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sentiments</SelectItem>
                  <SelectItem value="positive">Positive</SelectItem>
                  <SelectItem value="neutral">Neutral</SelectItem>
                  <SelectItem value="negative">Negative</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </Card>

        {/* Content */}
        {viewMode === 'kanban' ? (
          <KanbanView
            items={items}
            onStatusChange={handleStatusChange}
            statusCounts={statusCounts}
          />
        ) : (
          <Card className="animate-slide-up stagger-2 p-6">
            <DataTable
              columns={columns}
              data={items}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              onRowClick={(item) => router.push(`/feedbacks/${item.id}`)}
              isSearching={searching}
              searchPlaceholder="Search feedback..."
              totalCount={totalCount}
              emptyIcon={KanbanIcon}
              emptyTitle="No feedback found"
              emptyDescription="Try adjusting your filters or search"
              serverSide
              pageCount={totalPages}
              currentPage={currentPage}
              pageSize={pageSize}
              onPageChange={handlePageChange}
              onPageSizeChange={handlePageSizeChange}
              onSortingChange={handleSortingChange}
              rowSelection={tableRowSelection}
              onRowSelectionChange={handleRowSelectionChange}
            />
          </Card>
        )}

        {selectedIds.length > 0 && (
          <BulkActionsBar
            selectedCount={selectedIds.length}
            onStatusChange={handleBulkStatusChange}
            onAssign={handleBulkAssign}
            onClear={() => setSelectedIds([])}
            teamMembers={teamMembers}
          />
        )}
      </main>
    </div>
  );
}
