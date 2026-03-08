'use client';

import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { feedbackAPI, FeedbackItem, FeedbackFilters } from '@/lib/api/feedback';
import { Card } from '@/components/ui/card';
import { Lightbulb } from 'lucide-react';
import { DataTable } from '@/components/shared/data-table';
import { DataTablePageSkeleton } from '@/components/shared/page-skeletons';
import { createColumns } from './columns';
import { CreateIssueDialog } from '@/components/integrations/CreateIssueDialog';

export default function FeatureRequestsPage() {
  const router = useRouter();
  const [feedbackList, setFeedbackList] = useState<FeedbackItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const columns = useMemo(() => createColumns(), []);

  const fetchFeedback = useCallback(async (filters?: FeedbackFilters) => {
    try {
      // Fetch with large page size to get all feature requests
      const response = await feedbackAPI.list(1, 1000, {
        sentiment: 'positive',
        ...filters,
      });
      // Filter to only show items with tags (feature requests)
      const featureRequests = response.items.filter(item =>
        item.sentiment_label === 'positive' && item.tags && item.tags.length > 0
      );
      setFeedbackList(featureRequests);
      setTotalCount(featureRequests.length);
    } catch (err: any) {
      if (err.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
      setSearching(false);
    }
  }, [router]);

  useEffect(() => {
    fetchFeedback();
  }, [fetchFeedback]);

  // Debounced search effect
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    if (!loading) {
      setSearching(true);
      searchTimeoutRef.current = setTimeout(async () => {
        await fetchFeedback(searchQuery ? { search: searchQuery } : undefined);
      }, 300);
    }

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchQuery, fetchFeedback, loading]);

  const handleRowClick = (item: FeedbackItem) => {
    router.push(`/feedbacks/${item.id}`);
  };

  const handleAnalyze = async (selectedItems: FeedbackItem[]) => {
    try {
      const feedbackIds = selectedItems.map(item => item.id);
      await feedbackAPI.analyze(feedbackIds);
      await fetchFeedback(searchQuery ? { search: searchQuery } : undefined);
    } catch (err: any) {
      console.error('Error analyzing feedback:', err);
    }
  };

  const handleBulkDelete = async (selectedItems: FeedbackItem[]) => {
    try {
      const feedbackIds = selectedItems.map(item => item.id);
      await feedbackAPI.bulkDelete(feedbackIds);
      await fetchFeedback(searchQuery ? { search: searchQuery } : undefined);
    } catch (err: any) {
      console.error('Error deleting feedback:', err);
    }
  };

  if (loading) {
    return <DataTablePageSkeleton />;
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Lightbulb className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-foreground">Feature Requests</h1>
                <p className="text-muted-foreground text-lg">Customer suggestions and ideas for improvement</p>
              </div>
            </div>
            <CreateIssueDialog
              feedbackId={feedbackList[0]?.id ?? 0}
              aiTitle={feedbackList[0]?.extracted_issue ?? undefined}
              aiDescription={feedbackList[0]?.text}
            />
          </div>
        </div>

        {/* DataTable */}
        <Card className="p-6 animate-slide-up stagger-1">
          <DataTable
            columns={columns}
            data={feedbackList}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onRowClick={handleRowClick}
            onAnalyze={handleAnalyze}
            onBulkDelete={handleBulkDelete}
            isSearching={searching}
            searchPlaceholder="Search feature requests..."
            emptyIcon={Lightbulb}
            emptyTitle="No feature requests found"
            emptyDescription={searchQuery ? 'Try adjusting your search query' : 'No feature requests identified yet'}
            totalCount={totalCount}
          />
        </Card>
      </main>
    </div>
  );
}
