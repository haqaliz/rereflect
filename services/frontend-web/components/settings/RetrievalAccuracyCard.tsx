'use client';

import { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import {
  getEmbeddingAccuracy,
  formatMetricPercent,
  formatDelta,
  type ProviderRetrievalResult,
  type RetrievalAccuracyResponse,
} from '@/lib/api/embedding-accuracy';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

function SkeletonBar({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-muted ${className ?? 'h-4 w-24'}`}
    />
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}

function Badge({ meetsTarget }: { meetsTarget: boolean }) {
  return (
    <span
      className="inline-block px-2 py-0.5 rounded text-xs font-medium"
      style={{
        backgroundColor: meetsTarget
          ? 'color-mix(in oklch, var(--chart-1) 15%, transparent)'
          : 'color-mix(in oklch, var(--destructive) 12%, transparent)',
        color: meetsTarget ? 'var(--chart-1)' : 'var(--destructive)',
      }}
    >
      {meetsTarget ? 'Beats nomic-embed-text baseline' : 'Does not currently beat baseline'}
    </span>
  );
}

function ProviderBlock({
  label,
  result,
}: {
  label: string;
  result: ProviderRetrievalResult;
}) {
  return (
    <div className="p-4 rounded-lg border border-border bg-secondary/30 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-foreground">{label}</p>
        {result.model && <span className="text-xs font-mono text-muted-foreground">{result.model}</span>}
      </div>
      <MetricRow label="Recall@1" value={formatMetricPercent(result.recall_at_1)} />
      <MetricRow label="MRR" value={result.mrr.toFixed(2)} />
      <MetricRow label="False-match rate" value={formatMetricPercent(result.false_match_rate)} />
    </div>
  );
}

export function RetrievalAccuracyCard() {
  const [data, setData] = useState<RetrievalAccuracyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    getEmbeddingAccuracy()
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

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-[var(--chart-1)]" />
          Retrieval Accuracy (Local Embeddings vs Baseline)
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Recall@1 at the 0.85 match threshold; lower-ranked matches fall
          through to the LLM.
        </p>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div data-testid="retrieval-accuracy-skeleton" className="space-y-2">
            <SkeletonBar className="h-4 w-48" />
            <SkeletonBar className="h-16 w-full" />
          </div>
        ) : error ? (
          <p className="text-sm text-muted-foreground">Failed to load retrieval eval results.</p>
        ) : data === null || !data.has_results ? (
          <p className="text-sm text-muted-foreground">
            No eval results yet &mdash; run <code>scripts/eval_embeddings.py</code> to
            generate the retrieval accuracy report.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {`n=${data.n}`}
                {data.n_positives !== null && data.n_negatives !== null
                  ? ` (n_positives=${data.n_positives}, n_negatives=${data.n_negatives})`
                  : ''}
              </span>
              {data.meets_target !== null && <Badge meetsTarget={data.meets_target} />}
            </div>

            {data.baseline && <ProviderBlock label="Baseline" result={data.baseline} />}
            {data.candidate && <ProviderBlock label="Candidate (local)" result={data.candidate} />}

            <MetricRow label="Recall@1 delta (candidate - baseline)" value={formatDelta(data.recall_at_1_delta)} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
