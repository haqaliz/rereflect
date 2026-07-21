import apiClient from '../api-client';

export interface CustomCategory {
  id: number;
  name: string;
  description: string | null;
  category_type: 'pain_point' | 'feature_request' | 'urgency' | 'general';
  is_active: boolean;
  created_at: string;
}

export interface CustomCategoryCreate {
  name: string;
  description?: string;
  category_type: 'pain_point' | 'feature_request' | 'urgency' | 'general';
}

export interface CustomCategoryUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
}

/** All six weights the backend persists (`categories.py` `HealthWeightsUpdate`), summing to 100.
 *  `usage` is 0 until an operator opts in via Settings → AI → Health Score Weights.
 *  `crm` is not surfaced as an editable field anywhere in the UI, but must still round-trip
 *  through every read/write of this type — omitting it on a PUT zeros it server-side (D4). */
export interface HealthWeights {
  churn: number;
  sentiment: number;
  resolution: number;
  frequency: number;
  usage: number;
  crm: number;
}

/** Response from GET /health-weights. Identical shape to `HealthWeights` on the wire. */
export type HealthWeightsResponse = HealthWeights;

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

  getHealthWeights: async (): Promise<HealthWeightsResponse> => {
    const response = await apiClient.get('/api/v1/categories/health-weights');
    return response.data;
  },

  updateHealthWeights: async (data: HealthWeights): Promise<HealthWeights> => {
    const response = await apiClient.put('/api/v1/categories/health-weights', data);
    return response.data;
  },
};
