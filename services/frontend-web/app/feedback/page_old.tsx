'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { feedbackAPI, FeedbackItem, CSVImportResponse } from '@/lib/api/feedback';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import {
  Brain,
  Plus,
  Sparkles,
  Filter,
  Search,
  Smile,
  Meh,
  Frown,
  AlertTriangle,
  Check,
  X,
  LayoutDashboard,
  MessageSquare,
  Settings as SettingsIcon,
  LogOut,
  Edit,
  Trash2,
  Upload,
  FileUp
} from 'lucide-react';
import Link from 'next/link';
import { authAPI } from '@/lib/api/auth';

export default function FeedbackPage() {
  const router = useRouter();
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
  const [searchQuery, setSearchQuery] = useState('');
  const [sentimentFilter, setSentimentFilter] = useState<string>('all');
  const [urgentFilter, setUrgentFilter] = useState<boolean | null>(null);
  const [userEmail, setUserEmail] = useState('');
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

        const [user, response] = await Promise.all([
          authAPI.getMe(),
          feedbackAPI.list(1, 100)
        ]);

        setUserEmail(user.email);
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

  // Filter feedback based on search and filters
  useEffect(() => {
    let filtered = feedbackList;

    // Search filter
    if (searchQuery) {
      filtered = filtered.filter(item =>
        item.text.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.extracted_issue?.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Sentiment filter
    if (sentimentFilter !== 'all') {
      filtered = filtered.filter(item => item.sentiment_label === sentimentFilter);
    }

    // Urgent filter
    if (urgentFilter !== null) {
      filtered = filtered.filter(item => item.is_urgent === urgentFilter);
    }

    setFilteredList(filtered);
  }, [searchQuery, sentimentFilter, urgentFilter, feedbackList]);

  const handleCreate = async () => {
    try {
      await feedbackAPI.create({ text: newFeedbackText, source: 'manual' });
      setNewFeedbackText('');
      setShowCreateModal(false);
      // Reload feedback
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
      // Reload feedback
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
      // Reload feedback
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
      // Reload feedback
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

  const handleLogout = () => {
    authAPI.logout();
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setImporting(true);
    setImportResult(null);

    try {
      const result = await feedbackAPI.importCSV(file);
      setImportResult(result);

      // Reload feedback list
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
        return <Smile className="w-5 h-5 text-green-600" />;
      case 'negative':
        return <Frown className="w-5 h-5 text-red-600" />;
      case 'neutral':
        return <Meh className="w-5 h-5 text-gray-600" />;
      default:
        return <MessageSquare className="w-5 h-5 text-gray-400" />;
    }
  };

  const getTagStyles = (tag: string): { bg: string; text: string; displayName: string } => {
    const tagMap: Record<string, { bg: string; text: string; displayName: string }> = {
      'bug': { bg: 'bg-red-100', text: 'text-red-800', displayName: 'Bug' },
      'performance': { bg: 'bg-orange-100', text: 'text-orange-800', displayName: 'Performance' },
      'ui-ux': { bg: 'bg-purple-100', text: 'text-purple-800', displayName: 'UI/UX' },
      'feature-request': { bg: 'bg-blue-100', text: 'text-blue-800', displayName: 'Feature Request' },
      'mobile': { bg: 'bg-green-100', text: 'text-green-800', displayName: 'Mobile' },
      'web': { bg: 'bg-indigo-100', text: 'text-indigo-800', displayName: 'Web' },
      'security': { bg: 'bg-yellow-100', text: 'text-yellow-800', displayName: 'Security' },
      'pricing': { bg: 'bg-pink-100', text: 'text-pink-800', displayName: 'Pricing' },
      'support': { bg: 'bg-cyan-100', text: 'text-cyan-800', displayName: 'Support' },
      'documentation': { bg: 'bg-gray-100', text: 'text-gray-800', displayName: 'Documentation' },
      'integration': { bg: 'bg-teal-100', text: 'text-teal-800', displayName: 'Integration' },
      'data': { bg: 'bg-violet-100', text: 'text-violet-800', displayName: 'Data' },
      'notification': { bg: 'bg-amber-100', text: 'text-amber-800', displayName: 'Notification' },
      'search': { bg: 'bg-lime-100', text: 'text-lime-800', displayName: 'Search' },
      'accessibility': { bg: 'bg-emerald-100', text: 'text-emerald-800', displayName: 'Accessibility' },
    };

    return tagMap[tag] || { bg: 'bg-gray-100', text: 'text-gray-800', displayName: tag };
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="w-16 h-16 border-4 border-purple-600 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-gray-600 font-medium">Loading feedback...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-gradient-to-br from-purple-600 to-blue-600 rounded-xl flex items-center justify-center">
                <Brain className="w-6 h-6 text-white" />
              </div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
                FeedbackAI
              </h1>
            </div>

            <div className="flex items-center space-x-6">
              <Link
                href="/dashboard"
                className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 font-medium transition-colors"
              >
                <LayoutDashboard className="w-5 h-5" />
                <span>Dashboard</span>
              </Link>
              <Link
                href="/feedback"
                className="flex items-center space-x-2 text-purple-600 hover:text-purple-700 font-medium transition-colors"
              >
                <MessageSquare className="w-5 h-5" />
                <span>Feedback</span>
              </Link>
              <Link
                href="/settings"
                className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 font-medium transition-colors"
              >
                <SettingsIcon className="w-5 h-5" />
                <span>Settings</span>
              </Link>

              <div className="h-6 w-px bg-gray-300"></div>

              <div className="flex items-center space-x-3">
                <div className="text-right">
                  <p className="text-sm font-medium text-gray-900">{userEmail}</p>
                  <p className="text-xs text-gray-500">Admin</p>
                </div>
                <button
                  onClick={handleLogout}
                  className="p-2 text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all"
                  title="Logout"
                >
                  <LogOut className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Title and Actions */}
        <div className="mb-8 flex justify-between items-start">
          <div>
            <h2 className="text-3xl font-bold text-gray-900 mb-2">Feedback Management</h2>
            <p className="text-gray-600">View, analyze, and manage customer feedback</p>
          </div>
          <div className="flex gap-3">
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
              variant="primary"
              className="flex items-center space-x-2"
            >
              <Plus className="w-5 h-5" />
              <span>Add Feedback</span>
            </Button>
          </div>
        </div>

        {/* Filters and Search */}
        <Card className="mb-6">
          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Search */}
              <div className="md:col-span-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                  <input
                    type="text"
                    placeholder="Search feedback text or issues..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  />
                </div>
              </div>

              {/* Sentiment Filter */}
              <div>
                <select
                  value={sentimentFilter}
                  onChange={(e) => setSentimentFilter(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                >
                  <option value="all">All Sentiments</option>
                  <option value="positive">Positive</option>
                  <option value="neutral">Neutral</option>
                  <option value="negative">Negative</option>
                </select>
              </div>

              {/* Urgent Filter */}
              <div>
                <select
                  value={urgentFilter === null ? 'all' : urgentFilter.toString()}
                  onChange={(e) =>
                    setUrgentFilter(e.target.value === 'all' ? null : e.target.value === 'true')
                  }
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                >
                  <option value="all">All Status</option>
                  <option value="true">Urgent Only</option>
                  <option value="false">Non-Urgent</option>
                </select>
              </div>
            </div>

            {/* Results count and actions */}
            <div className="mt-4 flex justify-between items-center">
              <p className="text-sm text-gray-600">
                Showing <span className="font-semibold">{filteredList.length}</span> of{' '}
                <span className="font-semibold">{feedbackList.length}</span> feedback items
              </p>

              {selectedIds.length > 0 && (
                <div className="flex items-center space-x-3">
                  <Button
                    onClick={handleAnalyze}
                    variant="primary"
                    className="flex items-center space-x-2"
                  >
                    <Sparkles className="w-5 h-5" />
                    <span>Analyze Selected ({selectedIds.length})</span>
                  </Button>
                  <Button
                    onClick={() => handleBulkDelete()}
                    variant="outline"
                    className="flex items-center space-x-2 text-red-600 hover:text-red-700 hover:bg-red-50 border-red-300"
                  >
                    <Trash2 className="w-5 h-5" />
                    <span>Delete Selected ({selectedIds.length})</span>
                  </Button>
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Feedback Table */}
        <Card>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    <input
                      type="checkbox"
                      checked={selectedIds.length === filteredList.length && filteredList.length > 0}
                      onChange={(e) =>
                        setSelectedIds(
                          e.target.checked ? filteredList.map((item) => item.id) : []
                        )
                      }
                      className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
                    />
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    ID
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Feedback Text
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Sentiment
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Categories
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredList.length > 0 ? (
                  filteredList.map((item) => (
                    <tr
                      key={item.id}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-6 py-4 whitespace-nowrap">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.id)}
                          onChange={() => toggleSelection(item.id)}
                          className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        #{item.id}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900 max-w-md">
                        <p className="line-clamp-2">{item.text}</p>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {item.sentiment_label ? (
                          <div className="flex items-center space-x-2">
                            {getSentimentIcon(item.sentiment_label)}
                            <span
                              className={`px-3 py-1 rounded-full text-xs font-semibold ${
                                item.sentiment_label === 'positive'
                                  ? 'bg-green-100 text-green-800'
                                  : item.sentiment_label === 'negative'
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-gray-100 text-gray-800'
                              }`}
                            >
                              {item.sentiment_label.charAt(0).toUpperCase() +
                                item.sentiment_label.slice(1)}
                            </span>
                          </div>
                        ) : (
                          <span className="text-gray-400 text-sm flex items-center space-x-1">
                            <MessageSquare className="w-4 h-4" />
                            <span>Not analyzed</span>
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {item.tags && item.tags.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5">
                            {item.tags.map((tag) => {
                              const styles = getTagStyles(tag);
                              return (
                                <Link
                                  key={tag}
                                  href={`/categories/${tag}`}
                                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${styles.bg} ${styles.text} hover:opacity-80 transition-opacity`}
                                >
                                  {styles.displayName}
                                </Link>
                              );
                            })}
                          </div>
                        ) : (
                          <span className="text-gray-400 text-sm">-</span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {item.is_urgent ? (
                          <span className="inline-flex items-center space-x-1 px-3 py-1 bg-red-100 text-red-800 rounded-full text-xs font-semibold">
                            <AlertTriangle className="w-4 h-4" />
                            <span>Urgent</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center space-x-1 px-3 py-1 bg-gray-100 text-gray-600 rounded-full text-xs font-semibold">
                            <Check className="w-4 h-4" />
                            <span>Normal</span>
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={() => handleEdit(item)}
                            className="p-2 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-lg transition-all"
                            title="Edit feedback"
                          >
                            <Edit className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(item)}
                            className="p-2 text-red-600 hover:text-red-800 hover:bg-red-50 rounded-lg transition-all"
                            title="Delete feedback"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center">
                      <MessageSquare className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                      <p className="text-gray-500 font-medium">No feedback found</p>
                      <p className="text-sm text-gray-400 mt-1">
                        Try adjusting your filters or add new feedback
                      </p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </main>

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg shadow-2xl">
            <div className="p-6 border-b border-gray-100">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900">Add New Feedback</h2>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="p-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Feedback Text
              </label>
              <textarea
                className="w-full border border-gray-300 rounded-lg p-3 focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                rows={6}
                value={newFeedbackText}
                onChange={(e) => setNewFeedbackText(e.target.value)}
                placeholder="Enter customer feedback here..."
              />
            </div>

            <div className="p-6 bg-gray-50 border-t border-gray-100 rounded-b-xl flex gap-3 justify-end">
              <Button
                onClick={() => setShowCreateModal(false)}
                variant="outline"
              >
                Cancel
              </Button>
              <Button
                onClick={handleCreate}
                variant="primary"
                disabled={!newFeedbackText.trim()}
                className="flex items-center space-x-2"
              >
                <Plus className="w-5 h-5" />
                <span>Create Feedback</span>
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showEditModal && editingFeedback && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg shadow-2xl">
            <div className="p-6 border-b border-gray-100">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900">Edit Feedback</h2>
                <button
                  onClick={() => {
                    setShowEditModal(false);
                    setEditingFeedback(null);
                    setNewFeedbackText('');
                  }}
                  className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="p-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Feedback Text
              </label>
              <textarea
                className="w-full border border-gray-300 rounded-lg p-3 focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                rows={6}
                value={newFeedbackText}
                onChange={(e) => setNewFeedbackText(e.target.value)}
                placeholder="Enter customer feedback here..."
              />
              <p className="mt-2 text-xs text-gray-500">
                Editing this feedback will trigger automatic re-analysis
              </p>
            </div>

            <div className="p-6 bg-gray-50 border-t border-gray-100 rounded-b-xl flex gap-3 justify-end">
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
                variant="primary"
                disabled={!newFeedbackText.trim()}
                className="flex items-center space-x-2"
              >
                <Edit className="w-5 h-5" />
                <span>Update Feedback</span>
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && deletingFeedback && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-md shadow-2xl">
            <div className="p-6 border-b border-gray-100">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900">Delete Feedback</h2>
                <button
                  onClick={() => {
                    setShowDeleteModal(false);
                    setDeletingFeedback(null);
                  }}
                  className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="p-6">
              <div className="flex items-center space-x-3 mb-4">
                <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="w-6 h-6 text-red-600" />
                </div>
                <div>
                  <p className="text-gray-900 font-medium">Are you sure?</p>
                  <p className="text-sm text-gray-500">This action cannot be undone.</p>
                </div>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-sm text-gray-700 line-clamp-3">
                  {deletingFeedback.text}
                </p>
              </div>
            </div>

            <div className="p-6 bg-gray-50 border-t border-gray-100 rounded-b-xl flex gap-3 justify-end">
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
                variant="danger"
                className="flex items-center space-x-2"
              >
                <Trash2 className="w-5 h-5" />
                <span>Delete</span>
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Import Result Modal */}
      {importResult && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-2xl shadow-2xl">
            <div className="p-6 border-b border-gray-100">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900">CSV Import Results</h2>
                <button
                  onClick={() => setImportResult(null)}
                  className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="p-6">
              {/* Stats */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="bg-blue-50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-blue-600">{importResult.total_rows}</p>
                  <p className="text-sm text-blue-800 mt-1">Total Rows</p>
                </div>
                <div className="bg-green-50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-green-600">{importResult.imported_count}</p>
                  <p className="text-sm text-green-800 mt-1">Imported</p>
                </div>
                <div className="bg-red-50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-red-600">{importResult.failed_count}</p>
                  <p className="text-sm text-red-800 mt-1">Failed</p>
                </div>
              </div>

              {/* Success Message */}
              {importResult.imported_count > 0 && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                  <div className="flex items-start space-x-3">
                    <Check className="w-5 h-5 text-green-600 mt-0.5" />
                    <div>
                      <p className="text-green-900 font-medium">
                        Successfully imported {importResult.imported_count} feedback item{importResult.imported_count !== 1 ? 's' : ''}
                      </p>
                      <p className="text-sm text-green-700 mt-1">
                        All imported feedback has been automatically analyzed
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Errors */}
              {importResult.errors.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="flex items-start space-x-3">
                    <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-red-900 font-medium mb-2">Errors encountered:</p>
                      <ul className="space-y-1 text-sm text-red-700">
                        {importResult.errors.map((error, index) => (
                          <li key={index} className="font-mono">• {error}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="p-6 bg-gray-50 border-t border-gray-100 rounded-b-xl flex justify-end">
              <Button
                onClick={() => setImportResult(null)}
                variant="primary"
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Importing Overlay */}
      {importing && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-8 shadow-2xl flex flex-col items-center space-y-4">
            <div className="w-16 h-16 border-4 border-purple-600 border-t-transparent rounded-full animate-spin"></div>
            <div className="text-center">
              <p className="text-lg font-semibold text-gray-900">Importing Feedback...</p>
              <p className="text-sm text-gray-500 mt-1">Analyzing each item automatically</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
