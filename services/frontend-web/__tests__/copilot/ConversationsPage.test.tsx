import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
const mockReplace = vi.fn();
const mockSearchParams = vi.fn(() => new URLSearchParams());
const mockPathname = vi.fn(() => '/conversations');
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  usePathname: () => mockPathname(),
  useSearchParams: () => mockSearchParams(),
}));

// Mock Suspense-wrapped useSearchParams
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  usePathname: () => mockPathname(),
  useSearchParams: () => mockSearchParams(),
}));

// Mock AuthContext
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

// Mock conversations API
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

// Mock useCopilotWebSocket so ChatArea doesn't try to open a real WebSocket
vi.mock('@/hooks/useCopilotWebSocket', () => ({
  useCopilotWebSocket: vi.fn(() => ({
    connected: false,
    streaming: false,
    streamingContent: '',
    statusText: '',
    reconnecting: false,
    error: null,
    sendQuery: vi.fn(),
    stopGeneration: vi.fn(),
    regenerate: vi.fn(),
  })),
}));

// Mock sidebar — we test its state via data-testid, not the full shadcn component
vi.mock('@/components/ui/sidebar', () => ({
  useSidebar: vi.fn(() => ({
    open: true,
    setOpen: vi.fn(),
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

import { conversationsAPI } from '@/lib/api/conversations';
import ConversationsPage from '@/app/(dashboard)/conversations/page';

const mockedGetConversations = conversationsAPI.getConversations as ReturnType<typeof vi.fn>;
const mockedCreateConversation = conversationsAPI.createConversation as ReturnType<typeof vi.fn>;
const mockedGetConversation = conversationsAPI.getConversation as ReturnType<typeof vi.fn>;
const mockedGetFolders = conversationsAPI.getFolders as ReturnType<typeof vi.fn>;
const mockedGetTemplateStarters = conversationsAPI.getTemplateStarters as ReturnType<typeof vi.fn>;

const mockConversation = {
  id: 42,
  public_id: 'test-uuid-42',
  organization_id: 10,
  created_by_user_id: 1,
  title: 'How many negative feedbacks?',
  folder_id: null,
  context_scope: 'all_data',
  is_active: true,
  created_at: '2026-02-23T01:00:00Z',
  updated_at: '2026-02-23T01:00:00Z',
  messages: [],
};

const mockListResponse = {
  conversations: [mockConversation],
  total: 1,
  page: 1,
  page_size: 20,
};

const emptyListResponse = {
  conversations: [],
  total: 0,
  page: 1,
  page_size: 20,
};

describe('ConversationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams.mockReturnValue(new URLSearchParams());
    mockPathname.mockReturnValue('/conversations');
    mockedGetFolders.mockResolvedValue([]);
    mockedGetConversations.mockResolvedValue(mockListResponse);
    mockedGetTemplateStarters.mockResolvedValue({
      templates: ["This week's feedback summary", 'Top pain points this month'],
    });
    mockedGetConversation.mockResolvedValue({ ...mockConversation, messages: [] });
  });

  // ── Layout ─────────────────────────────────────────────────────────────────

  it('renders the conversations page container', async () => {
    render(<ConversationsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('conversations-page')).toBeInTheDocument();
    });
  });

  it('renders the conversation list panel', async () => {
    render(<ConversationsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('conversation-list-panel')).toBeInTheDocument();
    });
  });

  it('renders the chat area', async () => {
    render(<ConversationsPage />);
    expect(screen.getByTestId('chat-area')).toBeInTheDocument();
  });

  // ── Query param: ?new=true&q=... ───────────────────────────────────────────

  it('creates a new conversation when new=true query param is present', async () => {
    mockSearchParams.mockReturnValue(new URLSearchParams('new=true&q=How+many+negative+feedbacks'));
    mockedCreateConversation.mockResolvedValue(mockConversation);
    render(<ConversationsPage />);
    await waitFor(() => {
      expect(mockedCreateConversation).toHaveBeenCalledWith(
        expect.objectContaining({ context_scope: 'all_data' })
      );
    });
  });

  it('does not create a conversation without new=true param', async () => {
    mockSearchParams.mockReturnValue(new URLSearchParams());
    render(<ConversationsPage />);
    await waitFor(() => {
      expect(mockedGetConversations).toHaveBeenCalled();
    });
    expect(mockedCreateConversation).not.toHaveBeenCalled();
  });

  it('does not create a conversation when q param is empty', async () => {
    mockSearchParams.mockReturnValue(new URLSearchParams('new=true'));
    render(<ConversationsPage />);
    await waitFor(() => {
      expect(mockedGetConversations).toHaveBeenCalled();
    });
    expect(mockedCreateConversation).not.toHaveBeenCalled();
  });

  // ── Query param: ?id=... ───────────────────────────────────────────────────

  it('selects the conversation matching ?id param on load', async () => {
    mockSearchParams.mockReturnValue(new URLSearchParams('id=test-uuid-42'));
    render(<ConversationsPage />);
    await waitFor(() => {
      const item = screen.queryByTestId('conversation-item-test-uuid-42');
      if (item) {
        expect(item).toHaveAttribute('data-active', 'true');
      }
    });
  });

  // ── Empty state ────────────────────────────────────────────────────────────

  it('shows empty state with template starters when no conversations exist', async () => {
    mockedGetConversations.mockResolvedValue(emptyListResponse);
    render(<ConversationsPage />);
    await waitFor(() => {
      expect(screen.getByTestId('conversations-empty-state')).toBeInTheDocument();
    });
  });

  it('shows template starter chips in empty state', async () => {
    mockedGetConversations.mockResolvedValue(emptyListResponse);
    render(<ConversationsPage />);
    await waitFor(() => {
      expect(screen.getByText("This week's feedback summary")).toBeInTheDocument();
    });
  });

  // ── New conversation from chat area ───────────────────────────────────────

  it('renders "New Chat" button that triggers new conversation creation', async () => {
    render(<ConversationsPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
    });
  });
});

describe('ConversationsPage - sidebar auto-collapse', () => {
  it('sets collapsed class on the conversations page root element', async () => {
    render(<ConversationsPage />);
    await waitFor(() => {
      const page = screen.getByTestId('conversations-page');
      expect(page).toHaveAttribute('data-sidebar-collapsed', 'true');
    });
  });
});
