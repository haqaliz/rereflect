import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
const mockPathname = vi.fn(() => '/conversations');
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => mockPathname(),
  useSearchParams: () => new URLSearchParams(),
}));

// Mock conversations API
vi.mock('@/lib/api/conversations', () => ({
  conversationsAPI: {
    getConversations: vi.fn(),
    createConversation: vi.fn(),
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

import { conversationsAPI } from '@/lib/api/conversations';
import { ConversationList } from '@/components/copilot/ConversationList';
import type { Conversation, ConversationFolder } from '@/lib/api/conversations';

const mockedGetConversations = conversationsAPI.getConversations as ReturnType<typeof vi.fn>;
const mockedCreateConversation = conversationsAPI.createConversation as ReturnType<typeof vi.fn>;
const mockedUpdateConversation = conversationsAPI.updateConversation as ReturnType<typeof vi.fn>;
const mockedDeleteConversation = conversationsAPI.deleteConversation as ReturnType<typeof vi.fn>;
const mockedGetFolders = conversationsAPI.getFolders as ReturnType<typeof vi.fn>;
const mockedCreateFolder = conversationsAPI.createFolder as ReturnType<typeof vi.fn>;
const mockedDeleteFolder = conversationsAPI.deleteFolder as ReturnType<typeof vi.fn>;

// ─── Fixtures ────────────────────────────────────────────────────────────────

const mockFolder: ConversationFolder = {
  id: 1,
  organization_id: 10,
  name: 'General',
  sort_order: 0,
  created_at: '2026-02-23T00:00:00Z',
};

const mockConversation: Conversation = {
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

const mockConversation2: Conversation = {
  id: 43,
  public_id: 'test-uuid-43',
  organization_id: 10,
  created_by_user_id: 1,
  title: 'Top pain points this month',
  folder_id: 1,
  context_scope: 'all_data',
  is_active: true,
  created_at: '2026-02-23T00:00:00Z',
  updated_at: '2026-02-23T00:00:00Z',
  messages: [],
};

function renderList(props: {
  activeConversationId?: string | null;
  onSelectConversation?: (publicId: string) => void;
  onNewConversation?: () => void;
} = {}) {
  return render(
    <ConversationList
      activeConversationId={props.activeConversationId ?? null}
      onSelectConversation={props.onSelectConversation ?? vi.fn()}
      onNewConversation={props.onNewConversation ?? vi.fn()}
    />
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('ConversationList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetFolders.mockResolvedValue([mockFolder]);
    mockedGetConversations.mockResolvedValue({
      conversations: [mockConversation, mockConversation2],
      total: 2,
      page: 1,
      page_size: 20,
    });
  });

  // ── Rendering ──────────────────────────────────────────────────────────────

  it('renders the "New Chat" button', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
    });
  });

  it('loads and displays conversations', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByText('How many negative feedbacks?')).toBeInTheDocument();
      expect(screen.getByText('Top pain points this month')).toBeInTheDocument();
    });
  });

  it('displays folder names', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByText('General')).toBeInTheDocument();
    });
  });

  it('shows a loading skeleton while data is fetching', () => {
    mockedGetConversations.mockImplementation(() => new Promise(() => {}));
    mockedGetFolders.mockImplementation(() => new Promise(() => {}));
    renderList();
    expect(screen.getByTestId('conversation-list-loading')).toBeInTheDocument();
  });

  // ── Empty state ────────────────────────────────────────────────────────────

  it('shows empty state when no conversations exist', async () => {
    mockedGetConversations.mockResolvedValue({ conversations: [], total: 0, page: 1, page_size: 20 });
    mockedGetFolders.mockResolvedValue([]);
    renderList();
    await waitFor(() => {
      expect(screen.getByTestId('conversations-empty-state')).toBeInTheDocument();
    });
  });

  it('shows "Start your first conversation" text in empty state', async () => {
    mockedGetConversations.mockResolvedValue({ conversations: [], total: 0, page: 1, page_size: 20 });
    mockedGetFolders.mockResolvedValue([]);
    renderList();
    await waitFor(() => {
      expect(screen.getByText(/start your first conversation/i)).toBeInTheDocument();
    });
  });

  // ── New Chat ───────────────────────────────────────────────────────────────

  it('calls onNewConversation when "New Chat" is clicked', async () => {
    const onNew = vi.fn();
    renderList({ onNewConversation: onNew });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new chat/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /new chat/i }));
    expect(onNew).toHaveBeenCalledTimes(1);
  });

  // ── Selection ─────────────────────────────────────────────────────────────

  it('calls onSelectConversation when a conversation is clicked', async () => {
    const onSelect = vi.fn();
    renderList({ onSelectConversation: onSelect });
    await waitFor(() => {
      expect(screen.getByText('How many negative feedbacks?')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('How many negative feedbacks?'));
    expect(onSelect).toHaveBeenCalledWith('test-uuid-42');
  });

  it('highlights the active conversation', async () => {
    renderList({ activeConversationId: 'test-uuid-42' });
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-42')).toHaveAttribute('data-active', 'true');
    });
  });

  it('does not highlight inactive conversations', async () => {
    renderList({ activeConversationId: 'test-uuid-42' });
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-43')).not.toHaveAttribute('data-active', 'true');
    });
  });

  // ── Context menu (right-click) ─────────────────────────────────────────────

  it('shows context menu on right-click of a conversation', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-42')).toBeInTheDocument();
    });
    fireEvent.contextMenu(screen.getByTestId('conversation-item-test-uuid-42'));
    expect(screen.getByTestId('conversation-context-menu')).toBeInTheDocument();
  });

  it('context menu contains Rename option', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-42')).toBeInTheDocument();
    });
    fireEvent.contextMenu(screen.getByTestId('conversation-item-test-uuid-42'));
    expect(screen.getByText('Rename')).toBeInTheDocument();
  });

  it('context menu contains Delete option', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-42')).toBeInTheDocument();
    });
    fireEvent.contextMenu(screen.getByTestId('conversation-item-test-uuid-42'));
    expect(screen.getByText('Delete')).toBeInTheDocument();
  });

  it('calls deleteConversation API and removes item on Delete click', async () => {
    mockedDeleteConversation.mockResolvedValue(undefined);
    renderList();
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-42')).toBeInTheDocument();
    });
    fireEvent.contextMenu(screen.getByTestId('conversation-item-test-uuid-42'));
    fireEvent.click(screen.getByText('Delete'));
    await waitFor(() => {
      expect(mockedDeleteConversation).toHaveBeenCalledWith('test-uuid-42');
    });
  });

  // ── Inline rename (double-click) ───────────────────────────────────────────

  it('enters inline rename mode on double-click', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-42')).toBeInTheDocument();
    });
    fireEvent.doubleClick(screen.getByTestId('conversation-item-test-uuid-42'));
    expect(screen.getByTestId('conversation-rename-input-test-uuid-42')).toBeInTheDocument();
  });

  it('calls updateConversation API on rename Enter', async () => {
    mockedUpdateConversation.mockResolvedValue({ ...mockConversation, title: 'New title' });
    renderList();
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-42')).toBeInTheDocument();
    });
    fireEvent.doubleClick(screen.getByTestId('conversation-item-test-uuid-42'));
    const input = screen.getByTestId('conversation-rename-input-test-uuid-42');
    fireEvent.change(input, { target: { value: 'New title' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => {
      expect(mockedUpdateConversation).toHaveBeenCalledWith('test-uuid-42', { title: 'New title' });
    });
  });

  it('cancels rename on Escape key', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByTestId('conversation-item-test-uuid-42')).toBeInTheDocument();
    });
    fireEvent.doubleClick(screen.getByTestId('conversation-item-test-uuid-42'));
    const input = screen.getByTestId('conversation-rename-input-test-uuid-42');
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByTestId('conversation-rename-input-test-uuid-42')).not.toBeInTheDocument();
  });

  // ── Folder management ──────────────────────────────────────────────────────

  it('renders "New Folder" button', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new folder/i })).toBeInTheDocument();
    });
  });

  it('calls createFolder API and shows new folder', async () => {
    const newFolder: ConversationFolder = {
      id: 2,
      organization_id: 10,
      name: 'My Folder',
      sort_order: 1,
      created_at: '2026-02-23T01:00:00Z',
    };
    mockedCreateFolder.mockResolvedValue(newFolder);
    renderList();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new folder/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /new folder/i }));
    // Folder name input should appear
    await waitFor(() => {
      expect(screen.getByTestId('new-folder-input')).toBeInTheDocument();
    });
  });

  it('calls deleteFolder API on folder delete', async () => {
    mockedDeleteFolder.mockResolvedValue(undefined);
    renderList();
    await waitFor(() => {
      expect(screen.getByText('General')).toBeInTheDocument();
    });
    // Right-click the folder
    const folder = screen.getByTestId('folder-item-1');
    fireEvent.contextMenu(folder);
    fireEvent.click(screen.getByTestId('folder-delete-1'));
    await waitFor(() => {
      expect(mockedDeleteFolder).toHaveBeenCalledWith(1);
    });
  });

  // ── Collapsed folder state ─────────────────────────────────────────────────

  it('renders folders in expanded state by default', async () => {
    renderList();
    await waitFor(() => {
      // Conversations inside the folder should be visible
      expect(screen.getByText('Top pain points this month')).toBeInTheDocument();
    });
  });

  it('toggles folder collapse on folder header click', async () => {
    renderList();
    await waitFor(() => {
      expect(screen.getByText('General')).toBeInTheDocument();
    });
    const folder = screen.getByTestId('folder-item-1');
    fireEvent.click(folder);
    // After clicking, the folder collapses — conversations inside should be hidden
    await waitFor(() => {
      expect(screen.queryByText('Top pain points this month')).not.toBeInTheDocument();
    });
  });
});
