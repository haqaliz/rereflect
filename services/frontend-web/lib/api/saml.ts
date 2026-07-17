import apiClient from '../api-client';

export interface SamlStatus {
  enabled: boolean;
  button_label: string;
}

// Response shape — never includes idp_x509_cert (write-only). The signing
// cert IS public (unlike OIDC's client_secret), but the backend still
// returns only a SHA-256 fingerprint so the config form can confirm a cert
// is stored without echoing the full PEM back over the wire.
export interface SamlConfig {
  configured: boolean;
  idp_entity_id: string | null;
  idp_sso_url: string | null;
  cert_fingerprint: string | null;
  email_attribute: string | null;
  enabled: boolean;
  allowed_email_domains: string[];
  button_label: string | null;
}

export interface SamlConfigUpdate {
  idp_entity_id: string;
  idp_sso_url: string;
  idp_x509_cert?: string;
  email_attribute?: string;
  enabled: boolean;
  allowed_email_domains: string[];
  button_label?: string;
}

export const getSamlStatus = async (): Promise<SamlStatus> => {
  const response = await apiClient.get('/api/v1/auth/saml/status');
  return response.data;
};

export const getSamlConfig = async (): Promise<SamlConfig> => {
  const response = await apiClient.get('/api/v1/settings/saml');
  return response.data;
};

export const putSamlConfig = async (payload: SamlConfigUpdate): Promise<SamlConfig> => {
  const response = await apiClient.put('/api/v1/settings/saml', payload);
  return response.data;
};

export const deleteSamlConfig = async (): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.delete('/api/v1/settings/saml');
  return response.data;
};
