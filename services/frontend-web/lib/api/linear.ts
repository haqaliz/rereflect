import apiClient from '../api-client';
import { REREFLECT_STATUSES } from '../constants/workflow-status';

// ---- Types ----

export interface LinearConnectionStatus {
  connected: boolean;
  org_name: string | null;
  org_id: string | null;
  connected_by_email: string | null;
  connected_at: string | null;
  is_active: boolean;
}

export interface LinearTeam {
  id: string;
  name: string;
  key: string;
}

export interface LinearProject {
  id: string;
  name: string;
  team_id: string;
}

export interface LinearLabel {
  id: string;
  name: string;
  color: string;
}

export interface LinearTeamMapping {
  id: number;
  rereflect_category: string;
  linear_team_id: string;
  linear_team_name: string;
  linear_project_id: string | null;
  linear_project_name: string | null;
  priority: number;
}

export interface LinearStatusMapping {
  id: number;
  linear_status_name: string;
  linear_status_type: string;
  rereflect_status: string;
}

export interface LinearIssue {
  id: number;
  linear_issue_id: string;
  linear_issue_identifier: string;
  linear_issue_url: string;
  linear_issue_title: string;
  linear_status: string | null;
  linear_assignee: string | null;
  linear_priority: number | null;
  created_at: string;
}

export interface CreateLinearIssueRequest {
  feedback_id: number;
  team_id: string;
  project_id?: string;
  title?: string;
  description?: string;
  priority?: number;
  label_ids?: string[];
}

export interface CreateLinearIssueResponse {
  issue: LinearIssue;
  linear_url: string;
  warning?: string; // Present if duplicate detected
  existing_issues?: LinearIssue[];
}

export interface UpdateTeamMappingsRequest {
  mappings: Array<{
    rereflect_category: string;
    linear_team_id: string;
    linear_team_name: string;
    linear_project_id?: string;
    linear_project_name?: string;
    priority?: number;
  }>;
}

export interface UpdateStatusMappingsRequest {
  mappings: Array<{
    linear_status_name: string;
    linear_status_type: string;
    rereflect_status: string;
  }>;
}

export interface OAuthConnectResponse {
  auth_url: string;
}

export interface LinearConfig {
  issue_title_template: string | null;
  issue_description_template: string | null;
}

export interface LinearTemplateVariable {
  name: string;
  description: string;
  example: string;
}

export interface LinearTemplateVariablesResponse {
  variables: LinearTemplateVariable[];
  default_title_template: string;
  default_description_template: string;
}

// ---- API ----

export const linearAPI = {
  // OAuth
  getConnectUrl: async (): Promise<OAuthConnectResponse> => {
    const response = await apiClient.get('/api/v1/integrations/linear/connect');
    return response.data;
  },

  disconnect: async (): Promise<void> => {
    await apiClient.delete('/api/v1/integrations/linear/disconnect');
  },

  testConnection: async (): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.post('/api/v1/integrations/linear/test');
    return response.data;
  },

  getStatus: async (): Promise<LinearConnectionStatus> => {
    const response = await apiClient.get('/api/v1/integrations/linear/status');
    return response.data;
  },

  // Issue management
  createIssue: async (data: CreateLinearIssueRequest): Promise<CreateLinearIssueResponse> => {
    const response = await apiClient.post('/api/v1/integrations/linear/issues', data);
    return response.data;
  },

  getLinkedIssues: async (feedbackId: number): Promise<LinearIssue[]> => {
    const response = await apiClient.get('/api/v1/integrations/linear/issues', {
      params: { feedback_id: feedbackId },
    });
    return response.data;
  },

  // Configuration
  getTeams: async (): Promise<LinearTeam[]> => {
    const response = await apiClient.get('/api/v1/integrations/linear/teams');
    return response.data;
  },

  getProjects: async (teamId: string): Promise<LinearProject[]> => {
    const response = await apiClient.get('/api/v1/integrations/linear/projects', {
      params: { team_id: teamId },
    });
    return response.data;
  },

  getLabels: async (): Promise<LinearLabel[]> => {
    const response = await apiClient.get('/api/v1/integrations/linear/labels');
    return response.data;
  },

  getTeamMappings: async (): Promise<LinearTeamMapping[]> => {
    const response = await apiClient.get('/api/v1/integrations/linear/team-mappings');
    return response.data;
  },

  updateTeamMappings: async (data: UpdateTeamMappingsRequest): Promise<LinearTeamMapping[]> => {
    const response = await apiClient.put('/api/v1/integrations/linear/team-mappings', data);
    return response.data;
  },

  getStatusMappings: async (): Promise<LinearStatusMapping[]> => {
    const response = await apiClient.get('/api/v1/integrations/linear/status-mappings');
    return response.data;
  },

  updateStatusMappings: async (data: UpdateStatusMappingsRequest): Promise<LinearStatusMapping[]> => {
    const response = await apiClient.put('/api/v1/integrations/linear/status-mappings', data);
    return response.data;
  },

  // Config (templates)
  getConfig: async (): Promise<LinearConfig> => {
    const response = await apiClient.get('/api/v1/integrations/linear/config');
    return response.data;
  },

  updateConfig: async (data: Partial<LinearConfig>): Promise<LinearConfig> => {
    const response = await apiClient.put('/api/v1/integrations/linear/config', data);
    return response.data;
  },

  getTemplateVariables: async (): Promise<LinearTemplateVariablesResponse> => {
    const response = await apiClient.get('/api/v1/integrations/linear/template-variables');
    return response.data;
  },
};

// ---- Constants ----

export const REREFLECT_CATEGORIES = [
  { value: 'pain_point', label: 'Pain Point' },
  { value: 'feature_request', label: 'Feature Request' },
  { value: 'bug', label: 'Bug' },
  { value: 'question', label: 'Question' },
  { value: 'praise', label: 'Praise' },
] as const;

export const LINEAR_STATUS_TYPES = [
  { value: 'backlog', label: 'Backlog' },
  { value: 'unstarted', label: 'Unstarted' },
  { value: 'started', label: 'In Progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'canceled', label: 'Canceled' },
] as const;

// Relocated to lib/constants/workflow-status.ts (mapping-editor aspect) — kept
// as a re-export so existing `import { REREFLECT_STATUSES } from '@/lib/api/linear'`
// call sites keep working.
export { REREFLECT_STATUSES };

export const LINEAR_PRIORITY_LABELS: Record<number, string> = {
  0: 'No priority',
  1: 'Urgent',
  2: 'High',
  3: 'Medium',
  4: 'Low',
};
