'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  getChurnCohorts,
  cohortDimensionLabel,
  formatPercent,
  type CohortAnalyticsResponse,
  type CohortDimension,
  type CohortRange,
} from '@/lib/api/churn-analytics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { CohortHeatmap } from '@/components/analytics/CohortHeatmap';
import { ReasonCodeBreakdown } from '@/components/analytics/ReasonCodeBreakdown';
import { ChurnCohortBarChart } from '@/components/analytics/ChurnCohortBarChart';

const DIMENSION_OPTIONS: { value: CohortDimension; label: string }[] = [
  { value: 'source', label: 'Source' },
  { value: 'month', label: 'Acquisition Month' },
  { value: 'volume', label: 'Volume Segment' },
];

const RANGE_OPTIONS: { value: CohortRange; label: string }[] = [
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: 'all', label: 'All time' },
];

export default function ChurnCohortsPage() {
  const [dimension, setDimension] = useState<CohortDimension>('source');
  const [range, setRange] = useState<CohortRange>('30d');
  const [data, setData] = useState<CohortAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(
    async (dim: CohortDimension, rng: CohortRange) => {
      setLoading(true);
      setError(null);
      try {
        const result = await getChurnCohorts({ dimension: dim, range: rng });
        setData(result);
      } catch {
        setError('Failed to load cohort data. Please try again.');
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    fetchData(dimension, range);
  }, [dimension, range, fetchData]);

  const handleDimensionChange = (value: string) => {
    setDimension(value as CohortDimension);
  };

  const handleRangeChange = (value: string) => {
    setRange(value as CohortRange);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold">Churn Cohorts</h1>
        <p data-testid="page-description" className="text-sm text-muted-foreground">
          Analyze churn rates across customer cohorts segmented by {cohortDimensionLabel(dimension).toLowerCase()}.
          Business+ feature — identify patterns and act before customers leave.
        </p>
      </div>

      <>
          {/* Filter row */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">
                Segment by
              </span>
              <Select value={dimension} onValueChange={handleDimensionChange}>
                <SelectTrigger
                  aria-label="Segment by"
                  data-testid="dimension-select"
                  className="h-8 w-[180px]"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DIMENSION_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">
                Range
              </span>
              <Select value={range} onValueChange={handleRangeChange}>
                <SelectTrigger
                  aria-label="Range"
                  data-testid="range-select"
                  className="h-8 w-[140px]"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RANGE_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Error state */}
          {error && (
            <div data-testid="error-state" className="p-4 rounded-lg border border-destructive/20 bg-destructive/5 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Loading */}
          {loading && <LoadingSkeleton />}

          {/* Data */}
          {!loading && !error && data && (
            <>
              {/* Empty state */}
              {data.cohorts.length === 0 ? (
                <div
                  data-testid="empty-state"
                  className="flex flex-col items-center justify-center py-16 text-center"
                >
                  <p className="text-sm text-muted-foreground">
                    No cohort data found for the selected filters. Try a different dimension or date range.
                  </p>
                </div>
              ) : (
                <>
                  {/* Stat cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <Card>
                      <CardHeader className="pb-1">
                        <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                          Overall Churn Rate
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p
                          data-testid="stat-overall-churn-rate"
                          className="text-2xl font-bold tabular-nums"
                        >
                          {formatPercent(data.overall_churn_rate)}
                        </p>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader className="pb-1">
                        <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                          Total Customers
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p
                          data-testid="stat-total-customers"
                          className="text-2xl font-bold tabular-nums"
                        >
                          {data.total_customers.toLocaleString()}
                        </p>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader className="pb-1">
                        <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                          Total Churned
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p
                          data-testid="stat-total-churned"
                          className="text-2xl font-bold tabular-nums"
                        >
                          {data.total_churned.toLocaleString()}
                        </p>
                      </CardContent>
                    </Card>
                  </div>

                  {/* Bar chart */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base font-medium">
                        Churn Rate by Cohort
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ChurnCohortBarChart cohorts={data.cohorts} />
                    </CardContent>
                  </Card>

                  {/* Heatmap */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base font-medium">
                        Cohort x Time Heatmap
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <CohortHeatmap grid={data.grid} />
                    </CardContent>
                  </Card>

                  {/* Reason code breakdown */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base font-medium">
                        Churn Reason Breakdown
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ReasonCodeBreakdown cohorts={data.cohorts} />
                    </CardContent>
                  </Card>
                </>
              )}
            </>
          )}
      </>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <Skeleton className="h-64" />
      <Skeleton className="h-48" />
      <Skeleton className="h-56" />
    </div>
  );
}
