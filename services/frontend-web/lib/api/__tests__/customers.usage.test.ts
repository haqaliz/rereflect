import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the api-client so no real HTTP calls are made
vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import {
  customersAPI,
  type CustomerUsageResponse,
  type UsageHistoryEntry,
  type CustomerProfileData,
} from '@/lib/api/customers';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;

// ─── Fixtures ────────────────────────────────────────────────────────────────

const mockSeries: UsageHistoryEntry[] = [
  { date: '2026-06-01', events: 4 },
  { date: '2026-06-02', events: 7 },
  { date: '2026-06-03', events: 2 },
];

const mockUsageResponse: CustomerUsageResponse = {
  email: 'alice@acme.com',
  last_active_at: '2026-06-28T08:00:00Z',
  login_count_7d: 5,
  login_count_30d: 18,
  active_days_30d: 14,
  distinct_feature_count: 6,
  usage_score: 72,
  period_days: 30,
  series: mockSeries,
};

// ─── getUsage ────────────────────────────────────────────────────────────────

describe('customersAPI.getUsage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/customers/:email/usage?days=30 by default', async () => {
    mockGet.mockResolvedValue({ data: mockUsageResponse });
    await customersAPI.getUsage('alice@acme.com');
    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/customers/alice%40acme.com/usage?days=30'
    );
  });

  it('URL-encodes the email', async () => {
    mockGet.mockResolvedValue({ data: mockUsageResponse });
    await customersAPI.getUsage('alice+test@acme.com');
    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining('alice%2Btest%40acme.com')
    );
  });

  it('accepts a custom days param', async () => {
    mockGet.mockResolvedValue({ data: mockUsageResponse });
    await customersAPI.getUsage('alice@acme.com', 90);
    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/customers/alice%40acme.com/usage?days=90'
    );
  });

  it('returns CustomerUsageResponse with all required fields', async () => {
    mockGet.mockResolvedValue({ data: mockUsageResponse });
    const result = await customersAPI.getUsage('alice@acme.com');

    expect(result.email).toBe('alice@acme.com');
    expect(result.last_active_at).toBe('2026-06-28T08:00:00Z');
    expect(result.login_count_7d).toBe(5);
    expect(result.login_count_30d).toBe(18);
    expect(result.active_days_30d).toBe(14);
    expect(result.distinct_feature_count).toBe(6);
    expect(result.usage_score).toBe(72);
    expect(result.period_days).toBe(30);
  });

  it('returns series array with date+events entries', async () => {
    mockGet.mockResolvedValue({ data: mockUsageResponse });
    const result = await customersAPI.getUsage('alice@acme.com');

    expect(result.series).toHaveLength(3);
    expect(result.series[0]).toEqual({ date: '2026-06-01', events: 4 });
    expect(result.series[1].events).toBe(7);
  });

  it('handles null last_active_at (no usage yet)', async () => {
    const noUsage: CustomerUsageResponse = {
      ...mockUsageResponse,
      last_active_at: null,
      login_count_7d: 0,
      login_count_30d: 0,
      active_days_30d: 0,
      distinct_feature_count: 0,
      usage_score: 50,
      series: [],
    };
    mockGet.mockResolvedValue({ data: noUsage });
    const result = await customersAPI.getUsage('alice@acme.com');
    expect(result.last_active_at).toBeNull();
    expect(result.series).toHaveLength(0);
  });

  it('propagates errors from the API client', async () => {
    mockGet.mockRejectedValue(new Error('Network error'));
    await expect(customersAPI.getUsage('alice@acme.com')).rejects.toThrow('Network error');
  });
});

// ─── CustomerProfileData has usage_component ─────────────────────────────────

describe('CustomerProfileData type: usage_component', () => {
  it('accepts usage_component as an optional number field', () => {
    // TypeScript compile-time check via object assignment
    const profile: CustomerProfileData = {
      customer_email: 'test@co.com',
      customer_name: 'Test User',
      health_score: 80,
      risk_level: 'healthy',
      confidence_level: 'high',
      confidence_score: null,
      feedback_count: 10,
      last_feedback_at: null,
      churn_risk_component: 70,
      sentiment_component: 80,
      resolution_component: 75,
      frequency_component: 60,
      usage_component: 65,
      llm_analysis_summary: null,
      llm_recommended_actions: null,
      llm_risk_drivers: null,
      llm_urgency: null,
      llm_analysis_type: null,
      llm_analyzed_at: null,
      llm_actions: null,
      llm_analysis: null,
      is_archived: false,
      created_at: '2026-01-01T00:00:00Z',
    };
    expect(profile.usage_component).toBe(65);
  });

  it('usage_component is optional (absent = treated as missing)', () => {
    const profile: CustomerProfileData = {
      customer_email: 'test@co.com',
      customer_name: null,
      health_score: 60,
      risk_level: 'moderate',
      confidence_level: 'medium',
      confidence_score: null,
      feedback_count: 5,
      last_feedback_at: null,
      churn_risk_component: 50,
      sentiment_component: 60,
      resolution_component: 55,
      frequency_component: 65,
      llm_analysis_summary: null,
      llm_recommended_actions: null,
      llm_risk_drivers: null,
      llm_urgency: null,
      llm_analysis_type: null,
      llm_analyzed_at: null,
      llm_actions: null,
      llm_analysis: null,
      is_archived: false,
      created_at: '2026-01-01T00:00:00Z',
    };
    // No usage_component → undefined
    expect(profile.usage_component).toBeUndefined();
  });
});
