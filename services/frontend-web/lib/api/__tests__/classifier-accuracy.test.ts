import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import {
  getClassifierAccuracy,
  getClassifierVersions,
  rollbackClassifier,
  resumeClassifier,
  formatMetricPercent,
  formatDelta,
} from '@/lib/api/classifier-accuracy';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPost = apiClient.post as ReturnType<typeof vi.fn>;

describe('classifier-accuracy API client — classifierType threading', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getClassifierAccuracy() with no arg defaults to classifier_type=sentiment', async () => {
    mockGet.mockResolvedValue({ data: {} });
    await getClassifierAccuracy();

    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/accuracy?classifier_type=sentiment'
    );
  });

  it("getClassifierAccuracy('category') sends classifier_type=category", async () => {
    mockGet.mockResolvedValue({ data: {} });
    await getClassifierAccuracy('category');

    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/accuracy?classifier_type=category'
    );
  });

  it("getClassifierAccuracy('churn') sends classifier_type=churn", async () => {
    mockGet.mockResolvedValue({ data: {} });
    await getClassifierAccuracy('churn');

    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/accuracy?classifier_type=churn'
    );
  });

  it('rollbackClassifier() with no arg defaults to classifier_type=sentiment', async () => {
    mockPost.mockResolvedValue({ data: {} });
    await rollbackClassifier();

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/rollback?classifier_type=sentiment'
    );
  });

  it("rollbackClassifier('category') sends classifier_type=category", async () => {
    mockPost.mockResolvedValue({ data: {} });
    await rollbackClassifier('category');

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/rollback?classifier_type=category'
    );
  });

  it("rollbackClassifier('churn') sends classifier_type=churn", async () => {
    mockPost.mockResolvedValue({ data: {} });
    await rollbackClassifier('churn');

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/rollback?classifier_type=churn'
    );
  });

  it('rollbackClassifier() with a toVersionId appends &to_version_id=', async () => {
    mockPost.mockResolvedValue({ data: {} });
    await rollbackClassifier('sentiment', 42);

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/rollback?classifier_type=sentiment&to_version_id=42'
    );
  });

  it('rollbackClassifier() with no toVersionId omits the to_version_id param', async () => {
    mockPost.mockResolvedValue({ data: {} });
    await rollbackClassifier('category');

    expect(mockPost).toHaveBeenCalledWith(
      expect.not.stringContaining('to_version_id')
    );
  });

  it('getClassifierVersions() with no arg defaults to classifier_type=sentiment', async () => {
    mockGet.mockResolvedValue({ data: {} });
    await getClassifierVersions();

    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/versions?classifier_type=sentiment'
    );
  });

  it("getClassifierVersions('urgency') sends classifier_type=urgency", async () => {
    mockGet.mockResolvedValue({ data: {} });
    await getClassifierVersions('urgency');

    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/versions?classifier_type=urgency'
    );
  });

  it("getClassifierVersions('churn') sends classifier_type=churn", async () => {
    mockGet.mockResolvedValue({ data: {} });
    await getClassifierVersions('churn');

    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/versions?classifier_type=churn'
    );
  });

  it('resumeClassifier() with no arg defaults to classifier_type=sentiment', async () => {
    mockPost.mockResolvedValue({ data: {} });
    await resumeClassifier();

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/resume?classifier_type=sentiment'
    );
  });

  it("resumeClassifier('category') sends classifier_type=category", async () => {
    mockPost.mockResolvedValue({ data: {} });
    await resumeClassifier('category');

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/resume?classifier_type=category'
    );
  });

  it("resumeClassifier('churn') sends classifier_type=churn", async () => {
    mockPost.mockResolvedValue({ data: {} });
    await resumeClassifier('churn');

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/settings/ai/classifier/resume?classifier_type=churn'
    );
  });
});

describe('classifier-accuracy formatters (direct import, previously only exercised indirectly)', () => {
  it('formatMetricPercent formats a 0-1 fraction as a whole-number percent', () => {
    expect(formatMetricPercent(0.71)).toBe('71%');
  });

  it('formatMetricPercent formats 0 as 0%', () => {
    expect(formatMetricPercent(0)).toBe('0%');
  });

  it('formatMetricPercent formats 1 as 100%', () => {
    expect(formatMetricPercent(1)).toBe('100%');
  });

  it('formatMetricPercent returns an em dash for null', () => {
    expect(formatMetricPercent(null)).toBe('—');
  });

  it('formatDelta formats a positive delta with a leading +', () => {
    expect(formatDelta(0.06)).toBe('+0.06');
  });

  it('formatDelta formats a negative delta with a leading -', () => {
    expect(formatDelta(-0.03)).toBe('-0.03');
  });
});
