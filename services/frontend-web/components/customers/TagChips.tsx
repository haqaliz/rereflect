'use client';

import { Tag } from 'lucide-react';

export interface TagChipsProps {
  tags: string[] | null | undefined;
  size?: 'sm' | 'md';
  /** Max chips to render before collapsing the rest into a "+N" indicator. */
  maxVisible?: number;
  className?: string;
}

const SIZE_CLASSES: Record<'sm' | 'md', { text: string; icon: string; padding: string }> = {
  sm: { text: 'text-xs', icon: 'w-3 h-3', padding: 'px-1.5 py-0.5' },
  md: { text: 'text-xs', icon: 'w-3.5 h-3.5', padding: 'px-2 py-0.5' },
};

/**
 * Operator-managed tag chips (segment-actions bulk tag). Mirrors
 * SegmentBadge's Sunset-Horizon theming (CSS variables + color-mix, no
 * hardcoded colors). Renders a subtle "—" placeholder when there are no
 * tags, rather than an empty gap.
 */
export function TagChips({ tags, size = 'sm', maxVisible = 3, className = '' }: TagChipsProps) {
  const list = tags ?? [];
  const { text, icon, padding } = SIZE_CLASSES[size];

  if (list.length === 0) {
    return <span className={`text-xs text-muted-foreground ${className}`}>—</span>;
  }

  const visible = list.slice(0, maxVisible);
  const extraCount = list.length - visible.length;

  return (
    <div data-testid="tag-chips" className={`flex flex-wrap items-center gap-1 ${className}`}>
      {visible.map((tag) => (
        <span
          key={tag}
          className={`inline-flex items-center gap-1 font-medium rounded-full ${text} ${padding}`}
          style={{
            color: 'var(--chart-3)',
            backgroundColor: 'color-mix(in oklch, var(--chart-3) 12%, transparent)',
            borderWidth: 1,
            borderStyle: 'solid',
            borderColor: 'color-mix(in oklch, var(--chart-3) 30%, transparent)',
          }}
        >
          <Tag className={icon} />
          {tag}
        </span>
      ))}
      {extraCount > 0 && (
        <span className="text-xs text-muted-foreground">+{extraCount}</span>
      )}
    </div>
  );
}
