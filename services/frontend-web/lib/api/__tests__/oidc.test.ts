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
import { getOidcStatus, getOidcConfig, putOidcConfig, deleteOidcConfig } from '@/lib/api/oidc';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPut = apiClient.put as ReturnType<typeof vi.fn>;
const mockDelete = apiClient.delete as ReturnType<typeof vi.fn>;

describe('oidc API client', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getOidcStatus GETs the public status endpoint and returns the body', async () => {
    mockGet.mockResolvedValue({ data: { enabled: true, button_label: 'Sign in with SSO' } });

    const result = await getOidcStatus();

    expect(mockGet).toHaveBeenCalledWith('/api/v1/auth/oidc/status');
    expect(result).toEqual({ enabled: true, button_label: 'Sign in with SSO' });
  });

  it('getOidcConfig GETs the admin config endpoint and returns the body without client_secret', async () => {
    const body = {
      configured: true,
      issuer_url: 'https://idp.example.com',
      client_id: 'abc123',
      secret_hint: '****xyz9',
      enabled: true,
      allowed_email_domains: ['acme.com'],
      button_label: 'Sign in with SSO',
    };
    mockGet.mockResolvedValue({ data: body });

    const result = await getOidcConfig();

    expect(mockGet).toHaveBeenCalledWith('/api/v1/settings/oidc');
    expect(result).toEqual(body);
    expect(result).not.toHaveProperty('client_secret');
  });

  it('putOidcConfig PUTs the payload and returns the updated config', async () => {
    const payload = {
      issuer_url: 'https://idp.example.com',
      client_id: 'abc123',
      client_secret: 'super-secret',
      enabled: true,
      allowed_email_domains: ['acme.com'],
      button_label: 'Sign in with SSO',
    };
    const responseBody = {
      configured: true,
      issuer_url: payload.issuer_url,
      client_id: payload.client_id,
      secret_hint: '****cret',
      enabled: true,
      allowed_email_domains: payload.allowed_email_domains,
      button_label: payload.button_label,
    };
    mockPut.mockResolvedValue({ data: responseBody });

    const result = await putOidcConfig(payload);

    expect(mockPut).toHaveBeenCalledWith('/api/v1/settings/oidc', payload);
    expect(result).toEqual(responseBody);
  });

  it('putOidcConfig omits client_secret from the payload when not provided', async () => {
    const payload = {
      issuer_url: 'https://idp.example.com',
      client_id: 'abc123',
      enabled: false,
      allowed_email_domains: [],
    };
    mockPut.mockResolvedValue({ data: { configured: true, ...payload, secret_hint: '****cret' } });

    await putOidcConfig(payload);

    const [, sentBody] = mockPut.mock.calls[0];
    expect(sentBody).not.toHaveProperty('client_secret');
  });

  it('deleteOidcConfig DELETEs the config endpoint and returns success/message', async () => {
    mockDelete.mockResolvedValue({ data: { success: true, message: 'OIDC config deleted.' } });

    const result = await deleteOidcConfig();

    expect(mockDelete).toHaveBeenCalledWith('/api/v1/settings/oidc');
    expect(result).toEqual({ success: true, message: 'OIDC config deleted.' });
  });
});
