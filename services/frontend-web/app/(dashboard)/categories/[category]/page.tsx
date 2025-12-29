'use client';

import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { feedbackAPI, FeedbackItem, FeedbackFilters } from '@/lib/api/feedback';
import { Card } from '@/components/ui/card';
import { Tag } from 'lucide-react';
import { DataTable } from '@/components/shared/data-table';
import { DataTablePageSkeleton } from '@/components/shared/page-skeletons';
import { createColumns } from './columns';
import { getTagStyles } from '@/lib/category-utils';

export default function CategoryPage() {
  const router = useRouter();
  const params = useParams();
  const category = params.category as string;

  const [feedbackList, setFeedbackList] = useState<FeedbackItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const columns = useMemo(() => createColumns(), []);
  const categoryStyles = getTagStyles(category);

  const fetchFeedback = useCallback(async (filters?: FeedbackFilters) => {
    try {
      // Fetch with large page size to get all items for this category
      const response = await feedbackAPI.list(1, 1000, {
        tag: category,
        ...filters,
      });
      setFeedbackList(response.items);
      setTotalCount(response.items.length);
    } catch (err: any) {
      if (err.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
      setSearching(false);
    }
  }, [category, router]);

  useEffect(() => {
    setLoading(true);
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
          <div className="flex items-center space-x-3 mb-2">
            <div className="p-3 bg-secondary rounded-xl">
              <Tag className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground">
                {categoryStyles.displayName}
              </h1>
              <p className="text-muted-foreground text-lg">
                All feedback tagged with "{categoryStyles.displayName}"
              </p>
            </div>
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
            searchPlaceholder="Search feedback..."
            emptyIcon={Tag}
            emptyTitle="No feedback found for this category"
            emptyDescription={searchQuery ? 'Try adjusting your search query' : 'No feedback items in this category yet'}
            totalCount={totalCount}
          />
        </Card>
      </main>
    </div>
  );
}
