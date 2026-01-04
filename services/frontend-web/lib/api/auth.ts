import apiClient from '../api-client';

export interface SignupData {
  email: string;
  password: string;
  organization_name: string;
}

export interface LoginData {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: number;
  email: string;
  organization_id: number;
  role: string;
  created_at: string;
}

export const authAPI = {
  signup: async (data: SignupData): Promise<AuthResponse> => {
    const response = await apiClient.post('/api/v1/auth/signup', data);
    return response.data;
  },

  login: async (data: LoginData): Promise<AuthResponse> => {
    const response = await apiClient.post('/api/v1/auth/login', data);
    return response.data;
  },

  getMe: async (): Promise<UserResponse> => {
    const response = await apiClient.get('/api/v1/auth/me');
    return response.data;
  },

  logout: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
  },
};
