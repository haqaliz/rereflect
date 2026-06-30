import apiClient from '../api-client';

// ---- Types ----

export interface HubSpotConnectionStatus {
  connected: boolean;
  portal_name: string | null;
  hub_id: string | null;
  token_hint: string | null;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_error: string | null;
  contacts_synced: number;
  contacts_matched: number;
  arr_property_name: string;
  connected_at: string | null;
}

export interface HubSpotConnectResponse {
  connected: boolean;
  portal_name: string | null;
  hub_id: string | null;
  token_hint: string | null;
}

export interface HubSpotTestResponse {
  success: boolean;
  message: string;
}

export interface HubSpotDisconnectResponse {
  success: boolean;
  message: string;
}

// ---- API ----

export const hubspotAPI = {
  getStatus: async (): Promise<HubSpotConnectionStatus> => {
    const response = await apiClient.get('/api/v1/integrations/hubspot/status');
    return response.data;
  },

  connect: async (
    accessToken: string,
    arrPropertyName: string = 'annualrevenue',
  ): Promise<HubSpotConnectResponse> => {
    const response = await apiClient.post(
      '/api/v1/integrations/hubspot/connect',
      { access_token: accessToken, arr_property_name: arrPropertyName },
    );
    return response.data;
  },

  disconnect: async (): Promise<HubSpotDisconnectResponse> => {
    const response = await apiClient.delete(
      '/api/v1/integrations/hubspot/disconnect',
    );
    return response.data;
  },

  testConnection: async (): Promise<HubSpotTestResponse> => {
    const response = await apiClient.post(
      '/api/v1/integrations/hubspot/test',
    );
    return response.data;
  },
};
