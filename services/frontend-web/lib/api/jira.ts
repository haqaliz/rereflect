import apiClient from '../api-client';

// ---- Types ----

export interface JiraConnectionStatus {
  connected: boolean;
  site_url: string | null;
  email: string | null;
  token_hint: string | null;
  account_id: string | null;
  display_name: string | null;
  is_active: boolean | null;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_error: string | null;
  connected_at: string | null;
  // Inbound status sync (jira-status-sync/inbound-status-sync, Phase 5/6):
  // opt-in poller that pulls Jira issue status back onto linked feedback.
  // `last_sync_status`/`last_error` above are shared with the general
  // connection status but are also updated by the status-sync poller.
  status_sync_enabled: boolean;
  last_status_synced_at: string | null;
}

export interface JiraConnectRequest {
  site_url: string;
  email: string;
  api_token: string;
}

export interface JiraConnectResponse {
  connected: boolean;
  site_url: string | null;
  email: string | null;
  token_hint: string | null;
  account_id: string | null;
  display_name: string | null;
}

export interface JiraDisconnectResponse {
  success: boolean;
  message: string;
}

export interface JiraTestResponse {
  success: boolean;
  message: string | null;
}

export interface JiraProject {
  id: string;
  key: string | null;
  name: string | null;
}

export interface JiraIssueType {
  id: string;
  name: string | null;
}

export interface CreateJiraIssueRequest {
  feedback_id: number;
  project_id: string;
  issue_type_id: string;
  summary: string;
  description?: string;
  force?: boolean;
}

export interface CreateJiraIssueResponse {
  jira_issue_id: string;
  jira_issue_key: string;
  jira_issue_url: string;
  jira_issue_title: string;
  // Present on a 200 duplicate response instead of the fields above
  warning?: string;
  existing_issues?: Array<{
    id: number;
    jira_issue_key: string;
    jira_issue_url: string;
    jira_issue_title: string;
  }>;
}

export interface JiraLinkedIssue {
  id: number;
  feedback_id: number;
  jira_issue_id: string;
  jira_issue_key: string;
  jira_issue_url: string;
  jira_issue_title: string;
  created_at: string;
}

export interface JiraSyncTriggerResponse {
  status: string;
}

// ---- API ----

export const jiraAPI = {
  connect: async (data: JiraConnectRequest): Promise<JiraConnectResponse> => {
    const response = await apiClient.post('/api/v1/integrations/jira/connect', data);
    return response.data;
  },

  getStatus: async (): Promise<JiraConnectionStatus> => {
    const response = await apiClient.get('/api/v1/integrations/jira/status');
    return response.data;
  },

  disconnect: async (): Promise<JiraDisconnectResponse> => {
    const response = await apiClient.delete('/api/v1/integrations/jira/disconnect');
    return response.data;
  },

  testConnection: async (): Promise<JiraTestResponse> => {
    const response = await apiClient.post('/api/v1/integrations/jira/test');
    return response.data;
  },

  getProjects: async (): Promise<JiraProject[]> => {
    const response = await apiClient.get('/api/v1/integrations/jira/projects');
    return response.data;
  },

  getIssueTypes: async (projectId: string): Promise<JiraIssueType[]> => {
    const response = await apiClient.get('/api/v1/integrations/jira/issuetypes', {
      params: { project_id: projectId },
    });
    return response.data;
  },

  createIssue: async (data: CreateJiraIssueRequest): Promise<CreateJiraIssueResponse> => {
    const response = await apiClient.post('/api/v1/integrations/jira/issues', data);
    return response.data;
  },

  getLinkedIssues: async (feedbackId: number): Promise<JiraLinkedIssue[]> => {
    const response = await apiClient.get('/api/v1/integrations/jira/issues', {
      params: { feedback_id: feedbackId },
    });
    return response.data;
  },
};

// Inbound status sync (jira-status-sync/inbound-status-sync, Phase 6). Kept
// as standalone exports — used directly by JiraStatusSyncCard, mirroring
// zendeskAPI.triggerSync's shape but exposed at module scope.

export async function patchJiraStatusSync(
  enabled: boolean,
  statusMapping?: Record<string, string>
): Promise<JiraConnectionStatus> {
  const response = await apiClient.patch('/api/v1/integrations/jira/status-sync', {
    enabled,
    ...(statusMapping !== undefined ? { status_mapping: statusMapping } : {}),
  });
  return response.data;
}

export async function triggerJiraSync(): Promise<JiraSyncTriggerResponse> {
  const response = await apiClient.post('/api/v1/integrations/jira/sync');
  return response.data;
}
