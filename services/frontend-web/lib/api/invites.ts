import apiClient from '../api-client';

export interface InviteDetails {
  email: string;
  role: string;
  organization_name: string;
  expires_at: string;
  invited_by_name: string;
}

export interface AcceptInviteRequest {
  password: string;
}

export interface AcceptInviteResponse {
  user: {
    id: number;
    email: string;
    role: string;
  };
  access_token: string;
}

export const invitesAPI = {
  /**
   * Get invite details by token (public endpoint)
   */
  getDetails: async (token: string): Promise<InviteDetails> => {
    const response = await apiClient.get(`/api/v1/invites/${token}`);
    return response.data;
  },

  /**
   * Accept an invite and create user account (public endpoint)
   */
  accept: async (token: string, data: AcceptInviteRequest): Promise<AcceptInviteResponse> => {
    const response = await apiClient.post(`/api/v1/invites/${token}/accept`, data);
    return response.data;
  },
};
