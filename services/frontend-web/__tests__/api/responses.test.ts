import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the api-client so no real HTTP calls are made
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
import {
  responsesAPI,
  type ResponseTemplate,
  type FeedbackResponseRecord,
  type ResponseSettings,
  type ResponseUsage,
} from '@/lib/api/responses';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockPut = apiClient.put as ReturnType<typeof vi.fn>;
const mockDelete = apiClient.delete as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const mockTemplate: ResponseTemplate = {
  id: 1,
  name: 'Bug Report Acknowledgment',
  category: 'Bug Report',
  body: 'Hi {{customer_name}}, thank you for reporting this issue.',
  is_system: true,
  usage_count: 23,
};

const mockCustomTemplate: ResponseTemplate = {
  id: 10,
  name: 'Enterprise Welcome',
  category: 'Onboarding',
  body: 'Welcome {{customer_name}} to our enterprise plan!',
  is_system: false,
  usage_count: 3,
};

const mockResponseRecord: FeedbackResponseRecord = {
  id: 1,
  feedback_id: 42,
  user_id: 1,
  response_text: 'Hi Sarah, thank you for reporting this issue.',
  channel: 'clipboard',
  source: 'template',
  template_id: 1,
  tone: null,
  status: 'copied',
  error_message: null,
  created_at: '2026-03-09T10:00:00Z',
  user_name: 'Alex Kim',
};

const mockSettings: ResponseSettings = {
  brand_voice: 'We are a developer tools company. Keep responses concise.',
  default_tone: 'professional',
  product_name_display: 'Rereflect',
  support_email_display: 'support@rereflect.ca',
};

const mockUsage: ResponseUsage = {
  ai_responses_generated: 12,
  monthly_limit: 50,
  templates_used: 8,
  responses_sent: 20,
};

// ─── listTemplates ─────────────────────────────────────────────────────────────

describe('responsesAPI.listTemplates', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/response-templates', async () => {
    mockGet.mockResolvedValue({ data: [mockTemplate, mockCustomTemplate] });
    await responsesAPI.listTemplates();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/response-templates');
  });

  it('returns array of templates', async () => {
    mockGet.mockResolvedValue({ data: [mockTemplate, mockCustomTemplate] });
    const result = await responsesAPI.listTemplates();
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe('Bug Report Acknowledgment');
    expect(result[1].is_system).toBe(false);
  });

  it('propagates errors from the API client', async () => {
    mockGet.mockRejectedValue(new Error('Network error'));
    await expect(responsesAPI.listTemplates()).rejects.toThrow('Network error');
  });
});

// ─── createTemplate ───────────────────────────────────────────────────────────

describe('responsesAPI.createTemplate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls POST /api/v1/response-templates with correct body', async () => {
    const payload = { name: 'My Template', category: 'Sales', body: 'Hello {{customer_name}}' };
    mockPost.mockResolvedValue({ data: { ...mockCustomTemplate, ...payload } });
    await responsesAPI.createTemplate(payload);
    expect(mockPost).toHaveBeenCalledWith('/api/v1/response-templates', payload);
  });

  it('returns the created template', async () => {
    const payload = { name: 'My Template', category: 'Sales', body: 'Hello' };
    mockPost.mockResolvedValue({ data: { ...mockCustomTemplate, ...payload } });
    const result = await responsesAPI.createTemplate(payload);
    expect(result.name).toBe('My Template');
    expect(result.category).toBe('Sales');
  });
});

// ─── deleteTemplate ───────────────────────────────────────────────────────────

describe('responsesAPI.deleteTemplate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls DELETE /api/v1/response-templates/:id', async () => {
    mockDelete.mockResolvedValue({ data: {} });
    await responsesAPI.deleteTemplate(10);
    expect(mockDelete).toHaveBeenCalledWith('/api/v1/response-templates/10');
  });

  it('propagates 403 when trying to delete a system template', async () => {
    const err = Object.assign(new Error('Forbidden'), { response: { status: 403 } });
    mockDelete.mockRejectedValue(err);
    await expect(responsesAPI.deleteTemplate(1)).rejects.toMatchObject({ response: { status: 403 } });
  });
});

// ─── suggestTemplate ──────────────────────────────────────────────────────────

describe('responsesAPI.suggestTemplate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls POST /api/v1/response-templates/suggest with feedbackId', async () => {
    mockPost.mockResolvedValue({ data: { template: mockTemplate, score: 70 } });
    await responsesAPI.suggestTemplate(42);
    expect(mockPost).toHaveBeenCalledWith('/api/v1/response-templates/suggest', { feedback_id: 42 });
  });

  it('returns best matching template and score', async () => {
    mockPost.mockResolvedValue({ data: { template: mockTemplate, score: 70 } });
    const result = await responsesAPI.suggestTemplate(42);
    expect(result.template?.name).toBe('Bug Report Acknowledgment');
    expect(result.score).toBe(70);
  });

  it('returns null template when no match found', async () => {
    mockPost.mockResolvedValue({ data: { template: null, score: 0 } });
    const result = await responsesAPI.suggestTemplate(42);
    expect(result.template).toBeNull();
  });
});

// ─── generateResponse ─────────────────────────────────────────────────────────

describe('responsesAPI.generateResponse', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls POST /api/v1/feedback/:id/responses/generate with tone', async () => {
    mockPost.mockResolvedValue({ data: { response_text: 'Generated text', tokens_used: 120, remaining_this_month: 38 } });
    await responsesAPI.generateResponse(42, 'friendly');
    expect(mockPost).toHaveBeenCalledWith('/api/v1/feedback/42/responses/generate', { tone: 'friendly' });
  });

  it('calls generate endpoint with null tone when not specified', async () => {
    mockPost.mockResolvedValue({ data: { response_text: 'Generated text', tokens_used: 100, remaining_this_month: 49 } });
    await responsesAPI.generateResponse(42);
    expect(mockPost).toHaveBeenCalledWith('/api/v1/feedback/42/responses/generate', { tone: undefined });
  });

  it('returns generated text, tokens_used, and remaining_this_month', async () => {
    mockPost.mockResolvedValue({ data: { response_text: 'AI response here', tokens_used: 200, remaining_this_month: 30 } });
    const result = await responsesAPI.generateResponse(42, 'professional');
    expect(result.response_text).toBe('AI response here');
    expect(result.tokens_used).toBe(200);
    expect(result.remaining_this_month).toBe(30);
  });
});

// ─── sendResponse ─────────────────────────────────────────────────────────────

describe('responsesAPI.sendResponse', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls POST /api/v1/feedback/:id/responses/send with correct data', async () => {
    const payload = { response_text: 'Hello', channel: 'clipboard' as const, source: 'template' as const, template_id: 1, tone: null };
    mockPost.mockResolvedValue({ data: { success: true, response_id: 99, channel: 'clipboard', error: null } });
    await responsesAPI.sendResponse(42, payload);
    expect(mockPost).toHaveBeenCalledWith('/api/v1/feedback/42/responses/send', payload);
  });

  it('returns success, response_id, and channel', async () => {
    const payload = { response_text: 'Hello', channel: 'slack' as const, source: 'ai_generated' as const, template_id: null, tone: 'professional' };
    mockPost.mockResolvedValue({ data: { success: true, response_id: 55, channel: 'slack', error: null } });
    const result = await responsesAPI.sendResponse(42, payload);
    expect(result.success).toBe(true);
    expect(result.response_id).toBe(55);
    expect(result.channel).toBe('slack');
  });

  it('returns error message on send failure', async () => {
    const payload = { response_text: 'Hello', channel: 'slack' as const, source: 'manual' as const, template_id: null, tone: null };
    mockPost.mockResolvedValue({ data: { success: false, response_id: 60, channel: 'slack', error: 'Token expired' } });
    const result = await responsesAPI.sendResponse(42, payload);
    expect(result.success).toBe(false);
    expect(result.error).toBe('Token expired');
  });
});

// ─── getResponseSettings ─────────────────────────────────────────────────────

describe('responsesAPI.getResponseSettings', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/response-settings', async () => {
    mockGet.mockResolvedValue({ data: mockSettings });
    await responsesAPI.getResponseSettings();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/response-settings');
  });

  it('returns org response settings', async () => {
    mockGet.mockResolvedValue({ data: mockSettings });
    const result = await responsesAPI.getResponseSettings();
    expect(result.brand_voice).toBe('We are a developer tools company. Keep responses concise.');
    expect(result.default_tone).toBe('professional');
    expect(result.product_name_display).toBe('Rereflect');
  });
});

// ─── updateResponseSettings ───────────────────────────────────────────────────

describe('responsesAPI.updateResponseSettings', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls PUT /api/v1/response-settings with data', async () => {
    const update = { brand_voice: 'New voice', default_tone: 'friendly' };
    mockPut.mockResolvedValue({ data: { ...mockSettings, ...update } });
    await responsesAPI.updateResponseSettings(update);
    expect(mockPut).toHaveBeenCalledWith('/api/v1/response-settings', update);
  });

  it('returns updated settings', async () => {
    const update = { default_tone: 'empathetic', product_name_display: 'MyApp' };
    mockPut.mockResolvedValue({ data: { ...mockSettings, ...update } });
    const result = await responsesAPI.updateResponseSettings(update);
    expect(result.default_tone).toBe('empathetic');
    expect(result.product_name_display).toBe('MyApp');
  });
});

// ─── getResponseUsage ─────────────────────────────────────────────────────────

describe('responsesAPI.getResponseUsage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/response-settings/usage', async () => {
    mockGet.mockResolvedValue({ data: mockUsage });
    await responsesAPI.getResponseUsage();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/response-settings/usage');
  });

  it('returns usage counts including ai_responses_generated and monthly_limit', async () => {
    mockGet.mockResolvedValue({ data: mockUsage });
    const result = await responsesAPI.getResponseUsage();
    expect(result.ai_responses_generated).toBe(12);
    expect(result.monthly_limit).toBe(50);
    expect(result.templates_used).toBe(8);
    expect(result.responses_sent).toBe(20);
  });

  it('returns -1 for monthly_limit when plan has unlimited AI responses', async () => {
    const unlimitedUsage = { ...mockUsage, monthly_limit: -1 };
    mockGet.mockResolvedValue({ data: unlimitedUsage });
    const result = await responsesAPI.getResponseUsage();
    expect(result.monthly_limit).toBe(-1);
  });
});

// ─── listResponses ────────────────────────────────────────────────────────────

describe('responsesAPI.listResponses', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/feedback/:id/responses', async () => {
    mockGet.mockResolvedValue({ data: [mockResponseRecord] });
    await responsesAPI.listResponses(42);
    expect(mockGet).toHaveBeenCalledWith('/api/v1/feedback/42/responses');
  });

  it('returns array of response history records', async () => {
    mockGet.mockResolvedValue({ data: [mockResponseRecord] });
    const result = await responsesAPI.listResponses(42);
    expect(result).toHaveLength(1);
    expect(result[0].channel).toBe('clipboard');
    expect(result[0].source).toBe('template');
    expect(result[0].user_name).toBe('Alex Kim');
  });

  it('returns empty array when no responses exist', async () => {
    mockGet.mockResolvedValue({ data: [] });
    const result = await responsesAPI.listResponses(42);
    expect(result).toHaveLength(0);
  });
});

// ─── updateTemplate ───────────────────────────────────────────────────────────

describe('responsesAPI.updateTemplate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls PUT /api/v1/response-templates/:id with data', async () => {
    const update = { name: 'Updated Name', body: 'New body text' };
    mockPut.mockResolvedValue({ data: { ...mockCustomTemplate, ...update } });
    await responsesAPI.updateTemplate(10, update);
    expect(mockPut).toHaveBeenCalledWith('/api/v1/response-templates/10', update);
  });

  it('returns the updated template', async () => {
    const update = { name: 'Renamed Template' };
    mockPut.mockResolvedValue({ data: { ...mockCustomTemplate, name: 'Renamed Template' } });
    const result = await responsesAPI.updateTemplate(10, update);
    expect(result.name).toBe('Renamed Template');
  });
});
