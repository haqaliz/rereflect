'use client';

import { TrendingUp, TrendingDown } from 'lucide-react';

interface NpsScoreWidgetProps {
  score: number;
  label: string;
  deltaPct?: number;
}

function getScoreColor(score: number): string {
  if (score >= 50) return 'var(--chart-5)';
  if (score >= 20) return 'var(--chart-2)';
  if (score >= 0) return 'var(--chart-1)';
  return 'var(--destructive)';
}

function getScoreLabel(score: number): string {
  if (score >= 50) return 'Excellent';
  if (score >= 20) return 'Good';
  if (score >= 0) return 'Needs Improvement';
  return 'Critical';
}

export function NpsScoreWidget({ score, label, deltaPct }: NpsScoreWidgetProps) {
  const color = getScoreColor(score);
  const displayLabel = label || getScoreLabel(score);
  const clampedScore = Math.max(-100, Math.min(100, score));

  // Use stroke-dasharray on a circle to create the gauge
  // A circle with r=70, circumference = 2*PI*70 = 439.82
  // We only use the top half (semicircle) = 219.91
  const r = 70;
  const circumference = 2 * Math.PI * r;
  const halfCircumference = circumference / 2;

  // How much of the semicircle to fill: score maps [-100,+100] to [0%, 100%]
  const fillPct = (clampedScore + 100) / 200;
  const filledLength = fillPct * halfCircumference;

  const hasDelta = deltaPct !== undefined && deltaPct !== null;
  const deltaColor = hasDelta && deltaPct! > 0 ? 'var(--chart-5)' : 'var(--destructive)';

  return (
    <div className="h-full flex flex-col items-center justify-center">
      {/* Gauge */}
      <div className="w-full max-w-[320px]">
        <svg
          viewBox="0 0 180 105"
          className="w-full"
          style={{ display: 'block', overflow: 'visible' }}
        >
          {/* Background track */}
          <path
            d={`M 10 90 A 70 70 0 0 1 170 90`}
            fill="none"
            stroke="var(--border)"
            strokeWidth={12}
            strokeLinecap="round"
          />
          {/* Colored fill */}
          <path
            d={`M 10 90 A 70 70 0 0 1 170 90`}
            fill="none"
            stroke={color}
            strokeWidth={12}
            strokeLinecap="round"
            strokeDasharray={`${filledLength} ${halfCircumference}`}
          />
          {/* Scale labels */}
          <text x="10" y="104" fontSize="9" fill="var(--muted-foreground)" textAnchor="middle" dominantBaseline="hanging" style={{ fontFamily: 'var(--font-mono)' }}>-100</text>
          <text x="90" y="0" fontSize="9" fill="var(--muted-foreground)" textAnchor="middle" style={{ fontFamily: 'var(--font-mono)' }}>0</text>
          <text x="170" y="104" fontSize="9" fill="var(--muted-foreground)" textAnchor="middle" dominantBaseline="hanging" style={{ fontFamily: 'var(--font-mono)' }}>+100</text>
        </svg>
      </div>

      {/* Score + label */}
      <div className="text-center">
        <p className="text-5xl font-bold font-mono leading-none" style={{ color }}>
          {score > 0 ? '+' : ''}{score}
        </p>
        <p
          className="text-sm font-semibold mt-1.5 uppercase tracking-wide"
          style={{ color }}
        >
          {displayLabel}
        </p>
        {hasDelta && (
          <div
            className="inline-flex items-center gap-1 mt-2 px-2.5 py-1 rounded-md text-xs font-semibold"
            style={{
              backgroundColor: `color-mix(in oklch, ${deltaColor} 15%, transparent)`,
              color: deltaColor,
            }}
          >
            {deltaPct! > 0 ? (
              <TrendingUp className="w-3 h-3" />
            ) : (
              <TrendingDown className="w-3 h-3" />
            )}
            <span>{Math.abs(deltaPct!).toFixed(1)}% vs prev period</span>
          </div>
        )}
      </div>

      {/* Description */}
      <p className="text-[11px] text-muted-foreground text-center mt-3 px-4 leading-relaxed">
        NPS = % Positive − % Negative. Ranges from −100 to +100. Above 0 is good, above 50 is excellent.
      </p>
    </div>
  );
}
