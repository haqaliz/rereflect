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
  // CRM writeback config/status (writeback-config-api aspect)
  writeback_enabled: boolean;
  writeback_field_name: string | null;
  last_writeback_at: string | null;
  last_writeback_status: string | null;
  last_writeback_error: string | null;
  contacts_written: number;
  // CRM-sourced churn labels (crm-churn-labels aspect). Optional so existing
  // call sites (connect handler, older test fixtures) that predate this
  // aspect keep type-checking — additive, never required.
  churn_labels_enabled?: boolean;
  churn_label_config?: { renewal_pipeline_ids?: string[] } | null;
  last_harvest_at?: string | null;
  last_harvest_status?: string | null;
  last_harvest_error?: string | null;
  suggestions_created?: number;
  // Historical churn-label backfill (historical-backfill aspect). Optional
  // for the same reason as the harvest fields above — additive, never
  // required by existing call sites/fixtures.
  backfill_status?: BackfillStatus | null;
  backfill_progress?: BackfillProgress | null;
  backfill_last_run_at?: string | null;
  backfill_error?: string | null;
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

export interface HubSpotWritebackConfig {
  enabled: boolean;
  field_name: string | null;
}

export interface HubSpotWritebackResponse {
  writeback_enabled: boolean;
  writeback_field_name: string | null;
  last_writeback_at: string | null;
  last_writeback_status: string | null;
  last_writeback_error: string | null;
  contacts_written: number;
}

export interface HubSpotWritebackTestResponse {
  ok: boolean;
  reason: string | null;
}

export interface ChurnLabelsConfig {
  enabled: boolean;
  config: { renewal_pipeline_ids?: string[] } | null;
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
  churn_label_config: { renewal_pipeline_ids?: string[] } | null;
  last_harvest_at: string | null;
  last_harvest_status: string | null;
  last_harvest_error: string | null;
  suggestions_created: number;
  backfill_status?: BackfillStatus | null;
  backfill_progress?: BackfillProgress | null;
  backfill_last_run_at?: string | null;
  backfill_error?: string | null;
}

// Historical churn-label backfill (historical-backfill aspect)

export type BackfillStatus =
  | 'idle'
  | 'running'
  | 'cancelling'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface BackfillProgress {
  scanned?: number;
  suggested?: number;
  skipped_existing?: number;
  denied?: number;
  dropped_by_cap?: number;
  since?: string;
}

export interface BackfillActionResponse {
  status: string;
  backfill_status: BackfillStatus | null;
  backfill_progress: BackfillProgress | null;
  backfill_last_run_at: string | null;
  backfill_error: string | null;
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

  updateWriteback: async ({
    enabled,
    field_name,
  }: HubSpotWritebackConfig): Promise<HubSpotWritebackResponse> => {
    const response = await apiClient.patch(
      '/api/v1/integrations/hubspot/writeback',
      { enabled, field_name },
    );
    return response.data;
  },

  testWriteback: async (fieldName: string): Promise<HubSpotWritebackTestResponse> => {
    const response = await apiClient.post(
      '/api/v1/integrations/hubspot/writeback/test',
      { field_name: fieldName },
    );
    return response.data;
  },

  updateChurnLabels: async ({
    enabled,
    config,
  }: ChurnLabelsConfig): Promise<ChurnLabelsResponse> => {
    const response = await apiClient.patch(
      '/api/v1/integrations/hubspot/churn-labels',
      { enabled, config },
    );
    return response.data;
  },

  getChurnLabelOptions: async (): Promise<ChurnLabelOptionsResponse> => {
    const response = await apiClient.get(
      '/api/v1/integrations/hubspot/churn-labels/options',
    );
    return response.data;
  },

  triggerChurnBackfill: async (months: number): Promise<BackfillActionResponse> => {
    const response = await apiClient.post(
      '/api/v1/integrations/hubspot/churn-labels/backfill',
      { months },
    );
    return response.data;
  },

  cancelChurnBackfill: async (): Promise<BackfillActionResponse> => {
    const response = await apiClient.post(
      '/api/v1/integrations/hubspot/churn-labels/backfill/cancel',
    );
    return response.data;
  },
};
