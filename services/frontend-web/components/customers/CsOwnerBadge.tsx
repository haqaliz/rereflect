'use client';

import { UserCog } from 'lucide-react';
import type { CustomerOwnerRef } from '@/lib/api/customers';

export interface CsOwnerBadgeProps {
  owner: CustomerOwnerRef | null | undefined;
  size?: 'sm' | 'md';
  className?: string;
}

const SIZE_CLASSES: Record<'sm' | 'md', { text: string; icon: string; padding: string }> = {
  sm: { text: 'text-xs', icon: 'w-3 h-3', padding: 'px-1.5 py-0.5' },
  md: { text: 'text-xs', icon: 'w-3.5 h-3.5', padding: 'px-2 py-0.5' },
};

/**
 * Assigned CS-owner chip (segment-actions bulk assign-owner). Mirrors
 * SegmentBadge's Sunset-Horizon theming. Renders a clean "Unassigned"
 * label — no error state — when the customer has no owner.
 */
export function CsOwnerBadge({ owner, size = 'sm', className = '' }: CsOwnerBadgeProps) {
  const { text, icon, padding } = SIZE_CLASSES[size];

  if (!owner) {
    return (
      <span
        data-testid="cs-owner-badge"
        data-owner="unassigned"
        className={`inline-flex items-center gap-1 font-medium rounded-full ${text} ${padding} ${className}`}
        style={{ color: 'var(--muted-foreground)' }}
      >
        <UserCog className={icon} />
        Unassigned
      </span>
    );
  }

  return (
    <span
      data-testid="cs-owner-badge"
      data-owner={owner.email}
      className={`inline-flex items-center gap-1 font-medium rounded-full ${text} ${padding} ${className}`}
      style={{
        color: 'var(--chart-2)',
        backgroundColor: 'color-mix(in oklch, var(--chart-2) 12%, transparent)',
        borderWidth: 1,
        borderStyle: 'solid',
        borderColor: 'color-mix(in oklch, var(--chart-2) 30%, transparent)',
      }}
    >
      <UserCog className={icon} />
      {owner.email}
    </span>
  );
}
