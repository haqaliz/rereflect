import apiClient from '../api-client';

export interface Organization {
  id: number;
  name: string;
  plan: string;
  stripe_customer_id: string | null;
  created_at: string;
}

export interface OrganizationStats {
  total_users: number;
  total_feedback: number;
  plan: string;
}

export interface UpdateOrganizationData {
  name?: string;
}

export const organizationAPI = {
  getMe: async (): Promise<Organization> => {
    const response = await apiClient.get('/api/v1/organizations/me');
    return response.data;
  },

  getStats: async (): Promise<OrganizationStats> => {
    const response = await apiClient.get('/api/v1/organizations/me/stats');
    return response.data;
  },

  update: async (data: UpdateOrganizationData): Promise<Organization> => {
    const response = await apiClient.patch('/api/v1/organizations/me', data);
    return response.data;
  },
};
