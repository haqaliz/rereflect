import apiClient from '../api-client';

export interface AISettings {
  ai_analysis_enabled: boolean;
  has_custom_key: boolean;
}

export interface AISettingsUpdate {
  ai_analysis_enabled?: boolean;
  openai_api_key?: string;
}

export const aiSettingsAPI = {
  get: async (): Promise<AISettings> => {
    const response = await apiClient.get('/api/v1/settings/ai');
    return response.data;
  },

  update: async (data: AISettingsUpdate): Promise<AISettings> => {
    const response = await apiClient.patch('/api/v1/settings/ai', data);
    return response.data;
  },
};
