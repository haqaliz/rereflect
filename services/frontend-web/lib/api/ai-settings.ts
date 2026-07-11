import apiClient from '../api-client';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AIModels {
  categorization: string;
  analysis: string;
  insights: string;
}

export interface AISettings {
  ai_analysis_enabled: boolean;
  has_custom_key: boolean; // kept for backward compat
  default_provider: string;
  base_url: string | null;
  model_embeddings: string | null;
  sentiment_provider: string;
  classifier_mode: string;
  category_classifier_mode: string;
  models: AIModels;
}

export interface AISettingsUpdate {
  ai_analysis_enabled?: boolean;
  openai_api_key?: string; // legacy field
  default_provider?: string;
  base_url?: string | null;
  model_embeddings?: string | null;
  sentiment_provider?: string | null;
  classifier_mode?: string | null;
  category_classifier_mode?: string | null;
  model_categorization?: string;
  model_analysis?: string;
  model_insights?: string;
}

export interface EmbeddingStatus {
  provider: string;
  model: string | null;
  dimension: number | null;
  configured: boolean;
  system_templates_embedded: number;
}

export interface SentimentStatus {
  provider: string;
  available: boolean;
  model: string | null;
}

export interface AIKey {
  provider: string;
  key_hint: string;
  is_valid: boolean;
  created_at: string;
}

export interface AIModel {
  id: number;
  provider: string;
  model_id: string;
  display_name: string;
  input_price_per_1m_tokens: number;
  output_price_per_1m_tokens: number;
  context_window: number | null;
  max_output_tokens: number | null;
  supports_json_mode: boolean;
  tier: 'cheap' | 'mid' | 'premium';
  min_plan: string;
  is_available: boolean;
  is_deprecated: boolean;
  replacement_model_id: string | null;
}

export interface AIUsageByProvider {
  provider: string;
  tokens: number;
  requests: number;
  cost_cents: number;
}

export interface AIUsage {
  month: string;
  total_tokens: number;
  total_requests: number;
  estimated_cost_cents: number;
  by_provider: AIUsageByProvider[];
  fallback_count: number;
}

export interface AIUsageDay {
  date: string;
  tokens: number;
  requests: number;
  cost_cents: number;
}

export interface AIUsageDaily {
  days: AIUsageDay[];
}

export interface AIKeyValidateResponse {
  valid: boolean;
  error?: string;
}

export interface AIModelTestResponse {
  provider: string;
  model: string;
  result: Record<string, unknown>;
  tokens: number;
  cost_cents: number;
  latency_ms: number;
}

export interface AdminAIModel extends AIModel {
  updated_at: string;
}

// ─── API ─────────────────────────────────────────────────────────────────────

export const aiSettingsAPI = {
  get: async (): Promise<AISettings> => {
    const response = await apiClient.get('/api/v1/settings/ai');
    return response.data;
  },

  update: async (data: AISettingsUpdate): Promise<AISettings> => {
    const response = await apiClient.patch('/api/v1/settings/ai', data);
    return response.data;
  },

  // API Keys
  listKeys: async (): Promise<AIKey[]> => {
    const response = await apiClient.get('/api/v1/settings/ai/keys');
    return response.data;
  },

  addKey: async (provider: string, api_key: string): Promise<AIKey> => {
    const response = await apiClient.post('/api/v1/settings/ai/keys', { provider, api_key });
    return response.data;
  },

  removeKey: async (provider: string): Promise<void> => {
    await apiClient.delete(`/api/v1/settings/ai/keys/${provider}`);
  },

  validateKey: async (provider: string, api_key: string): Promise<AIKeyValidateResponse> => {
    const response = await apiClient.post('/api/v1/settings/ai/keys/validate', { provider, api_key });
    return response.data;
  },

  // Model testing
  testModel: async (provider: string, model: string): Promise<AIModelTestResponse> => {
    const response = await apiClient.post('/api/v1/settings/ai/test-model', { provider, model });
    return response.data;
  },

  // Available models
  listModels: async (): Promise<AIModel[]> => {
    const response = await apiClient.get('/api/v1/settings/ai/models');
    return response.data;
  },

  // Usage
  getUsage: async (): Promise<AIUsage> => {
    const response = await apiClient.get('/api/v1/settings/ai/usage');
    return response.data;
  },

  getUsageDaily: async (): Promise<AIUsageDaily> => {
    const response = await apiClient.get('/api/v1/settings/ai/usage/daily');
    return response.data;
  },

  // Embeddings (S3 — local embeddings / offline Copilot)
  getEmbeddingStatus: async (): Promise<EmbeddingStatus> => {
    const response = await apiClient.get('/api/v1/settings/ai/embeddings/status');
    return response.data;
  },

  // Sentiment engine (M5.1 local-analyzer-sentiment-model, per-org-resolution)
  getSentimentStatus: async (): Promise<SentimentStatus> => {
    const response = await apiClient.get('/api/v1/settings/ai/sentiment/status');
    return response.data;
  },
};

// ─── Admin API ────────────────────────────────────────────────────────────────

export interface AdminAIModelUpdate {
  input_price_per_1m_tokens?: number;
  output_price_per_1m_tokens?: number;
  is_available?: boolean;
  is_deprecated?: boolean;
  replacement_model_id?: string | null;
}

export const adminAIModelsAPI = {
  list: async (): Promise<AdminAIModel[]> => {
    const response = await apiClient.get('/api/v1/admin/ai-models');
    return response.data;
  },

  update: async (id: number, data: AdminAIModelUpdate): Promise<AdminAIModel> => {
    const response = await apiClient.patch(`/api/v1/admin/ai-models/${id}`, data);
    return response.data;
  },

  syncPrices: async (): Promise<{ synced: number }> => {
    const response = await apiClient.post('/api/v1/admin/ai-models/sync-prices');
    return response.data;
  },
};
