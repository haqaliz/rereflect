import apiClient from '../api-client';

export interface OidcStatus {
  enabled: boolean;
  button_label: string;
}

// Response shape — never includes client_secret (write-only, server-side only).
export interface OidcConfig {
  configured: boolean;
  issuer_url: string | null;
  client_id: string | null;
  secret_hint: string | null;
  enabled: boolean;
  allowed_email_domains: string[];
  button_label: string | null;
}

export interface OidcConfigUpdate {
  issuer_url: string;
  client_id: string;
  client_secret?: string;
  enabled: boolean;
  allowed_email_domains: string[];
  button_label?: string;
}

export const getOidcStatus = async (): Promise<OidcStatus> => {
  const response = await apiClient.get('/api/v1/auth/oidc/status');
  return response.data;
};

export const getOidcConfig = async (): Promise<OidcConfig> => {
  const response = await apiClient.get('/api/v1/settings/oidc');
  return response.data;
};

export const putOidcConfig = async (payload: OidcConfigUpdate): Promise<OidcConfig> => {
  const response = await apiClient.put('/api/v1/settings/oidc', payload);
  return response.data;
};

export const deleteOidcConfig = async (): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.delete('/api/v1/settings/oidc');
  return response.data;
};
