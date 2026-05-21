'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Activity } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import {
  getAccuracyCard,
  formatMetricPercent,
  type AccuracyCardResponse,
} from '@/lib/api/churn-accuracy';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

function SkeletonBar({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-muted ${className ?? 'h-4 w-24'}`}
    />
  );
}

export function ModelAccuracyCard() {
  const { user } = useAuth();
  const [data, setData] = useState<AccuracyCardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    getAccuracyCard()
      .then((result) => {
        if (!cancelled) {
          setData(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const isSystemAdmin = user?.is_system_admin === true;
  const hasMetrics =
    data !== null &&
    data.precision !== null &&
    data.recall !== null &&
    data.f1 !== null;

  const cardTitle = (
    <CardTitle className="text-base flex items-center gap-2">
      <Activity className="w-4 h-4 text-[var(--chart-1)]" />
      Model Accuracy
    </CardTitle>
  );

  const cardInner = (
    <>
      <CardHeader className="pb-3">{cardTitle}</CardHeader>
      <CardContent>
        {loading ? (
          <div data-testid="accuracy-card-skeleton" className="space-y-2">
            <SkeletonBar className="h-4 w-48" />
            <SkeletonBar className="h-3 w-64" />
          </div>
        ) : error ? (
          <p className="text-sm text-muted-foreground">Failed to load accuracy data.</p>
        ) : data === null ? null : hasMetrics ? (
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {formatMetricPercent(data.precision)} precision &middot;{' '}
              {formatMetricPercent(data.recall)} recall &middot;{' '}
              <span className="text-muted-foreground">{data.label_count} labeled</span>
            </p>
            {data.is_global_fallback && (
              <p className="text-xs text-muted-foreground">
                Using global model &mdash; mark customers as churned to improve accuracy.
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              No labeled outcomes yet &mdash; start labeling to enable accuracy tracking.
            </p>
            {data.label_count > 0 && (
              <p className="text-xs text-muted-foreground">
                {data.label_count} label{data.label_count !== 1 ? 's' : ''} collected
              </p>
            )}
          </div>
        )}
      </CardContent>
    </>
  );

  if (isSystemAdmin) {
    return (
      <Card>
        <Link href="/system/churn-accuracy" className="block hover:bg-muted/30 transition-colors rounded-xl">
          {cardInner}
        </Link>
      </Card>
    );
  }

  return <Card>{cardInner}</Card>;
}
