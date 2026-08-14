'use client';

import { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import {
  getChurnLabelGate,
  verdictLabel,
  type ChurnLabelGateResponse,
} from '@/lib/api/churn-label-gate';
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

function VerdictBadge({ verdict }: { verdict: string }) {
  const tone =
    verdict === 'no_defensible_gate' ? 'var(--destructive)' : 'var(--chart-1)';
  return (
    <span
      className="inline-block px-2 py-0.5 rounded text-xs font-medium"
      style={{
        backgroundColor: `color-mix(in oklch, ${tone} 15%, transparent)`,
        color: tone,
      }}
    >
      {verdictLabel(verdict)}
    </span>
  );
}

export function ChurnLabelGateCard() {
  const [data, setData] = useState<ChurnLabelGateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    getChurnLabelGate()
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
          Churn Label Gate (ML Head Study)
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Simulated study: the per-org churn-label volume at which the ML head
          reliably beats the calibrated heuristic. Disclosure only &mdash; the
          verdict is a bound, not a measurement.
        </p>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div data-testid="churn-label-gate-skeleton" className="space-y-2">
            <SkeletonBar className="h-4 w-48" />
            <SkeletonBar className="h-16 w-full" />
          </div>
        ) : error ? (
          <p className="text-sm text-muted-foreground">
            Failed to load churn label-gate study results.
          </p>
        ) : data === null || !data.has_results ? (
          <p className="text-sm text-muted-foreground">
            Study not run yet &mdash; run <code>scripts/eval_churn_label_gate.py</code>{' '}
            to generate the verdict.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {`v${data.artifact_version ?? '?'}`}
                {data.n_simulations !== null
                  ? `, n=${data.n_simulations} simulations x 3 scenario families`
                  : ''}
              </span>
              {data.verdict && <VerdictBadge verdict={data.verdict} />}
            </div>

            <div className="p-4 rounded-lg border border-border bg-secondary/30 space-y-2">
              <MetricRow
                label="Activation gate"
                value={data.target !== null ? `${data.target.toLocaleString()} labels` : '—'}
              />
              <MetricRow
                label="Simulated crossover"
                value={data.crossover_label_volume !== null ? `${data.crossover_label_volume.toLocaleString()} labels` : 'never'}
              />
              {data.fidelity_sensitivity && (
                <MetricRow
                  label={`Crossover with ${Math.round(
                    data.fidelity_sensitivity.missing_fraction * 100
                  )}% missing snapshots`}
                  value={data.fidelity_sensitivity.crossover_label_volume !== null ? `${data.fidelity_sensitivity.crossover_label_volume.toLocaleString()} labels` : 'never'}
                />
              )}
            </div>

            {data.honest_limits && data.honest_limits.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1.5">
                  Honest limits
                </p>
                <ul className="space-y-1.5">
                  {data.honest_limits.map((line) => (
                    <li key={line} className="text-xs text-muted-foreground flex gap-1.5">
                      <span aria-hidden="true">•</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
