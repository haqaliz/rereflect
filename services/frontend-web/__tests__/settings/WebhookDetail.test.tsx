import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/webhooks/1',
  useParams: () => ({ id: '1' }),
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
import WebhookDetailPage from '@/app/(dashboard)/settings/webhooks/[id]/page';

const mockGet = webhooksAPI.get as ReturnType<typeof vi.fn>;
const mockListDeliveries = webhooksAPI.listDeliveries as ReturnType<typeof vi.fn>;
const mockRotateSecret = webhooksAPI.rotateSecret as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const mockWebhook = {
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
};

const mockDeliveries = [
  {
    id: 101,
    event: 'feedback.created',
    feedback_id: 2207,
    status: 'sent' as const,
    attempt: 1,
    response_code: 200,
    response_body: 'OK',
    error_message: null,
    latency_ms: 38,
    created_at: '2026-03-15T12:00:00Z',
  },
  {
    id: 102,
    event: 'feedback.urgent',
    feedback_id: 2208,
    status: 'failed' as const,
    attempt: 1,
    response_code: 500,
    response_body: 'Internal Server Error',
    error_message: 'Receiver returned 500',
    latency_ms: 120,
    created_at: '2026-03-15T13:00:00Z',
  },
];

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('WebhookDetail - configuration tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGet.mockResolvedValue(mockWebhook);
    mockListDeliveries.mockResolvedValue(mockDeliveries);
  });

  it('test_renders_webhook_config_form', async () => {
    render(<WebhookDetailPage />);

    await waitFor(() => {
      // Name field pre-filled
      const nameInput = screen.getByTestId('webhook-name-input');
      expect(nameInput).toBeInTheDocument();
      expect(nameInput).toHaveValue('Slack Bot');
    });

    // URL field pre-filled
    const urlInput = screen.getByTestId('webhook-url-input');
    expect(urlInput).toHaveValue('https://hooks.slack.com/services/T00000/B00000/XXXX');

    // Events checkboxes rendered
    expect(screen.getByText(/feedback created/i)).toBeInTheDocument();
    expect(screen.getByText(/feedback urgent/i)).toBeInTheDocument();

    // Retry mode shown
    expect(screen.getByText(/fire.and.forget/i)).toBeInTheDocument();
  });
});

describe('WebhookDetail - delivery log tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGet.mockResolvedValue(mockWebhook);
    mockListDeliveries.mockResolvedValue(mockDeliveries);
  });

  it('test_delivery_log_tab_shows_deliveries', async () => {
    render(<WebhookDetailPage />);

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /delivery log/i })).toBeInTheDocument();
    });

    // Switch to Delivery Log tab
    fireEvent.click(screen.getByRole('tab', { name: /delivery log/i }));

    await waitFor(() => {
      // Delivery events shown
      expect(screen.getByText(/feedback\.created/)).toBeInTheDocument();
      expect(screen.getByText(/feedback\.urgent/)).toBeInTheDocument();

      // Status badges shown
      expect(screen.getByText(/^sent$/i)).toBeInTheDocument();
      expect(screen.getByText(/^failed$/i)).toBeInTheDocument();

      // Response codes shown
      expect(screen.getByText('200')).toBeInTheDocument();
      expect(screen.getByText('500')).toBeInTheDocument();
    });
  });
});

describe('WebhookDetail - rotate secret', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockGet.mockResolvedValue(mockWebhook);
    mockListDeliveries.mockResolvedValue(mockDeliveries);
    mockRotateSecret.mockResolvedValue({
      ...mockWebhook,
      signing_secret: 'new-secret-abc123xyz',
    });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('test_rotate_secret_shows_new_secret', async () => {
    render(<WebhookDetailPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /rotate secret/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /rotate secret/i }));

    await waitFor(() => {
      expect(mockRotateSecret).toHaveBeenCalledWith(1);
      // New secret displayed
      expect(screen.getByText(/new-secret-abc123xyz/)).toBeInTheDocument();
    });
  });
});
