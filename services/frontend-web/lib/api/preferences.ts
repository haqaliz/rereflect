import apiClient from '../api-client';

export interface Preferences {
  weekly_digest_enabled: boolean;
}

export const preferencesAPI = {
  get: async (): Promise<Preferences> => {
    const response = await apiClient.get('/api/v1/auth/me/preferences');
    return response.data;
  },

  update: async (data: Partial<Preferences>): Promise<Preferences> => {
    const response = await apiClient.patch('/api/v1/auth/me/preferences', data);
    return response.data;
  },
};
