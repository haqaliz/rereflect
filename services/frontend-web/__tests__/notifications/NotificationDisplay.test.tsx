import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { NotificationItem } from '@/lib/api/notifications';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: '1' }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/notifications',
}));

// Mock useRealtimeEvents (NotificationBell now uses it)
vi.mock('@/hooks/useRealtimeEvents', () => ({
  useRealtimeEvents: vi.fn(() => ({ connected: false, reconnecting: false })),
}));

// Mock notifications API
vi.mock('@/lib/api/notifications', () => ({
  notificationsAPI: {
    list: vi.fn(),
    getById: vi.fn(),
    getUnreadCount: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    dismiss: vi.fn(),
    restore: vi.fn(),
    getPreferences: vi.fn(),
    updatePreferences: vi.fn(),
    getRetention: vi.fn(),
  },
}));

import { notificationsAPI } from '@/lib/api/notifications';

// ---- Shared test data ----

const baseHealthDrop: NotificationItem = {
  id: 1,
  type: 'customer_health_drop',
  title: 'Customer health drop: john@acme.com',
  message: 'Health score dropped from 65 to 42 (moderate → at_risk). Top risk drivers: churn_risk, sentiment.',
  link: '/customers/john%40acme.com',
  is_read: false,
  is_dismissed: false,
  metadata: {
    customer_email: 'john@acme.com',
    customer_name: 'John Smith',
    old_score: 65,
    new_score: 42,
    old_risk_level: 'moderate',
    new_risk_level: 'at_risk',
    is_recovery: false,
    components: { churn_risk: 78, sentiment: 35, resolution: 60, frequency: 45 },
    top_risk_drivers: ['churn_risk', 'sentiment'],
  },
  created_at: new Date().toISOString(),
};

const baseRecovery: NotificationItem = {
  id: 2,
  type: 'customer_health_drop',
  title: 'Customer health improved: jane@corp.com',
  message: 'Health score recovered from 42 to 65 (at_risk → moderate).',
  link: '/customers/jane%40corp.com',
  is_read: false,
  is_dismissed: false,
  metadata: {
    customer_email: 'jane@corp.com',
    customer_name: 'Jane Corp',
    old_score: 42,
    new_score: 65,
    old_risk_level: 'at_risk',
    new_risk_level: 'moderate',
    is_recovery: true,
    components: { churn_risk: 30, sentiment: 70, resolution: 80, frequency: 60 },
    top_risk_drivers: [],
  },
  created_at: new Date().toISOString(),
};

function makeListResponse(items: NotificationItem[]) {
  return { items, total: items.length, unread_count: items.filter(n => !n.is_read).length };
}

// =========================================================
// 1. notification-utils: icon + color for customer_health_drop
// =========================================================
describe('notification-utils: customer_health_drop type', () => {
  it('TYPE_ICONS has an entry for customer_health_drop', async () => {
    const { TYPE_ICONS } = await import('@/lib/notification-utils');
    expect(TYPE_ICONS['customer_health_drop']).toBeDefined();
  });

  it('TYPE_COLORS has a destructive/red color for customer_health_drop', async () => {
    const { TYPE_COLORS } = await import('@/lib/notification-utils');
    expect(TYPE_COLORS['customer_health_drop']).toBeDefined();
    // Should be red/destructive for drops — check it's not a totally unexpected color
    const color = TYPE_COLORS['customer_health_drop'];
    expect(color).toMatch(/destructive|red/);
  });
});

// =========================================================
// 2. Notification List page
// =========================================================
describe('NotificationsPage: customer_health_drop type filter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (notificationsAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeListResponse([baseHealthDrop])
    );
  });

  it('renders a "Health Drop" filter pill in the type filter bar', async () => {
    const { default: NotificationsPage } = await import(
      '@/app/(dashboard)/notifications/page'
    );
    render(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Health Drop')).toBeInTheDocument();
    });
  });

  it('clicking "Health Drop" filter sets filterType to customer_health_drop', async () => {
    const { default: NotificationsPage } = await import(
      '@/app/(dashboard)/notifications/page'
    );
    render(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Health Drop')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Health Drop'));

    await waitFor(() => {
      expect(notificationsAPI.list).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'customer_health_drop' })
      );
    });
  });
});

describe('NotificationsPage: health drop notification renders with red/destructive icon', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (notificationsAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeListResponse([baseHealthDrop])
    );
  });

  it('renders the health drop notification title', async () => {
    const { default: NotificationsPage } = await import(
      '@/app/(dashboard)/notifications/page'
    );
    render(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Customer health drop: john@acme.com')).toBeInTheDocument();
    });
  });

  it('notification icon container has destructive color class for health drop', async () => {
    const { default: NotificationsPage } = await import(
      '@/app/(dashboard)/notifications/page'
    );
    render(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Customer health drop: john@acme.com')).toBeInTheDocument();
    });

    // The icon wrapper div should have a destructive color class
    const iconWrapper = document.querySelector('[data-testid="notif-icon-1"]');
    expect(iconWrapper).toBeInTheDocument();
    expect(iconWrapper?.className).toMatch(/destructive|red/);
  });

  it('clicking health drop notification navigates to /notifications/1', async () => {
    const { default: NotificationsPage } = await import(
      '@/app/(dashboard)/notifications/page'
    );
    render(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Customer health drop: john@acme.com')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Customer health drop: john@acme.com'));
    expect(mockPush).toHaveBeenCalledWith('/notifications/1');
  });
});

describe('NotificationsPage: recovery notification renders with green styling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (notificationsAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeListResponse([baseRecovery])
    );
  });

  it('renders the recovery notification title', async () => {
    const { default: NotificationsPage } = await import(
      '@/app/(dashboard)/notifications/page'
    );
    render(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Customer health improved: jane@corp.com')).toBeInTheDocument();
    });
  });

  it('recovery notification icon container has green color class', async () => {
    const { default: NotificationsPage } = await import(
      '@/app/(dashboard)/notifications/page'
    );
    render(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText('Customer health improved: jane@corp.com')).toBeInTheDocument();
    });

    const iconWrapper = document.querySelector('[data-testid="notif-icon-2"]');
    expect(iconWrapper).toBeInTheDocument();
    expect(iconWrapper?.className).toMatch(/green/);
  });
});

// =========================================================
// 3. Notification Detail page — customer_health_drop metadata
// =========================================================
describe('NotificationDetailPage: customer_health_drop metadata breakdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (notificationsAPI.getById as ReturnType<typeof vi.fn>).mockResolvedValue(baseHealthDrop);
    (notificationsAPI.markRead as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
  });

  it('renders score change text: "65 → 42 (-23)"', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('65 → 42 (-23)')).toBeInTheDocument();
    });
  });

  it('renders risk level badge with "at_risk" text', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      const badge = screen.getByTestId('risk-level-badge');
      expect(badge).toHaveTextContent('at_risk');
    });
  });

  it('risk level badge has orange class for at_risk', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      const badge = screen.getByTestId('risk-level-badge');
      expect(badge).toBeInTheDocument();
      expect(badge.className).toMatch(/orange/);
    });
  });

  it('renders top risk drivers from metadata', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      // Top risk driver badges are rendered as separate <span> elements
      const allChurnRisk = screen.getAllByText(/churn_risk/i);
      expect(allChurnRisk.length).toBeGreaterThanOrEqual(1);
      // At least one should be a span (the badge), not the message paragraph
      const spanBadge = allChurnRisk.find(el => el.tagName === 'SPAN');
      expect(spanBadge).toBeInTheDocument();
    });
  });

  it('renders component breakdown scores', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      // churn_risk component score of 78 should be visible
      expect(screen.getByTestId('component-churn_risk')).toBeInTheDocument();
    });
  });

  it('renders "View Customer" link navigating to /customers/{encoded_email}', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      const viewBtn = screen.getByTestId('view-customer-link');
      expect(viewBtn).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('view-customer-link'));
    expect(mockPush).toHaveBeenCalledWith('/customers/john%40acme.com');
  });
});

describe('NotificationDetailPage: recovery notification metadata', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (notificationsAPI.getById as ReturnType<typeof vi.fn>).mockResolvedValue(baseRecovery);
    (notificationsAPI.markRead as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
  });

  it('renders positive score change for recovery: "42 → 65 (+23)"', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('42 → 65 (+23)')).toBeInTheDocument();
    });
  });

  it('risk level badge has yellow class for moderate risk level', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      const badge = screen.getByTestId('risk-level-badge');
      expect(badge.className).toMatch(/yellow/);
    });
  });
});

describe('NotificationDetailPage: TYPE_LABELS includes customer_health_drop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (notificationsAPI.getById as ReturnType<typeof vi.fn>).mockResolvedValue(baseHealthDrop);
    (notificationsAPI.markRead as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
  });

  it('shows "Customer Health Drop" type label in detail header', async () => {
    const { default: NotificationDetailPage } = await import(
      '@/app/(dashboard)/notifications/[id]/page'
    );
    render(<NotificationDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('Customer Health Drop')).toBeInTheDocument();
    });
  });
});

// =========================================================
// 4. NotificationBell popover — health drop icon rendered
// =========================================================
describe('NotificationBell: health drop notification in popover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (notificationsAPI.getUnreadCount as ReturnType<typeof vi.fn>).mockResolvedValue({ count: 1 });
    (notificationsAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeListResponse([baseHealthDrop])
    );
  });

  it('renders health drop notification title in bell popover', async () => {
    const { NotificationBell } = await import('@/components/NotificationBell');
    render(<NotificationBell />);

    // Open popover
    const bellBtn = screen.getByRole('button', { name: /notifications/i });
    fireEvent.click(bellBtn);

    await waitFor(() => {
      expect(screen.getByText('Customer health drop: john@acme.com')).toBeInTheDocument();
    });
  });

  it('bell popover health drop notification icon wrapper has data-testid with notif id', async () => {
    const { NotificationBell } = await import('@/components/NotificationBell');
    render(<NotificationBell />);

    const bellBtn = screen.getByRole('button', { name: /notifications/i });
    fireEvent.click(bellBtn);

    await waitFor(() => {
      const iconWrapper = document.querySelector('[data-testid="popover-notif-icon-1"]');
      expect(iconWrapper).toBeInTheDocument();
      expect(iconWrapper?.className).toMatch(/destructive|red/);
    });
  });
});
