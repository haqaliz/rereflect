import { describe, it, expect } from 'vitest';
import { formatMetricPercent, formatDelta } from '@/lib/api/sentiment-accuracy';

describe('sentiment-accuracy formatting helpers', () => {
  describe('formatMetricPercent', () => {
    it('returns em dash for null', () => {
      expect(formatMetricPercent(null)).toBe('—');
    });

    it('returns rounded percent for a fraction', () => {
      expect(formatMetricPercent(0.77)).toBe('77%');
    });

    it('rounds to nearest whole percent', () => {
      expect(formatMetricPercent(0.595)).toBe('60%'); // Math.round(59.5) === 60
    });
  });

  describe('formatDelta', () => {
    it('returns em dash for null', () => {
      expect(formatDelta(null)).toBe('—');
    });

    it('returns a signed positive string', () => {
      expect(formatDelta(0.06)).toBe('+0.06');
    });

    it('returns a signed negative string', () => {
      expect(formatDelta(-0.02)).toBe('-0.02');
    });

    it('returns a signed zero string', () => {
      expect(formatDelta(0)).toBe('+0.00');
    });
  });
});
