import apiClient from '../api-client';

export interface AdminUser {
  id: number;
  email: string;
  role: string;
  organization_id: number;
  organization_name: string;
  plan: string;
  is_system_admin: boolean;
  auth_provider: string;
  created_at: string;
  last_active_at: string | null;
}

export interface AdminUserListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUserUpdate {
  organization_id?: number;
  role?: string;
  is_system_admin?: boolean;
}

export const adminUsersAPI = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    search?: string;
    organization_id?: number;
  }): Promise<AdminUserListResponse> => {
    const response = await apiClient.get('/api/v1/admin/users', { params });
    return response.data;
  },

  get: async (id: number): Promise<AdminUser> => {
    const response = await apiClient.get(`/api/v1/admin/users/${id}`);
    return response.data;
  },

  update: async (id: number, data: AdminUserUpdate): Promise<AdminUser> => {
    const response = await apiClient.patch(`/api/v1/admin/users/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/admin/users/${id}`);
  },
};
