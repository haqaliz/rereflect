import apiClient from '../api-client';

export interface CustomCategory {
  id: number;
  name: string;
  description: string | null;
  category_type: 'pain_point' | 'feature_request' | 'general';
  is_active: boolean;
  created_at: string;
}

export interface CustomCategoryCreate {
  name: string;
  description?: string;
  category_type: 'pain_point' | 'feature_request' | 'general';
}

export interface CustomCategoryUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
}

export const categoriesAPI = {
  list: async (categoryType?: string): Promise<CustomCategory[]> => {
    const params = categoryType ? { category_type: categoryType } : {};
    const response = await apiClient.get('/api/v1/categories/custom', { params });
    return response.data;
  },

  create: async (data: CustomCategoryCreate): Promise<CustomCategory> => {
    const response = await apiClient.post('/api/v1/categories/custom', data);
    return response.data;
  },

  update: async (id: number, data: CustomCategoryUpdate): Promise<CustomCategory> => {
    const response = await apiClient.patch(`/api/v1/categories/custom/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/categories/custom/${id}`);
  },
};
