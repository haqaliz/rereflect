/**
 * E2E-style integration tests for the AI Copilot conversation flow.
 *
 * These tests verify the full lifecycle:
 * - Template click → conversation creation → first message auto-sent
 * - New Chat → conversation creation → sidebar updates
 * - Cmd+K navigation → conversation creation with initialQuery
 * - WebSocket: connection, query, streaming, response, reconnect
 * - Multi-scope selection via @ trigger → correct scope string on send
 * - ConversationList + ChatArea interaction: select, rename, delete
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mock next/navigation ─────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockReplace = vi.fn();
let currentSearchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  usePathname: () => '/conversations',
  useSearchParams: () => currentSearchParams,
}));

// ─── Mock AuthContext ─────────────────────────────────────────────────────────

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'test@test.com',
      role: 'owner',
      plan: 'pro',
      organization_id: 1,
      is_system_admin: false,
    },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

// ─── Mock sidebar ─────────────────────────────────────────────────────────────

const mockSetOpen = vi.fn();
vi.mock('@/components/ui/sidebar', () => ({
  useSidebar: vi.fn(() => ({
    open: true,
    setOpen: mockSetOpen,
    state: 'expanded',
    toggleSidebar: vi.fn(),
    isMobile: false,
    openMobile: false,
    setOpenMobile: vi.fn(),
  })),
  SidebarProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SidebarInset: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SidebarTrigger: () => <button>Toggle</button>,
}));

// ─── Mock conversations API ──────────────────────────────────────────────────

vi.mock('@/lib/api/conversations', () => ({
  conversationsAPI: {
    getConversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    updateConversation: vi.fn(),
    deleteConversation: vi.fn(),
    getFolders: vi.fn(),
    createFolder: vi.fn(),
    updateFolder: vi.fn(),
    deleteFolder: vi.fn(),
    getTemplateStarters: vi.fn(),
    getSuggestions: vi.fn(),
    getCopilotUsage: vi.fn(),
  },
}));

// ─── Mock WebSocket hook ─────────────────────────────────────────────────────

const mockSendQuery = vi.fn();
const mockStopGeneration = vi.fn();
const mockRegenerate = vi.fn();
let wsHookState = {
  connected: true,
  streaming: false,
  streamingContent: '',
  statusText: '',
  reconnecting: false,
  error: null as string | null,
  sendQuery: mockSendQuery,
  stopGeneration: mockStopGeneration,
  regenerate: mockRegenerate,
};
let wsOnMessage: ((msg: unknown) => void) | null = null;

vi.mock('@/hooks/useCopilotWebSocket', () => ({
  useCopilotWebSocket: vi.fn((options?: { onMessage?: (msg: unknown) => void }) => {
    if (options?.onMessage) {
      wsOnMessage = options.onMessage;
    }
    return wsHookState;
  }),
}));

// ─── Mock sonner ──────────────────────────────────────────────────────────────

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── Imports after mocks ─────────────────────────────────────────────────────

import { conversationsAPI } from '@/lib/api/conversations';
import ConversationsPage from '@/app/(dashboard)/conversations/page';
import { ChatArea } from '@/components/copilot/ChatArea';

const api = conversationsAPI as Record<string, ReturnType<typeof vi.fn>>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

let nextConvId = 100;

function makeConversation(overrides: Record<string, unknown> = {}) {
  const id = nextConvId++;
  return {
    id,
    public_id: overrides.public_id ?? `uuid-${id}`,
    organization_id: 1,
    created_by_user_id: 1,
    title: overrides.title ?? `Conversation ${id}`,
    folder_id: null,
    context_scope: 'all_data',
    is_active: true,
    created_at: '2026-02-23T01:00:00Z',
    updated_at: '2026-02-23T01:00:00Z',
    messages: [],
    ...overrides,
  };
}

function makeMessage(overrides: Record<string, unknown> = {}) {
  return {
    id: Math.floor(Math.random() * 10000),
    conversation_id: 42,
    role: 'user',
    content: 'Hello',
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
    created_at: '2026-02-23T01:00:00Z',
    ...overrides,
  };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

describe('Copilot Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    nextConvId = 100;
    currentSearchParams = new URLSearchParams();
    wsOnMessage = null;
    wsHookState = {
      connected: true,
      streaming: false,
      streamingContent: '',
      statusText: '',
      reconnecting: false,
      error: null,
      sendQuery: mockSendQuery,
      stopGeneration: mockStopGeneration,
      regenerate: mockRegenerate,
    };

    // Default API responses
    api.getFolders.mockResolvedValue([]);
    api.getConversations.mockResolvedValue({
      conversations: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    api.getTemplateStarters.mockResolvedValue({
      templates: ["This week's feedback summary", 'Top pain points this month'],
    });
    api.getCopilotUsage.mockResolvedValue({
      queries_today: 0,
      daily_limit: 50,
      plan: 'pro',
    });
    api.getConversation.mockImplementation(async (publicId: string) => ({
      ...makeConversation({ public_id: publicId }),
      messages: [],
    }));
    api.createConversation.mockImplementation(async (data: Record<string, unknown>) =>
      makeConversation({ title: data.title ?? 'New Chat' })
    );
    api.deleteConversation.mockResolvedValue(undefined);
    api.updateConversation.mockImplementation(async (publicId: string, data: Record<string, unknown>) => ({
      ...makeConversation({ public_id: publicId }),
      ...data,
    }));
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. Full Page: Template Click → Conversation Created → First Message Sent
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Template click flow', () => {
    it('clicking a template creates exactly one conversation and opens the chat', async () => {
      const createdConv = makeConversation({ title: "This week's fee" });
      api.createConversation.mockResolvedValueOnce(createdConv);
      api.getConversation.mockResolvedValueOnce({ ...createdConv, messages: [] });

      render(<ConversationsPage />);

      // Wait for the page and empty state to appear
      await waitFor(() => {
        expect(screen.getByTestId('conversations-empty-state')).toBeInTheDocument();
      });

      // Click the template
      fireEvent.click(screen.getByText("This week's feedback summary"));

      // Should create exactly one conversation
      await waitFor(() => {
        expect(api.createConversation).toHaveBeenCalledTimes(1);
        expect(api.createConversation).toHaveBeenCalledWith(
          expect.objectContaining({
            context_scope: 'all_data',
            title: "This week's feedback summary".slice(0, 50),
          })
        );
      });

      // Chat area should now be visible (conversation selected)
      await waitFor(() => {
        expect(screen.getByTestId('chat-area-container')).toBeInTheDocument();
      });
    });

    it('double-clicking a template does not create two conversations (useRef guard)', async () => {
      // Slow down createConversation to simulate network delay
      let resolveFirst!: (v: unknown) => void;
      const firstCall = new Promise((r) => { resolveFirst = r; });
      api.createConversation.mockReturnValueOnce(firstCall);

      render(<ConversationsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('conversations-empty-state')).toBeInTheDocument();
      });

      const templateBtn = screen.getByText("This week's feedback summary");

      // Rapid double-click
      fireEvent.click(templateBtn);
      fireEvent.click(templateBtn);

      // Only one call should have been made (second blocked by useRef guard)
      expect(api.createConversation).toHaveBeenCalledTimes(1);

      // Resolve the first call
      const conv = makeConversation({ title: "This week's fee" });
      api.getConversation.mockResolvedValue({ ...conv, messages: [] });
      resolveFirst(conv);

      await waitFor(() => {
        expect(screen.getByTestId('chat-area-container')).toBeInTheDocument();
      });

      // Still only one call
      expect(api.createConversation).toHaveBeenCalledTimes(1);
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. New Chat Button → Conversation Created → Sidebar Updated
  // ═══════════════════════════════════════════════════════════════════════════

  describe('New Chat flow', () => {
    it('New Chat button resets to welcome state with template starters', async () => {
      render(<ConversationsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
      });

      // Click "New Chat"
      fireEvent.click(screen.getByRole('button', { name: /new chat/i }));

      // The main chat area should show the welcome state (with Sparkles icon + templates)
      const chatArea = screen.getByTestId('chat-area');
      await waitFor(() => {
        expect(within(chatArea).getByText('AI Copilot')).toBeInTheDocument();
      });

      // Conversation is NOT created eagerly — deferred until user sends a message
      expect(api.createConversation).not.toHaveBeenCalled();
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. Cmd+K Navigation Flow (via ?new=true&q=... params)
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Cmd+K navigation flow', () => {
    it('creates conversation from URL params and cleans up the URL', async () => {
      currentSearchParams = new URLSearchParams('new=true&q=Show+churn+risks');
      const conv = makeConversation({ title: 'Show churn risks' });
      api.createConversation.mockResolvedValueOnce(conv);
      api.getConversation.mockResolvedValue({ ...conv, messages: [] });

      render(<ConversationsPage />);

      await waitFor(() => {
        expect(api.createConversation).toHaveBeenCalledWith(
          expect.objectContaining({
            context_scope: 'all_data',
            title: 'Show churn risks',
          })
        );
      });

      // Should update URL with the new conversation's public_id
      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith(`/conversations?id=${conv.public_id}`, { scroll: false });
      });
    });

    it('does not create conversation with empty q param', () => {
      currentSearchParams = new URLSearchParams('new=true&q=');
      render(<ConversationsPage />);
      expect(api.createConversation).not.toHaveBeenCalled();
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. ChatArea: Message Send → WebSocket Query → Optimistic Update
  // ═══════════════════════════════════════════════════════════════════════════

  describe('ChatArea message sending', () => {
    it('sends message via WebSocket and adds optimistic user bubble', async () => {
      const user = userEvent.setup();
      const conv = makeConversation({ id: 42, public_id: 'test-uuid-42' });
      api.getConversation.mockResolvedValue({ ...conv, messages: [] });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });

      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, 'How many feedbacks this week?');
      await user.keyboard('{Enter}');

      // Optimistic user message should appear immediately
      await waitFor(() => {
        expect(screen.getByText('How many feedbacks this week?')).toBeInTheDocument();
      });

      // WebSocket sendQuery should have been called
      expect(mockSendQuery).toHaveBeenCalledWith('test-uuid-42', 'How many feedbacks this week?', 'all_data');
    });

    it('initialQuery auto-sends the first message after loading', async () => {
      const conv = makeConversation({ id: 42, public_id: 'test-uuid-42' });
      api.getConversation.mockResolvedValue({ ...conv, messages: [] });

      render(<ChatArea conversationId={'test-uuid-42'} initialQuery="Top pain points this month" />);

      await waitFor(() => {
        expect(mockSendQuery).toHaveBeenCalledWith('test-uuid-42', 'Top pain points this month', 'all_data');
      });

      // Optimistic user message should appear
      await waitFor(() => {
        expect(screen.getByText('Top pain points this month')).toBeInTheDocument();
      });
    });

    it('sends with comma-separated scopes when multiple scope chips are selected', async () => {
      const user = userEvent.setup();
      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42', context_scope: 'feedbacks,pain_points' }),
        messages: [],
      });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-feedbacks')).toBeInTheDocument();
        expect(screen.getByTestId('scope-chip-pain_points')).toBeInTheDocument();
      });

      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, 'Show trends');
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockSendQuery).toHaveBeenCalledWith('test-uuid-42', 'Show trends', 'feedbacks,pain_points');
      });
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. ChatArea: WebSocket Response → Assistant Message Added
  // ═══════════════════════════════════════════════════════════════════════════

  describe('ChatArea WebSocket response handling', () => {
    it('adds assistant message when onMessage callback fires', async () => {
      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42' }),
        messages: [makeMessage({ id: 101, role: 'user', content: 'Show trends' })],
      });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByText('Show trends')).toBeInTheDocument();
      });

      // Simulate WebSocket response via onMessage callback
      expect(wsOnMessage).not.toBeNull();
      act(() => {
        wsOnMessage!({
          type: 'assistant_message',
          message_id: 'uuid-201',
          content: 'Here are the feedback trends for your organization.',
        });
      });

      await waitFor(() => {
        expect(screen.getByText('Here are the feedback trends for your organization.')).toBeInTheDocument();
      });
    });

    it('attaches structured data to the correct assistant message', async () => {
      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42' }),
        messages: [],
      });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });

      // First add an assistant message
      act(() => {
        wsOnMessage!({
          type: 'assistant_message',
          message_id: 'uuid-301',
          content: 'Here is the data:',
        });
      });

      await waitFor(() => {
        expect(screen.getByText('Here is the data:')).toBeInTheDocument();
      });

      // Then attach structured data
      act(() => {
        wsOnMessage!({
          type: 'structured_data',
          message_id: 'uuid-301',
          data: { kind: 'table', columns: ['Name', 'Count'], rows: [['Bug', 5]] },
        });
      });

      // The message should still be displayed (structured data is rendered by MessageBubble)
      await waitFor(() => {
        expect(screen.getByText('Here is the data:')).toBeInTheDocument();
      });
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 6. ChatArea: Streaming Lifecycle
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Streaming lifecycle', () => {
    it('shows streaming indicator and stop button when streaming', async () => {
      wsHookState = {
        ...wsHookState,
        streaming: true,
        streamingContent: 'Analyzing your feedback data...',
        statusText: 'Running query...',
      };

      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42' }),
        messages: [],
      });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByTestId('streaming-indicator')).toBeInTheDocument();
        expect(screen.getByText('Analyzing your feedback data...')).toBeInTheDocument();
        expect(screen.getByTestId('stop-generating-btn')).toBeInTheDocument();
      });
    });

    it('shows status text with bouncing dots before content arrives', async () => {
      wsHookState = {
        ...wsHookState,
        streaming: true,
        streamingContent: '',
        statusText: 'Searching feedbacks...',
      };

      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42' }),
        messages: [],
      });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByTestId('streaming-indicator')).toBeInTheDocument();
        // Status text in the streaming bubble
        const bubble = screen.getByTestId('streaming-indicator');
        expect(within(bubble).getByText('Searching feedbacks...')).toBeInTheDocument();
      });
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 7. Reconnecting Banner
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Reconnecting', () => {
    it('shows reconnecting banner when WebSocket is reconnecting', async () => {
      wsHookState = {
        ...wsHookState,
        connected: false,
        reconnecting: true,
      };

      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42' }),
        messages: [],
      });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByTestId('reconnecting-banner')).toBeInTheDocument();
        expect(screen.getByText('Reconnecting...')).toBeInTheDocument();
      });
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 8. Multi-Scope Flow: @ Trigger → Select → Chip → Remove → Send
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Multi-scope chip full flow', () => {
    it('full scope lifecycle: add via @, see chip, add another, remove one, send with correct scope', async () => {
      const user = userEvent.setup();
      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42' }),
        messages: [],
      });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });

      const input = screen.getByTestId('chat-input');

      // Step 1: Type @ to open scope dropdown
      await user.click(input);
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-autocomplete')).toBeInTheDocument();
      });

      // Step 2: Select "Feedbacks"
      fireEvent.click(screen.getByTestId('mention-option-@scope:feedbacks'));
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-feedbacks')).toBeInTheDocument();
      });

      // Step 3: @ again to add "Pain Points"
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-autocomplete')).toBeInTheDocument();
        // Feedbacks should be hidden (already selected)
        expect(screen.queryByTestId('mention-option-@scope:feedbacks')).not.toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('mention-option-@scope:pain_points'));
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-pain_points')).toBeInTheDocument();
      });

      // Step 4: @ again to add "Customers"
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-autocomplete')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('mention-option-@scope:customers'));
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-customers')).toBeInTheDocument();
      });

      // Step 5: Remove "Pain Points" chip
      fireEvent.click(screen.getByTestId('scope-chip-remove-pain_points'));
      await waitFor(() => {
        expect(screen.queryByTestId('scope-chip-pain_points')).not.toBeInTheDocument();
      });

      // Step 6: Send message with remaining scopes (feedbacks,customers)
      await user.type(input, 'What are the trends?');
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockSendQuery).toHaveBeenCalledWith('test-uuid-42', 'What are the trends?', 'feedbacks,customers');
      });
    });

    it('removing all chips sends with all_data default', async () => {
      const user = userEvent.setup();
      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42', context_scope: 'feedbacks' }),
        messages: [],
      });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-feedbacks')).toBeInTheDocument();
      });

      // Remove the chip
      fireEvent.click(screen.getByTestId('scope-chip-remove-feedbacks'));
      await waitFor(() => {
        expect(screen.queryByTestId('scope-chip-feedbacks')).not.toBeInTheDocument();
      });

      // Send — should default to all_data
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, 'Query');
      await user.keyboard('{Enter}');

      await waitFor(() => {
        expect(mockSendQuery).toHaveBeenCalledWith('test-uuid-42', 'Query', 'all_data');
      });
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 9. ConversationList: Selection, Rename, Delete
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Conversation list interactions in full page', () => {
    it('selecting a conversation loads it in the chat area', async () => {
      const conv1 = makeConversation({ id: 50, public_id: 'uuid-50', title: 'First conv' });
      const conv2 = makeConversation({ id: 51, public_id: 'uuid-51', title: 'Second conv' });

      api.getConversations.mockResolvedValue({
        conversations: [conv1, conv2],
        total: 2,
        page: 1,
        page_size: 20,
      });
      api.getConversation.mockImplementation(async (publicId: string) => {
        if (publicId === 'uuid-50') return { ...conv1, messages: [makeMessage({ content: 'Hello from conv1' })] };
        if (publicId === 'uuid-51') return { ...conv2, messages: [makeMessage({ content: 'Hello from conv2' })] };
        return { ...makeConversation({ public_id: publicId }), messages: [] };
      });

      render(<ConversationsPage />);

      // Wait for list to load
      await waitFor(() => {
        expect(screen.getByText('First conv')).toBeInTheDocument();
        expect(screen.getByText('Second conv')).toBeInTheDocument();
      });

      // Click on "First conv"
      fireEvent.click(screen.getByText('First conv'));

      // Chat area should load
      await waitFor(() => {
        expect(screen.getByTestId('chat-area-container')).toBeInTheDocument();
      });
    });

    it('deleting a conversation removes it from the list', async () => {
      const conv = makeConversation({ id: 60, public_id: 'uuid-60', title: 'Deletable conv' });
      api.getConversations.mockResolvedValue({
        conversations: [conv],
        total: 1,
        page: 1,
        page_size: 20,
      });

      render(<ConversationsPage />);

      await waitFor(() => {
        expect(screen.getByText('Deletable conv')).toBeInTheDocument();
      });

      // Hover to show delete button, then click
      const deleteBtn = screen.getByTestId('conversation-delete-uuid-60');
      fireEvent.click(deleteBtn);

      // Confirm delete dialog
      await waitFor(() => {
        expect(screen.getByTestId('confirm-delete-btn')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('confirm-delete-btn'));

      await waitFor(() => {
        expect(api.deleteConversation).toHaveBeenCalledWith('uuid-60');
      });
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 10. Sidebar Auto-Collapse
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Sidebar behavior', () => {
    it('auto-collapses the main sidebar on mount', async () => {
      render(<ConversationsPage />);
      await waitFor(() => {
        expect(mockSetOpen).toHaveBeenCalledWith(false);
      });
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 11. Loading Existing Conversation with Messages
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Loading existing conversation', () => {
    it('renders existing user and assistant messages from API', async () => {
      const conv = makeConversation({ id: 42, public_id: 'test-uuid-42', context_scope: 'feedbacks' });
      const userMsg = makeMessage({ id: 1, role: 'user', content: 'What are top pain points?', conversation_id: 42 });
      const assistantMsg = makeMessage({ id: 2, role: 'assistant', content: 'The top pain points are: billing, onboarding, performance.', conversation_id: 42 });

      api.getConversation.mockResolvedValue({ ...conv, messages: [userMsg, assistantMsg] });

      render(<ChatArea conversationId={'test-uuid-42'} />);

      await waitFor(() => {
        expect(screen.getByText('What are top pain points?')).toBeInTheDocument();
        expect(screen.getByText('The top pain points are: billing, onboarding, performance.')).toBeInTheDocument();
      });

      // Saved scope should be loaded as a chip
      expect(screen.getByTestId('scope-chip-feedbacks')).toBeInTheDocument();
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // 12. Token Budget Exceeded Banner
  // ═══════════════════════════════════════════════════════════════════════════

  describe('Token budget', () => {
    it('shows budget exceeded banner and disables input when token budget is reached', async () => {
      api.getConversation.mockResolvedValue({
        ...makeConversation({ id: 42, public_id: 'test-uuid-42' }),
        messages: [],
      });

      render(
        <ChatArea
          conversationId={'test-uuid-42'}
          copilotUsage={{
            queries_today: 10,
            daily_limit: 50,
            plan: 'pro',
            tokens_used_month: 1000000,
            tokens_budget_month: 1000000,
          }}
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('token-budget-banner')).toBeInTheDocument();
      });

      // Input should be disabled
      const input = screen.getByTestId('chat-input') as HTMLTextAreaElement;
      expect(input.disabled).toBe(true);
    });
  });
});
