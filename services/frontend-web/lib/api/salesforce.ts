import apiClient from '../api-client';

// ---- Types ----

export interface SalesforceConnectionStatus {
  connected: boolean;
  instance_url: string | null;
  sf_org_id: string | null;
  token_hint?: string | null;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_error: string | null;
  contacts_synced: number;
  contacts_matched: number;
  connected_at: string | null;
}

export interface SalesforceConnectUrlResponse {
  auth_url: string;
}

export interface SalesforceDisconnectResponse {
  success: boolean;
  message: string;
}

export interface SalesforceTestResponse {
  success: boolean;
  message: string;
}

// ---- API ----
// OAuth redirect only — there is no connect(token) method. The flow is:
// getConnectUrl() -> redirect the browser to auth_url -> Salesforce
// redirects back to /api/v1/integrations/salesforce/callback.

export const salesforceAPI = {
  // withCredentials: true so the HttpOnly `sf_oauth_nonce` cookie set by
  // /connect-url round-trips to /callback (SEC-1, see backend
  // salesforce_integration.py). Requires the deployment's CORS config to
  // send Access-Control-Allow-Credentials: true with a non-wildcard origin.
  getConnectUrl: async (): Promise<SalesforceConnectUrlResponse> => {
    const response = await apiClient.get(
      '/api/v1/integrations/salesforce/connect-url',
      { withCredentials: true },
    );
    return response.data;
  },

  getStatus: async (): Promise<SalesforceConnectionStatus> => {
    const response = await apiClient.get('/api/v1/integrations/salesforce/status');
    return response.data;
  },

  disconnect: async (): Promise<SalesforceDisconnectResponse> => {
    const response = await apiClient.delete(
      '/api/v1/integrations/salesforce/disconnect',
    );
    return response.data;
  },

  test: async (): Promise<SalesforceTestResponse> => {
    const response = await apiClient.post('/api/v1/integrations/salesforce/test');
    return response.data;
  },
};
