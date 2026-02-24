import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the api-client so no real HTTP calls are made
vi.mock('@/lib/api-client', () => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mockClient, apiClient: mockClient };
});

import apiClient from '@/lib/api-client';
import {
  conversationsAPI,
  type Conversation,
  type ConversationFolder,
  type ConversationMessage,
  type ConversationListResponse,
  type CreateConversationData,
  type UpdateConversationData,
  type CreateFolderData,
  type UpdateFolderData,
  type TemplateStartersResponse,
} from '@/lib/api/conversations';

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockPatch = apiClient.patch as ReturnType<typeof vi.fn>;
const mockDelete = apiClient.delete as ReturnType<typeof vi.fn>;

// ─── Fixtures ────────────────────────────────────────────────────────────────

const mockFolder: ConversationFolder = {
  id: 1,
  organization_id: 10,
  name: 'General',
  sort_order: 0,
  created_at: '2026-02-23T00:00:00Z',
};

const mockMessage: ConversationMessage = {
  id: 1,
  conversation_id: 42,
  role: 'user',
  content: 'How many negative feedbacks this week?',
  structured_data: null,
  context_scope: 'all_data',
  query_type: null,
  template_id: null,
  sql_generated: null,
  llm_provider: null,
  llm_model: null,
  tokens_in: null,
  tokens_out: null,
  cost_cents: null,
  latency_ms: null,
  is_regenerated: false,
  created_at: '2026-02-23T00:00:00Z',
};

const mockConversation: Conversation = {
  id: 42,
  public_id: 'test-uuid-42',
  organization_id: 10,
  created_by_user_id: 1,
  title: 'How many negative feedbacks this week?',
  folder_id: null,
  context_scope: 'all_data',
  is_active: true,
  created_at: '2026-02-23T00:00:00Z',
  updated_at: '2026-02-23T00:00:00Z',
  messages: [],
};

const mockListResponse: ConversationListResponse = {
  conversations: [mockConversation],
  total: 1,
  page: 1,
  page_size: 20,
};

// ─── Conversations ────────────────────────────────────────────────────────────

describe('conversationsAPI.getConversations', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/conversations', async () => {
    mockGet.mockResolvedValue({ data: mockListResponse });
    await conversationsAPI.getConversations();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/conversations', { params: undefined });
  });

  it('passes folder_id filter as query param', async () => {
    mockGet.mockResolvedValue({ data: mockListResponse });
    await conversationsAPI.getConversations({ folder_id: 5, page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith('/api/v1/conversations', {
      params: { folder_id: 5, page: 1, page_size: 20 },
    });
  });

  it('returns the parsed response data', async () => {
    mockGet.mockResolvedValue({ data: mockListResponse });
    const result = await conversationsAPI.getConversations();
    expect(result).toEqual(mockListResponse);
  });

  it('propagates errors from the API client', async () => {
    mockGet.mockRejectedValue(new Error('Network error'));
    await expect(conversationsAPI.getConversations()).rejects.toThrow('Network error');
  });
});

describe('conversationsAPI.createConversation', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls POST /api/v1/conversations with data', async () => {
    const data: CreateConversationData = { title: 'New chat', context_scope: 'all_data' };
    mockPost.mockResolvedValue({ data: mockConversation });
    await conversationsAPI.createConversation(data);
    expect(mockPost).toHaveBeenCalledWith('/api/v1/conversations', data);
  });

  it('returns the created conversation', async () => {
    mockPost.mockResolvedValue({ data: mockConversation });
    const result = await conversationsAPI.createConversation({ context_scope: 'all_data' });
    expect(result).toEqual(mockConversation);
  });
});

describe('conversationsAPI.getConversation', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/conversations/:publicId', async () => {
    mockGet.mockResolvedValue({ data: { ...mockConversation, messages: [mockMessage] } });
    await conversationsAPI.getConversation('test-uuid-42');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/conversations/test-uuid-42');
  });

  it('returns conversation with messages', async () => {
    const withMessages = { ...mockConversation, messages: [mockMessage] };
    mockGet.mockResolvedValue({ data: withMessages });
    const result = await conversationsAPI.getConversation('test-uuid-42');
    expect(result.messages).toHaveLength(1);
    expect(result.messages[0].role).toBe('user');
  });
});

describe('conversationsAPI.updateConversation', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls PATCH /api/v1/conversations/:publicId with data', async () => {
    const update: UpdateConversationData = { title: 'Renamed chat' };
    mockPatch.mockResolvedValue({ data: { ...mockConversation, title: 'Renamed chat' } });
    await conversationsAPI.updateConversation('test-uuid-42', update);
    expect(mockPatch).toHaveBeenCalledWith('/api/v1/conversations/test-uuid-42', update);
  });

  it('returns the updated conversation', async () => {
    const updated = { ...mockConversation, title: 'New title' };
    mockPatch.mockResolvedValue({ data: updated });
    const result = await conversationsAPI.updateConversation('test-uuid-42', { title: 'New title' });
    expect(result.title).toBe('New title');
  });
});

describe('conversationsAPI.deleteConversation', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls DELETE /api/v1/conversations/:publicId', async () => {
    mockDelete.mockResolvedValue({ data: {} });
    await conversationsAPI.deleteConversation('test-uuid-42');
    expect(mockDelete).toHaveBeenCalledWith('/api/v1/conversations/test-uuid-42');
  });
});

// ─── Folders ──────────────────────────────────────────────────────────────────

describe('conversationsAPI.getFolders', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/conversations/folders', async () => {
    mockGet.mockResolvedValue({ data: [mockFolder] });
    await conversationsAPI.getFolders();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/conversations/folders');
  });

  it('returns array of folders', async () => {
    mockGet.mockResolvedValue({ data: [mockFolder] });
    const result = await conversationsAPI.getFolders();
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('General');
  });
});

describe('conversationsAPI.createFolder', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls POST /api/v1/conversations/folders with data', async () => {
    const data: CreateFolderData = { name: 'Customer Insights' };
    mockPost.mockResolvedValue({ data: { ...mockFolder, name: 'Customer Insights' } });
    await conversationsAPI.createFolder(data);
    expect(mockPost).toHaveBeenCalledWith('/api/v1/conversations/folders', data);
  });

  it('returns the created folder', async () => {
    const newFolder = { ...mockFolder, name: 'My Folder' };
    mockPost.mockResolvedValue({ data: newFolder });
    const result = await conversationsAPI.createFolder({ name: 'My Folder' });
    expect(result.name).toBe('My Folder');
  });
});

describe('conversationsAPI.updateFolder', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls PATCH /api/v1/conversations/folders/:id', async () => {
    const update: UpdateFolderData = { name: 'Renamed Folder' };
    mockPatch.mockResolvedValue({ data: { ...mockFolder, name: 'Renamed Folder' } });
    await conversationsAPI.updateFolder(1, update);
    expect(mockPatch).toHaveBeenCalledWith('/api/v1/conversations/folders/1', update);
  });
});

describe('conversationsAPI.deleteFolder', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls DELETE /api/v1/conversations/folders/:id', async () => {
    mockDelete.mockResolvedValue({ data: {} });
    await conversationsAPI.deleteFolder(1);
    expect(mockDelete).toHaveBeenCalledWith('/api/v1/conversations/folders/1');
  });
});

// ─── Templates & Suggestions ──────────────────────────────────────────────────

describe('conversationsAPI.getTemplateStarters', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/conversations/templates', async () => {
    const mockTemplates: TemplateStartersResponse = {
      templates: ["This week's feedback summary", 'Top pain points this month'],
    };
    mockGet.mockResolvedValue({ data: mockTemplates });
    await conversationsAPI.getTemplateStarters();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/conversations/templates');
  });

  it('returns the templates list', async () => {
    const mockTemplates: TemplateStartersResponse = {
      templates: ["This week's feedback summary"],
    };
    mockGet.mockResolvedValue({ data: mockTemplates });
    const result = await conversationsAPI.getTemplateStarters();
    expect(result.templates).toHaveLength(1);
  });
});

describe('conversationsAPI.getSuggestions', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls POST /api/v1/conversations/suggestions', async () => {
    mockPost.mockResolvedValue({ data: { suggestions: ['Check churn risk'] } });
    await conversationsAPI.getSuggestions();
    expect(mockPost).toHaveBeenCalledWith('/api/v1/conversations/suggestions');
  });

  it('returns the suggestions list', async () => {
    mockPost.mockResolvedValue({ data: { suggestions: ['Check churn risk', 'Sentiment trends'] } });
    const result = await conversationsAPI.getSuggestions();
    expect(result.suggestions).toHaveLength(2);
  });
});

describe('conversationsAPI.getCopilotUsage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls GET /api/v1/copilot/usage', async () => {
    mockGet.mockResolvedValue({ data: { queries_today: 3, daily_limit: 10, plan: 'free' } });
    await conversationsAPI.getCopilotUsage();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/copilot/usage');
  });

  it('returns usage data with queries_today, daily_limit, and plan', async () => {
    mockGet.mockResolvedValue({ data: { queries_today: 3, daily_limit: 10, plan: 'free' } });
    const result = await conversationsAPI.getCopilotUsage();
    expect(result.queries_today).toBe(3);
    expect(result.daily_limit).toBe(10);
    expect(result.plan).toBe('free');
  });

  it('handles null daily_limit for paid plans', async () => {
    mockGet.mockResolvedValue({ data: { queries_today: 50, daily_limit: null, plan: 'pro' } });
    const result = await conversationsAPI.getCopilotUsage();
    expect(result.daily_limit).toBeNull();
  });
});

// ─── Error handling ───────────────────────────────────────────────────────────

describe('conversationsAPI error handling', () => {
  beforeEach(() => vi.clearAllMocks());

  it('propagates 401 errors from getConversation', async () => {
    const err = Object.assign(new Error('Unauthorized'), { response: { status: 401 } });
    mockGet.mockRejectedValue(err);
    await expect(conversationsAPI.getConversation('test-uuid-42')).rejects.toMatchObject({
      response: { status: 401 },
    });
  });

  it('propagates 403 errors from deleteConversation', async () => {
    const err = Object.assign(new Error('Forbidden'), { response: { status: 403 } });
    mockDelete.mockRejectedValue(err);
    await expect(conversationsAPI.deleteConversation('test-uuid-42')).rejects.toMatchObject({
      response: { status: 403 },
    });
  });

  it('propagates 404 errors from getConversation', async () => {
    const err = Object.assign(new Error('Not found'), { response: { status: 404 } });
    mockGet.mockRejectedValue(err);
    await expect(conversationsAPI.getConversation('nonexistent-uuid')).rejects.toMatchObject({
      response: { status: 404 },
    });
  });

  it('propagates 429 errors from getSuggestions', async () => {
    const err = Object.assign(new Error('Rate limited'), { response: { status: 429 } });
    mockPost.mockRejectedValue(err);
    await expect(conversationsAPI.getSuggestions()).rejects.toMatchObject({
      response: { status: 429 },
    });
  });

  it('propagates 500 errors from createConversation', async () => {
    const err = Object.assign(new Error('Server error'), { response: { status: 500 } });
    mockPost.mockRejectedValue(err);
    await expect(conversationsAPI.createConversation({ context_scope: 'all_data' })).rejects.toMatchObject({
      response: { status: 500 },
    });
  });
});
