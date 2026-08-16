import apiClient from '../api-client';

// ---- Types ----
//
// Mirrors the backend contract in
// services/backend-api/src/api/routes/intercom_integration.py exactly.
//
// This is the TOKEN-PASTE path. The older OAuth flow still exists (see
// integrationsAPI.getIntercomOAuthUrl, driven from the settings/integrations/new
// wizard) and both remain supported — an org may use one or the other, never
// both at once. See docs/planning/intercom-selfhost-ingestion/prd.md D4/D6.
//
// Intercom is inbound for ingestion but outbound for resolve write-back:
// marking Intercom-sourced feedback resolved can add a note to (and close)
// the linked conversation. There is no createIssue/getProjects equivalent
// beyond that.

export interface IntercomConnectionStatus {
  connected: boolean;
  workspace_id: string | null;
  workspace_name: string | null;
  token_hint: string | null;
  admin_id: string | null;
  // Whether an app Client Secret is stored for this org. Never the secret
  // itself — the backend returns only this boolean, from either endpoint.
  has_client_secret: boolean;
  // Whether an `intercom` FeedbackSource exists (connect auto-provisions one).
  has_feedback_source: boolean;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_error: string | null;
  // How many feedback items this integration has produced. A connected
  // integration sitting at 0 is the most useful thing an operator can know.
  feedback_items_ingested: number;
  // Estimated conversations left to sync in the current drain window (from
  // Intercom's total_count minus seen at the last completed run). null = no
  // estimate: never synced, failed run, OAuth, or an empty window.
  backlog_remaining: number | null;
  // Resolve write-back config/status (config-api-routes aspect). Required —
  // the card only ever reads them while connected, and the connected response
  // always carries them.
  writeback_enabled: boolean;
  writeback_action: 'note_only' | 'note_and_close' | null;
  last_writeback_at: string | null;
  last_writeback_status: string | null;
  last_writeback_error: string | null;
}

export interface IntercomConnectRequest {
  access_token: string;
  // Optional: the Developer Hub app's Client Secret, which is what Intercom
  // signs webhook deliveries with. Supplying it makes signature verification
  // per-tenant. An operator who only wants the 15-minute pull can omit it.
  client_secret?: string;
}

export interface IntercomConnectResponse {
  connected: boolean;
  workspace_id: string | null;
  workspace_name: string | null;
  token_hint: string | null;
  admin_id: string | null;
  has_client_secret: boolean;
  has_feedback_source: boolean;
  // access_token and client_secret are intentionally NEVER included
}

export interface IntercomDisconnectResponse {
  disconnected: boolean;
}

export interface IntercomWritebackConfig {
  enabled: boolean;
  action?: 'note_only' | 'note_and_close';
}

export interface IntercomWritebackResponse {
  writeback_enabled: boolean;
  writeback_action: 'note_only' | 'note_and_close' | null;
  last_writeback_at: string | null;
  last_writeback_status: string | null;
  last_writeback_error: string | null;
}

export interface IntercomWritebackTestResponse {
  ok: boolean;
  reason: string | null;
}

// ---- API ----

export const intercomAPI = {
  connect: async (
    data: IntercomConnectRequest
  ): Promise<IntercomConnectResponse> => {
    const response = await apiClient.post(
      '/api/v1/integrations/intercom/connect',
      data
    );
    return response.data;
  },

  getStatus: async (): Promise<IntercomConnectionStatus> => {
    const response = await apiClient.get('/api/v1/integrations/intercom/status');
    return response.data;
  },

  disconnect: async (): Promise<IntercomDisconnectResponse> => {
    const response = await apiClient.delete(
      '/api/v1/integrations/intercom/disconnect'
    );
    return response.data;
  },

  updateWriteback: async ({
    enabled,
    action,
  }: IntercomWritebackConfig): Promise<IntercomWritebackResponse> => {
    const response = await apiClient.patch(
      '/api/v1/integrations/intercom/writeback',
      { enabled, action }
    );
    return response.data;
  },

  testWriteback: async (): Promise<IntercomWritebackTestResponse> => {
    const response = await apiClient.post(
      '/api/v1/integrations/intercom/writeback/test'
    );
    return response.data;
  },
};
