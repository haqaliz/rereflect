import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

export type TriggerType =
  | 'health_score_threshold'
  | 'sentiment_pattern'
  | 'churn_risk_level_change'
  | 'feedback_category_match';

export type ActionType =
  | 'auto_assign'
  | 'change_status'
  | 'send_notification'
  | 'draft_response';

export interface AutomationAction {
  type: ActionType | string;
  config: Record<string, any>;
}

export interface AutomationRule {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  trigger_type: TriggerType;
  trigger_config: Record<string, any>;
  trigger?: { type: string; config: Record<string, any> };
  actions: AutomationAction[];
  cooldown_hours: number;
  execution_count: number;
  last_executed_at: string | null;
  is_template: boolean;
  template_id: string | null;
  created_at: string;
}

export interface AutomationExecution {
  id: number;
  rule_id: number;
  feedback_id: number | null;
  customer_email: string | null;
  trigger_snapshot: Record<string, any>;
  actions_executed: { type: string; result: string; error: string | null }[];
  status: 'success' | 'partial_failure' | 'failed';
  executed_at: string;
}

export interface AutomationTemplate {
  id: string;
  name: string;
  description: string;
  trigger_type: TriggerType | string;
  trigger_config: Record<string, any>;
  trigger?: { type: string; config: Record<string, any> };
  actions: AutomationAction[];
  cooldown_hours: number;
}

export interface CreateAutomationRequest {
  name: string;
  description?: string | null;
  trigger: { type: TriggerType; config: Record<string, any> };
  actions: { type: ActionType; config: Record<string, any> }[];
  cooldown_hours?: number;
}

export interface UpdateAutomationRequest {
  name?: string;
  description?: string | null;
  is_active?: boolean;
  trigger?: { type: TriggerType; config: Record<string, any> };
  actions?: { type: ActionType; config: Record<string, any> }[];
  cooldown_hours?: number;
}

// ─── API Client ───────────────────────────────────────────────────────────────

export const automationsAPI = {
  list: async (): Promise<{ rules: AutomationRule[]; count: number; limit: number | null }> => {
    const response = await apiClient.get('/api/v1/automations');
    return response.data;
  },

  create: async (data: CreateAutomationRequest): Promise<AutomationRule> => {
    const response = await apiClient.post('/api/v1/automations', data);
    return response.data;
  },

  get: async (id: number): Promise<AutomationRule> => {
    const response = await apiClient.get(`/api/v1/automations/${id}`);
    return response.data;
  },

  update: async (id: number, data: UpdateAutomationRequest): Promise<AutomationRule> => {
    const response = await apiClient.put(`/api/v1/automations/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/automations/${id}`);
  },

  toggle: async (id: number): Promise<AutomationRule> => {
    const response = await apiClient.patch(`/api/v1/automations/${id}/toggle`);
    return response.data;
  },

  listExecutions: async (id: number): Promise<AutomationExecution[]> => {
    const response = await apiClient.get(`/api/v1/automations/${id}/executions`);
    return Array.isArray(response.data) ? response.data : response.data.executions ?? [];
  },

  listTemplates: async (): Promise<AutomationTemplate[]> => {
    const response = await apiClient.get('/api/v1/automations/templates');
    return Array.isArray(response.data) ? response.data : response.data.templates ?? [];
  },

  enableTemplate: async (templateId: string): Promise<AutomationRule> => {
    const response = await apiClient.post(`/api/v1/automations/templates/${templateId}/enable`);
    return response.data;
  },
};

// ─── Constants ────────────────────────────────────────────────────────────────

export const TRIGGER_TYPE_LABELS: Record<TriggerType, string> = {
  health_score_threshold: 'Health Score Threshold',
  sentiment_pattern: 'Sentiment Pattern',
  churn_risk_level_change: 'Churn Risk Level Change',
  feedback_category_match: 'Category Match',
};

export const ACTION_TYPE_LABELS: Record<ActionType, string> = {
  auto_assign: 'Auto-Assign',
  change_status: 'Change Status',
  send_notification: 'Send Notification',
  draft_response: 'Draft AI Response',
};

export const PLAN_AUTOMATION_LIMITS: Record<string, number | null> = {
  free: 0,
  pro: 5,
  business: 20,
  enterprise: null,
};
