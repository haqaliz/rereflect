import apiClient from '../api-client';

// ============ Types ============

export interface TriggerConfig {
  all_messages?: boolean;
  reactions?: string[];
  mentions?: { bot?: boolean; users?: string[] };
  keywords?: string[];
  labels?: string[];
  custom_rules?: any[];
}

export interface FieldMappingConfig {
  text_source: 'message' | 'thread' | 'full';
  include_author: boolean;
  include_source_name: boolean;
  include_context: boolean;
  max_context_messages: number;
  custom_template: string | null;
}

export interface FeedbackSource {
  id: number;
  organization_id: number;
  integration_id: number | null;
  source_type: 'slack' | 'intercom' | 'webhook' | 'discord' | 'email' | 'linear';
  name: string | null;
  provider_config: Record<string, any>;
  triggers: TriggerConfig;
  field_mapping: FieldMappingConfig;
  auto_import: boolean;
  is_active: boolean;
  last_event_at: string | null;
  events_processed: number;
  error_count: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  webhook_url: string | null;
}

export interface FeedbackSourceListResponse {
  sources: FeedbackSource[];
  total: number;
}

export interface CreateFeedbackSourceRequest {
  source_type: string;
  name?: string;
  integration_id?: number;
  provider_config?: Record<string, any>;
  triggers?: TriggerConfig;
  field_mapping?: Partial<FieldMappingConfig>;
  auto_import?: boolean;
}

export interface UpdateFeedbackSourceRequest {
  name?: string;
  provider_config?: Record<string, any>;
  triggers?: TriggerConfig;
  field_mapping?: Partial<FieldMappingConfig>;
  auto_import?: boolean;
  is_active?: boolean;
}

export interface SourceTypeInfo {
  type: string;
  name: string;
  description: string;
  requires_integration: boolean;
  available: boolean;
}

export interface ChannelInfo {
  id: string;
  name: string;
  is_private: boolean;
  is_configured: boolean;
}

export interface FeedbackSourceEvent {
  id: number;
  external_event_id: string;
  external_message_id: string | null;
  event_type: string;
  status: 'pending' | 'processed' | 'ignored' | 'failed';
  trigger_matched: string | null;
  feedback_id: number | null;
  pending_feedback_id: number | null;
  error_message: string | null;
  received_at: string;
  processed_at: string | null;
}

export interface PendingFeedback {
  id: number;
  source_id: number;
  source_type: string;
  source_name: string | null;
  organization_id: number;
  event_id: number;
  text: string;
  source_metadata: Record<string, any> | null;
  trigger_type: string | null;
  status: 'pending' | 'approved' | 'rejected';
  reviewed_at: string | null;
  reviewed_by: number | null;
  created_at: string;
}

export interface PendingFeedbackListResponse {
  items: PendingFeedback[];
  total: number;
  page: number;
  page_size: number;
}

export interface BulkActionResponse {
  processed: number;
  failed: number;
  errors: string[];
}

// ============ API Client ============

export const feedbackSourcesAPI = {
  // List supported source types
  getTypes: async (): Promise<SourceTypeInfo[]> => {
    const response = await apiClient.get('/api/v1/feedback-sources/types');
    return response.data;
  },

  // List all feedback sources
  list: async (sourceType?: string, isActive?: boolean): Promise<FeedbackSourceListResponse> => {
    const params: Record<string, any> = {};
    if (sourceType) params.source_type = sourceType;
    if (isActive !== undefined) params.is_active = isActive;

    const response = await apiClient.get('/api/v1/feedback-sources/', { params });
    return response.data;
  },

  // Get a specific source
  get: async (id: number): Promise<FeedbackSource> => {
    const response = await apiClient.get(`/api/v1/feedback-sources/${id}`);
    return response.data;
  },

  // Create a new source
  create: async (data: CreateFeedbackSourceRequest): Promise<FeedbackSource> => {
    const response = await apiClient.post('/api/v1/feedback-sources/', data);
    return response.data;
  },

  // Update a source
  update: async (id: number, data: UpdateFeedbackSourceRequest): Promise<FeedbackSource> => {
    const response = await apiClient.patch(`/api/v1/feedback-sources/${id}`, data);
    return response.data;
  },

  // Delete a source
  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/feedback-sources/${id}`);
  },

  // Get events for a source
  getEvents: async (
    id: number,
    page = 1,
    pageSize = 50,
    status?: string
  ): Promise<FeedbackSourceEvent[]> => {
    const params: Record<string, any> = { page, page_size: pageSize };
    if (status) params.status = status;

    const response = await apiClient.get(`/api/v1/feedback-sources/${id}/events`, { params });
    return response.data;
  },

  // Get available Slack channels for a source
  getSlackChannels: async (id: number): Promise<ChannelInfo[]> => {
    const response = await apiClient.get(`/api/v1/feedback-sources/${id}/slack/channels`);
    return response.data;
  },
};

export const pendingFeedbackAPI = {
  // List pending feedback
  list: async (
    page = 1,
    pageSize = 20,
    sourceType?: string,
    sourceId?: number,
    status = 'pending'
  ): Promise<PendingFeedbackListResponse> => {
    const params: Record<string, any> = { page, page_size: pageSize, status };
    if (sourceType) params.source_type = sourceType;
    if (sourceId) params.source_id = sourceId;

    const response = await apiClient.get('/api/v1/pending-feedback/', { params });
    return response.data;
  },

  // Get a specific pending item
  get: async (id: number): Promise<PendingFeedback> => {
    const response = await apiClient.get(`/api/v1/pending-feedback/${id}`);
    return response.data;
  },

  // Approve a pending item (creates feedback)
  approve: async (id: number): Promise<any> => {
    const response = await apiClient.post(`/api/v1/pending-feedback/${id}/approve`);
    return response.data;
  },

  // Reject a pending item
  reject: async (id: number): Promise<void> => {
    await apiClient.post(`/api/v1/pending-feedback/${id}/reject`);
  },

  // Bulk approve
  bulkApprove: async (ids: number[]): Promise<BulkActionResponse> => {
    const response = await apiClient.post('/api/v1/pending-feedback/bulk-approve', { ids });
    return response.data;
  },

  // Bulk reject
  bulkReject: async (ids: number[]): Promise<BulkActionResponse> => {
    const response = await apiClient.post('/api/v1/pending-feedback/bulk-reject', { ids });
    return response.data;
  },
};

// ============ Trigger Options by Source Type ============

export const TRIGGER_OPTIONS: Record<string, { key: string; label: string; description: string; hasValues?: boolean }[]> = {
  slack: [
    { key: 'all_messages', label: 'All Messages', description: 'Capture every message posted' },
    { key: 'reactions', label: 'Emoji Reactions', description: 'Messages with specific reactions', hasValues: true },
    { key: 'mentions.bot', label: 'Bot Mentions', description: 'When @Rereflect is mentioned' },
    { key: 'mentions.users', label: 'User Mentions', description: 'When specific users are mentioned', hasValues: true },
    { key: 'keywords', label: 'Keywords', description: 'Messages containing keywords', hasValues: true },
  ],
  intercom: [
    { key: 'all_messages', label: 'All Conversations', description: 'Capture every conversation event' },
    { key: 'new_conversations', label: 'New Conversations', description: 'Only new customer conversations' },
    { key: 'replies', label: 'Customer Replies', description: 'When customers reply to conversations' },
    { key: 'ratings', label: 'Conversation Ratings', description: 'When customers rate conversations' },
    { key: 'keywords', label: 'Keywords', description: 'Messages containing keywords', hasValues: true },
  ],
  webhook: [
    { key: 'all_messages', label: 'All Requests', description: 'Process every incoming request' },
    { key: 'keywords', label: 'Content Match (optional)', description: 'Requests containing keywords', hasValues: true },
    { key: 'labels', label: 'Field Match (optional)', description: 'Requests with specific field values', hasValues: true },
  ],
  discord: [
    { key: 'all_messages', label: 'All Messages', description: 'Capture every message' },
    { key: 'reactions', label: 'Reactions', description: 'Messages with specific reactions', hasValues: true },
    { key: 'mentions.bot', label: 'Bot Mentions', description: 'When bot is mentioned' },
    { key: 'keywords', label: 'Keywords', description: 'Messages containing keywords', hasValues: true },
  ],
  email: [
    { key: 'all_messages', label: 'All Emails', description: 'Process every forwarded email' },
    { key: 'keywords', label: 'Keywords (optional)', description: 'Only emails containing keywords', hasValues: true },
  ],
  linear: [
    { key: 'all_messages', label: 'All Issue Comments', description: 'Capture every comment on issues' },
    { key: 'labels', label: 'Issue Labels', description: 'Only issues with specific labels', hasValues: true },
    { key: 'keywords', label: 'Keywords', description: 'Comments containing keywords', hasValues: true },
  ],
  jira: [
    { key: 'all_messages', label: 'All Issue Comments', description: 'Capture every comment on issues' },
    { key: 'labels', label: 'Issue Labels', description: 'Only issues with specific labels', hasValues: true },
    { key: 'keywords', label: 'Keywords', description: 'Comments containing keywords', hasValues: true },
  ],
};

// ============ Default Field Mapping ============

export const DEFAULT_FIELD_MAPPING: FieldMappingConfig = {
  text_source: 'message',
  include_author: true,
  include_source_name: true,
  include_context: false,
  max_context_messages: 5,
  custom_template: null,
};

// ============ Default Triggers ============

export const DEFAULT_TRIGGERS: TriggerConfig = {
  all_messages: false,
  reactions: [],
  mentions: { bot: true, users: [] },
  keywords: [],
  labels: [],
  custom_rules: [],
};
