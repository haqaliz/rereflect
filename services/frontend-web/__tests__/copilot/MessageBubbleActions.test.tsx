/**
 * TDD tests for the copilot suggested-actions UI (frontend-actions-ui,
 * Phase G): the tag-confirm dialog, the execute call, and the honest
 * outcome display on MessageBubble.
 *
 * The golden fixture (copilot_actions_item.json) is read across from the
 * backend suite, mirroring actionsContract.test.tsx — one fixture, read
 * twice, so the two ends cannot drift.
 */

import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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

const mockExecute = vi.fn();
vi.mock('@/lib/api/copilot-actions', () => ({
  executeCopilotAction: (...args: unknown[]) => mockExecute(...args),
}));

// ─── WebSocket hook mock (threading test) ────────────────────────────────────

const mockSendQuery = vi.fn();
const mockStopGeneration = vi.fn();
const mockRegenerate = vi.fn();
let wsOnMessage: ((msg: unknown) => void) | null = null;

vi.mock('@/hooks/useCopilotWebSocket', () => ({
  useCopilotWebSocket: vi.fn((options?: { onMessage?: (msg: unknown) => void }) => {
    if (options?.onMessage) {
      wsOnMessage = options.onMessage;
    }
    return {
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
  }),
}));

vi.mock('@/lib/api/conversations', () => ({
  conversationsAPI: {
    getConversation: vi.fn(),
  },
}));

// ─── Imports after mocks ──────────────────────────────────────────────────────

import { toast } from 'sonner';
import { conversationsAPI } from '@/lib/api/conversations';
import { MessageBubble } from '@/components/copilot/MessageBubble';
import { ChatArea } from '@/components/copilot/ChatArea';
import type { ChatMessage } from '@/components/copilot/ChatArea';

// ─── Fixture ──────────────────────────────────────────────────────────────────

// __tests__/copilot/ -> frontend-web/ -> services/
const FIXTURE = path.resolve(
  __dirname, '../../../backend-api/tests/fixtures/copilot_actions_item.json',
);
const goldenActionsItem = JSON.parse(fs.readFileSync(FIXTURE, 'utf-8'));

const PROPOSAL_ID = goldenActionsItem.data.proposal_id as string;
const ACTION_LABEL = goldenActionsItem.data.actions[0].label as string;

function actionsMessage(): ChatMessage {
  return {
    id: 'actions-msg',
    role: 'assistant',
    content: 'Here is what I found:',
    structured_data: [goldenActionsItem] as unknown as ChatMessage['structured_data'],
    created_at: new Date().toISOString(),
  };
}

const ownerUser = {
  id: 1,
  email: 'owner@test.com',
  organization_id: 1,
  role: 'owner',
  plan: 'enterprise',
  is_system_admin: false,
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('MessageBubble — suggested actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockExecute.mockResolvedValue({ matched: 3, updated: 2, skipped: 1, errors: [] });
  });

  it('renders one button per action from the golden fixture', () => {
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);
    expect(screen.getAllByRole('button', { name: ACTION_LABEL })).toHaveLength(1);
  });

  it('hides the action entirely for members (cosmetic; server enforces)', () => {
    mockUseAuth.mockReturnValue({ user: { ...ownerUser, role: 'member' } });
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);
    expect(screen.queryByRole('button', { name: ACTION_LABEL })).not.toBeInTheDocument();
  });

  it('disables the action button when no conversationId is available', () => {
    render(<MessageBubble message={actionsMessage()} />);
    expect(screen.getByRole('button', { name: ACTION_LABEL })).toBeDisabled();
  });

  it('opens the tag dialog on click and makes NO execute call before confirm', async () => {
    const user = userEvent.setup();
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);

    await user.click(screen.getByRole('button', { name: ACTION_LABEL }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('refuses an empty or whitespace tag client-side without a network call', async () => {
    const user = userEvent.setup();
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);

    await user.click(screen.getByRole('button', { name: ACTION_LABEL }));
    const confirm = screen.getByTestId('copilot-action-confirm');
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText('Tag name'), '   ');
    expect(confirm).toBeDisabled();
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('executes once with (conversationId, proposalId, action, {tag}) on confirm', async () => {
    const user = userEvent.setup();
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);

    await user.click(screen.getByRole('button', { name: ACTION_LABEL }));
    await user.type(screen.getByLabelText('Tag name'), 'vip-customers');
    await user.click(screen.getByTestId('copilot-action-confirm'));

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledTimes(1);
      expect(mockExecute).toHaveBeenCalledWith(42, PROPOSAL_ID, 'tag_customers', { tag: 'vip-customers' });
    });
  });

  it('renders matched/updated/skipped and errors[] inline under the button', async () => {
    mockExecute.mockResolvedValue({
      matched: 3,
      updated: 1,
      skipped: 2,
      errors: ['ada@example.com: tag cap of 20 reached'],
    });
    const user = userEvent.setup();
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);

    await user.click(screen.getByRole('button', { name: ACTION_LABEL }));
    await user.type(screen.getByLabelText('Tag name'), 'vip');
    await user.click(screen.getByTestId('copilot-action-confirm'));

    const outcome = await screen.findByTestId('copilot-action-outcome');
    expect(outcome).toHaveTextContent('3 matched');
    expect(outcome).toHaveTextContent('1 updated');
    expect(outcome).toHaveTextContent('2 skipped');
    expect(outcome).toHaveTextContent('ada@example.com: tag cap of 20 reached');
    expect(toast.success).toHaveBeenCalled();
  });

  it('surfaces a failed execution inline and leaves the button re-clickable', async () => {
    mockExecute.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);

    await user.click(screen.getByRole('button', { name: ACTION_LABEL }));
    await user.type(screen.getByLabelText('Tag name'), 'vip');
    await user.click(screen.getByTestId('copilot-action-confirm'));

    const error = await screen.findByTestId('copilot-action-error');
    expect(error).toHaveTextContent('Failed to apply the tag');
    expect(toast.error).toHaveBeenCalled();

    // Button is still clickable — clicking again reopens the dialog.
    await user.click(screen.getByRole('button', { name: ACTION_LABEL }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.click(screen.getByTestId('copilot-action-confirm'));
    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledTimes(2);
    });
  });

  it('shows a clear admin/owner message on a 403', async () => {
    mockExecute.mockRejectedValue({
      response: { status: 403 },
      message: 'Request failed with status code 403',
    });
    const user = userEvent.setup();
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);

    await user.click(screen.getByRole('button', { name: ACTION_LABEL }));
    await user.type(screen.getByLabelText('Tag name'), 'vip');
    await user.click(screen.getByTestId('copilot-action-confirm'));

    const error = await screen.findByTestId('copilot-action-error');
    expect(error).toHaveTextContent('requires an admin or owner role');
  });

  it('marks the button executed after success and cannot re-fire', async () => {
    const user = userEvent.setup();
    render(<MessageBubble message={actionsMessage()} conversationId={42} />);

    await user.click(screen.getByRole('button', { name: ACTION_LABEL }));
    await user.type(screen.getByLabelText('Tag name'), 'vip');
    await user.click(screen.getByTestId('copilot-action-confirm'));

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledTimes(1);
    });

    const button = screen.getByRole('button', { name: ACTION_LABEL });
    await waitFor(() => {
      expect(button).toBeDisabled();
    });
    fireEvent.click(button);
    expect(mockExecute).toHaveBeenCalledTimes(1);
  });
});

describe('MessageBubble — suggested actions threaded through ChatArea', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: ownerUser });
    mockExecute.mockResolvedValue({ matched: 3, updated: 0, skipped: 0, errors: [] });
    wsOnMessage = null;
    (conversationsAPI.getConversation as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 42,
      public_id: 'test-uuid-42',
      organization_id: 1,
      created_by_user_id: 1,
      title: 'Threaded conversation',
      folder_id: null,
      context_scope: 'all_data',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      messages: [],
    });
  });

  it('executes with the numeric conversation id after a WS actions message renders', async () => {
    const user = userEvent.setup();
    render(<ChatArea conversationId={'test-uuid-42'} />);

    await waitFor(() => {
      expect(screen.getByTestId('chat-input')).toBeInTheDocument();
    });

    // WS turn: assistant message, then its structured actions item.
    act(() => {
      wsOnMessage!({
        type: 'assistant_message',
        message_id: 'uuid-301',
        content: 'Here is what I found:',
      });
    });
    act(() => {
      wsOnMessage!({
        type: 'structured_data',
        message_id: 'uuid-301',
        data: [goldenActionsItem],
      });
    });

    const actionButton = await screen.findByRole('button', { name: ACTION_LABEL });
    await user.click(actionButton);
    await user.type(screen.getByLabelText('Tag name'), 'vip');
    await user.click(screen.getByTestId('copilot-action-confirm'));

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledWith(42, PROPOSAL_ID, 'tag_customers', { tag: 'vip' });
    });
  });
});