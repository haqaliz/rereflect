import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import { aiSettingsAPI, type AISettings } from '@/lib/api/ai-settings';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPatch = apiClient.patch as ReturnType<typeof vi.fn>;

describe('aiSettingsAPI — category_classifier_mode field (M5.2 category classifier)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('update({ category_classifier_mode }) PATCHes /api/v1/settings/ai with exactly that payload', async () => {
    mockPatch.mockResolvedValue({ data: { category_classifier_mode: 'shadow' } });

    await aiSettingsAPI.update({ category_classifier_mode: 'shadow' });

    expect(mockPatch).toHaveBeenCalledWith('/api/v1/settings/ai', {
      category_classifier_mode: 'shadow',
    });
  });

  it('get() round-trips category_classifier_mode through the typed AISettings return value', async () => {
    mockGet.mockResolvedValue({
      data: {
        ai_analysis_enabled: true,
        has_custom_key: false,
        default_provider: 'openai',
        base_url: null,
        model_embeddings: null,
        sentiment_provider: 'vader',
        classifier_mode: 'off',
        category_classifier_mode: 'off',
        models: { categorization: 'gpt-4o-mini', analysis: 'gpt-4o-mini', insights: 'gpt-4o-mini' },
      },
    });

    const settings: AISettings = await aiSettingsAPI.get();

    expect(settings.category_classifier_mode).toBe('off');
  });
});
