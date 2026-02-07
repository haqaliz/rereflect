import apiClient from '../api-client';

export interface ChangelogEntry {
  id: number;
  title: string;
  description: string | null;
  entry_type: string;
  is_breaking: boolean;
  committed_at: string;
}

export interface ChangelogEntryAdmin extends ChangelogEntry {
  commit_hash: string;
  is_hidden: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface ChangelogListResponse {
  items: ChangelogEntry[];
  total: number;
  has_more: boolean;
}

export interface ChangelogAdminListResponse {
  items: ChangelogEntryAdmin[];
  total: number;
  has_more: boolean;
}

export interface ChangelogEntryUpdate {
  title?: string;
  description?: string | null;
  entry_type?: string;
  is_breaking?: boolean;
  is_hidden?: boolean;
}

export const changelogAPI = {
  getPublic: async (params?: {
    entry_type?: string;
    days?: number;
    offset?: number;
    limit?: number;
  }): Promise<ChangelogListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.entry_type) searchParams.set('entry_type', params.entry_type);
    if (params?.days) searchParams.set('days', String(params.days));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    const qs = searchParams.toString();
    const response = await apiClient.get(`/api/v1/changelog${qs ? `?${qs}` : ''}`);
    return response.data;
  },

  getAdmin: async (params?: {
    entry_type?: string;
    days?: number;
    offset?: number;
    limit?: number;
  }): Promise<ChangelogAdminListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.entry_type) searchParams.set('entry_type', params.entry_type);
    if (params?.days) searchParams.set('days', String(params.days));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    const qs = searchParams.toString();
    const response = await apiClient.get(`/api/v1/changelog/admin${qs ? `?${qs}` : ''}`);
    return response.data;
  },

  updateEntry: async (id: number, data: ChangelogEntryUpdate): Promise<ChangelogEntryAdmin> => {
    const response = await apiClient.patch(`/api/v1/changelog/admin/${id}`, data);
    return response.data;
  },

  deleteEntry: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/changelog/admin/${id}`);
  },
};
