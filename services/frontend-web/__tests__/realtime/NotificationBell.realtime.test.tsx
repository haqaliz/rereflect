import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mock next/navigation ────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/notifications',
}));

// ─── Mock notifications API ───────────────────────────────────────────────────

vi.mock('@/lib/api/notifications', () => ({
  notificationsAPI: {
    list: vi.fn(),
    getUnreadCount: vi.fn(),
    markRead: vi.fn(),
  },
  TYPE_ICONS: {},
  TYPE_COLORS: {},
}));

// ─── Mock notification-utils ──────────────────────────────────────────────────

vi.mock('@/lib/notification-utils', () => ({
  TYPE_ICONS: {},
  TYPE_COLORS: {},
  timeAgo: vi.fn(() => '5m ago'),
}));

// ─── Mock useRealtimeEvents ───────────────────────────────────────────────────

const mockUseRealtimeEvents = vi.fn();
vi.mock('@/hooks/useRealtimeEvents', () => ({
  useRealtimeEvents: (...args: unknown[]) => {
    mockUseRealtimeEvents(...args);
    return { connected: true, reconnecting: false };
  },
}));

// ─── Imports (after mocks) ────────────────────────────────────────────────────

import { notificationsAPI } from '@/lib/api/notifications';

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('NotificationBell — realtime migration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (notificationsAPI.getUnreadCount as ReturnType<typeof vi.fn>).mockResolvedValue({ count: 3 });
    (notificationsAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 0,
      unread_count: 3,
    });
  });

  // 1. test_no_setinterval_used
  it('test_no_setinterval_used — component does NOT call setInterval', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    const { NotificationBell } = await import('@/components/NotificationBell');
    render(<NotificationBell />);

    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });

  // 2. test_subscribes_to_notification_events
  it('test_subscribes_to_notification_events — useRealtimeEvents called with "notification:count" pattern', async () => {
    const { NotificationBell } = await import('@/components/NotificationBell');
    render(<NotificationBell />);

    expect(mockUseRealtimeEvents).toHaveBeenCalledWith(
      'notification:count',
      expect.any(Function)
    );
  });

  // 3. test_updates_badge_on_notification_count_event
  it('test_updates_badge_on_notification_count_event — push notification:count event → badge updates', async () => {
    let capturedHandler: ((event: unknown) => void) | null = null;

    mockUseRealtimeEvents.mockImplementation((pattern: string, handler: (event: unknown) => void) => {
      if (pattern === 'notification:count') {
        capturedHandler = handler;
      }
      return { connected: true, reconnecting: false };
    });

    const { NotificationBell } = await import('@/components/NotificationBell');
    render(<NotificationBell />);

    // Wait for initial fetch to complete
    await waitFor(() => {
      expect(notificationsAPI.getUnreadCount).toHaveBeenCalled();
    });

    // Simulate receiving a real-time event with unread_count
    const { act } = await import('@testing-library/react');
    act(() => {
      capturedHandler?.({ unread_count: 7 });
    });

    await waitFor(() => {
      expect(screen.getByText('7')).toBeInTheDocument();
    });
  });
});
