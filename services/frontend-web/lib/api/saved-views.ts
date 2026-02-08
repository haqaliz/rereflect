import apiClient from '../api-client';

export interface SavedView {
  id: number;
  name: string;
  page: string;
  config: Record<string, unknown>;
  created_by_id: number;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface SavedViewCreateData {
  name: string;
  page: string;
  config: Record<string, unknown>;
}

export const savedViewsAPI = {
  list: async (page: string = 'analytics'): Promise<SavedView[]> => {
    const response = await apiClient.get(`/api/v1/saved-views/?page=${page}`);
    return response.data;
  },

  create: async (data: SavedViewCreateData): Promise<SavedView> => {
    const response = await apiClient.post('/api/v1/saved-views/', data);
    return response.data;
  },

  update: async (id: number, data: { name?: string; config?: Record<string, unknown> }): Promise<SavedView> => {
    const response = await apiClient.patch(`/api/v1/saved-views/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/saved-views/${id}`);
  },

  reorder: async (items: { id: number; position: number }[]): Promise<SavedView[]> => {
    const response = await apiClient.patch('/api/v1/saved-views/reorder', { items });
    return response.data;
  },
};
