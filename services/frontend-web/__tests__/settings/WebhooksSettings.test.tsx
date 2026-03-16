import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/webhooks',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/webhooks', () => ({
  webhooksAPI: {
    list: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    test: vi.fn(),
    rotateSecret: vi.fn(),
    listDeliveries: vi.fn(),
  },
  WEBHOOK_EVENTS: [
    { id: 'feedback.created', label: 'Feedback Created' },
    { id: 'feedback.analyzed', label: 'Feedback Analyzed' },
    { id: 'feedback.status_changed', label: 'Status Changed' },
    { id: 'feedback.urgent', label: 'Feedback Urgent' },
    { id: 'feedback.category_match', label: 'Category Match' },
  ],
  PLAN_WEBHOOK_LIMITS: {
    free: 2,
    pro: 5,
    business: 10,
    enterprise: null,
  },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { webhooksAPI } from '@/lib/api/webhooks';
import WebhooksPage from '@/app/(dashboard)/settings/webhooks/page';

const mockList = webhooksAPI.list as ReturnType<typeof vi.fn>;
const mockTest = webhooksAPI.test as ReturnType<typeof vi.fn>;
const mockDelete = webhooksAPI.delete as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const mockWebhooks = [
  {
    id: 1,
    name: 'Slack Bot',
    url: 'https://hooks.slack.com/services/T00000/B00000/XXXX',
    events: ['feedback.created', 'feedback.urgent'],
    category_filters: [],
    retry_mode: 'fire_and_forget' as const,
    is_active: true,
    consecutive_failures: 0,
    custom_headers: {},
    created_at: '2026-03-10T10:00:00Z',
    updated_at: '2026-03-10T10:00:00Z',
  },
  {
    id: 2,
    name: 'Internal Dashboard',
    url: 'https://internal.example.com/webhook',
    events: ['feedback.analyzed', 'feedback.status_changed', 'feedback.category_match'],
    category_filters: ['billing'],
    retry_mode: 'exponential_backoff' as const,
    is_active: false,
    consecutive_failures: 3,
    custom_headers: { Authorization: 'Bearer token123' },
    created_at: '2026-03-12T08:00:00Z',
    updated_at: '2026-03-14T15:00:00Z',
  },
];

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('WebhooksSettings - empty state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockList.mockResolvedValue([]);
  });

  it('test_renders_empty_state_when_no_webhooks', async () => {
    render(<WebhooksPage />);
    await waitFor(() => {
      expect(screen.getByText(/no webhooks/i)).toBeInTheDocument();
    });
    // Add Webhook button visible
    expect(screen.getByRole('button', { name: /add webhook/i })).toBeInTheDocument();
  });
});

describe('WebhooksSettings - list rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockList.mockResolvedValue(mockWebhooks);
  });

  it('test_renders_webhook_list', async () => {
    render(<WebhooksPage />);

    await waitFor(() => {
      expect(screen.getByText('Slack Bot')).toBeInTheDocument();
    });

    // Webhook names
    expect(screen.getByText('Internal Dashboard')).toBeInTheDocument();

    // URL shown (possibly truncated)
    expect(screen.getByText(/hooks\.slack\.com/)).toBeInTheDocument();

    // Events badges — first webhook has 2 events so both should show
    expect(screen.getByText(/feedback\.created/i)).toBeInTheDocument();
    expect(screen.getByText(/feedback\.urgent/i)).toBeInTheDocument();

    // Status badge: Slack Bot is active
    const activeBadges = screen.getAllByText(/active/i);
    expect(activeBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('test_plan_limit_indicator', async () => {
    render(<WebhooksPage />);

    await waitFor(() => {
      // 2 webhooks out of 5 pro limit
      expect(screen.getByText(/2\/5/)).toBeInTheDocument();
    });
  });
});

describe('WebhooksSettings - add button at plan limit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Pro plan allows 5 webhooks — fill to limit
    const fiveWebhooks = Array.from({ length: 5 }, (_, i) => ({
      ...mockWebhooks[0],
      id: i + 1,
      name: `Webhook ${i + 1}`,
    }));
    mockUseAuth.mockReturnValue({ user: adminUser }); // pro plan
    mockList.mockResolvedValue(fiveWebhooks);
  });

  it('test_add_button_disabled_at_plan_limit', async () => {
    render(<WebhooksPage />);

    await waitFor(() => {
      const addBtn = screen.getByRole('button', { name: /add webhook/i });
      expect(addBtn).toBeDisabled();
    });
  });
});

describe('WebhooksSettings - delete webhook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockList.mockResolvedValue(mockWebhooks);
    mockDelete.mockResolvedValue(undefined);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('test_delete_webhook', async () => {
    render(<WebhooksPage />);

    await waitFor(() => {
      expect(screen.getByText('Slack Bot')).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith(1);
    });
  });
});

describe('WebhooksSettings - test button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockList.mockResolvedValue(mockWebhooks);
    mockTest.mockResolvedValue({
      success: true,
      response_code: 200,
      response_body: 'OK',
      latency_ms: 42,
    });
  });

  it('test_test_button_sends_test_delivery', async () => {
    render(<WebhooksPage />);

    await waitFor(() => {
      expect(screen.getByText('Slack Bot')).toBeInTheDocument();
    });

    const testButtons = screen.getAllByRole('button', { name: /^test$/i });
    fireEvent.click(testButtons[0]);

    await waitFor(() => {
      expect(mockTest).toHaveBeenCalledWith(1);
    });
  });
});
