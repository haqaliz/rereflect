'use client';

import { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  pendingFeedbackAPI,
  feedbackSourcesAPI,
  PendingFeedback,
  FeedbackSource,
} from '@/lib/api/feedback-sources';
import {
  Webhook,
  MessageCircle,
  Mail,
  ArrowLeft,
  Loader2,
  Check,
  X,
  Inbox,
  ChevronLeft,
  ChevronRight,
  User,
  Clock,
  Tag,
  CheckCircle,
  XCircle,
  AlertCircle,
} from 'lucide-react';
import { SlackIcon } from '@/components/icons/SlackIcon';
import { IntercomIcon } from '@/components/icons/IntercomIcon';
import { LinearIcon } from '@/components/icons/LinearIcon';

// Source type icon mapping
const SOURCE_ICONS: Record<string, React.ElementType> = {
  slack: SlackIcon,
  intercom: IntercomIcon,
  webhook: Webhook,
  discord: MessageCircle,
  email: Mail,
  linear: LinearIcon,
};

function PendingFeedbackContent() {
  const [items, setItems] = useState<PendingFeedback[]>([]);
  const [sources, setSources] = useState<FeedbackSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // Filters
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('pending');

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Action state
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [actionResult, setActionResult] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  useEffect(() => {
    fetchData();
  }, [page, sourceFilter, statusFilter]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [pendingRes, sourcesRes] = await Promise.all([
        pendingFeedbackAPI.list(
          page,
          pageSize,
          undefined,
          sourceFilter !== 'all' ? parseInt(sourceFilter) : undefined,
          statusFilter
        ),
        feedbackSourcesAPI.list(),
      ]);
      setItems(pendingRes.items);
      setTotal(pendingRes.total);
      setSources(sourcesRes.sources);
      setSelectedIds(new Set());
    } catch (err) {
      console.error('Failed to load pending feedback:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (id: number) => {
    try {
      setActionLoading(id);
      await pendingFeedbackAPI.approve(id);
      setActionResult({ type: 'success', message: 'Feedback approved and queued for analysis' });
      await fetchData();
    } catch (err: any) {
      setActionResult({
        type: 'error',
        message: err.response?.data?.detail || 'Failed to approve',
      });
    } finally {
      setActionLoading(null);
      setTimeout(() => setActionResult(null), 3000);
    }
  };

  const handleReject = async (id: number) => {
    try {
      setActionLoading(id);
      await pendingFeedbackAPI.reject(id);
      setActionResult({ type: 'success', message: 'Feedback rejected' });
      await fetchData();
    } catch (err: any) {
      setActionResult({
        type: 'error',
        message: err.response?.data?.detail || 'Failed to reject',
      });
    } finally {
      setActionLoading(null);
      setTimeout(() => setActionResult(null), 3000);
    }
  };

  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return;
    try {
      setBulkLoading(true);
      const result = await pendingFeedbackAPI.bulkApprove(Array.from(selectedIds));
      setActionResult({
        type: result.failed === 0 ? 'success' : 'error',
        message: `Approved ${result.processed} item(s)${result.failed > 0 ? `, ${result.failed} failed` : ''}`,
      });
      await fetchData();
    } catch (err: any) {
      setActionResult({
        type: 'error',
        message: err.response?.data?.detail || 'Bulk approve failed',
      });
    } finally {
      setBulkLoading(false);
      setTimeout(() => setActionResult(null), 3000);
    }
  };

  const handleBulkReject = async () => {
    if (selectedIds.size === 0) return;
    try {
      setBulkLoading(true);
      const result = await pendingFeedbackAPI.bulkReject(Array.from(selectedIds));
      setActionResult({
        type: result.failed === 0 ? 'success' : 'error',
        message: `Rejected ${result.processed} item(s)${result.failed > 0 ? `, ${result.failed} failed` : ''}`,
      });
      await fetchData();
    } catch (err: any) {
      setActionResult({
        type: 'error',
        message: err.response?.data?.detail || 'Bulk reject failed',
      });
    } finally {
      setBulkLoading(false);
      setTimeout(() => setActionResult(null), 3000);
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map(i => i.id)));
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  if (loading && items.length === 0) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <Link
            href="/feedback-sources"
            className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Feedback Sources
          </Link>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Inbox className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-foreground">Pending Feedback</h1>
                <p className="text-muted-foreground">
                  Review and approve feedback before analysis
                </p>
              </div>
            </div>
            <Badge variant="secondary" className="text-lg px-3 py-1">
              {total} pending
            </Badge>
          </div>
        </div>

        {/* Action Result */}
        {actionResult && (
          <div
            className={`p-4 rounded-lg flex items-center gap-2 animate-fade-in ${
              actionResult.type === 'success'
                ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                : 'bg-destructive/10 text-destructive'
            }`}
          >
            {actionResult.type === 'success' ? (
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
            )}
            {actionResult.message}
          </div>
        )}

        {/* Filters & Bulk Actions */}
        <Card className="animate-slide-up">
          <CardContent className="py-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <Select value={sourceFilter} onValueChange={setSourceFilter}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="All Sources" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Sources</SelectItem>
                    {sources.map(source => (
                      <SelectItem key={source.id} value={source.id.toString()}>
                        {source.name || `${source.source_type} source`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-[150px]">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="rejected">Rejected</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {selectedIds.size > 0 && statusFilter === 'pending' && (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    {selectedIds.size} selected
                  </span>
                  <Button
                    size="sm"
                    onClick={handleBulkApprove}
                    disabled={bulkLoading}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    {bulkLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Check className="w-4 h-4 mr-1" />
                    )}
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleBulkReject}
                    disabled={bulkLoading}
                    className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                  >
                    {bulkLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <X className="w-4 h-4 mr-1" />
                    )}
                    Reject
                  </Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Items List */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border py-3">
            <div className="flex items-center gap-4">
              {statusFilter === 'pending' && items.length > 0 && (
                <Checkbox
                  checked={selectedIds.size === items.length && items.length > 0}
                  onCheckedChange={toggleSelectAll}
                />
              )}
              <CardTitle className="text-base">
                {loading ? 'Loading...' : `${total} item${total !== 1 ? 's' : ''}`}
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {items.length === 0 ? (
              <div className="text-center py-12">
                <Inbox className="w-16 h-16 mx-auto text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-semibold text-foreground mb-2">
                  No {statusFilter} items
                </h3>
                <p className="text-muted-foreground">
                  {statusFilter === 'pending'
                    ? 'Feedback will appear here when sources have review mode enabled'
                    : `No ${statusFilter} items found`}
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {items.map(item => {
                  const Icon = SOURCE_ICONS[item.source_type] || Webhook;

                  return (
                    <div
                      key={item.id}
                      className={`p-4 hover:bg-muted/30 transition-colors ${
                        selectedIds.has(item.id) ? 'bg-primary/5' : ''
                      }`}
                    >
                      <div className="flex items-start gap-4">
                        {statusFilter === 'pending' && (
                          <Checkbox
                            checked={selectedIds.has(item.id)}
                            onCheckedChange={() => toggleSelect(item.id)}
                            className="mt-1"
                          />
                        )}

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <Icon className="w-4 h-4 text-muted-foreground" />
                            <span className="text-sm font-medium text-foreground">
                              {item.source_name || `${item.source_type} source`}
                            </span>
                            {item.trigger_type && (
                              <Badge variant="secondary" className="text-xs">
                                <Tag className="w-3 h-3 mr-1" />
                                {item.trigger_type}
                              </Badge>
                            )}
                            {item.status !== 'pending' && (
                              <Badge
                                variant={item.status === 'approved' ? 'default' : 'outline'}
                                className={
                                  item.status === 'approved'
                                    ? 'bg-green-600'
                                    : 'text-muted-foreground'
                                }
                              >
                                {item.status === 'approved' ? (
                                  <CheckCircle className="w-3 h-3 mr-1" />
                                ) : (
                                  <XCircle className="w-3 h-3 mr-1" />
                                )}
                                {item.status}
                              </Badge>
                            )}
                          </div>

                          <p className="text-foreground mb-2 whitespace-pre-wrap line-clamp-3">
                            {item.text}
                          </p>

                          <div className="flex items-center gap-4 text-xs text-muted-foreground">
                            {item.source_metadata?.author_name && (
                              <span className="flex items-center gap-1">
                                <User className="w-3 h-3" />
                                {item.source_metadata.author_name}
                              </span>
                            )}
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {formatTime(item.created_at)}
                            </span>
                          </div>
                        </div>

                        {statusFilter === 'pending' && (
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <Button
                              size="sm"
                              onClick={() => handleApprove(item.id)}
                              disabled={actionLoading === item.id}
                              className="bg-green-600 hover:bg-green-700"
                            >
                              {actionLoading === item.id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Check className="w-4 h-4" />
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleReject(item.id)}
                              disabled={actionLoading === item.id}
                              className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                            >
                              {actionLoading === item.id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <X className="w-4 h-4" />
                              )}
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1 || loading}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages || loading}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}
      </main>
    </div>
  );
}

export default function PendingFeedbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen pattern-bg">
        <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    }>
      <PendingFeedbackContent />
    </Suspense>
  );
}
