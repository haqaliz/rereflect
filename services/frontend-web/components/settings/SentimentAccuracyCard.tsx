'use client';

import { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import {
  getSentimentAccuracy,
  formatMetricPercent,
  formatDelta,
  type EvalSetResult,
  type SentimentAccuracyResponse,
} from '@/lib/api/sentiment-accuracy';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const SET_LABELS: Record<string, string> = {
  public: 'Public baseline',
  in_domain: 'In-domain (your feedback)',
};

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
      {meetsTarget ? 'Beats VADER' : 'Does not currently beat VADER'}
    </span>
  );
}

function EvalSetBlock({ result }: { result: EvalSetResult }) {
  const title = SET_LABELS[result.set_name] ?? result.set_name;

  return (
    <div className="p-4 rounded-lg border border-border bg-secondary/30 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-foreground">{title}</p>
        <span className="text-xs text-muted-foreground">{`n=${result.n}`}</span>
      </div>

      <MetricRow
        label="VADER macro-F1"
        value={formatMetricPercent(result.vader?.macro_f1 ?? null)}
      />

      {result.transformer ? (
        <>
          <MetricRow
            label="Transformer macro-F1"
            value={formatMetricPercent(result.transformer.macro_f1)}
          />
          <MetricRow label="Delta (transformer - VADER)" value={formatDelta(result.macro_f1_delta)} />
          {result.meets_target !== null && <Badge meetsTarget={result.meets_target} />}
        </>
      ) : (
        <p className="text-xs text-muted-foreground italic">Transformer not evaluated</p>
      )}
    </div>
  );
}

export function SentimentAccuracyCard() {
  const [data, setData] = useState<SentimentAccuracyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    getSentimentAccuracy()
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
          Sentiment Model Accuracy (VADER vs Transformer)
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Disclosure only &mdash; the local transformer ships opt-in and off by
          default regardless of these results.
        </p>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div data-testid="sentiment-accuracy-skeleton" className="space-y-2">
            <SkeletonBar className="h-4 w-48" />
            <SkeletonBar className="h-16 w-full" />
          </div>
        ) : error ? (
          <p className="text-sm text-muted-foreground">Failed to load sentiment eval results.</p>
        ) : data === null || !data.has_results ? (
          <p className="text-sm text-muted-foreground">
            No eval results yet &mdash; run <code>scripts/eval_sentiment.py</code> to
            generate the accuracy report.
          </p>
        ) : (
          <div className="space-y-4">
            {data.model_id && (
              <p className="text-xs text-muted-foreground">
                Transformer model: <span className="font-mono">{data.model_id}</span>
              </p>
            )}
            {data.public && <EvalSetBlock result={data.public} />}
            {data.in_domain && <EvalSetBlock result={data.in_domain} />}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
