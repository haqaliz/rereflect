import apiClient from '../api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

export type ApiKeyScope = 'read' | 'ingest';

export interface ApiKeyListItem {
  id: number;
  name: string;
  key_prefix: string;
  scopes: string;
  organization_id: number;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

/** Returned only on creation — includes the raw key shown exactly once. */
export interface ApiKeyCreateResponse extends Omit<ApiKeyListItem, 'last_used_at' | 'revoked_at'> {
  key: string;
}

export interface CreateApiKeyRequest {
  name: string;
  scopes: ApiKeyScope[];
}

export interface RevokeResponse {
  id: number;
  revoked_at: string;
}

// ─── API client ───────────────────────────────────────────────────────────────

export const apiKeysAPI = {
  /** Create a new API key. The raw key is in the response — store it, it's shown once. */
  create: async (data: CreateApiKeyRequest): Promise<ApiKeyCreateResponse> => {
    const resp = await apiClient.post<ApiKeyCreateResponse>('/api/v1/api-keys', data);
    return resp.data;
  },

  /** List all (including revoked) API keys for the current org. */
  list: async (): Promise<ApiKeyListItem[]> => {
    const resp = await apiClient.get<ApiKeyListItem[]>('/api/v1/api-keys');
    return resp.data;
  },

  /** Soft-revoke an API key. */
  revoke: async (id: number): Promise<RevokeResponse> => {
    const resp = await apiClient.post<RevokeResponse>(`/api/v1/api-keys/${id}/revoke`);
    return resp.data;
  },
};
