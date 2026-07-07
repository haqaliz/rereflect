'use client';

import { AlertTriangle, VolumeX, Moon, Zap, Heart, Sparkles, Minus } from 'lucide-react';
import {
  SEGMENT_LABELS,
  SEGMENT_COLOR,
  normalizeSegment,
  type SegmentSlug,
} from '@/lib/constants/segments';

export interface SegmentBadgeProps {
  segment: string | null | undefined;
  size?: 'sm' | 'md';
  className?: string;
}

interface SegmentIconConfig {
  iconTestId: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const SEGMENT_ICON_CONFIG: Record<SegmentSlug, SegmentIconConfig> = {
  at_risk: { iconTestId: 'segment-icon-alert-triangle', Icon: AlertTriangle },
  silent_churner: { iconTestId: 'segment-icon-volume-x', Icon: VolumeX },
  dormant: { iconTestId: 'segment-icon-moon', Icon: Moon },
  power_user: { iconTestId: 'segment-icon-zap', Icon: Zap },
  happy_advocate: { iconTestId: 'segment-icon-heart', Icon: Heart },
  new: { iconTestId: 'segment-icon-sparkles', Icon: Sparkles },
  unsegmented: { iconTestId: 'segment-icon-minus', Icon: Minus },
};

const SIZE_CLASSES: Record<'sm' | 'md', { text: string; icon: string; padding: string }> = {
  sm: { text: 'text-xs', icon: 'w-3 h-3', padding: 'px-1.5 py-0.5' },
  md: { text: 'text-xs', icon: 'w-3.5 h-3.5', padding: 'px-2 py-0.5' },
};

/**
 * Rule-based customer segment chip. Mirrors ChurnTimelineBadge styling.
 * Handles null/undefined/unrecognized segment values by rendering a subtle
 * neutral "Unsegmented" chip instead of crashing or rendering nothing.
 */
export function SegmentBadge({ segment, size = 'md', className = '' }: SegmentBadgeProps) {
  const slug = normalizeSegment(segment);
  const label = SEGMENT_LABELS[slug];
  const color = SEGMENT_COLOR[slug];
  const { text, icon, padding } = SIZE_CLASSES[size];
  const { Icon, iconTestId } = SEGMENT_ICON_CONFIG[slug];

  return (
    <span
      data-testid="segment-badge"
      data-segment={slug}
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
      {label}
    </span>
  );
}
