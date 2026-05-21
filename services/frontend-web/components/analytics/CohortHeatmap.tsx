'use client';

import { useState } from 'react';
import type { CohortGridCell } from '@/lib/api/churn-analytics';
import { getRiskBandColor, RISK_BAND_COLOR, type RiskBand } from '@/lib/constants/churn';
import { formatPercent } from '@/lib/api/churn-analytics';

interface CohortHeatmapProps {
  grid: CohortGridCell[];
}

/** 2D heatmap of churn rate by cohort x time bucket. */
export function CohortHeatmap({ grid }: CohortHeatmapProps) {
  const [tooltip, setTooltip] = useState<{
    cell: CohortGridCell;
    x: number;
    y: number;
  } | null>(null);

  if (grid.length === 0) {
    return (
      <div data-testid="cohort-heatmap-empty" className="text-sm text-muted-foreground text-center py-8">
        No cohort data available.
      </div>
    );
  }

  // Derive sorted unique cohort labels and time buckets
  const cohortLabels = [...new Set(grid.map((c) => c.cohort_label))].sort();
  const timeBuckets = [...new Set(grid.map((c) => c.time_bucket))].sort();

  // Build lookup: "cohortLabel|timeBucket" -> cell
  const lookup = new Map<string, CohortGridCell>();
  for (const cell of grid) {
    lookup.set(`${cell.cohort_label}|${cell.time_bucket}`, cell);
  }

  return (
    <div data-testid="cohort-heatmap" className="relative overflow-auto">
      {/* Column headers */}
      <div
        className="grid"
        style={{ gridTemplateColumns: `140px repeat(${timeBuckets.length}, 1fr)` }}
      >
        {/* top-left corner spacer */}
        <div />
        {timeBuckets.map((tb) => (
          <div
            key={tb}
            data-testid="heatmap-col-label"
            className="text-xs font-medium text-muted-foreground text-center pb-1 px-1"
          >
            {tb}
          </div>
        ))}

        {/* Rows */}
        {cohortLabels.map((label) => (
          <div key={`row-${label}`} className="contents">
            <div
              data-testid="heatmap-row-label"
              className="text-sm text-muted-foreground truncate pr-2 flex items-center"
            >
              {label}
            </div>
            {timeBuckets.map((tb) => {
              const cell = lookup.get(`${label}|${tb}`);
              const rate = cell?.churn_rate ?? 0;
              const band: RiskBand = getRiskBandColor(rate);
              const color = RISK_BAND_COLOR[band];

              return (
                <div
                  key={`${label}|${tb}`}
                  data-testid="heatmap-cell"
                  data-band={band}
                  className="h-8 m-0.5 rounded cursor-pointer transition-opacity hover:opacity-80"
                  style={{
                    backgroundColor: cell ? color : 'var(--muted)',
                    opacity: cell ? 1 : 0.15,
                  }}
                  onMouseEnter={(e) => {
                    if (cell) {
                      const rect = (e.target as HTMLElement).getBoundingClientRect();
                      setTooltip({ cell, x: rect.left, y: rect.top });
                    }
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          data-testid="heatmap-tooltip"
          className="fixed z-50 rounded-lg border px-3 py-2 text-xs shadow-xl pointer-events-none"
          style={{
            left: tooltip.x + 10,
            top: tooltip.y - 60,
            backgroundColor: 'var(--background)',
            borderColor: 'var(--border)',
          }}
        >
          <p className="font-semibold mb-0.5">{tooltip.cell.cohort_label} / {tooltip.cell.time_bucket}</p>
          <p>Churn rate: <span className="font-mono font-medium">{formatPercent(tooltip.cell.churn_rate)}</span></p>
          <p>Churned: <span className="font-mono font-medium">{tooltip.cell.churned_count}</span></p>
        </div>
      )}
    </div>
  );
}
