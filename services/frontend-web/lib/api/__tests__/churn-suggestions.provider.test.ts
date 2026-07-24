import { describe, it, expect } from 'vitest';
import type { ChurnSuggestionProvider, ChurnSuggestion } from '@/lib/api/churn-suggestions';

// TS-only widening (no runtime behaviour change) — verified by `tsc --noEmit`.
// Vitest's esbuild transform does not type-check, so this test's real RED/GREEN
// signal comes from the TypeScript compiler, not test failure. The runtime
// assertion below just keeps the file a meaningful, non-trivial test.

describe('ChurnSuggestionProvider — widened to include usage_decline', () => {
  it('accepts "usage_decline" as a valid ChurnSuggestionProvider value', () => {
    const provider: ChurnSuggestionProvider = 'usage_decline';
    expect(provider).toBe('usage_decline');
  });

  it('a ChurnSuggestion can carry provider "usage_decline"', () => {
    const suggestion: ChurnSuggestion = {
      id: 1,
      organization_id: 1,
      customer_email: 'alice@example.com',
      provider: 'usage_decline',
      external_opportunity_id: 'usage-1',
      suggested_churned_at: '2026-05-01T00:00:00Z',
      evidence: null,
      status: 'pending',
      reviewed_by_user_id: null,
      reviewed_at: null,
      churn_event_id: null,
      created_at: '2026-05-01T00:00:00Z',
      updated_at: '2026-05-01T00:00:00Z',
    };
    expect(suggestion.provider).toBe('usage_decline');
  });
});
