/**
 * Rule-based customer segment slugs (segment-engine contract).
 * `unsegmented` (or `null` from the API) means the engine hasn't computed a
 * segment for this customer yet — not an error state.
 */
export type SegmentSlug =
  | 'at_risk'
  | 'silent_churner'
  | 'dormant'
  | 'power_user'
  | 'happy_advocate'
  | 'new'
  | 'unsegmented';

/** Canonical slug order, mirrors backend `SEGMENT_SLUGS`. */
export const SEGMENT_SLUGS: SegmentSlug[] = [
  'at_risk',
  'silent_churner',
  'dormant',
  'power_user',
  'happy_advocate',
  'new',
  'unsegmented',
];

/** Human-readable labels — single source of truth for badge + filter dropdown. */
export const SEGMENT_LABELS: Record<SegmentSlug, string> = {
  at_risk: 'At Risk',
  silent_churner: 'Silent Churner',
  dormant: 'Dormant',
  power_user: 'Power User',
  happy_advocate: 'Happy Advocate',
  new: 'New',
  unsegmented: 'Unsegmented',
};

/** CSS color value for each segment using design system tokens (--chart-*, --destructive, --muted-foreground). */
export const SEGMENT_COLOR: Record<SegmentSlug, string> = {
  at_risk: 'var(--destructive)',
  power_user: 'var(--chart-2)',
  happy_advocate: 'var(--chart-1)',
  silent_churner: 'var(--chart-5)',
  dormant: 'var(--muted-foreground)',
  new: 'var(--chart-3)',
  unsegmented: 'var(--muted-foreground)',
};

/** Normalizes an API segment value (string | null | undefined | unknown) to a known slug. */
export function normalizeSegment(segment: string | null | undefined): SegmentSlug {
  if (!segment) return 'unsegmented';
  return (SEGMENT_SLUGS as string[]).includes(segment) ? (segment as SegmentSlug) : 'unsegmented';
}
