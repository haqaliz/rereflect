'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { feedbackAPI, FeedbackItem } from '@/lib/api/feedback';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
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
  Lightbulb,
  Search,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import Link from 'next/link';
import { Header } from '@/components/Header';
import { FeatureRequestsPageProvider, useFeatureRequestsPage } from '@/contexts/FeatureRequestsPageContext';

function FeatureRequestsPageContent() {
  const router = useRouter();
  const { searchQuery, currentPage, setSearchQuery, setCurrentPage } = useFeatureRequestsPage();
  const [feedbackList, setFeedbackList] = useState<FeedbackItem[]>([]);
  const [filteredList, setFilteredList] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const itemsPerPage = 10;

  useEffect(() => {
    fetchFeedback();
  }, []);

  useEffect(() => {
    filterFeedback();
  }, [feedbackList, searchQuery]);

  const fetchFeedback = async () => {
    try {
      // Fetch first page to get total count
      const firstPage = await feedbackAPI.list(1, 100, { sentiment: 'positive' });
      let allItems = [...firstPage.items];

      // Fetch remaining pages if needed
      const totalPages = firstPage.total_pages;
      if (totalPages > 1) {
        const pagePromises = [];
        for (let page = 2; page <= totalPages; page++) {
          pagePromises.push(feedbackAPI.list(page, 100, { sentiment: 'positive' }));
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
    let filtered = feedbackList.filter(item =>
      item.sentiment_label === 'positive' && item.tags && item.tags.length > 0
    );

    if (searchQuery) {
      filtered = filtered.filter(item =>
        item.text.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (item.tags && item.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase())))
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
          <p className="text-text-secondary font-medium">Loading feature requests...</p>
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
            <div className="p-3 bg-emerald-100 dark:bg-emerald-900/30 rounded-xl">
              <Lightbulb className="w-8 h-8 text-emerald-700 dark:text-emerald-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-text-primary">Feature Requests</h1>
              <p className="text-text-secondary text-lg">Customer suggestions and ideas for improvement</p>
            </div>
          </div>
        </div>

        {/* Search */}
        <Card className="p-6 animate-slide-up stagger-1">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5 z-10" />
            <Input
              type="text"
              placeholder="Search feature requests..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 h-10"
            />
          </div>
          <p className="text-sm text-muted-foreground mt-4 font-mono">
            Showing <span className="font-semibold text-foreground">{filteredList.length}</span> feature requests
          </p>
        </Card>

        {/* Feature Requests Table */}
        <Card className="animate-slide-up stagger-2">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20">ID</TableHead>
                  <TableHead>Feedback Text</TableHead>
                  <TableHead>Categories</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Sentiment</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {currentItems.length > 0 ? (
                  currentItems.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-bold font-mono text-muted-foreground">
                        #{item.id}
                      </TableCell>
                      <TableCell className="max-w-md">
                        <div className="flex items-start space-x-3">
                          <div className="flex-shrink-0 mt-1">
                            <div className="p-2 bg-emerald-100 dark:bg-emerald-900/30 rounded-lg border border-emerald-200 dark:border-emerald-800/50">
                              <Lightbulb className="w-4 h-4 text-emerald-700 dark:text-emerald-400" />
                            </div>
                          </div>
                          <p className="leading-relaxed">{item.text}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1.5">
                          {item.tags && item.tags.length > 0 ? (
                            item.tags.map((tag) => {
                              const styles = getTagStyles(tag);
                              return (
                                <Link key={tag} href={`/categories/${tag}`}>
                                  <Badge
                                    variant="outline"
                                    className="transition-all hover:scale-105 cursor-pointer"
                                    style={{
                                      backgroundColor: `${styles.color}15`,
                                      color: styles.color,
                                      borderColor: `${styles.color}30`
                                    }}
                                  >
                                    {styles.displayName}
                                  </Badge>
                                </Link>
                              );
                            })
                          ) : (
                            <span className="text-xs text-muted-foreground italic">No tags</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="font-mono">
                        {new Date(item.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        {item.source ? (
                          <Badge variant="secondary">{item.source}</Badge>
                        ) : (
                          <span className="text-xs text-muted-foreground italic">N/A</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge className="bg-success-bg text-success-text hover:bg-success-bg">
                          POSITIVE
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className="h-48 text-center">
                      <div className="flex flex-col items-center justify-center space-y-4">
                        <Lightbulb className="w-16 h-16 text-muted-foreground opacity-20" />
                        <div>
                          <h3 className="text-lg font-medium mb-2">No feature requests found</h3>
                          <p className="text-muted-foreground">
                            {searchQuery
                              ? 'Try adjusting your search query'
                              : 'No feature requests identified yet'}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </Card>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between animate-fade-in">
            <p className="text-sm text-text-secondary font-mono">
              Page <span className="font-semibold text-text-primary">{currentPage}</span> of <span className="font-semibold text-text-primary">{totalPages}</span>
            </p>
            <div className="flex items-center space-x-2">
              <Button
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                variant="outline"
                className="flex items-center space-x-1"
              >
                <ChevronLeft className="w-4 h-4" />
                <span>Previous</span>
              </Button>
              <Button
                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
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

export default function FeatureRequestsPage() {
  return (
    <FeatureRequestsPageProvider>
      <FeatureRequestsPageContent />
    </FeatureRequestsPageProvider>
  );
}
