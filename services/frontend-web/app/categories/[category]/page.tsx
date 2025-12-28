'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { feedbackAPI, FeedbackItem } from '@/lib/api/feedback';
import { Button } from '@/components/Button';
import { Header } from '@/components/Header';
import {
  Search,
  ChevronLeft,
  ChevronRight,
  Smile,
  Frown,
  Meh,
  Tag,
  MessageSquare
} from 'lucide-react';
import Link from 'next/link';

export default function CategoryPage() {
  const router = useRouter();
  const params = useParams();
  const category = params.category as string;

  const [feedbackList, setFeedbackList] = useState<FeedbackItem[]>([]);
  const [filteredList, setFilteredList] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  useEffect(() => {
    fetchFeedback();
  }, [category]);

  useEffect(() => {
    filterFeedback();
  }, [feedbackList, searchQuery]);

  const fetchFeedback = async () => {
    try {
      // Fetch first page to get total count
      const firstPage = await feedbackAPI.list(1, 100, { tag: category });
      let allItems = [...firstPage.items];

      // Fetch remaining pages if needed
      const totalPages = firstPage.total_pages;
      if (totalPages > 1) {
        const pagePromises = [];
        for (let page = 2; page <= totalPages; page++) {
          pagePromises.push(feedbackAPI.list(page, 100, { tag: category }));
        }
        const remainingPages = await Promise.all(pagePromises);
        remainingPages.forEach(pageData => {
          allItems = [...allItems, ...pageData.items];
        });
      }

      setFeedbackList(allItems);
      setFilteredList(allItems);
    } catch (err: any) {
      if (err.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  const filterFeedback = () => {
    let filtered = feedbackList;

    if (searchQuery) {
      filtered = filtered.filter(item =>
        item.text.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    setFilteredList(filtered);
    setCurrentPage(1);
  };

  const getTagStyles = (tag: string): { color: string; displayName: string } => {
    const tagMap: Record<string, { color: string; displayName: string }> = {
      'bug': { color: '#ef4444', displayName: 'Bug' },
      'performance': { color: '#f97316', displayName: 'Performance' },
      'ui-ux': { color: '#a855f7', displayName: 'UI/UX' },
      'feature-request': { color: '#3b82f6', displayName: 'Feature Request' },
      'mobile': { color: '#10b981', displayName: 'Mobile' },
      'web': { color: '#6366f1', displayName: 'Web' },
      'security': { color: '#eab308', displayName: 'Security' },
      'pricing': { color: '#ec4899', displayName: 'Pricing' },
      'support': { color: '#06b6d4', displayName: 'Support' },
      'documentation': { color: '#6b7280', displayName: 'Documentation' },
      'integration': { color: '#14b8a6', displayName: 'Integration' },
      'data': { color: '#8b5cf6', displayName: 'Data' },
      'notification': { color: '#f59e0b', displayName: 'Notification' },
      'search': { color: '#84cc16', displayName: 'Search' },
      'accessibility': { color: '#059669', displayName: 'Accessibility' },
    };
    return tagMap[tag] || { color: '#6b7280', displayName: tag };
  };

  const getSentimentIcon = (sentiment: string | null) => {
    switch (sentiment) {
      case 'positive':
        return <Smile className="w-5 h-5 text-success-text" />;
      case 'negative':
        return <Frown className="w-5 h-5 text-error-text" />;
      case 'neutral':
        return <Meh className="w-5 h-5 text-text-secondary" />;
      default:
        return <MessageSquare className="w-5 h-5 text-text-tertiary" />;
    }
  };

  const getSentimentBadge = (sentiment: string | null) => {
    switch (sentiment) {
      case 'positive':
        return <span className="px-2.5 py-1 bg-success-bg text-success-text rounded-lg text-xs font-semibold">Positive</span>;
      case 'negative':
        return <span className="px-2.5 py-1 bg-error-bg text-error-text rounded-lg text-xs font-semibold">Negative</span>;
      case 'neutral':
        return <span className="px-2.5 py-1 bg-background-secondary text-text-secondary rounded-lg text-xs font-semibold">Neutral</span>;
      default:
        return null;
    }
  };

  const categoryStyles = getTagStyles(category);

  // Pagination
  const totalPages = Math.ceil(filteredList.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const currentItems = filteredList.slice(startIndex, endIndex);

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
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center space-x-3 mb-2">
            <div
              className="p-3 rounded-xl"
              style={{ backgroundColor: `${categoryStyles.color}15` }}
            >
              <Tag
                className="w-8 h-8"
                style={{ color: categoryStyles.color }}
              />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-text-primary">
                {categoryStyles.displayName}
              </h1>
              <p className="text-text-secondary text-lg">
                All feedback tagged with "{categoryStyles.displayName}"
              </p>
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="surface-raised rounded-2xl p-6 animate-slide-up stagger-1">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-tertiary w-5 h-5" />
            <input
              type="text"
              placeholder="Search feedback..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-background-secondary border border-border rounded-xl text-text-primary placeholder:text-text-tertiary focus:ring-2 focus:ring-accent-amber-500 focus:border-accent-amber-500 transition-all"
            />
          </div>
          <p className="text-sm text-text-secondary mt-4 font-mono">
            Showing <span className="font-semibold text-text-primary">{filteredList.length}</span> feedback items
          </p>
        </div>

        {/* Feedback Table */}
        <div className="surface-raised rounded-2xl overflow-hidden border border-border-subtle animate-slide-up stagger-2">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead style={{ backgroundColor: 'var(--background-secondary)' }}>
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-bold text-text-secondary uppercase tracking-wider">
                    ID
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-text-secondary uppercase tracking-wider">
                    Feedback Text
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-text-secondary uppercase tracking-wider">
                    Sentiment
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-text-secondary uppercase tracking-wider">
                    Categories
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-text-secondary uppercase tracking-wider">
                    Date
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-text-secondary uppercase tracking-wider">
                    Source
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {currentItems.length > 0 ? (
                  currentItems.map((item) => (
                    <tr
                      key={item.id}
                      className="hover:bg-background-secondary transition-colors group"
                    >
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-text-secondary font-mono">
                        #{item.id}
                      </td>
                      <td className="px-6 py-4 text-sm text-text-primary max-w-md">
                        <p className="leading-relaxed">{item.text}</p>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center space-x-2">
                          <div
                            className="p-2 rounded-lg"
                            style={{ backgroundColor: `${categoryStyles.color}15` }}
                          >
                            {getSentimentIcon(item.sentiment_label)}
                          </div>
                          {getSentimentBadge(item.sentiment_label)}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex flex-wrap gap-1.5">
                          {item.tags && item.tags.length > 0 ? (
                            item.tags.map((tag) => {
                              const styles = getTagStyles(tag);
                              return (
                                <Link
                                  key={tag}
                                  href={`/categories/${tag}`}
                                  className="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold transition-all hover:scale-105 hover:shadow-md"
                                  style={{
                                    backgroundColor: `${styles.color}15`,
                                    color: styles.color,
                                    border: `1px solid ${styles.color}30`
                                  }}
                                >
                                  {styles.displayName}
                                </Link>
                              );
                            })
                          ) : (
                            <span className="text-xs text-text-tertiary italic">No tags</span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-text-secondary font-mono">
                        {new Date(item.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {item.source ? (
                          <span className="px-2.5 py-1 bg-background-secondary text-text-secondary rounded-lg text-xs font-medium">
                            {item.source}
                          </span>
                        ) : (
                          <span className="text-xs text-text-tertiary italic">N/A</span>
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center">
                      <Tag className="w-16 h-16 mx-auto mb-4 text-text-tertiary opacity-20" />
                      <h3 className="text-lg font-medium text-text-primary mb-2">No feedback found for this category</h3>
                      <p className="text-text-secondary">
                        {searchQuery
                          ? 'Try adjusting your search query'
                          : 'No feedback items in this category yet'}
                      </p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between animate-fade-in">
            <p className="text-sm text-text-secondary font-mono">
              Page <span className="font-semibold text-text-primary">{currentPage}</span> of <span className="font-semibold text-text-primary">{totalPages}</span>
            </p>
            <div className="flex items-center space-x-2">
              <Button
                onClick={() => setCurrentPage(Math.max(currentPage - 1, 1))}
                disabled={currentPage === 1}
                variant="outline"
                className="flex items-center space-x-1"
              >
                <ChevronLeft className="w-4 h-4" />
                <span>Previous</span>
              </Button>
              <Button
                onClick={() => setCurrentPage(Math.min(currentPage + 1, totalPages))}
                disabled={currentPage === totalPages}
                variant="outline"
                className="flex items-center space-x-1"
              >
                <span>Next</span>
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
