'use client';

import { useState, useRef, useCallback, Suspense, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { feedbackAPI, FeedbackItem, CSVImportResponse, FeedbackFilters } from '@/lib/api/feedback';
import { analytics } from '@/lib/analytics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sparkles,
  AlertTriangle,
  Check,
  Edit,
  Trash2,
  Upload,
  FileText,
  Inbox,
  RefreshCw,
  X,
  User,
} from 'lucide-react';
import Link from 'next/link';
import { FeedbackPageProvider, useFeedbackPage } from '@/contexts/FeedbackPageContext';
import { useRealtimeEvents } from '@/hooks/useRealtimeEvents';
import { DataTable } from '@/components/shared/data-table';
import { FeedbacksPageSkeleton } from '@/components/shared/page-skeletons';
import { MessageSquare } from 'lucide-react';
import { createColumns } from './columns';

function FeedbackPageContent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { searchQuery, sentimentFilter, urgentFilter, churnRiskFilter, customerEmailFilter, currentPage, setSearchQuery, setSentimentFilter, setUrgentFilter, setChurnRiskFilter, setCustomerEmailFilter, setCurrentPage } = useFeedbackPage();
  const [workflowStatusFilter, setWorkflowStatusFilter] = useState('');
  const [pageSize, setPageSize] = useState(20);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [newFeedbackText, setNewFeedbackText] = useState('');
  const [editingFeedback, setEditingFeedback] = useState<FeedbackItem | null>(null);
  const [deletingFeedback, setDeletingFeedback] = useState<FeedbackItem | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<CSVImportResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [debouncedSearch, setDebouncedSearch] = useState(searchQuery);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Build filters object from current state
  const buildFilters = useCallback((): FeedbackFilters => {
    const filters: FeedbackFilters = {};
    if (debouncedSearch) filters.search = debouncedSearch;
    if (sentimentFilter) filters.sentiment = sentimentFilter;
    if (customerEmailFilter) filters.customer_email = customerEmailFilter;
    if (urgentFilter) {
      filters.is_urgent = urgentFilter === 'urgent';
    }
    if (workflowStatusFilter) {
      filters.workflow_status = workflowStatusFilter;
    }
    if (churnRiskFilter) {
      switch (churnRiskFilter) {
        case 'low':
          filters.churn_risk_min = 0;
          filters.churn_risk_max = 39;
          break;
        case 'medium':
          filters.churn_risk_min = 40;
          filters.churn_risk_max = 70;
          break;
        case 'high':
          filters.churn_risk_min = 71;
          filters.churn_risk_max = 100;
          break;
        case 'at_risk':
          filters.churn_risk_min = 40;
          break;
      }
    }
    return filters;
  }, [debouncedSearch, sentimentFilter, customerEmailFilter, urgentFilter, workflowStatusFilter, churnRiskFilter]);

  // Fetch feedback with React Query
  const {
    data: feedbackResponse,
    isLoading: loading,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['feedback', currentPage, pageSize, buildFilters()],
    queryFn: async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        router.push('/login');
        throw new Error('No token');
      }
      return await feedbackAPI.list(currentPage, pageSize, buildFilters());
    },
    staleTime: 5 * 60 * 1000, // 5 min
    gcTime: 30 * 60 * 1000, // 30 min
  });

  const feedbackList = feedbackResponse?.items || [];
  const searching = searchQuery !== debouncedSearch;
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt) : null;

  useRealtimeEvents('feedback:*', () => {
    queryClient.invalidateQueries({ queryKey: ['feedback'] });
  });

  const handleAnalyze = async (selectedItems?: FeedbackItem[]) => {
    const idsToAnalyze = selectedItems ? selectedItems.map(item => item.id) : selectedIds;
    if (idsToAnalyze.length === 0) return;
    try {
      await feedbackAPI.analyze(idsToAnalyze);
      queryClient.invalidateQueries({ queryKey: ['feedback'] });
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
      queryClient.invalidateQueries({ queryKey: ['feedback'] });
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
      queryClient.invalidateQueries({ queryKey: ['feedback'] });
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
      queryClient.invalidateQueries({ queryKey: ['feedback'] });
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

  const importFile = async (file: File) => {
    if (!file.name.endsWith('.csv')) return;
    setShowImportDialog(false);
    setImporting(true);
    setImportResult(null);

    try {
      const result = await feedbackAPI.importCSV(file);
      setImportResult(result);
      analytics.csvUploaded(result.imported_count);
      queryClient.invalidateQueries({ queryKey: ['feedback'] });
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

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) importFile(file);
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) importFile(file);
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
              onClick={() => setShowImportDialog(true)}
              variant="outline"
              className="flex items-center space-x-2"
            >
              <Upload className="w-5 h-5" />
              <span>Import CSV</span>
            </Button>
            <Link href="/feedback-sources">
              <Button
                variant="default"
                className="flex items-center space-x-2"
              >
                <Inbox className="w-5 h-5" />
                <span>Sources</span>
              </Button>
            </Link>
          </div>
        </div>

        {/* Customer email filter chip */}
        {customerEmailFilter && (
          <div className="mb-4 animate-fade-in">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-sm">
              <User className="w-3.5 h-3.5 text-primary" />
              <span className="text-muted-foreground">Customer:</span>
              <span className="font-medium text-foreground">{customerEmailFilter}</span>
              <button
                onClick={() => setCustomerEmailFilter('')}
                className="ml-1 p-0.5 rounded-full hover:bg-primary/20 transition-colors"
              >
                <X className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground" />
              </button>
            </div>
          </div>
        )}

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

              {/* Churn Risk Filter */}
              <Select value={churnRiskFilter || "all"} onValueChange={(value) => setChurnRiskFilter(value === "all" ? "" : value)}>
                <SelectTrigger className="h-10 w-[180px]">
                  <SelectValue placeholder="All Risk Levels" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Risk Levels</SelectItem>
                  <SelectItem value="low">Low Risk (0-39)</SelectItem>
                  <SelectItem value="medium">Medium Risk (40-70)</SelectItem>
                  <SelectItem value="high">High Risk (71-100)</SelectItem>
                  <SelectItem value="at_risk">At Risk (40+)</SelectItem>
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
            serverSide
            totalCount={feedbackResponse?.total ?? 0}
            pageCount={feedbackResponse?.total_pages ?? 1}
            currentPage={currentPage}
            pageSize={pageSize}
            onPageChange={setCurrentPage}
            onPageSizeChange={setPageSize}
          />
        </Card>
      </main>

      {/* Import CSV Dialog */}
      <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <div className="flex items-center space-x-3 mb-2">
              <div className="p-2.5 bg-secondary rounded-xl">
                <Upload className="w-5 h-5 text-primary" />
              </div>
              <DialogTitle className="text-2xl">Import CSV</DialogTitle>
            </div>
            <DialogDescription>
              Upload a CSV file with your customer feedback. Each row will be automatically analyzed.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-5 py-4">
            {/* Drop Zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`
                relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all
                ${isDragging
                  ? 'border-primary bg-primary/5 scale-[1.02]'
                  : 'border-border hover:border-primary/50 hover:bg-muted/50'
                }
              `}
            >
              <div className="flex flex-col items-center space-y-3">
                <div className={`p-3 rounded-full transition-colors ${isDragging ? 'bg-primary/10' : 'bg-muted'}`}>
                  <Upload className={`w-6 h-6 ${isDragging ? 'text-primary' : 'text-muted-foreground'}`} />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {isDragging ? 'Drop your CSV file here' : 'Drag & drop your CSV file here'}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">or click to browse</p>
                </div>
              </div>
            </div>

            {/* Example CSV Format */}
            <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
              <p className="text-sm font-semibold text-foreground flex items-center gap-2">
                <FileText className="w-4 h-4 text-muted-foreground" />
                Example CSV Format
              </p>
              <div className="rounded-md border border-border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="text-xs font-mono h-8">feedback_text</TableHead>
                      <TableHead className="text-xs font-mono h-8">source</TableHead>
                      <TableHead className="text-xs font-mono h-8">customer_email</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell className="text-xs py-2">The checkout flow is confusing...</TableCell>
                      <TableCell className="text-xs py-2">survey</TableCell>
                      <TableCell className="text-xs py-2">jane@acme.com</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="text-xs py-2">Love the new dashboard!</TableCell>
                      <TableCell className="text-xs py-2">intercom</TableCell>
                      <TableCell className="text-xs py-2">tom@startup.io</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
              <div className="space-y-1.5 text-xs text-muted-foreground">
                <p>
                  <span className="font-medium text-foreground">feedback_text</span> is required — also accepts: <span className="font-mono">text, feedback, comment, message, description, review</span>
                </p>
                <p>
                  <span className="font-medium text-foreground">source</span> and <span className="font-medium text-foreground">customer_email</span> are optional
                </p>
                <p className="flex items-center gap-1.5 pt-1">
                  <Sparkles className="w-3.5 h-3.5" />
                  All imported feedback is automatically analyzed by AI
                </p>
              </div>
            </div>
          </div>
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
