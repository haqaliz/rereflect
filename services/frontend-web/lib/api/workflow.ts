import apiClient from '../api-client';

export interface WorkflowFeedbackItem {
  id: number;
  text: string;
  source: string | null;
  sentiment_label: string | null;
  sentiment_score: number | null;
  is_urgent: boolean;
  workflow_status: string;
  assigned_to: number | null;
  assigned_to_email: string | null;
  created_at: string;
  churn_risk_score: number | null;
}

export interface WorkflowOverviewResponse {
  items: WorkflowFeedbackItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  status_counts: Record<string, number>;
}

export interface TimelineEvent {
  id: number;
  feedback_id: number;
  actor_id: number;
  actor_email: string;
  event_type: string;
  old_value: string | null;
  new_value: string | null;
  metadata: Record<string, any> | null;
  created_at: string;
}

export interface FeedbackNote {
  id: number;
  feedback_id: number;
  author_id: number;
  author_email: string;
  content: string;
  created_at: string;
  updated_at: string | null;
}

export interface AssignmentRule {
  id: number;
  organization_id: number;
  rule_type: string;
  match_field: string;
  match_value: string;
  assign_to_user_id: number;
  assign_to_email: string;
  priority: number;
  is_active: boolean;
  created_at: string;
}

export interface WorkflowOverviewFilters {
  workflow_status?: string;
  assigned_to?: number;
  sentiment?: string;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export const workflowAPI = {
  // Status + Assignment
  changeStatus: async (feedbackIds: number[], newStatus: string, resolutionNote?: string) => {
    const response = await apiClient.post('/api/v1/workflow/status', {
      feedback_ids: feedbackIds,
      new_status: newStatus,
      resolution_note: resolutionNote,
    });
    return response.data;
  },

  assign: async (feedbackIds: number[], assignToUserId?: number | null) => {
    const response = await apiClient.post('/api/v1/workflow/assign', {
      feedback_ids: feedbackIds,
      assign_to_user_id: assignToUserId ?? null,
    });
    return response.data;
  },

  // Overview
  getOverview: async (page = 1, pageSize = 20, filters?: WorkflowOverviewFilters): Promise<WorkflowOverviewResponse> => {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    });
    if (filters?.workflow_status) params.append('workflow_status', filters.workflow_status);
    if (filters?.assigned_to !== undefined) params.append('assigned_to', filters.assigned_to.toString());
    if (filters?.sentiment) params.append('sentiment', filters.sentiment);
    if (filters?.search) params.append('search', filters.search);
    if (filters?.sort_by) params.append('sort_by', filters.sort_by);
    if (filters?.sort_order) params.append('sort_order', filters.sort_order);

    const response = await apiClient.get(`/api/v1/workflow/overview?${params.toString()}`);
    return response.data;
  },

  getStatusCounts: async (): Promise<Record<string, number>> => {
    const response = await apiClient.get('/api/v1/workflow/status-counts');
    return response.data;
  },

  // Timeline
  getTimeline: async (feedbackId: number): Promise<TimelineEvent[]> => {
    const response = await apiClient.get(`/api/v1/workflow/${feedbackId}/timeline`);
    return response.data;
  },

  // Notes
  getNotes: async (feedbackId: number): Promise<FeedbackNote[]> => {
    const response = await apiClient.get(`/api/v1/workflow/${feedbackId}/notes`);
    return response.data;
  },

  createNote: async (feedbackId: number, content: string): Promise<FeedbackNote> => {
    const response = await apiClient.post(`/api/v1/workflow/${feedbackId}/notes`, { content });
    return response.data;
  },

  updateNote: async (noteId: number, content: string): Promise<FeedbackNote> => {
    const response = await apiClient.patch(`/api/v1/workflow/notes/${noteId}`, { content });
    return response.data;
  },

  deleteNote: async (noteId: number): Promise<void> => {
    await apiClient.delete(`/api/v1/workflow/notes/${noteId}`);
  },

  // Assignment Rules
  getAssignmentRules: async (): Promise<AssignmentRule[]> => {
    const response = await apiClient.get('/api/v1/workflow/assignment-rules');
    return response.data;
  },

  createRule: async (data: {
    match_field: string;
    match_value: string;
    assign_to_user_id: number;
    priority?: number;
    is_active?: boolean;
  }): Promise<AssignmentRule> => {
    const response = await apiClient.post('/api/v1/workflow/assignment-rules', data);
    return response.data;
  },

  updateRule: async (ruleId: number, data: Partial<{
    match_field: string;
    match_value: string;
    assign_to_user_id: number;
    priority: number;
    is_active: boolean;
  }>): Promise<AssignmentRule> => {
    const response = await apiClient.patch(`/api/v1/workflow/assignment-rules/${ruleId}`, data);
    return response.data;
  },

  deleteRule: async (ruleId: number): Promise<void> => {
    await apiClient.delete(`/api/v1/workflow/assignment-rules/${ruleId}`);
  },

  // Settings
  getAutoAssignmentSettings: async (): Promise<{ auto_assignment_enabled: boolean }> => {
    const response = await apiClient.get('/api/v1/workflow/auto-assignment-settings');
    return response.data;
  },

  updateAutoAssignmentSettings: async (data: { auto_assignment_enabled: boolean }): Promise<{ auto_assignment_enabled: boolean }> => {
    const response = await apiClient.patch('/api/v1/workflow/auto-assignment-settings', data);
    return response.data;
  },
};
