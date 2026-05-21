import type { ChurnReasonCode } from '@/lib/api/churn-events';

export type RiskBand = 'low' | 'medium' | 'high' | 'critical';

/**
 * Returns a risk band string based on churn probability (0.0–1.0).
 * Bands: <0.30 low, <0.50 medium, <0.70 high, >=0.70 critical.
 */
export function getRiskBandColor(p: number): RiskBand {
  if (p >= 0.70) return 'critical';
  if (p >= 0.50) return 'high';
  if (p >= 0.30) return 'medium';
  return 'low';
}

/** CSS color value for each risk band using design system tokens. */
export const RISK_BAND_COLOR: Record<RiskBand, string> = {
  critical: 'var(--destructive)',
  high: 'var(--chart-1)',
  medium: 'var(--chart-2)',
  low: 'var(--chart-5)',
};

export const CHURN_REASON_LABELS: Record<ChurnReasonCode, string> = {
  price: 'Price',
  competitor: 'Competitor',
  product_quality: 'Product Quality',
  no_longer_needed: 'No Longer Needed',
  silent_churn: 'Silent Churn',
  other: 'Other',
};

export const CHURN_REASON_CODES: ChurnReasonCode[] = [
  'price',
  'competitor',
  'product_quality',
  'no_longer_needed',
  'silent_churn',
  'other',
];
