'use client';

import { getRiskBandColor, RISK_BAND_COLOR } from '@/lib/constants/churn';

export interface ChurnProbabilityBadgeProps {
  probability: number | null | undefined;
  probabilityLow?: number;
  probabilityHigh?: number;
  size?: 'sm' | 'md' | 'lg';
  labelCount?: number;
  showTooltip?: boolean;
  className?: string;
}

const SIZE_CLASSES: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'text-xs px-1.5 py-0.5',
  md: 'text-xs px-2 py-0.5',
  lg: 'text-sm px-2.5 py-1',
};

export function ChurnProbabilityBadge({
  probability,
  probabilityLow,
  probabilityHigh,
  size = 'md',
  labelCount,
  showTooltip = true,
  className = '',
}: ChurnProbabilityBadgeProps) {
  const isValid = probability !== null && probability !== undefined && !isNaN(probability as number);

  if (!isValid) {
    return (
      <span
        data-testid="churn-probability-badge"
        data-size={size}
        className={`inline-flex items-center font-medium rounded-full font-mono ${SIZE_CLASSES[size]} ${className}`}
        style={{
          color: 'var(--muted-foreground)',
          backgroundColor: 'color-mix(in oklch, var(--muted-foreground) 12%, transparent)',
          borderWidth: 1,
          borderStyle: 'solid',
          borderColor: 'color-mix(in oklch, var(--muted-foreground) 25%, transparent)',
        }}
      >
        —
      </span>
    );
  }

  const p = probability as number;
  const band = getRiskBandColor(p);
  const color = RISK_BAND_COLOR[band];
  const pct = Math.round(p * 100);

  const hasCi = probabilityLow !== undefined && probabilityHigh !== undefined;
  const lowPct = hasCi ? Math.round((probabilityLow as number) * 100) : null;
  const highPct = hasCi ? Math.round((probabilityHigh as number) * 100) : null;

  const tooltipText = hasCi
    ? `30-day churn probability. 90% CI: ${lowPct}%–${highPct}%.${labelCount !== undefined ? ` Based on ${labelCount} labeled outcomes.` : ''}`
    : undefined;

  return (
    <div className="relative inline-block group">
      <span
        data-testid="churn-probability-badge"
        data-band={band}
        data-size={size}
        className={`inline-flex items-center font-medium rounded-full font-mono ${SIZE_CLASSES[size]} ${className}`}
        style={{
          color,
          backgroundColor: `color-mix(in oklch, ${color} 12%, transparent)`,
          borderWidth: 1,
          borderStyle: 'solid',
          borderColor: `color-mix(in oklch, ${color} 30%, transparent)`,
        }}
      >
        {pct}%
      </span>
      {showTooltip && tooltipText && (
        <span
          data-testid="churn-probability-tooltip"
          className="sr-only"
          aria-hidden="true"
        >
          {tooltipText}
        </span>
      )}
    </div>
  );
}
