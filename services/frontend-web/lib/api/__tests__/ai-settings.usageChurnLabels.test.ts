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

describe('aiSettingsAPI — usage_churn_labels_mode + usage_churn_label_config (usage-decline churn labels)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('update({ usage_churn_labels_mode }) PATCHes /api/v1/settings/ai with exactly that payload', async () => {
    mockPatch.mockResolvedValue({ data: { usage_churn_labels_mode: 'shadow' } });

    await aiSettingsAPI.update({ usage_churn_labels_mode: 'shadow' });

    expect(mockPatch).toHaveBeenCalledWith('/api/v1/settings/ai', {
      usage_churn_labels_mode: 'shadow',
    });
  });

  it('update({ usage_churn_label_config }) PATCHes /api/v1/settings/ai with the sustain_days payload', async () => {
    mockPatch.mockResolvedValue({
      data: { usage_churn_label_config: { sustain_days: 10 } },
    });

    await aiSettingsAPI.update({ usage_churn_label_config: { sustain_days: 10 } });

    expect(mockPatch).toHaveBeenCalledWith('/api/v1/settings/ai', {
      usage_churn_label_config: { sustain_days: 10 },
    });
  });

  it('get() round-trips usage_churn_labels_mode + usage_churn_label_config through the typed AISettings return value', async () => {
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
        urgency_classifier_mode: 'off',
        usage_churn_labels_mode: 'shadow',
        usage_churn_label_config: { sustain_days: 14 },
        models: { categorization: 'gpt-4o-mini', analysis: 'gpt-4o-mini', insights: 'gpt-4o-mini' },
      },
    });

    const settings: AISettings = await aiSettingsAPI.get();

    expect(settings.usage_churn_labels_mode).toBe('shadow');
    expect(settings.usage_churn_label_config).toEqual({ sustain_days: 14 });
  });
});
