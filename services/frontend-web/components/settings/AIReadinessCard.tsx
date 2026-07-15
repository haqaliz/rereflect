'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Database } from 'lucide-react';
import { aiReadinessAPI, type AIReadiness } from '@/lib/api/ai-readiness';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

// Local label map — duplicated from settings/ai/page.tsx's CORRECTION_TYPE_LABELS
// rather than shared, to avoid a cross-file coupling risk with the sibling
// eval-harness-and-card aspect that also touches that file's 'accuracy' tab.
const CORRECTION_TYPE_LABELS: Record<string, string> = {
  sentiment: 'Sentiment',
  category: 'Category',
  churn_risk: 'Churn Risk',
  copilot_response: 'Copilot Response',
};

function SkeletonBar({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded bg-muted ${className ?? 'h-4 w-24'}`} />
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="p-4 rounded-lg border border-border bg-secondary/30">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">
        {label}
      </p>
      <p className="text-2xl font-bold text-foreground">{value.toLocaleString()}</p>
    </div>
  );
}

function BreakdownList({
  title,
  data,
  labelMap,
}: {
  title: string;
  data: Record<string, number>;
  labelMap?: Record<string, string>;
}) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <div>
      <p className="text-sm font-medium text-foreground mb-2">{title}</p>
      <div className="space-y-1">
        {entries.map(([key, count]) => (
          <div
            key={key}
            className="flex items-center justify-between py-1 border-b border-border last:border-0"
          >
            <span className="text-sm text-foreground">{labelMap?.[key] ?? key}</span>
            <span className="text-sm font-medium tabular-nums">{count.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ThresholdRow({
  label,
  current,
  target,
  ready,
}: {
  label: string;
  current: number;
  target: number;
  ready: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-sm text-foreground">
        {label}: {current.toLocaleString()} / {target.toLocaleString()}
      </span>
      <Badge variant={ready ? 'success' : 'secondary'}>{ready ? 'Ready' : 'Not Yet Ready'}</Badge>
    </div>
  );
}

export function AIReadinessCard() {
  const [data, setData] = useState<AIReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    aiReadinessAPI
      .get()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const cardTitle = (
    <div className="flex items-center space-x-2">
      <div className="p-2 bg-secondary rounded-lg">
        <Database className="w-5 h-5 text-primary" />
      </div>
      <CardTitle className="text-base">AI Training Readiness</CardTitle>
    </div>
  );

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-3">{cardTitle}</CardHeader>
        <CardContent>
          <div data-testid="readiness-card-skeleton" className="space-y-2">
            <SkeletonBar className="h-4 w-48" />
            <SkeletonBar className="h-3 w-64" />
            <SkeletonBar className="h-24 w-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader className="pb-3">{cardTitle}</CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Failed to load readiness data.</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const isEmpty =
    data.feedback_volume === 0 &&
    data.corrections_total === 0 &&
    data.churn_labels_total === 0;

  return (
    <Card>
      <CardHeader className="pb-3">{cardTitle}</CardHeader>
      <CardContent className="space-y-6">
        <p className="text-sm text-muted-foreground">
          Snapshot of the data available to train future self-improving models
          (M5.2/M5.3) — reporting only, no ML runs here.
        </p>

        {isEmpty && (
          <div className="text-center py-8 text-muted-foreground">
            <Database className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>
              No data yet &mdash; readiness metrics will appear as feedback,
              corrections, and churn labels accumulate.
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <StatTile label="Feedback Volume" value={data.feedback_volume} />
          <StatTile label="Corrections Total" value={data.corrections_total} />
        </div>

        <BreakdownList
          title="Corrections by Type"
          data={data.corrections_by_type}
          labelMap={CORRECTION_TYPE_LABELS}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <StatTile label="Churn Labels Total" value={data.churn_labels_total} />
          <StatTile label="Churn Labels Recovered" value={data.churn_labels_recovered} />
        </div>

        <BreakdownList title="Churn Labels by Reason" data={data.churn_labels_by_reason} />
        <BreakdownList title="Churn Labels by Source" data={data.churn_labels_by_source} />

        <div className="space-y-1 pt-2 border-t border-border">
          <ThresholdRow
            label="Corrections"
            current={data.corrections_total}
            target={data.correction_volume_target}
            ready={data.correction_volume_ready}
          />
          <ThresholdRow
            label="Trainable churn labels"
            current={data.churn_labels_trainable}
            target={data.churn_label_target}
            ready={data.churn_labels_ready}
          />
          {data.pending_suggestions > 0 && (
            <p className="text-sm text-muted-foreground pt-1">
              <Link href="/customers" className="underline hover:text-foreground">
                {data.pending_suggestions.toLocaleString()} CRM suggestions awaiting review
              </Link>
            </p>
          )}
        </div>

        <p className="text-xs text-muted-foreground italic">
          These targets are planning estimates for future self-improving models
          (M5.2/M5.3), not guarantees.
        </p>
      </CardContent>
    </Card>
  );
}
