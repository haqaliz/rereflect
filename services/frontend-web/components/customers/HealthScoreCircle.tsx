interface HealthScoreCircleProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
}

export function getHealthColor(score: number): string {
  if (score >= 70) return 'var(--chart-5)';
  if (score >= 50) return 'var(--chart-2)';
  if (score >= 30) return 'var(--chart-1)';
  return 'var(--destructive)';
}

const sizeMap = {
  sm: { outer: 'w-8 h-8', text: 'text-xs' },
  md: { outer: 'w-10 h-10', text: 'text-sm' },
  lg: { outer: 'w-16 h-16', text: 'text-xl' },
};

export function HealthScoreCircle({ score, size = 'md' }: HealthScoreCircleProps) {
  const color = getHealthColor(score);
  const { outer, text } = sizeMap[size];

  return (
    <span
      className={`${outer} rounded-full flex items-center justify-center font-bold font-mono flex-shrink-0`}
      style={{
        backgroundColor: `color-mix(in oklch, ${color} 20%, transparent)`,
        color,
      }}
    >
      <span className={text}>{score}</span>
    </span>
  );
}
