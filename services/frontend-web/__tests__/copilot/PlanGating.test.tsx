import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

vi.mock('@/lib/api/copilot', () => ({
  copilotAPI: {
    getCopilotUsage: vi.fn(),
    getSuggestions: vi.fn(),
  },
}));

vi.mock('@/lib/api/conversations', () => ({
  conversationsAPI: {
    getConversation: vi.fn(),
    getConversations: vi.fn(),
    getCopilotUsage: vi.fn(),
  },
}));

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

import { copilotAPI } from '@/lib/api/copilot';
import { conversationsAPI } from '@/lib/api/conversations';
import { CommandBar } from '@/components/copilot/CommandBar';
import { ChatArea } from '@/components/copilot/ChatArea';
import { UpgradeCTA } from '@/components/copilot/UpgradeCTA';

const mockedGetUsage = copilotAPI.getCopilotUsage as ReturnType<typeof vi.fn>;
const mockedGetConversation = conversationsAPI.getConversation as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const freeUser = {
  id: 1, email: 'free@test.com', role: 'member', plan: 'free', organization_id: 1,
};

const proUser = {
  id: 2, email: 'pro@test.com', role: 'admin', plan: 'pro', organization_id: 1,
};

const freeUsageUnderLimit = {
  queries_today: 7,
  daily_limit: 10,
  plan: 'free',
  tokens_used_month: 5_000,
  tokens_budget_month: null,
  plan_tier: 'free',
  days_remaining_in_billing_cycle: 14,
};

const freeUsageAtLimit = {
  ...freeUsageUnderLimit,
  queries_today: 10,
};

const proUsage = {
  queries_today: 42,
  daily_limit: null,
  plan: 'pro',
  tokens_used_month: 120_000,
  tokens_budget_month: 500_000,
  plan_tier: 'pro',
  days_remaining_in_billing_cycle: 14,
};

const proUsageBudgetExceeded = {
  ...proUsage,
  tokens_used_month: 500_000,
  tokens_budget_month: 500_000,
};

const mockConversation = {
  id: 1, organization_id: 1, created_by_user_id: 1, title: 'Test',
  folder_id: null, context_scope: 'all_data', is_active: true,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  messages: [],
};

// ─── CommandBar plan gating tests ─────────────────────────────────────────────

describe('CommandBar — plan gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (copilotAPI.getSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({ suggestions: [] });
  });

  it('shows remaining queries for free tier under limit', async () => {
    mockUseAuth.mockReturnValue({ user: freeUser });
    mockedGetUsage.mockResolvedValue(freeUsageUnderLimit);
    render(<CommandBar open={true} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('queries-remaining')).toBeInTheDocument();
      expect(screen.getByTestId('queries-remaining')).toHaveTextContent('3/10 remaining today');
    });
  });

  it('disables input and shows upgrade CTA when free tier limit reached', async () => {
    mockUseAuth.mockReturnValue({ user: freeUser });
    mockedGetUsage.mockResolvedValue(freeUsageAtLimit);
    render(<CommandBar open={true} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('upgrade-cta')).toBeInTheDocument();
    });
    const input = screen.getByRole('textbox');
    expect(input).toBeDisabled();
  });

  it('shows "Upgrade to Pro" link in upgrade CTA', async () => {
    mockUseAuth.mockReturnValue({ user: freeUser });
    mockedGetUsage.mockResolvedValue(freeUsageAtLimit);
    render(<CommandBar open={true} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText(/upgrade to pro/i)).toBeInTheDocument();
    });
  });

  it('does not show remaining queries for Pro tier', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    mockedGetUsage.mockResolvedValue(proUsage);
    render(<CommandBar open={true} onClose={vi.fn()} />);
    await waitFor(() => {
      expect(mockedGetUsage).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('queries-remaining')).not.toBeInTheDocument();
    expect(screen.queryByTestId('upgrade-cta')).not.toBeInTheDocument();
  });

  it('does not show any gating UI when usage is not yet loaded', () => {
    mockUseAuth.mockReturnValue({ user: freeUser });
    mockedGetUsage.mockReturnValue(new Promise(() => {})); // never resolves
    render(<CommandBar open={true} onClose={vi.fn()} />);
    expect(screen.queryByTestId('queries-remaining')).not.toBeInTheDocument();
    expect(screen.queryByTestId('upgrade-cta')).not.toBeInTheDocument();
  });
});

// ─── ChatArea token budget tests ───────────────────────────────────────────────

describe('ChatArea — token budget gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetConversation.mockResolvedValue(mockConversation);
  });

  it('shows token budget exceeded banner when budget is used up', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    (conversationsAPI.getCopilotUsage as ReturnType<typeof vi.fn>).mockResolvedValue(proUsageBudgetExceeded);
    render(<ChatArea conversationId={1} copilotUsage={proUsageBudgetExceeded} />);
    await waitFor(() => {
      expect(screen.getByTestId('token-budget-banner')).toBeInTheDocument();
    });
  });

  it('disables chat input when token budget is exceeded', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    render(<ChatArea conversationId={1} copilotUsage={proUsageBudgetExceeded} />);
    await waitFor(() => {
      expect(screen.getByTestId('chat-input')).toBeDisabled();
    });
  });

  it('does not show budget banner when usage is within budget', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    render(<ChatArea conversationId={1} copilotUsage={proUsage} />);
    await waitFor(() => {
      expect(screen.getByTestId('chat-input')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('token-budget-banner')).not.toBeInTheDocument();
  });

  it('does not disable input when no budget cap (free tier or unlimited)', async () => {
    mockUseAuth.mockReturnValue({ user: freeUser });
    render(<ChatArea conversationId={1} copilotUsage={freeUsageUnderLimit} />);
    await waitFor(() => {
      expect(screen.getByTestId('chat-input')).not.toBeDisabled();
    });
  });
});

// ─── UpgradeCTA component ──────────────────────────────────────────────────────

describe('UpgradeCTA', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: freeUser });
  });

  it('renders the upgrade CTA with a message', () => {
    render(<UpgradeCTA message="Upgrade to unlock unlimited queries" variant="inline" />);
    expect(screen.getByTestId('upgrade-cta-component')).toBeInTheDocument();
    expect(screen.getByText('Upgrade to unlock unlimited queries')).toBeInTheDocument();
  });

  it('renders an Upgrade button linking to /settings/billing', () => {
    render(<UpgradeCTA message="Upgrade for more" variant="inline" />);
    const btn = screen.getByRole('button', { name: /upgrade/i });
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(mockPush).toHaveBeenCalledWith('/settings/billing');
  });

  it('renders banner variant with distinct styling', () => {
    render(<UpgradeCTA message="Monthly token budget reached" variant="banner" />);
    const el = screen.getByTestId('upgrade-cta-component');
    expect(el).toHaveAttribute('data-variant', 'banner');
  });

  it('renders inline variant', () => {
    render(<UpgradeCTA message="Inline message" variant="inline" />);
    const el = screen.getByTestId('upgrade-cta-component');
    expect(el).toHaveAttribute('data-variant', 'inline');
  });
});

// ─── Usage stats display ───────────────────────────────────────────────────────

describe('Copilot usage stats in AISettingsUsage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders copilot usage section with token progress bar', async () => {
    // Import lazily to avoid circular mock issues
    const { CopilotUsageSection } = await import('@/components/copilot/CopilotUsageSection');
    render(<CopilotUsageSection usage={proUsage} />);
    expect(screen.getByTestId('copilot-token-bar')).toBeInTheDocument();
  });

  it('renders tokens used out of budget', async () => {
    const { CopilotUsageSection } = await import('@/components/copilot/CopilotUsageSection');
    render(<CopilotUsageSection usage={proUsage} />);
    expect(screen.getByTestId('copilot-tokens-text')).toHaveTextContent('120,000 / 500,000');
  });

  it('renders queries today count', async () => {
    const { CopilotUsageSection } = await import('@/components/copilot/CopilotUsageSection');
    render(<CopilotUsageSection usage={proUsage} />);
    expect(screen.getByTestId('copilot-queries-today')).toHaveTextContent('42');
  });

  it('shows daily limit for free tier', async () => {
    const { CopilotUsageSection } = await import('@/components/copilot/CopilotUsageSection');
    render(<CopilotUsageSection usage={freeUsageUnderLimit} />);
    expect(screen.getByTestId('copilot-queries-today')).toHaveTextContent('7/10');
  });

  it('renders no token bar when budget is null (free tier)', async () => {
    const { CopilotUsageSection } = await import('@/components/copilot/CopilotUsageSection');
    render(<CopilotUsageSection usage={freeUsageUnderLimit} />);
    expect(screen.queryByTestId('copilot-token-bar')).not.toBeInTheDocument();
  });
});
