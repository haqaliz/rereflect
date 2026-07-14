'use client';

import { useCallback, useEffect, useState } from 'react';
import { Wand2 } from 'lucide-react';
import {
  getClassifierAccuracy,
  rollbackClassifier,
  formatMetricPercent,
  formatDelta,
  type ClassifierAccuracyResponse,
  type ClassifierEvalRunSummary,
} from '@/lib/api/classifier-accuracy';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const DECISION_LABELS: Record<string, string> = {
  promoted: 'Promoted',
  retained: 'Retained',
  skipped: 'Skipped (held-out too small)',
};

/**
 * Per-classifier-type copy. Keeps the two PRD-mandated honesty clauses (critique #3) intact:
 * (a) the model is "promoted only when it beats the keyword categorizer on your held-out data"
 * (b) the fair-A/B disclosure — "evaluated on labels the [keyword] baseline can produce".
 * Do not paraphrase these away.
 */
const TYPE_COPY: Record<string, { label: string; trainedOn: string; note?: string }> = {
  sentiment: {
    label: 'Sentiment',
    trainedOn: "your team's sentiment corrections",
  },
  category: {
    label: 'Category',
    trainedOn:
      "your team's category corrections; promoted only when it beats the keyword " +
      'categorizer on your held-out data',
    note: 'Evaluated on labels the keyword categorizer can produce.',
  },
  urgency: {
    label: 'Urgency',
    trainedOn:
      "your org's urgency corrections; promoted only when it beats the keyword " +
      'urgency heuristic on your held-out data',
    note:
      'In auto mode this model is add-only: it can escalate a feedback item from ' +
      'not-urgent to urgent, but it never de-escalates an already-urgent item.',
  },
};

interface ClassifierAccuracyCardProps {
  /** Show the Roll back action — admin/owner only. Defaults to false. */
  isAdminOrOwner?: boolean;
  /** Which classifier this card reports on — 'sentiment' (default) or 'category'. */
  classifierType?: string;
}

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

function DeltaBadge({ delta }: { delta: number | null }) {
  if (delta === null) {
    return <span className="text-xs text-muted-foreground">{formatDelta(delta)}</span>;
  }
  const positive = delta >= 0;
  return (
    <span
      className="inline-block px-2 py-0.5 rounded text-xs font-medium tabular-nums"
      style={{
        backgroundColor: positive
          ? 'color-mix(in oklch, var(--chart-1) 15%, transparent)'
          : 'color-mix(in oklch, var(--destructive) 12%, transparent)',
        color: positive ? 'var(--chart-1)' : 'var(--destructive)',
      }}
    >
      {formatDelta(delta)}
    </span>
  );
}

function EvalRunRow({ run }: { run: ClassifierEvalRunSummary }) {
  const decisionLabel = DECISION_LABELS[run.decision] ?? run.decision;
  return (
    <div className="p-3 rounded-lg border border-border bg-secondary/30 space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-foreground">{decisionLabel}</span>
        <span className="text-xs text-muted-foreground">{`n=${run.n ?? 0}`}</span>
      </div>
      <MetricRow label="Incumbent macro-F1" value={formatMetricPercent(run.incumbent_macro_f1)} />
      <MetricRow label="Challenger macro-F1" value={formatMetricPercent(run.challenger_macro_f1)} />
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Delta</span>
        <DeltaBadge delta={run.macro_f1_delta} />
      </div>
    </div>
  );
}

export function ClassifierAccuracyCard({
  isAdminOrOwner = false,
  classifierType = 'sentiment',
}: ClassifierAccuracyCardProps) {
  const [data, setData] = useState<ClassifierAccuracyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [rollbackError, setRollbackError] = useState<string | null>(null);

  const copy = TYPE_COPY[classifierType] ?? {
    label: classifierType,
    trainedOn: `your team's ${classifierType} corrections`,
  };

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    getClassifierAccuracy(classifierType)
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
  }, [classifierType]);

  useEffect(() => {
    return load();
  }, [load]);

  const handleRollback = async () => {
    setRollingBack(true);
    setRollbackError(null);
    try {
      await rollbackClassifier(classifierType);
      load();
    } catch (err: any) {
      setRollbackError(err?.response?.data?.detail || 'Failed to roll back classifier');
    } finally {
      setRollingBack(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Wand2 className="w-4 h-4 text-[var(--chart-1)]" />
          {copy.label} Corrections Classifier Accuracy
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Per-org TF-IDF + logistic regression, trained on {copy.trainedOn}. We recommend{' '}
          <strong>shadow</strong> mode until this history is substantial.
        </p>
        {copy.note && <p className="text-xs text-muted-foreground">{copy.note}</p>}
      </CardHeader>
      <CardContent>
        {loading ? (
          <div data-testid="classifier-accuracy-skeleton" className="space-y-2">
            <SkeletonBar className="h-4 w-48" />
            <SkeletonBar className="h-16 w-full" />
          </div>
        ) : error ? (
          <p className="text-sm text-muted-foreground">Failed to load classifier accuracy.</p>
        ) : data === null || !data.has_model ? (
          <p className="text-sm text-muted-foreground">
            No model yet &mdash; accumulate at least {data?.min_labels ?? 20}{' '}
            {copy.label.toLowerCase()} corrections and wait for the next scheduled fit.
          </p>
        ) : !data.is_ready ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Not enough labels to trust this model yet:{' '}
              <span className="font-medium tabular-nums">
                {data.label_count}/{data.min_labels}
              </span>{' '}
              corrections.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="p-4 rounded-lg border border-border bg-secondary/30 space-y-2">
              <p className="text-xs text-muted-foreground">{data.model_kind}</p>
              <MetricRow label="Macro-F1" value={formatMetricPercent(data.macro_f1)} />
              <MetricRow
                label="Labels used"
                value={`${data.label_count}/${data.min_labels}`}
              />
              {data.fit_at && (
                <MetricRow label="Last fit" value={new Date(data.fit_at).toLocaleDateString()} />
              )}
            </div>

            {data.history.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-foreground">Recent shadow-mode evaluations</p>
                {data.history.map((run, idx) => (
                  <EvalRunRow key={idx} run={run} />
                ))}
              </div>
            )}

            {isAdminOrOwner && (
              <div className="pt-2 space-y-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRollback}
                  disabled={rollingBack}
                >
                  Roll back
                </Button>
                {rollbackError && <p className="text-xs text-destructive">{rollbackError}</p>}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
