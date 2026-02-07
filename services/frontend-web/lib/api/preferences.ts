import apiClient from '../api-client';

export interface AlertChannels {
  dashboard: boolean;
  email: boolean;
  slack: boolean;
}

export interface Preferences {
  weekly_digest_enabled: boolean;
  alert_channels: AlertChannels | null;
}

export interface PreferencesUpdate {
  weekly_digest_enabled?: boolean;
  alert_channels?: AlertChannels;
}

export const preferencesAPI = {
  get: async (): Promise<Preferences> => {
    const response = await apiClient.get('/api/v1/auth/me/preferences');
    return response.data;
  },

  update: async (data: PreferencesUpdate): Promise<Preferences> => {
    const response = await apiClient.patch('/api/v1/auth/me/preferences', data);
    return response.data;
  },
};
