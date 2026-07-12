import apiClient from '../api-client';

// ---- Types ----

export interface AsanaConnectionStatus {
  connected: boolean;
  token_hint: string | null;
  account_gid: string | null;
  display_name: string | null;
  is_active: boolean | null;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_error: string | null;
  connected_at: string | null;
  // Inbound status sync (asana-status-sync). Opt-in poller that pulls
  // Asana task completion back onto linked feedback. `last_sync_status` /
  // `last_error` above are shared with the general connection status but
  // are also updated by the status-sync poller.
  status_sync_enabled: boolean;
  last_status_synced_at: string | null;
}

export interface AsanaConnectRequest {
  api_token: string;
}

export interface AsanaConnectResponse {
  connected: boolean;
  token_hint: string | null;
  account_gid: string | null;
  display_name: string | null;
}

export interface AsanaDisconnectResponse {
  success: boolean;
  message: string;
}

export interface AsanaTestResponse {
  success: boolean;
  message: string | null;
}

export interface AsanaWorkspace {
  gid: string | null;
  name: string | null;
}

export interface AsanaProject {
  gid: string | null;
  name: string | null;
}

export interface CreateAsanaTaskRequest {
  feedback_id: number;
  workspace_gid: string;
  project_gid: string;
  name: string;
  notes?: string;
  force?: boolean;
}

export interface CreateAsanaTaskResponse {
  asana_task_gid?: string;
  asana_task_url?: string;
  asana_task_name?: string;
  // Present on a 200 duplicate response instead of the fields above
  warning?: string;
  existing_tasks?: Array<{
    id: number;
    asana_task_gid: string;
    asana_task_url: string;
    asana_task_name: string;
  }>;
}

export interface AsanaLinkedTask {
  id: number;
  feedback_id: number;
  asana_task_gid: string;
  asana_task_url: string;
  asana_task_name: string;
  created_at: string;
}

export interface AsanaSyncTriggerResponse {
  status: string;
}

// ---- API ----

export const asanaAPI = {
  connect: async (data: AsanaConnectRequest): Promise<AsanaConnectResponse> => {
    const response = await apiClient.post('/api/v1/integrations/asana/connect', data);
    return response.data;
  },

  getStatus: async (): Promise<AsanaConnectionStatus> => {
    const response = await apiClient.get('/api/v1/integrations/asana/status');
    return response.data;
  },

  disconnect: async (): Promise<AsanaDisconnectResponse> => {
    const response = await apiClient.delete('/api/v1/integrations/asana/disconnect');
    return response.data;
  },

  testConnection: async (): Promise<AsanaTestResponse> => {
    const response = await apiClient.post('/api/v1/integrations/asana/test');
    return response.data;
  },

  getWorkspaces: async (): Promise<AsanaWorkspace[]> => {
    const response = await apiClient.get('/api/v1/integrations/asana/workspaces');
    return response.data;
  },

  getProjects: async (workspaceGid: string): Promise<AsanaProject[]> => {
    const response = await apiClient.get('/api/v1/integrations/asana/projects', {
      params: { workspace_gid: workspaceGid },
    });
    return response.data;
  },

  createTask: async (data: CreateAsanaTaskRequest): Promise<CreateAsanaTaskResponse> => {
    const response = await apiClient.post('/api/v1/integrations/asana/tasks', data);
    return response.data;
  },

  getLinkedTasks: async (feedbackId: number): Promise<AsanaLinkedTask[]> => {
    const response = await apiClient.get('/api/v1/integrations/asana/tasks', {
      params: { feedback_id: feedbackId },
    });
    return response.data;
  },
};

// Inbound status sync (asana-status-sync). Kept as standalone exports —
// used directly by AsanaStatusSyncCard, mirroring the Jira status-sync
// client shape but exposed at module scope.

export async function patchAsanaStatusSync(
  enabled: boolean,
  statusMapping?: Record<string, string>
): Promise<AsanaConnectionStatus> {
  const response = await apiClient.patch('/api/v1/integrations/asana/status-sync', {
    enabled,
    ...(statusMapping !== undefined ? { status_mapping: statusMapping } : {}),
  });
  return response.data;
}

export async function triggerAsanaSync(): Promise<AsanaSyncTriggerResponse> {
  const response = await apiClient.post('/api/v1/integrations/asana/sync');
  return response.data;
}
