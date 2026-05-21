'use client';

/**
 * /system/churn-events — System admin view of all churn events across all organizations.
 * Read-only in v1. Supports filtering, server-side pagination, and CSV export.
 */

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  listChurnEvents,
  exportChurnEventsCsv,
  type ChurnEvent,
  type ChurnEventsListParams,
  type ChurnReasonCode,
} from '@/lib/api/churn-events';
import { CHURN_REASON_LABELS, CHURN_REASON_CODES } from '@/lib/constants/churn';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertOctagon,
  Loader2,
  Search,
  ChevronLeft,
  ChevronRight,
  Download,
} from 'lucide-react';
import { toast } from 'sonner';

const PAGE_SIZE = 25;

/** Derive display status from recovered_at field. */
function deriveStatus(event: ChurnEvent): 'Active' | 'Recovered' {
  return event.recovered_at ? 'Recovered' : 'Active';
}

function StatusBadge({ event }: { event: ChurnEvent }) {
  const status = deriveStatus(event);
  return status === 'Active' ? (
    <Badge variant="destructive">Active</Badge>
  ) : (
    <Badge variant="secondary">Recovered</Badge>
  );
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/** Source label mapping for display. */
const SOURCE_LABELS: Record<ChurnEvent['source'], string> = {
  manual: 'Manual',
  csv_import: 'CSV Import',
  auto_suggested: 'Auto',
};

export default function ChurnEventsPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [events, setEvents] = useState<ChurnEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);

  // Filter state
  const [emailInput, setEmailInput] = useState('');
  const [emailFilter, setEmailFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'recovered'>('all');
  const [reasonFilter, setReasonFilter] = useState<ChurnReasonCode | 'all'>('all');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  // Auth guard — redirect non-system-admins
  useEffect(() => {
    if (user && !user.is_system_admin) {
      router.push('/dashboard');
    }
  }, [user, router]);

  // Debounce email search input by 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setEmailFilter(emailInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [emailInput]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [statusFilter, reasonFilter, fromDate, toDate]);

  const buildParams = useCallback((): ChurnEventsListParams => {
    const params: ChurnEventsListParams = { page, page_size: PAGE_SIZE };
    if (statusFilter === 'active') params.active = true;
    if (statusFilter === 'recovered') params.active = false;
    if (reasonFilter !== 'all') params.reason_code = reasonFilter;
    if (fromDate) params.from_date = fromDate;
    if (toDate) params.to_date = toDate;
    if (emailFilter) params.customer_email = emailFilter;
    return params;
  }, [page, statusFilter, reasonFilter, fromDate, toDate, emailFilter]);

  const fetchEvents = useCallback(async () => {
    if (!user?.is_system_admin) return;
    try {
      setIsLoading(true);
      const params = buildParams();
      const data = await listChurnEvents(params);
      setEvents(data.items);
      setTotal(data.total);
    } catch {
      toast.error('Failed to load churn events');
    } finally {
      setIsLoading(false);
    }
  }, [user, buildParams]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const filterParams: Omit<ChurnEventsListParams, 'page' | 'page_size'> = {};
      if (statusFilter === 'active') filterParams.active = true;
      if (statusFilter === 'recovered') filterParams.active = false;
      if (reasonFilter !== 'all') filterParams.reason_code = reasonFilter;
      if (fromDate) filterParams.from_date = fromDate;
      if (toDate) filterParams.to_date = toDate;
      await exportChurnEventsCsv(filterParams);
    } catch {
      toast.error('Failed to export churn events');
    } finally {
      setIsExporting(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  if (!user?.is_system_admin) return null;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Churn Events</h1>
          <p className="text-muted-foreground">
            All churn events across all organizations. {total} total.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={handleExport}
          disabled={isExporting || total === 0}
        >
          {isExporting ? (
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
          ) : (
            <Download className="w-4 h-4 mr-2" />
          )}
          Export CSV
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by email..."
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
            className="pl-9"
          />
        </div>

        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as 'all' | 'active' | 'recovered')}
          aria-label="Status"
        >
          <SelectTrigger className="w-[160px]" aria-label="Status">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="recovered">Recovered</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={reasonFilter}
          onValueChange={(v) => setReasonFilter(v as ChurnReasonCode | 'all')}
          aria-label="Reason"
        >
          <SelectTrigger className="w-[180px]" aria-label="Reason">
            <SelectValue placeholder="Reason code" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Reasons</SelectItem>
            {CHURN_REASON_CODES.map((code) => (
              <SelectItem key={code} value={code}>
                {CHURN_REASON_LABELS[code]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          type="date"
          value={fromDate}
          onChange={(e) => setFromDate(e.target.value)}
          className="w-[160px]"
          aria-label="From date"
        />
        <Input
          type="date"
          value={toDate}
          onChange={(e) => setToDate(e.target.value)}
          className="w-[160px]"
          aria-label="To date"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertOctagon className="w-5 h-5" />
            All Churn Events
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : events.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              No churn events found.
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    {/*
                     * TODO (follow-up): The listChurnEvents API currently returns
                     * organization_id and marked_by_user_id instead of
                     * organization_name and marked_by_email. The backend endpoint
                     * needs enrichment (JOIN organizations + users) to return
                     * human-readable fields. Until then, we display ID placeholders.
                     */}
                    <TableHead>Organization</TableHead>
                    <TableHead>Customer Email</TableHead>
                    <TableHead>Churned At</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Marked By</TableHead>
                    <TableHead>Created At</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.map((event) => (
                    <TableRow key={event.id}>
                      <TableCell className="text-muted-foreground text-sm">
                        {/* Placeholder until API returns organization_name */}
                        Org #{event.organization_id}
                      </TableCell>
                      <TableCell className="font-medium">{event.customer_email}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {formatDate(event.churned_at)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {CHURN_REASON_LABELS[event.reason_code] ?? event.reason_code}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <StatusBadge event={event} />
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm capitalize">
                        {SOURCE_LABELS[event.source] ?? event.source}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {/* Placeholder until API returns marked_by_email */}
                        {event.marked_by_user_id != null
                          ? `User #${event.marked_by_user_id}`
                          : '-'}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {formatDate(event.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Server-side pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4">
                  <span className="text-sm text-muted-foreground">
                    Page {page} of {totalPages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => p - 1)}
                      aria-label="Previous page"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => p + 1)}
                      aria-label="Next page"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
