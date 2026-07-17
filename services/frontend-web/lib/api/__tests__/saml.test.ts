import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import { getSamlStatus, getSamlConfig, putSamlConfig, deleteSamlConfig } from '@/lib/api/saml';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPut = apiClient.put as ReturnType<typeof vi.fn>;
const mockDelete = apiClient.delete as ReturnType<typeof vi.fn>;

describe('saml API client', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getSamlStatus GETs the public status endpoint and returns the body', async () => {
    mockGet.mockResolvedValue({ data: { enabled: true, button_label: 'Sign in with SSO' } });

    const result = await getSamlStatus();

    expect(mockGet).toHaveBeenCalledWith('/api/v1/auth/saml/status');
    expect(result).toEqual({ enabled: true, button_label: 'Sign in with SSO' });
  });

  it('getSamlConfig GETs the admin config endpoint and returns the body without the raw PEM', async () => {
    const body = {
      configured: true,
      idp_entity_id: 'https://idp.example.com/entity',
      idp_sso_url: 'https://idp.example.com/sso',
      cert_fingerprint: 'AB:CD:EF:00',
      email_attribute: null,
      enabled: true,
      allowed_email_domains: ['acme.com'],
      button_label: 'Sign in with SSO',
    };
    mockGet.mockResolvedValue({ data: body });

    const result = await getSamlConfig();

    expect(mockGet).toHaveBeenCalledWith('/api/v1/settings/saml');
    expect(result).toEqual(body);
    expect(result).not.toHaveProperty('idp_x509_cert');
  });

  it('putSamlConfig PUTs the payload (incl. a freshly pasted cert) and returns the updated config', async () => {
    const payload = {
      idp_entity_id: 'https://idp.example.com/entity',
      idp_sso_url: 'https://idp.example.com/sso',
      idp_x509_cert: '-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----',
      email_attribute: 'email',
      enabled: true,
      allowed_email_domains: ['acme.com'],
      button_label: 'Sign in with SSO',
    };
    const responseBody = {
      configured: true,
      idp_entity_id: payload.idp_entity_id,
      idp_sso_url: payload.idp_sso_url,
      cert_fingerprint: 'AB:CD:EF:00',
      email_attribute: payload.email_attribute,
      enabled: true,
      allowed_email_domains: payload.allowed_email_domains,
      button_label: payload.button_label,
    };
    mockPut.mockResolvedValue({ data: responseBody });

    const result = await putSamlConfig(payload);

    expect(mockPut).toHaveBeenCalledWith('/api/v1/settings/saml', payload);
    expect(result).toEqual(responseBody);
  });

  it('putSamlConfig omits idp_x509_cert from the payload when not provided (keeps existing cert)', async () => {
    const payload = {
      idp_entity_id: 'https://idp.example.com/entity',
      idp_sso_url: 'https://idp.example.com/sso',
      enabled: false,
      allowed_email_domains: [],
    };
    mockPut.mockResolvedValue({ data: { configured: true, ...payload, cert_fingerprint: 'AB:CD:EF:00' } });

    await putSamlConfig(payload);

    const [, sentBody] = mockPut.mock.calls[0];
    expect(sentBody).not.toHaveProperty('idp_x509_cert');
  });

  it('deleteSamlConfig DELETEs the config endpoint and returns success/message', async () => {
    mockDelete.mockResolvedValue({ data: { success: true, message: 'SAML config deleted.' } });

    const result = await deleteSamlConfig();

    expect(mockDelete).toHaveBeenCalledWith('/api/v1/settings/saml');
    expect(result).toEqual({ success: true, message: 'SAML config deleted.' });
  });
});
