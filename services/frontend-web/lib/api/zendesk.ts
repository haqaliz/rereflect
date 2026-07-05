import apiClient from '../api-client';

// ---- Types ----
//
// Mirrors the backend contract in
// services/backend-api/src/api/routes/zendesk_integration.py exactly.
// Zendesk is inbound-only (PRD explicit) — there is no outbound
// createIssue/getProjects/getIssueTypes equivalent here, unlike jira.ts.

export interface ZendeskConnectionStatus {
  connected: boolean;
  subdomain: string | null;
  email: string | null;
  token_hint: string | null;
  account_user_id: string | null;
  display_name: string | null;
  is_active: boolean | null;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_error: string | null;
  connected_at: string | null;
  // Whether a `zendesk` FeedbackSource already exists for this org (connect
  // auto-provisions one — see backend-connection/_impl-report.md). Absent on
  // older/partial payloads; treat as falsy, never assume true.
  has_feedback_source?: boolean | null;
}

export interface ZendeskConnectRequest {
  subdomain: string;
  email: string;
  api_token: string;
}

export interface ZendeskConnectResponse {
  connected: boolean;
  subdomain: string | null;
  email: string | null;
  token_hint: string | null;
  account_user_id: string | null;
  display_name: string | null;
  // Display-once: the plaintext webhook HMAC secret. Only ever returned by
  // POST /connect (never by GET /status). Always optional in this type.
  webhook_secret?: string | null;
  has_feedback_source?: boolean | null;
  // api_token is intentionally NEVER included
}

export interface ZendeskDisconnectResponse {
  success: boolean;
  message: string;
}

export interface ZendeskTestResponse {
  success: boolean;
  message: string | null;
}

export interface ZendeskSyncResponse {
  status: string;
  integration_id: number;
}

// ---- API ----

export const zendeskAPI = {
  connect: async (data: ZendeskConnectRequest): Promise<ZendeskConnectResponse> => {
    const response = await apiClient.post('/api/v1/integrations/zendesk/connect', data);
    return response.data;
  },

  getStatus: async (): Promise<ZendeskConnectionStatus> => {
    const response = await apiClient.get('/api/v1/integrations/zendesk/status');
    return response.data;
  },

  disconnect: async (): Promise<ZendeskDisconnectResponse> => {
    const response = await apiClient.delete('/api/v1/integrations/zendesk/disconnect');
    return response.data;
  },

  testConnection: async (): Promise<ZendeskTestResponse> => {
    const response = await apiClient.post('/api/v1/integrations/zendesk/test');
    return response.data;
  },

  // Should-have (PRD): manual "Sync now" trigger, reuses the beat task on
  // demand. Mirrors the backend's POST /sync (no plan gating — OSS/BYOK).
  triggerSync: async (): Promise<ZendeskSyncResponse> => {
    const response = await apiClient.post('/api/v1/integrations/zendesk/sync');
    return response.data;
  },
};
