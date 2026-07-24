'use client';

import { useCallback, useEffect, useState } from 'react';
import { Wand2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  getClassifierAccuracy,
  getClassifierVersions,
  rollbackClassifier,
  resumeClassifier,
  formatMetricPercent,
  formatDelta,
  type ClassifierAccuracyResponse,
  type ClassifierEvalRunSummary,
  type ClassifierVersionSummary,
  type ClassifierVersionsResponse,
} from '@/lib/api/classifier-accuracy';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';

const DECISION_LABELS: Record<string, string> = {
  promoted: 'Promoted',
  retained: 'Retained',
  skipped: 'Skipped (held-out too small)',
  held: 'Held (promotion skipped)',
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

/** Version-history table caps visible rows so the settings card stays compact. */
const MAX_VISIBLE_VERSIONS = 10;

interface ClassifierAccuracyCardProps {
  /** Show mutating actions (roll back, resume) — admin/owner only. Defaults to false. */
  isAdminOrOwner?: boolean;
  /** Which classifier this card reports on — 'sentiment' (default), 'category', or 'urgency'. */
  classifierType?: string;
}

type ConfirmAction =
  | { kind: 'rollback'; version: ClassifierVersionSummary }
  | { kind: 'resume' };

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

function ActiveBadge() {
  return (
    <span
      className="inline-block px-2 py-0.5 rounded text-xs font-medium"
      style={{
        backgroundColor: 'color-mix(in oklch, var(--chart-1) 15%, transparent)',
        color: 'var(--chart-1)',
      }}
    >
      Active
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

function VersionHistoryTable({
  versions,
  isAdminOrOwner,
  onRollbackClick,
}: {
  versions: ClassifierVersionSummary[];
  isAdminOrOwner: boolean;
  onRollbackClick: (version: ClassifierVersionSummary) => void;
}) {
  const visible = versions.slice(0, MAX_VISIBLE_VERSIONS);
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-foreground">Version history</p>
      <div className="max-h-64 overflow-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Fit at</TableHead>
              <TableHead>Macro-F1</TableHead>
              <TableHead>Labels</TableHead>
              <TableHead className="text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((v) => (
              <TableRow key={v.id}>
                <TableCell>{new Date(v.fit_at).toLocaleDateString()}</TableCell>
                <TableCell>{formatMetricPercent(v.macro_f1)}</TableCell>
                <TableCell className="tabular-nums">{v.label_count}</TableCell>
                <TableCell className="text-right">
                  {v.is_active ? (
                    <ActiveBadge />
                  ) : isAdminOrOwner ? (
                    <Button variant="outline" size="sm" onClick={() => onRollbackClick(v)}>
                      Roll back to this
                    </Button>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function HoldBanner({
  isAdminOrOwner,
  nudgeText,
  onResumeClick,
}: {
  isAdminOrOwner: boolean;
  nudgeText: string | null;
  onResumeClick: () => void;
}) {
  return (
    <div
      className="p-3 rounded-lg border space-y-2"
      style={{
        borderColor: 'color-mix(in oklch, var(--destructive) 30%, transparent)',
        backgroundColor: 'color-mix(in oklch, var(--destructive) 8%, transparent)',
      }}
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="text-sm font-medium" style={{ color: 'var(--destructive)' }}>
          Auto-promotion paused
        </span>
        {isAdminOrOwner && (
          <Button variant="outline" size="sm" onClick={onResumeClick}>
            Resume auto-promotion
          </Button>
        )}
      </div>
      {nudgeText && <p className="text-xs text-muted-foreground">{nudgeText}</p>}
    </div>
  );
}

/** S1 nudge: when held and the latest eval run beat the held version, surface it. Degrades to null if data is absent. */
function computeHoldNudge(data: ClassifierAccuracyResponse | null): string | null {
  if (!data || !data.hold || data.history.length === 0) return null;
  const latest = data.history[0];
  if (latest.macro_f1_delta === null || latest.macro_f1_delta <= 0) return null;
  const pct = Math.round(latest.macro_f1_delta * 100);
  return `A newer candidate would beat your held version by +${pct}% — Resume?`;
}

export function ClassifierAccuracyCard({
  isAdminOrOwner = false,
  classifierType = 'sentiment',
}: ClassifierAccuracyCardProps) {
  const [data, setData] = useState<ClassifierAccuracyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [versions, setVersions] = useState<ClassifierVersionsResponse | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(true);

  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [actionInFlight, setActionInFlight] = useState(false);

  const copy = TYPE_COPY[classifierType] ?? {
    label: classifierType,
    trainedOn: `your team's ${classifierType} corrections`,
  };

  const loadAccuracy = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const result = await getClassifierAccuracy(classifierType);
      setData(result);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [classifierType]);

  const loadVersions = useCallback(async () => {
    setVersionsLoading(true);
    try {
      const result = await getClassifierVersions(classifierType);
      setVersions(result);
    } catch {
      // Degrade gracefully — the versions table simply doesn't render.
      setVersions(null);
    } finally {
      setVersionsLoading(false);
    }
  }, [classifierType]);

  useEffect(() => {
    loadAccuracy();
    loadVersions();
  }, [loadAccuracy, loadVersions]);

  const refetchAll = useCallback(async () => {
    await Promise.all([loadAccuracy(), loadVersions()]);
  }, [loadAccuracy, loadVersions]);

  const handleConfirm = async () => {
    if (!confirmAction) return;
    setActionInFlight(true);
    try {
      if (confirmAction.kind === 'rollback') {
        await rollbackClassifier(classifierType, confirmAction.version.id);
        toast.success(
          `Rolled back to the ${new Date(confirmAction.version.fit_at).toLocaleDateString()} version.`
        );
      } else {
        await resumeClassifier(classifierType);
        toast.success('Auto-promotion resumed.');
      }
      setConfirmAction(null);
      await refetchAll();
    } catch (err: any) {
      const fallback =
        confirmAction.kind === 'rollback'
          ? 'Failed to roll back classifier'
          : 'Failed to resume auto-promotion';
      toast.error(err?.response?.data?.detail || fallback);
    } finally {
      setActionInFlight(false);
    }
  };

  const holdNudge = computeHoldNudge(data);

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

            {data.hold && (
              <HoldBanner
                isAdminOrOwner={isAdminOrOwner}
                nudgeText={holdNudge}
                onResumeClick={() => setConfirmAction({ kind: 'resume' })}
              />
            )}

            {data.history.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-foreground">Recent shadow-mode evaluations</p>
                {data.history.map((run, idx) => (
                  <EvalRunRow key={idx} run={run} />
                ))}
              </div>
            )}
          </div>
        )}

        {!versionsLoading && versions !== null && versions.versions.length > 0 && (
          <div className="pt-4">
            <VersionHistoryTable
              versions={versions.versions}
              isAdminOrOwner={isAdminOrOwner}
              onRollbackClick={(version) => setConfirmAction({ kind: 'rollback', version })}
            />
          </div>
        )}
      </CardContent>

      <Dialog
        open={confirmAction !== null}
        onOpenChange={(open) => !open && setConfirmAction(null)}
      >
        <DialogContent className="sm:max-w-md">
          {confirmAction?.kind === 'rollback' ? (
            <>
              <DialogHeader>
                <DialogTitle>Roll back {copy.label} classifier?</DialogTitle>
                <DialogDescription>
                  This reactivates the version fit on{' '}
                  <strong>{new Date(confirmAction.version.fit_at).toLocaleDateString()}</strong>{' '}
                  and pauses auto-promotion for this classifier until you resume it.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setConfirmAction(null)}
                  disabled={actionInFlight}
                >
                  Cancel
                </Button>
                <Button onClick={handleConfirm} disabled={actionInFlight}>
                  Confirm rollback
                </Button>
              </DialogFooter>
            </>
          ) : confirmAction?.kind === 'resume' ? (
            <>
              <DialogHeader>
                <DialogTitle>Resume auto-promotion?</DialogTitle>
                <DialogDescription>
                  The weekly retrain job will be allowed to promote a new winning{' '}
                  {copy.label.toLowerCase()} model again.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setConfirmAction(null)}
                  disabled={actionInFlight}
                >
                  Cancel
                </Button>
                <Button onClick={handleConfirm} disabled={actionInFlight}>
                  Confirm resume
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
