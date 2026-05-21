'use client';

import { AlertOctagon, AlertTriangle, Clock, CheckCircle } from 'lucide-react';
import { RISK_BAND_COLOR, type RiskBand } from '@/lib/constants/churn';

export type TimeToChurnBucket = 'immediate' | '2w' | '2-4w' | '1-3m' | 'low';

export interface ChurnTimelineBadgeProps {
  bucket: TimeToChurnBucket | null | undefined;
  size?: 'sm' | 'md';
  className?: string;
}

interface BucketConfig {
  label: string;
  band: RiskBand;
  iconTestId: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const BUCKET_CONFIG: Record<TimeToChurnBucket, BucketConfig> = {
  immediate: {
    label: 'Immediate',
    band: 'critical',
    iconTestId: 'churn-timeline-icon-alert-octagon',
    Icon: AlertOctagon,
  },
  '2w': {
    label: 'Within 2 weeks',
    band: 'high',
    iconTestId: 'churn-timeline-icon-alert-triangle',
    Icon: AlertTriangle,
  },
  '2-4w': {
    label: '2–4 weeks',
    band: 'medium',
    iconTestId: 'churn-timeline-icon-clock',
    Icon: Clock,
  },
  '1-3m': {
    label: '1–3 months',
    band: 'medium',
    iconTestId: 'churn-timeline-icon-clock',
    Icon: Clock,
  },
  low: {
    label: 'Low risk',
    band: 'low',
    iconTestId: 'churn-timeline-icon-check-circle',
    Icon: CheckCircle,
  },
};

const SIZE_CLASSES: Record<'sm' | 'md', { text: string; icon: string; padding: string }> = {
  sm: { text: 'text-xs', icon: 'w-3 h-3', padding: 'px-1.5 py-0.5' },
  md: { text: 'text-xs', icon: 'w-3.5 h-3.5', padding: 'px-2 py-0.5' },
};

export function ChurnTimelineBadge({
  bucket,
  size = 'md',
  className = '',
}: ChurnTimelineBadgeProps) {
  if (bucket === null || bucket === undefined) return null;

  const config = BUCKET_CONFIG[bucket];
  const color = RISK_BAND_COLOR[config.band];
  const { text, icon, padding } = SIZE_CLASSES[size];
  const { Icon, iconTestId } = config;

  return (
    <span
      data-testid="churn-timeline-badge"
      data-band={config.band}
      className={`inline-flex items-center gap-1 font-medium rounded-full ${text} ${padding} ${className}`}
      style={{
        color,
        backgroundColor: `color-mix(in oklch, ${color} 12%, transparent)`,
        borderWidth: 1,
        borderStyle: 'solid',
        borderColor: `color-mix(in oklch, ${color} 30%, transparent)`,
      }}
    >
      <Icon data-testid={iconTestId} className={icon} />
      {config.label}
    </span>
  );
}
