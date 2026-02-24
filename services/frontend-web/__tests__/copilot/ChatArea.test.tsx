import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockSendQuery = vi.fn();
const mockStopGeneration = vi.fn();
const mockRegenerate = vi.fn();

vi.mock('@/hooks/useCopilotWebSocket', () => ({
  useCopilotWebSocket: vi.fn(() => ({
    connected: true,
    streaming: false,
    streamingContent: '',
    statusText: '',
    reconnecting: false,
    error: null,
    sendQuery: mockSendQuery,
    stopGeneration: mockStopGeneration,
    regenerate: mockRegenerate,
  })),
}));

vi.mock('@/lib/api/conversations', () => ({
  conversationsAPI: {
    getConversation: vi.fn(),
  },
}));

import { ChatArea } from '@/components/copilot/ChatArea';
import { conversationsAPI } from '@/lib/api/conversations';
import { useCopilotWebSocket } from '@/hooks/useCopilotWebSocket';

const mockedGetConversation = conversationsAPI.getConversation as ReturnType<typeof vi.fn>;
const mockedUseWebSocket = useCopilotWebSocket as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'owner',
  plan: 'enterprise',
  organization_id: 1,
};

const mockConversation = {
  id: 42,
  public_id: 'test-uuid-42',
  organization_id: 1,
  created_by_user_id: 1,
  title: 'Test conversation',
  folder_id: null,
  context_scope: 'all_data',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  messages: [
    {
      id: 101,
      conversation_id: 42,
      role: 'user',
      content: 'Show me feedback trends',
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
      created_at: '2026-01-01T00:01:00Z',
    },
    {
      id: 102,
      conversation_id: 42,
      role: 'assistant',
      content: 'Here are the trends for your feedback data.',
      structured_data: null,
      context_scope: 'all_data',
      query_type: 'data',
      template_id: null,
      sql_generated: null,
      llm_provider: null,
      llm_model: null,
      tokens_in: null,
      tokens_out: null,
      cost_cents: null,
      latency_ms: null,
      is_regenerated: false,
      created_at: '2026-01-01T00:01:05Z',
    },
  ],
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ChatArea', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockedGetConversation.mockResolvedValue(mockConversation);
    mockedUseWebSocket.mockReturnValue({
      connected: true,
      streaming: false,
      streamingContent: '',
      statusText: '',
      reconnecting: false,
      error: null,
      sendQuery: mockSendQuery,
      stopGeneration: mockStopGeneration,
      regenerate: mockRegenerate,
    });
  });

  // ── Rendering ──────────────────────────────────────────────────────────────

  describe('Rendering', () => {
    it('renders the chat area container', async () => {
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-area-container')).toBeInTheDocument();
      });
    });

    it('renders existing messages from the conversation', async () => {
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByText('Show me feedback trends')).toBeInTheDocument();
        expect(screen.getByText('Here are the trends for your feedback data.')).toBeInTheDocument();
      });
    });

    it('renders the message input textarea', async () => {
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
    });
  });

  // ── Message sending ────────────────────────────────────────────────────────

  describe('Message sending', () => {
    it('calls sendQuery when Enter is pressed', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, 'What are the top pain points?');
      await user.keyboard('{Enter}');
      await waitFor(() => {
        expect(mockSendQuery).toHaveBeenCalledWith(
          'test-uuid-42',
          'What are the top pain points?',
          'all_data'
        );
      });
    });

    it('adds a newline with Shift+Enter instead of sending', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input') as HTMLTextAreaElement;
      await user.click(input);
      await user.type(input, 'line one');
      await user.keyboard('{Shift>}{Enter}{/Shift}');
      expect(mockSendQuery).not.toHaveBeenCalled();
      expect(input.value).toContain('\n');
    });

    it('clears the input after sending', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input') as HTMLTextAreaElement;
      await user.click(input);
      await user.type(input, 'Test query');
      await user.keyboard('{Enter}');
      await waitFor(() => {
        expect(input.value).toBe('');
      });
    });

    it('does not send empty messages', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.keyboard('{Enter}');
      expect(mockSendQuery).not.toHaveBeenCalled();
    });

    it('adds the optimistic user message to the chat immediately', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, 'Urgent feedbacks this week?');
      await user.keyboard('{Enter}');
      await waitFor(() => {
        expect(screen.getByText('Urgent feedbacks this week?')).toBeInTheDocument();
      });
    });
  });

  // ── Streaming ─────────────────────────────────────────────────────────────

  describe('Streaming', () => {
    it('shows streaming indicator when streaming=true', async () => {
      mockedUseWebSocket.mockReturnValue({
        connected: true,
        streaming: true,
        streamingContent: 'Analyzing...',
        statusText: 'Analyzing data...',
        reconnecting: false,
        error: null,
        sendQuery: mockSendQuery,
        stopGeneration: mockStopGeneration,
        regenerate: mockRegenerate,
      });
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('streaming-indicator')).toBeInTheDocument();
      });
    });

    it('shows status text during streaming', async () => {
      mockedUseWebSocket.mockReturnValue({
        connected: true,
        streaming: true,
        streamingContent: '',
        statusText: 'Searching feedbacks...',
        reconnecting: false,
        error: null,
        sendQuery: mockSendQuery,
        stopGeneration: mockStopGeneration,
        regenerate: mockRegenerate,
      });
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        // Status text may appear in the streaming bubble and/or below it
        expect(screen.getAllByText('Searching feedbacks...').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows stop button during streaming', async () => {
      mockedUseWebSocket.mockReturnValue({
        connected: true,
        streaming: true,
        streamingContent: 'partial response...',
        statusText: '',
        reconnecting: false,
        error: null,
        sendQuery: mockSendQuery,
        stopGeneration: mockStopGeneration,
        regenerate: mockRegenerate,
      });
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('stop-generating-btn')).toBeInTheDocument();
      });
    });

    it('calls stopGeneration when stop button is clicked', async () => {
      mockedUseWebSocket.mockReturnValue({
        connected: true,
        streaming: true,
        streamingContent: 'partial...',
        statusText: '',
        reconnecting: false,
        error: null,
        sendQuery: mockSendQuery,
        stopGeneration: mockStopGeneration,
        regenerate: mockRegenerate,
      });
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('stop-generating-btn')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('stop-generating-btn'));
      expect(mockStopGeneration).toHaveBeenCalled();
    });
  });

  // ── Context scope chips ─────────────────────────────────────────────────────

  describe('Context scope chips', () => {
    it('starts with no scope chips (defaults to all_data on send)', async () => {
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      // No scope chips should be rendered
      expect(screen.queryByTestId('scope-chip-feedbacks')).not.toBeInTheDocument();
      expect(screen.queryByTestId('scope-chip-all_data')).not.toBeInTheDocument();
    });

    it('sends all_data when no scope chips are selected', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, 'Test query');
      await user.keyboard('{Enter}');
      await waitFor(() => {
        expect(mockSendQuery).toHaveBeenCalledWith('test-uuid-42', 'Test query', 'all_data');
      });
    });

    it('shows scope autocomplete when bare @ is typed', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-autocomplete')).toBeInTheDocument();
        // Should show scope options
        expect(screen.getByTestId('mention-option-@scope:feedbacks')).toBeInTheDocument();
        expect(screen.getByTestId('mention-option-@scope:pain_points')).toBeInTheDocument();
      });
    });

    it('adds scope chip when scope option is selected from @ dropdown', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-option-@scope:feedbacks')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('mention-option-@scope:feedbacks'));
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-feedbacks')).toBeInTheDocument();
      });
      // The @ should be removed from the input text
      expect((input as HTMLTextAreaElement).value).toBe('');
    });

    it('removes scope chip when x button is clicked', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      // Add a scope first
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-option-@scope:pain_points')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('mention-option-@scope:pain_points'));
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-pain_points')).toBeInTheDocument();
      });
      // Now remove it
      fireEvent.click(screen.getByTestId('scope-chip-remove-pain_points'));
      await waitFor(() => {
        expect(screen.queryByTestId('scope-chip-pain_points')).not.toBeInTheDocument();
      });
    });

    it('sends comma-separated scopes when multiple chips are selected', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');

      // Add first scope
      await user.click(input);
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-option-@scope:feedbacks')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('mention-option-@scope:feedbacks'));
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-feedbacks')).toBeInTheDocument();
      });

      // Add second scope
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-option-@scope:pain_points')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('mention-option-@scope:pain_points'));
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-pain_points')).toBeInTheDocument();
      });

      // Send message
      await user.type(input, 'Show trends');
      await user.keyboard('{Enter}');
      await waitFor(() => {
        expect(mockSendQuery).toHaveBeenCalledWith('test-uuid-42', 'Show trends', 'feedbacks,pain_points');
      });
    });

    it('hides already-selected scopes from the @ dropdown', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');

      // Add feedbacks scope
      await user.click(input);
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-option-@scope:feedbacks')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId('mention-option-@scope:feedbacks'));
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-feedbacks')).toBeInTheDocument();
      });

      // Open @ dropdown again — feedbacks should not be shown
      await user.type(input, '@');
      await waitFor(() => {
        expect(screen.getByTestId('mention-autocomplete')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('mention-option-@scope:feedbacks')).not.toBeInTheDocument();
      expect(screen.getByTestId('mention-option-@scope:pain_points')).toBeInTheDocument();
    });

    it('loads saved scopes from conversation context_scope', async () => {
      mockedGetConversation.mockResolvedValue({
        ...mockConversation,
        context_scope: 'feedbacks,customers',
      });
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('scope-chip-feedbacks')).toBeInTheDocument();
        expect(screen.getByTestId('scope-chip-customers')).toBeInTheDocument();
      });
    });
  });

  // ── Reconnecting indicator ─────────────────────────────────────────────────

  describe('Reconnecting indicator', () => {
    it('shows reconnecting banner when reconnecting=true', async () => {
      mockedUseWebSocket.mockReturnValue({
        connected: false,
        streaming: false,
        streamingContent: '',
        statusText: '',
        reconnecting: true,
        error: null,
        sendQuery: mockSendQuery,
        stopGeneration: mockStopGeneration,
        regenerate: mockRegenerate,
      });
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('reconnecting-banner')).toBeInTheDocument();
      });
    });
  });

  // ── @mention autocomplete ──────────────────────────────────────────────────

  describe('@mention autocomplete', () => {
    it('shows autocomplete dropdown when @customer: is typed', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, '@customer:');
      await waitFor(() => {
        expect(screen.getByTestId('mention-autocomplete')).toBeInTheDocument();
      });
    });

    it('shows period presets when @period: is typed', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, '@period:');
      await waitFor(() => {
        expect(screen.getByTestId('mention-autocomplete')).toBeInTheDocument();
        expect(screen.getByText('last-7-days')).toBeInTheDocument();
      });
    });

    it('hides autocomplete when input is cleared', async () => {
      const user = userEvent.setup();
      render(<ChatArea conversationId={'test-uuid-42'} />);
      await waitFor(() => {
        expect(screen.getByTestId('chat-input')).toBeInTheDocument();
      });
      const input = screen.getByTestId('chat-input');
      await user.click(input);
      await user.type(input, '@period:');
      await waitFor(() => {
        expect(screen.getByTestId('mention-autocomplete')).toBeInTheDocument();
      });
      await user.clear(input);
      await waitFor(() => {
        expect(screen.queryByTestId('mention-autocomplete')).not.toBeInTheDocument();
      });
    });
  });
});
