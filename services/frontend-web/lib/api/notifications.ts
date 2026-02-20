import apiClient from '../api-client';

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  message: string | null;
  link: string | null;
  is_read: boolean;
  is_dismissed: boolean;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  unread_count: number;
}

export interface AlertPreference {
  alert_type: string;
  is_enabled: boolean;
  channel_email: boolean;
  channel_slack: boolean;
  channel_inapp: boolean;
  channel_intercom: boolean;
  threshold_value: number | null;
  drop_threshold?: number | null;
  retention_days: number;
}

export interface RetentionTypeItem {
  alert_type: string;
  retention_days: number;
  extra_days: number;
  monthly_cost: number;
}

export interface RetentionInfo {
  types: RetentionTypeItem[];
  total_extra_days: number;
  total_monthly_cost: number;
  min_days: number;
  max_days: number;
  price_per_day: number;
}

export const notificationsAPI = {
  list: async (params?: { page?: number; page_size?: number; type?: string; dismissed?: boolean }): Promise<NotificationListResponse> => {
    const response = await apiClient.get('/api/v1/notifications', { params });
    return response.data;
  },

  getById: async (id: number): Promise<NotificationItem> => {
    const response = await apiClient.get(`/api/v1/notifications/${id}`);
    return response.data;
  },

  getUnreadCount: async (): Promise<{ count: number }> => {
    const response = await apiClient.get('/api/v1/notifications/unread-count');
    return response.data;
  },

  markRead: async (id: number): Promise<void> => {
    await apiClient.patch(`/api/v1/notifications/${id}/read`);
  },

  markAllRead: async (): Promise<{ updated: number }> => {
    const response = await apiClient.post('/api/v1/notifications/read-all');
    return response.data;
  },

  dismiss: async (id: number): Promise<void> => {
    await apiClient.patch(`/api/v1/notifications/${id}/dismiss`);
  },

  restore: async (id: number): Promise<void> => {
    await apiClient.patch(`/api/v1/notifications/${id}/restore`);
  },

  getPreferences: async (): Promise<{ preferences: AlertPreference[] }> => {
    const response = await apiClient.get('/api/v1/notifications/preferences');
    return response.data;
  },

  updatePreferences: async (preferences: AlertPreference[]): Promise<{ preferences: AlertPreference[] }> => {
    const response = await apiClient.put('/api/v1/notifications/preferences', { preferences });
    return response.data;
  },

  getRetention: async (): Promise<RetentionInfo> => {
    const response = await apiClient.get('/api/v1/notifications/retention');
    return response.data;
  },

  updateRetention: async (retentions: { alert_type: string; days: number }[]): Promise<RetentionInfo> => {
    const response = await apiClient.put('/api/v1/notifications/retention', { retentions });
    return response.data;
  },
};
