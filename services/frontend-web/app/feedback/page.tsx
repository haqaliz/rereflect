'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { feedbackAPI, FeedbackItem, CSVImportResponse } from '@/lib/api/feedback';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Plus,
  Sparkles,
  Search,
  Smile,
  Meh,
  Frown,
  AlertTriangle,
  Check,
  X,
  Edit,
  Trash2,
  Upload,
  FileText,
  MessageSquare
} from 'lucide-react';
import Link from 'next/link';
import { Header } from '@/components/Header';
import { FeedbackPageProvider, useFeedbackPage } from '@/contexts/FeedbackPageContext';
import { DataTable } from './data-table';
import { createColumns } from './columns';

function FeedbackPageContent() {
  const router = useRouter();
  const { searchQuery, sentimentFilter, urgentFilter, setSearchQuery, setSentimentFilter, setUrgentFilter } = useFeedbackPage();
  const [feedbackList, setFeedbackList] = useState<FeedbackItem[]>([]);
  const [filteredList, setFilteredList] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
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

  useEffect(() => {
    const fetchFeedback = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
          return;
        }

        const response = await feedbackAPI.list(1, 100);

        setFeedbackList(response.items);
        setFilteredList(response.items);
      } catch (err) {
        console.error('Failed to load feedback:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchFeedback();
  }, [router]);

  useEffect(() => {
    let filtered = feedbackList;

    if (searchQuery) {
      filtered = filtered.filter(item =>
        item.text.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.extracted_issue?.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    if (sentimentFilter) {
      filtered = filtered.filter(item => item.sentiment_label === sentimentFilter);
    }

    if (urgentFilter) {
      filtered = filtered.filter(item => item.is_urgent === (urgentFilter === 'urgent'));
    }

    setFilteredList(filtered);
  }, [searchQuery, sentimentFilter, urgentFilter, feedbackList]);

  const handleCreate = async () => {
    try {
      await feedbackAPI.create({ text: newFeedbackText, source: 'manual' });
      setNewFeedbackText('');
      setShowCreateModal(false);
      const response = await feedbackAPI.list(1, 100);
      setFeedbackList(response.items);
      setFilteredList(response.items);
    } catch (err) {
      console.error('Failed to create feedback:', err);
    }
  };

  const handleAnalyze = async () => {
    if (selectedIds.length === 0) return;
    try {
      await feedbackAPI.analyze(selectedIds);
      const response = await feedbackAPI.list(1, 100);
      setFeedbackList(response.items);
      setFilteredList(response.items);
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
      const response = await feedbackAPI.list(1, 100);
      setFeedbackList(response.items);
      setFilteredList(response.items);
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
      const response = await feedbackAPI.list(1, 100);
      setFeedbackList(response.items);
      setFilteredList(response.items);
    } catch (err) {
      console.error('Failed to delete feedback:', err);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    const confirmed = window.confirm(
      `Are you sure you want to delete ${selectedIds.length} feedback item(s)? This action cannot be undone.`
    );
    if (!confirmed) return;
    try {
      await feedbackAPI.bulkDelete(selectedIds);
      setSelectedIds([]);
      const response = await feedbackAPI.list(1, 100);
      setFeedbackList(response.items);
      setFilteredList(response.items);
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
      const response = await feedbackAPI.list(1, 100);
      setFeedbackList(response.items);
      setFilteredList(response.items);
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

  const getSentimentIcon = (sentiment: string | null) => {
    switch (sentiment) {
      case 'positive':
        return <Smile className="w-5 h-5 text-emerald-600" />;
      case 'negative':
        return <Frown className="w-5 h-5 text-red-600" />;
      case 'neutral':
        return <Meh className="w-5 h-5 text-amber-600" />;
      default:
        return <MessageSquare className="w-5 h-5" style={{ color: 'var(--text-tertiary)' }} />;
    }
  };

  const getTagStyles = (tag: string): { bg: string; text: string; displayName: string } => {
    const tagMap: Record<string, { bg: string; text: string; displayName: string }> = {
      'bug': { bg: 'bg-red-500/10 border-red-500/20', text: 'text-red-600 dark:text-red-400', displayName: 'Bug' },
      'performance': { bg: 'bg-orange-500/10 border-orange-500/20', text: 'text-orange-600 dark:text-orange-400', displayName: 'Performance' },
      'ui-ux': { bg: 'bg-purple-500/10 border-purple-500/20', text: 'text-purple-600 dark:text-purple-400', displayName: 'UI/UX' },
      'feature-request': { bg: 'bg-blue-500/10 border-blue-500/20', text: 'text-blue-600 dark:text-blue-400', displayName: 'Feature Request' },
      'mobile': { bg: 'bg-green-500/10 border-green-500/20', text: 'text-green-600 dark:text-green-400', displayName: 'Mobile' },
      'web': { bg: 'bg-indigo-500/10 border-indigo-500/20', text: 'text-indigo-600 dark:text-indigo-400', displayName: 'Web' },
      'security': { bg: 'bg-yellow-500/10 border-yellow-500/20', text: 'text-yellow-600 dark:text-yellow-400', displayName: 'Security' },
      'pricing': { bg: 'bg-pink-500/10 border-pink-500/20', text: 'text-pink-600 dark:text-pink-400', displayName: 'Pricing' },
      'support': { bg: 'bg-cyan-500/10 border-cyan-500/20', text: 'text-cyan-600 dark:text-cyan-400', displayName: 'Support' },
      'documentation': { bg: 'bg-gray-500/10 border-gray-500/20', text: 'text-gray-600 dark:text-gray-400', displayName: 'Documentation' },
      'integration': { bg: 'bg-teal-500/10 border-teal-500/20', text: 'text-teal-600 dark:text-teal-400', displayName: 'Integration' },
      'data': { bg: 'bg-violet-500/10 border-violet-500/20', text: 'text-violet-600 dark:text-violet-400', displayName: 'Data' },
      'notification': { bg: 'bg-amber-500/10 border-amber-500/20', text: 'text-amber-600 dark:text-amber-400', displayName: 'Notification' },
      'search': { bg: 'bg-lime-500/10 border-lime-500/20', text: 'text-lime-600 dark:text-lime-400', displayName: 'Search' },
      'accessibility': { bg: 'bg-emerald-500/10 border-emerald-500/20', text: 'text-emerald-600 dark:text-emerald-400', displayName: 'Accessibility' },
    };
    return tagMap[tag] || { bg: 'bg-gray-500/10 border-gray-500/20', text: 'text-gray-600 dark:text-gray-400', displayName: tag };
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-accent-amber-200 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-accent-amber-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-text-secondary font-medium">Loading feedback...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <Header />

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Title and Actions */}
        <div className="mb-8 flex justify-between items-start">
          <div className="animate-fade-in">
            <h2 className="text-4xl font-bold text-text-primary mb-2">Feedback Management</h2>
            <p className="text-text-secondary text-lg">View, analyze, and manage customer feedback</p>
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

        {/* Filters and Search */}
        <Card className="mb-6 animate-slide-up stagger-1">
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Search */}
              <div className="md:col-span-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5 z-10" />
                  <Input
                    type="text"
                    placeholder="Search feedback text or issues..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10 h-10"
                  />
                </div>
              </div>

              {/* Sentiment Filter */}
              <Select value={sentimentFilter || "all"} onValueChange={(value) => setSentimentFilter(value === "all" ? "" : value)}>
                <SelectTrigger className="h-10">
                  <SelectValue placeholder="All Sentiments" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sentiments</SelectItem>
                  <SelectItem value="positive">Positive</SelectItem>
                  <SelectItem value="neutral">Neutral</SelectItem>
                  <SelectItem value="negative">Negative</SelectItem>
                </SelectContent>
              </Select>

              {/* Urgent Filter */}
              <Select value={urgentFilter || "all"} onValueChange={(value) => setUrgentFilter(value === "all" ? "" : value)}>
                <SelectTrigger className="h-10">
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="urgent">Urgent Only</SelectItem>
                  <SelectItem value="non-urgent">Non-Urgent</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Results count and actions */}
            <div className="mt-6 flex justify-between items-center">
              <p className="text-sm text-text-secondary font-mono">
                Showing <span className="font-bold text-text-primary">{filteredList.length}</span> of{' '}
                <span className="font-bold text-text-primary">{feedbackList.length}</span> items
              </p>

              {selectedIds.length > 0 && (
                <div className="flex items-center space-x-3">
                  <Button
                    onClick={handleAnalyze}
                    variant="default"
                    className="flex items-center space-x-2"
                  >
                    <Sparkles className="w-5 h-5" />
                    <span>Analyze ({selectedIds.length})</span>
                  </Button>
                  <Button
                    onClick={() => handleBulkDelete()}
                    variant="outline"
                    className="flex items-center space-x-2 text-error-text hover:bg-error-bg border-error-border"
                  >
                    <Trash2 className="w-5 h-5" />
                    <span>Delete ({selectedIds.length})</span>
                  </Button>
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Feedback Table */}
        <Card className="animate-slide-up stagger-2 p-6">
          <DataTable
            columns={createColumns(handleEdit, handleDelete)}
            data={filteredList}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
          />
        </Card>
      </main>

      {/* Create Modal */}
      <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <div className="flex items-center space-x-3 mb-2">
              <div className="p-2.5 bg-accent-amber-100 rounded-xl">
                <Plus className="w-5 h-5 text-accent-amber-700" />
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
              <div className="p-2.5 bg-info-bg rounded-xl">
                <Edit className="w-5 h-5 text-info-text" />
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
              <p className="text-xs text-text-tertiary flex items-center space-x-1.5">
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
              <div className="p-2.5 bg-error-bg rounded-xl">
                <Trash2 className="w-5 h-5 text-error-text" />
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
                <p className="text-sm text-text-primary leading-relaxed line-clamp-3">
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
              <div className="p-2.5 bg-info-bg rounded-xl">
                <FileText className="w-5 h-5 text-info-text" />
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
              <div className="bg-info-bg rounded-xl p-5 text-center border-2 border-info-border">
                <p className="text-3xl font-bold text-info-text font-mono">{importResult?.total_rows}</p>
                <p className="text-sm text-text-secondary mt-2 font-semibold uppercase tracking-wide">Total Rows</p>
              </div>
              <div className="bg-success-bg rounded-xl p-5 text-center border-2 border-success-border">
                <p className="text-3xl font-bold text-success-text font-mono">{importResult?.imported_count}</p>
                <p className="text-sm text-text-secondary mt-2 font-semibold uppercase tracking-wide">Imported</p>
              </div>
              <div className="bg-error-bg rounded-xl p-5 text-center border-2 border-error-border">
                <p className="text-3xl font-bold text-error-text font-mono">{importResult?.failed_count}</p>
                <p className="text-sm text-text-secondary mt-2 font-semibold uppercase tracking-wide">Failed</p>
              </div>
            </div>

            {/* Success Message */}
            {importResult && importResult.imported_count > 0 && (
              <Alert variant="default" className="bg-success-bg border-success-border">
                <Check className="w-4 h-4 text-success-text" />
                <AlertDescription className="text-success-text">
                  <p className="font-semibold">
                    Successfully imported {importResult.imported_count} feedback item{importResult.imported_count !== 1 ? 's' : ''}
                  </p>
                  <p className="text-sm text-text-secondary mt-1.5 flex items-center space-x-1.5">
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
          <div className="surface-raised rounded-2xl p-10 shadow-xl flex flex-col items-center space-y-5 animate-scale-in">
            <div className="relative w-20 h-20">
              <div className="absolute inset-0 border-4 border-accent-amber-200 rounded-full"></div>
              <div className="absolute inset-0 border-4 border-accent-amber-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
            <div className="text-center">
              <p className="text-xl font-bold text-text-primary mb-2">Importing Feedback...</p>
              <p className="text-sm text-text-secondary flex items-center space-x-1.5 justify-center">
                <Sparkles className="w-4 h-4" />
                <span>Analyzing each item automatically</span>
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function FeedbackPage() {
  return (
    <FeedbackPageProvider>
      <FeedbackPageContent />
    </FeedbackPageProvider>
  );
}
