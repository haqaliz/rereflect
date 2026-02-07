'use client';

import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { feedbackAPI, FeedbackItem, FeedbackFilters } from '@/lib/api/feedback';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { UserX } from 'lucide-react';
import { DataTable } from '@/components/shared/data-table';
import { DataTablePageSkeleton } from '@/components/shared/page-skeletons';
import { createColumns } from './columns';

export default function ChurnRisksPage() {
  const router = useRouter();
  const [feedbackList, setFeedbackList] = useState<FeedbackItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState<string>('all');
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const columns = useMemo(() => createColumns(), []);

  // Summary counts
  const highCount = feedbackList.filter(f => (f.churn_risk_score ?? 0) > 70).length;
  const mediumCount = feedbackList.filter(f => {
    const s = f.churn_risk_score ?? 0;
    return s >= 40 && s <= 70;
  }).length;
  const lowCount = feedbackList.filter(f => {
    const s = f.churn_risk_score ?? 0;
    return s > 0 && s < 40;
  }).length;

  const buildFilters = useCallback((): FeedbackFilters => {
    const filters: FeedbackFilters = {
      sort_by: 'churn_risk_score',
      sort_order: 'desc',
    };
    if (searchQuery) filters.search = searchQuery;
    if (riskFilter === 'high') {
      filters.churn_risk_min = 71;
    } else if (riskFilter === 'medium') {
      filters.churn_risk_min = 40;
      filters.churn_risk_max = 70;
    } else if (riskFilter === 'low') {
      filters.churn_risk_min = 1;
      filters.churn_risk_max = 39;
    } else {
      // "all" — only show items that have a churn risk score > 0
      filters.churn_risk_min = 1;
    }
    return filters;
  }, [searchQuery, riskFilter]);

  const fetchFeedback = useCallback(async (filters?: FeedbackFilters) => {
    try {
      const response = await feedbackAPI.list(1, 1000, filters);
      const items = response.items.filter(item => (item.churn_risk_score ?? 0) > 0);
      setFeedbackList(items);
      setTotalCount(items.length);
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
    fetchFeedback(buildFilters());
  }, [fetchFeedback, buildFilters]);

  // Debounced search effect
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    if (!loading) {
      setSearching(true);
      searchTimeoutRef.current = setTimeout(async () => {
        await fetchFeedback(buildFilters());
      }, 300);
    }

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchQuery, riskFilter, fetchFeedback, loading, buildFilters]);

  const handleRowClick = (item: FeedbackItem) => {
    router.push(`/feedbacks/${item.id}`);
  };

  const handleAnalyze = async (selectedItems: FeedbackItem[]) => {
    try {
      const feedbackIds = selectedItems.map(item => item.id);
      await feedbackAPI.analyze(feedbackIds);
      await fetchFeedback(buildFilters());
    } catch (err: any) {
      console.error('Error analyzing feedback:', err);
    }
  };

  const handleBulkDelete = async (selectedItems: FeedbackItem[]) => {
    try {
      const feedbackIds = selectedItems.map(item => item.id);
      await feedbackAPI.bulkDelete(feedbackIds);
      await fetchFeedback(buildFilters());
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
              <UserX className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground">Churn Risks</h1>
              <p className="text-muted-foreground text-lg">Feedback items with high churn risk scores</p>
            </div>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 animate-slide-up stagger-1">
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">High Risk</p>
                <p className="text-3xl font-bold font-mono text-destructive">{highCount}</p>
              </div>
              <Badge variant="destructive">{'> 70'}</Badge>
            </div>
          </Card>
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Medium Risk</p>
                <p className="text-3xl font-bold font-mono" style={{ color: 'var(--chart-2)' }}>{mediumCount}</p>
              </div>
              <Badge variant="outline" style={{ backgroundColor: 'color-mix(in oklch, var(--chart-2) 15%, transparent)', color: 'var(--chart-2)', borderColor: 'color-mix(in oklch, var(--chart-2) 30%, transparent)' }}>40-70</Badge>
            </div>
          </Card>
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Low Risk</p>
                <p className="text-3xl font-bold font-mono" style={{ color: 'var(--chart-5)' }}>{lowCount}</p>
              </div>
              <Badge variant="outline" style={{ backgroundColor: 'color-mix(in oklch, var(--chart-5) 15%, transparent)', color: 'var(--chart-5)', borderColor: 'color-mix(in oklch, var(--chart-5) 30%, transparent)' }}>{'< 40'}</Badge>
            </div>
          </Card>
        </div>

        {/* Risk Level Filter */}
        <Card className="animate-slide-up stagger-2">
          <div className="p-6">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-4">Filters</h3>
            <div className="flex flex-wrap gap-4">
              <Select value={riskFilter} onValueChange={setRiskFilter}>
                <SelectTrigger className="h-10 w-[180px]">
                  <SelectValue placeholder="All Risk Levels" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Risk Levels</SelectItem>
                  <SelectItem value="high">High ({"> 70"})</SelectItem>
                  <SelectItem value="medium">Medium (40-70)</SelectItem>
                  <SelectItem value="low">Low ({"< 40"})</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </Card>

        {/* DataTable */}
        <Card className="p-6 animate-slide-up stagger-3">
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
            emptyIcon={UserX}
            emptyTitle="No churn risks found"
            emptyDescription={searchQuery || riskFilter !== 'all' ? 'Try adjusting your filters' : 'No churn risk feedback detected yet'}
            totalCount={totalCount}
          />
        </Card>
      </main>
    </div>
  );
}
