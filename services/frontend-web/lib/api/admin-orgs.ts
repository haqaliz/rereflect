import apiClient from '../api-client';

export interface AdminOrg {
  id: number;
  name: string;
  plan: string;
  user_count: number;
  stripe_customer_id: string | null;
  promo_code_used: string | null;
  created_at: string;
}

export interface AdminOrgUser {
  id: number;
  email: string;
  role: string;
  is_system_admin: boolean;
  last_active_at: string | null;
}

export interface AdminOrgDetail extends AdminOrg {
  users: AdminOrgUser[];
  seat_count: number;
  max_seats: number | null;
  ai_analysis_enabled: boolean;
  auto_assignment_enabled: boolean;
}

export interface AdminOrgListResponse {
  organizations: AdminOrg[];
  total: number;
  page: number;
  page_size: number;
}

export const adminOrgsAPI = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    search?: string;
  }): Promise<AdminOrgListResponse> => {
    const response = await apiClient.get('/api/v1/admin/organizations', { params });
    return response.data;
  },

  get: async (id: number): Promise<AdminOrgDetail> => {
    const response = await apiClient.get(`/api/v1/admin/organizations/${id}`);
    return response.data;
  },
};
