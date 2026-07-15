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
  // CRM writeback config/status (writeback-config-api aspect)
  writeback_enabled: boolean;
  writeback_field_name: string | null;
  last_writeback_at: string | null;
  last_writeback_status: string | null;
  last_writeback_error: string | null;
  contacts_written: number;
  // CRM-sourced churn labels (crm-churn-labels aspect). Optional so existing
  // call sites (older test fixtures) that predate this aspect keep
  // type-checking — additive, never required.
  churn_labels_enabled?: boolean;
  churn_label_config?: { renewal_opportunity_types?: string[] } | null;
  last_harvest_at?: string | null;
  last_harvest_status?: string | null;
  last_harvest_error?: string | null;
  suggestions_created?: number;
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

export interface SalesforceWritebackConfig {
  enabled: boolean;
  field_name: string | null;
}

export interface SalesforceWritebackResponse {
  writeback_enabled: boolean;
  writeback_field_name: string | null;
  last_writeback_at: string | null;
  last_writeback_status: string | null;
  last_writeback_error: string | null;
  contacts_written: number;
}

export interface SalesforceWritebackTestResponse {
  ok: boolean;
  reason: string | null;
}

export interface ChurnLabelsConfig {
  enabled: boolean;
  config: { renewal_opportunity_types?: string[] } | null;
}

export interface ChurnLabelOption {
  id: string;
  label: string;
}

export interface ChurnLabelOptionsResponse {
  options: ChurnLabelOption[];
  provider: string;
}

export interface ChurnLabelsResponse {
  churn_labels_enabled: boolean;
  churn_label_config: { renewal_opportunity_types?: string[] } | null;
  last_harvest_at: string | null;
  last_harvest_status: string | null;
  last_harvest_error: string | null;
  suggestions_created: number;
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

  updateWriteback: async ({
    enabled,
    field_name,
  }: SalesforceWritebackConfig): Promise<SalesforceWritebackResponse> => {
    const response = await apiClient.patch(
      '/api/v1/integrations/salesforce/writeback',
      { enabled, field_name },
    );
    return response.data;
  },

  testWriteback: async (fieldName: string): Promise<SalesforceWritebackTestResponse> => {
    const response = await apiClient.post(
      '/api/v1/integrations/salesforce/writeback/test',
      { field_name: fieldName },
    );
    return response.data;
  },

  updateChurnLabels: async ({
    enabled,
    config,
  }: ChurnLabelsConfig): Promise<ChurnLabelsResponse> => {
    const response = await apiClient.patch(
      '/api/v1/integrations/salesforce/churn-labels',
      { enabled, config },
    );
    return response.data;
  },

  getChurnLabelOptions: async (): Promise<ChurnLabelOptionsResponse> => {
    const response = await apiClient.get(
      '/api/v1/integrations/salesforce/churn-labels/options',
    );
    return response.data;
  },
};
