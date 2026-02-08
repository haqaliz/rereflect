'use client';

import { useEffect, useState, useRef, useCallback, Suspense } from 'react';
import { useRouter } from 'next/navigation';
import { feedbackAPI, FeedbackItem, CSVImportResponse, FeedbackFilters } from '@/lib/api/feedback';
import { analytics } from '@/lib/analytics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Plus,
  Sparkles,
  AlertTriangle,
  Check,
  Edit,
  Trash2,
  Upload,
  FileText,
  Inbox,
  RefreshCw
} from 'lucide-react';
import Link from 'next/link';
import { FeedbackPageProvider, useFeedbackPage } from '@/contexts/FeedbackPageContext';
import { DataTable } from '@/components/shared/data-table';
import { FeedbacksPageSkeleton } from '@/components/shared/page-skeletons';
import { MessageSquare } from 'lucide-react';
import { createColumns } from './columns';

function FeedbackPageContent() {
  const router = useRouter();
  const { searchQuery, sentimentFilter, urgentFilter, setSearchQuery, setSentimentFilter, setUrgentFilter } = useFeedbackPage();
  const [workflowStatusFilter, setWorkflowStatusFilter] = useState('');
  const [feedbackList, setFeedbackList] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [newFeedbackText, setNewFeedbackText] = useState('');
  const [editingFeedback, setEditingFeedback] = useState<FeedbackItem | null>(null);
  const [deletingFeedback, setDeletingFeedback] = useState<FeedbackItem | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<CSVImportResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Build filters object from current state
  const buildFilters = useCallback((search?: string): FeedbackFilters => {
    const filters: FeedbackFilters = {};
    if (search) filters.search = search;
    if (sentimentFilter) filters.sentiment = sentimentFilter;
    if (urgentFilter) {
      filters.is_urgent = urgentFilter === 'urgent';
    }
    if (workflowStatusFilter) {
      filters.workflow_status = workflowStatusFilter;
    }
    return filters;
  }, [sentimentFilter, urgentFilter, workflowStatusFilter]);

  // Fetch feedback with filters
  const fetchFeedback = useCallback(async (filters?: FeedbackFilters, isPolling = false) => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        router.push('/login');
        return;
      }

      const response = await feedbackAPI.list(1, 100, filters);
      setFeedbackList(response.items);
      if (!isPolling) {
        setLastUpdated(new Date());
      }
    } catch (err) {
      console.error('Failed to load feedback:', err);
    }
  }, [router]);

  // Initial load
  useEffect(() => {
    const initialLoad = async () => {
      await fetchFeedback(buildFilters(searchQuery));
      setLastUpdated(new Date());
      setLoading(false);
    };
    initialLoad();
  }, []);

  // Polling for auto-refresh (every 30 seconds)
  useEffect(() => {
    if (loading) return;

    pollingIntervalRef.current = setInterval(async () => {
      await fetchFeedback(buildFilters(searchQuery), true);
      setLastUpdated(new Date());
    }, 30000);

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, [loading, fetchFeedback, buildFilters, searchQuery]);

  // Debounced search - triggers backend query
  useEffect(() => {
    // Clear previous timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    // Set searching state
    setSearching(true);

    // Debounce the search
    searchTimeoutRef.current = setTimeout(async () => {
      await fetchFeedback(buildFilters(searchQuery));
      setSearching(false);
    }, 300);

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchQuery, buildFilters, fetchFeedback]);

  // Immediately fetch when filters change (no debounce needed for dropdowns)
  useEffect(() => {
    if (!loading) {
      fetchFeedback(buildFilters(searchQuery));
    }
  }, [sentimentFilter, urgentFilter, workflowStatusFilter]);

  const handleCreate = async () => {
    try {
      await feedbackAPI.create({ text: newFeedbackText, source: 'manual' });
      setNewFeedbackText('');
      setShowCreateModal(false);
      await fetchFeedback(buildFilters(searchQuery));
    } catch (err) {
      console.error('Failed to create feedback:', err);
    }
  };

  const handleAnalyze = async (selectedItems?: FeedbackItem[]) => {
    const idsToAnalyze = selectedItems ? selectedItems.map(item => item.id) : selectedIds;
    if (idsToAnalyze.length === 0) return;
    try {
      await feedbackAPI.analyze(idsToAnalyze);
      await fetchFeedback(buildFilters(searchQuery));
      setSelectedIds([]);
    } catch (err) {
      console.error('Failed to analyze feedback:', err);
    }
  };

  const handleEdit = (feedback: FeedbackItem) => {
    setEditingFeedback(feedback);
    setNewFeedbackText(feedback.text);
    setShowEditModal(true);
  };

  const handleUpdate = async () => {
    if (!editingFeedback) return;
    try {
      await feedbackAPI.update(editingFeedback.id, {
        text: newFeedbackText,
        source: editingFeedback.source || 'manual'
      });
      setNewFeedbackText('');
      setEditingFeedback(null);
      setShowEditModal(false);
      await fetchFeedback(buildFilters(searchQuery));
    } catch (err) {
      console.error('Failed to update feedback:', err);
    }
  };

  const handleDelete = (feedback: FeedbackItem) => {
    setDeletingFeedback(feedback);
    setShowDeleteModal(true);
  };

  const confirmDelete = async () => {
    if (!deletingFeedback) return;
    try {
      await feedbackAPI.delete(deletingFeedback.id);
      setDeletingFeedback(null);
      setShowDeleteModal(false);
      await fetchFeedback(buildFilters(searchQuery));
    } catch (err) {
      console.error('Failed to delete feedback:', err);
    }
  };

  const handleBulkDelete = async (selectedItems?: FeedbackItem[]) => {
    const idsToDelete = selectedItems ? selectedItems.map(item => item.id) : selectedIds;
    if (idsToDelete.length === 0) return;
    const confirmed = window.confirm(
      `Are you sure you want to delete ${idsToDelete.length} feedback item(s)? This action cannot be undone.`
    );
    if (!confirmed) return;
    try {
      await feedbackAPI.bulkDelete(idsToDelete);
      setSelectedIds([]);
      await fetchFeedback(buildFilters(searchQuery));
    } catch (err) {
      console.error('Failed to bulk delete feedback:', err);
      alert('Failed to delete feedback items. Please try again.');
    }
  };

  const toggleSelection = (id: number) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setImporting(true);
    setImportResult(null);

    try {
      const result = await feedbackAPI.importCSV(file);
      setImportResult(result);
      analytics.csvUploaded(result.imported_count);
      await fetchFeedback(buildFilters(searchQuery));
    } catch (err: any) {
      console.error('Failed to import CSV:', err);
      setImportResult({
        total_rows: 0,
        imported_count: 0,
        failed_count: 0,
        errors: [err.response?.data?.detail || 'Failed to import CSV file']
      });
    } finally {
      setImporting(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };


  if (loading) {
    return <FeedbacksPageSkeleton />;
  }

  return (
    <div className="min-h-screen pattern-bg">
      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Title and Actions */}
        <div className="mb-8 flex justify-between items-start">
          <div className="animate-fade-in">
            <h2 className="text-4xl font-bold text-foreground mb-2">Feedbacks</h2>
            <div className="flex items-center gap-3">
              <p className="text-muted-foreground text-lg">View, analyze, and manage customer feedbacks</p>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground bg-muted px-2 py-1 rounded-full">
                <RefreshCw className="w-3 h-3 animate-spin" style={{ animationDuration: '3s' }} />
                Auto-refresh
              </span>
            </div>
          </div>
          <div className="flex gap-3 animate-slide-up">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleFileSelect}
              className="hidden"
            />
            <Button
              onClick={() => {
                setShowImportModal(true);
                fileInputRef.current?.click();
              }}
              variant="outline"
              className="flex items-center space-x-2"
            >
              <Upload className="w-5 h-5" />
              <span>Import CSV</span>
            </Button>
            <Link href="/feedback-sources">
              <Button
                variant="outline"
                className="flex items-center space-x-2"
              >
                <Inbox className="w-5 h-5" />
                <span>Sources</span>
              </Button>
            </Link>
            <Button
              onClick={() => setShowCreateModal(true)}
              variant="default"
              className="flex items-center space-x-2"
            >
              <Plus className="w-5 h-5" />
              <span>Add Feedback</span>
            </Button>
          </div>
        </div>

        {/* Filters */}
        <Card className="mb-6 animate-slide-up stagger-1">
          <div className="p-6">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-4">Filters</h3>
            <div className="flex flex-wrap gap-4">
              {/* Sentiment Filter */}
              <Select value={sentimentFilter || "all"} onValueChange={(value) => setSentimentFilter(value === "all" ? "" : value)}>
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

              {/* Workflow Status Filter */}
              <Select value={workflowStatusFilter || "all"} onValueChange={(value) => setWorkflowStatusFilter(value === "all" ? "" : value)}>
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

              {/* Urgent Filter */}
              <Select value={urgentFilter || "all"} onValueChange={(value) => setUrgentFilter(value === "all" ? "" : value)}>
                <SelectTrigger className="h-10 w-[180px]">
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="urgent">Urgent Only</SelectItem>
                  <SelectItem value="non-urgent">Non-Urgent</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </Card>

        {/* Feedback Table */}
        <Card className="animate-slide-up stagger-2 p-6">
          <DataTable
            columns={createColumns(handleEdit, handleDelete)}
            data={feedbackList}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onAnalyze={handleAnalyze}
            onBulkDelete={handleBulkDelete}
            onRowClick={(item) => router.push(`/feedbacks/${item.id}`)}
            isSearching={searching}
            searchPlaceholder="Search feedback text or issues..."
            emptyIcon={MessageSquare}
            emptyTitle="No feedback found"
            emptyDescription="Try adjusting your filters or add new feedback"
          />
        </Card>
      </main>

      {/* Create Modal */}
      <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <div className="flex items-center space-x-3 mb-2">
              <div className="p-2.5 bg-secondary rounded-xl">
                <Plus className="w-5 h-5 text-primary" />
              </div>
              <DialogTitle className="text-2xl">Add New Feedback</DialogTitle>
            </div>
            <DialogDescription>
              Create a new feedback entry to be analyzed by the system.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="feedback-text" className="text-sm font-semibold uppercase tracking-wide">
                Feedback Text
              </Label>
              <Textarea
                id="feedback-text"
                rows={6}
                value={newFeedbackText}
                onChange={(e) => setNewFeedbackText(e.target.value)}
                placeholder="Enter customer feedback here..."
                className="resize-none"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => setShowCreateModal(false)}
              variant="outline"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              variant="default"
              disabled={!newFeedbackText.trim()}
              className="flex items-center space-x-2"
            >
              <Plus className="w-5 h-5" />
              <span>Create Feedback</span>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Modal */}
      <Dialog open={showEditModal} onOpenChange={(open) => {
        setShowEditModal(open);
        if (!open) {
          setEditingFeedback(null);
          setNewFeedbackText('');
        }
      }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <div className="flex items-center space-x-3 mb-2">
              <div className="p-2.5 bg-secondary rounded-xl">
                <Edit className="w-5 h-5 text-[var(--chart-5)]" />
              </div>
              <DialogTitle className="text-2xl">Edit Feedback</DialogTitle>
            </div>
            <DialogDescription>
              Update the feedback text. Changes will trigger automatic re-analysis.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-feedback-text" className="text-sm font-semibold uppercase tracking-wide">
                Feedback Text
              </Label>
              <Textarea
                id="edit-feedback-text"
                rows={6}
                value={newFeedbackText}
                onChange={(e) => setNewFeedbackText(e.target.value)}
                placeholder="Enter customer feedback here..."
                className="resize-none"
              />
              <p className="text-xs text-muted-foreground flex items-center space-x-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Editing will trigger automatic re-analysis</span>
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                setShowEditModal(false);
                setEditingFeedback(null);
                setNewFeedbackText('');
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button
              onClick={handleUpdate}
              variant="default"
              disabled={!newFeedbackText.trim()}
              className="flex items-center space-x-2"
            >
              <Edit className="w-5 h-5" />
              <span>Update Feedback</span>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Modal */}
      <Dialog open={showDeleteModal} onOpenChange={(open) => {
        setShowDeleteModal(open);
        if (!open) {
          setDeletingFeedback(null);
        }
      }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="flex items-center space-x-3 mb-2">
              <div className="p-2.5 bg-destructive/10 rounded-xl">
                <Trash2 className="w-5 h-5 text-destructive" />
              </div>
              <DialogTitle className="text-2xl">Delete Feedback</DialogTitle>
            </div>
            <DialogDescription>
              This action cannot be undone. This will permanently delete the feedback item.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <Alert variant="destructive">
              <AlertTriangle className="w-4 h-4" />
              <AlertDescription>
                Are you sure you want to delete this feedback?
              </AlertDescription>
            </Alert>
            {deletingFeedback && (
              <div className="bg-muted rounded-lg p-4 border border-border">
                <p className="text-sm text-foreground leading-relaxed line-clamp-3">
                  {deletingFeedback.text}
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                setShowDeleteModal(false);
                setDeletingFeedback(null);
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button
              onClick={confirmDelete}
              variant="destructive"
              className="flex items-center space-x-2"
            >
              <Trash2 className="w-5 h-5" />
              <span>Delete</span>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Import Result Modal */}
      <Dialog open={!!importResult} onOpenChange={(open) => !open && setImportResult(null)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <div className="flex items-center space-x-3 mb-2">
              <div className="p-2.5 bg-secondary rounded-xl">
                <FileText className="w-5 h-5 text-[var(--chart-5)]" />
              </div>
              <DialogTitle className="text-2xl">CSV Import Results</DialogTitle>
            </div>
            <DialogDescription>
              Summary of the CSV import operation and any errors encountered.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-6 py-4">
            {/* Stats */}
            <div className="grid grid-cols-3 gap-4">
              <div className="rounded-xl p-5 text-center border-2" style={{ backgroundColor: 'color-mix(in oklch, var(--chart-5) 15%, transparent)', borderColor: 'color-mix(in oklch, var(--chart-5) 30%, transparent)' }}>
                <p className="text-3xl font-bold font-mono" style={{ color: 'var(--chart-5)' }}>{importResult?.total_rows}</p>
                <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">Total Rows</p>
              </div>
              <div className="rounded-xl p-5 text-center border-2" style={{ backgroundColor: 'color-mix(in oklch, var(--chart-2) 15%, transparent)', borderColor: 'color-mix(in oklch, var(--chart-2) 30%, transparent)' }}>
                <p className="text-3xl font-bold font-mono" style={{ color: 'var(--chart-2)' }}>{importResult?.imported_count}</p>
                <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">Imported</p>
              </div>
              <div className="rounded-xl p-5 text-center border-2" style={{ backgroundColor: 'color-mix(in oklch, var(--destructive) 15%, transparent)', borderColor: 'color-mix(in oklch, var(--destructive) 30%, transparent)' }}>
                <p className="text-3xl font-bold font-mono text-destructive">{importResult?.failed_count}</p>
                <p className="text-sm text-muted-foreground mt-2 font-semibold uppercase tracking-wide">Failed</p>
              </div>
            </div>

            {/* Success Message */}
            {importResult && importResult.imported_count > 0 && (
              <Alert variant="default" className="border-2" style={{ backgroundColor: 'color-mix(in oklch, var(--chart-2) 15%, transparent)', borderColor: 'color-mix(in oklch, var(--chart-2) 30%, transparent)' }}>
                <Check className="w-4 h-4" style={{ color: 'var(--chart-2)' }} />
                <AlertDescription style={{ color: 'var(--chart-2)' }}>
                  <p className="font-semibold">
                    Successfully imported {importResult.imported_count} feedback item{importResult.imported_count !== 1 ? 's' : ''}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1.5 flex items-center space-x-1.5">
                    <Sparkles className="w-4 h-4" />
                    <span>All imported feedback has been automatically analyzed</span>
                  </p>
                </AlertDescription>
              </Alert>
            )}

            {/* Errors */}
            {importResult && importResult.errors.length > 0 && (
              <Alert variant="destructive">
                <AlertTriangle className="w-4 h-4" />
                <AlertDescription>
                  <p className="font-semibold mb-3">Errors encountered:</p>
                  <ul className="space-y-2 text-sm">
                    {importResult.errors.map((error, index) => (
                      <li key={index} className="font-mono bg-background rounded-lg p-2">• {error}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}
          </div>
          <DialogFooter>
            <Button
              onClick={() => setImportResult(null)}
              variant="default"
            >
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Importing Overlay */}
      {importing && (
        <div className="fixed inset-0 bg-black bg-opacity-70 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <Card className="rounded-2xl p-10 shadow-xl flex flex-col items-center space-y-5 animate-scale-in">
            <div className="relative w-20 h-20">
              <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
              <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
            </div>
            <div className="text-center">
              <p className="text-xl font-bold text-foreground mb-2">Importing Feedback...</p>
              <p className="text-sm text-muted-foreground flex items-center space-x-1.5 justify-center">
                <Sparkles className="w-4 h-4" />
                <span>Analyzing each item automatically</span>
              </p>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function FeedbackPageWrapper() {
  return (
    <FeedbackPageProvider>
      <FeedbackPageContent />
    </FeedbackPageProvider>
  );
}

export default function FeedbackPage() {
  return (
    <Suspense fallback={<FeedbacksPageSkeleton />}>
      <FeedbackPageWrapper />
    </Suspense>
  );
}
