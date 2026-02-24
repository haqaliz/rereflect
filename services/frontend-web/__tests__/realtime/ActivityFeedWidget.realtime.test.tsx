import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ─── Mock dashboard-v2 API ────────────────────────────────────────────────────

vi.mock('@/lib/api/dashboard-v2', () => ({
  dashboardV2API: {
    getActivityFeed: vi.fn(),
  },
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

import { dashboardV2API } from '@/lib/api/dashboard-v2';

// ─── Helper ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function Wrapper({ children, qc }: { children: React.ReactNode; qc: QueryClient }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ActivityFeedWidget — realtime migration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (dashboardV2API.getActivityFeed as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      last_updated: new Date().toISOString(),
    });
  });

  // 4. test_no_setinterval_used
  it('test_no_setinterval_used — component does NOT call setInterval', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    const { ActivityFeedWidget } = await import(
      '@/components/dashboard/widgets/ActivityFeedWidget'
    );
    const qc = makeQueryClient();
    render(
      <Wrapper qc={qc}>
        <ActivityFeedWidget />
      </Wrapper>
    );

    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });

  // 5. test_subscribes_to_activity_events
  it('test_subscribes_to_activity_events — useRealtimeEvents called with "activity:*" pattern', async () => {
    const { ActivityFeedWidget } = await import(
      '@/components/dashboard/widgets/ActivityFeedWidget'
    );
    const qc = makeQueryClient();
    render(
      <Wrapper qc={qc}>
        <ActivityFeedWidget />
      </Wrapper>
    );

    expect(mockUseRealtimeEvents).toHaveBeenCalledWith(
      'activity:*',
      expect.any(Function)
    );
  });

  // 6. test_invalidates_cache_on_activity_event
  it('test_invalidates_cache_on_activity_event — push activity:new event → queryClient.invalidateQueries called for activity-feed', async () => {
    let capturedHandler: ((event: unknown) => void) | null = null;

    mockUseRealtimeEvents.mockImplementation((pattern: string, handler: (event: unknown) => void) => {
      if (pattern === 'activity:*') {
        capturedHandler = handler;
      }
      return { connected: true, reconnecting: false };
    });

    const { ActivityFeedWidget } = await import(
      '@/components/dashboard/widgets/ActivityFeedWidget'
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    render(
      <Wrapper qc={qc}>
        <ActivityFeedWidget />
      </Wrapper>
    );

    await waitFor(() => {
      expect(capturedHandler).not.toBeNull();
    });

    const { act } = await import('@testing-library/react');
    act(() => {
      capturedHandler?.({ type: 'activity:new', id: 1 });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['activity-feed'] })
      );
    });
  });
});
