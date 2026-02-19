interface RiskDistribution {
  healthy: number;
  moderate: number;
  at_risk: number;
  critical: number;
}

interface RiskDistributionBarProps {
  distribution: RiskDistribution;
  total: number;
  onFilterChange?: (riskLevel: string) => void;
  activeFilter?: string;
}

const segments = [
  { key: 'healthy', label: 'Healthy', color: 'var(--chart-5)' },
  { key: 'moderate', label: 'Moderate', color: 'var(--chart-2)' },
  { key: 'at_risk', label: 'At Risk', color: 'var(--chart-1)' },
  { key: 'critical', label: 'Critical', color: 'var(--destructive)' },
] as const;

export function RiskDistributionBar({
  distribution,
  total,
  onFilterChange,
  activeFilter,
}: RiskDistributionBarProps) {
  const getPercent = (count: number) =>
    total > 0 ? Math.round((count / total) * 100) : 0;

  return (
    <div className="space-y-3">
      {/* Stacked bar */}
      <div className="flex h-4 rounded-full overflow-hidden w-full">
        {segments.map(({ key, color }) => {
          const count = distribution[key as keyof RiskDistribution];
          const pct = getPercent(count);
          if (pct === 0) return null;
          return (
            <div
              key={key}
              data-segment={key}
              data-testid={`bar-segment-${key}`}
              className="cursor-pointer transition-opacity hover:opacity-80"
              style={{ width: `${pct}%`, backgroundColor: color }}
              onClick={() => onFilterChange?.(key)}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4">
        {segments.map(({ key, label, color }) => {
          const count = distribution[key as keyof RiskDistribution];
          const pct = getPercent(count);
          const isActive = activeFilter === key;
          return (
            <button
              key={key}
              data-segment={key}
              className="flex items-center gap-1.5 text-sm transition-opacity"
              style={{ opacity: activeFilter && !isActive ? 0.5 : 1 }}
              onClick={() => onFilterChange?.(key)}
            >
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="font-medium" style={{ color }}>
                {label}
              </span>
              <span className="text-muted-foreground font-mono">
                {count}
              </span>
              <span className="text-muted-foreground text-xs">({pct}%)</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
