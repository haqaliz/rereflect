import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React, { Suspense } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ─── Mock next/navigation ─────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/feedbacks',
  useSearchParams: () => new URLSearchParams(),
}));

// ─── Mock feedback API ────────────────────────────────────────────────────────

vi.mock('@/lib/api/feedback', () => ({
  feedbackAPI: {
    list: vi.fn(),
    analyze: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    bulkDelete: vi.fn(),
    importCSV: vi.fn(),
  },
}));

// ─── Mock analytics ───────────────────────────────────────────────────────────

vi.mock('@/lib/analytics', () => ({
  analytics: {
    csvUploaded: vi.fn(),
  },
}));

// ─── Mock shared components ────────────────────────────────────────────────────

vi.mock('@/components/shared/page-skeletons', () => ({
  FeedbacksPageSkeleton: () => <div data-testid="skeleton">Loading...</div>,
}));

vi.mock('@/components/shared/data-table', () => ({
  DataTable: () => <div data-testid="data-table">Table</div>,
}));

vi.mock('@/app/(dashboard)/feedbacks/columns', () => ({
  createColumns: vi.fn(() => []),
}));

// ─── Mock useRealtimeEvents ───────────────────────────────────────────────────

const mockUseRealtimeEvents = vi.fn();
vi.mock('@/hooks/useRealtimeEvents', () => ({
  useRealtimeEvents: (...args: unknown[]) => {
    mockUseRealtimeEvents(...args);
    return { connected: true, reconnecting: false };
  },
}));

// ─── Mock FeedbackPageContext ─────────────────────────────────────────────────

vi.mock('@/contexts/FeedbackPageContext', () => ({
  FeedbackPageProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useFeedbackPage: () => ({
    searchQuery: '',
    sentimentFilter: '',
    urgentFilter: '',
    churnRiskFilter: '',
    customerEmailFilter: '',
    currentPage: 1,
    setSearchQuery: vi.fn(),
    setSentimentFilter: vi.fn(),
    setUrgentFilter: vi.fn(),
    setChurnRiskFilter: vi.fn(),
    setCustomerEmailFilter: vi.fn(),
    setCurrentPage: vi.fn(),
  }),
}));

// ─── Mock localStorage ────────────────────────────────────────────────────────

vi.stubGlobal('localStorage', {
  getItem: vi.fn(() => 'test-token'),
  setItem: vi.fn(),
  removeItem: vi.fn(),
});

// ─── Imports (after mocks) ────────────────────────────────────────────────────

import { feedbackAPI } from '@/lib/api/feedback';

// ─── Helper ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function Wrapper({ children, qc }: { children: React.ReactNode; qc: QueryClient }) {
  return (
    <QueryClientProvider client={qc}>
      <Suspense fallback={<div>Loading...</div>}>{children}</Suspense>
    </QueryClientProvider>
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('FeedbacksPage — realtime migration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (feedbackAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 0,
      total_pages: 1,
    });
  });

  // 7. test_no_refetch_interval_configured
  it('test_no_refetch_interval_configured — React Query config does NOT have refetchInterval', async () => {
    // Read the source file and verify refetchInterval is not present in the feedback query config
    const fs = await import('fs');
    const path = await import('path');
    const filePath = path.resolve(
      process.cwd(),
      'app/(dashboard)/feedbacks/page.tsx'
    );
    const source = fs.readFileSync(filePath, 'utf-8');

    expect(source).not.toMatch(/refetchInterval\s*:/);
    expect(source).not.toMatch(/refetchIntervalInBackground\s*:/);
  });

  // 8. test_subscribes_to_feedback_events
  it('test_subscribes_to_feedback_events — useRealtimeEvents called with "feedback:*" pattern', async () => {
    const { default: FeedbackPage } = await import('@/app/(dashboard)/feedbacks/page');
    const qc = makeQueryClient();
    render(
      <Wrapper qc={qc}>
        <FeedbackPage />
      </Wrapper>
    );

    await waitFor(() => {
      expect(mockUseRealtimeEvents).toHaveBeenCalledWith(
        'feedback:*',
        expect.any(Function)
      );
    });
  });

  // 9. test_invalidates_feedback_cache_on_event
  it('test_invalidates_feedback_cache_on_event — push feedback:created → invalidateQueries(["feedback"]) called', async () => {
    let capturedHandler: ((event: unknown) => void) | null = null;

    mockUseRealtimeEvents.mockImplementation((pattern: string, handler: (event: unknown) => void) => {
      if (pattern === 'feedback:*') {
        capturedHandler = handler;
      }
      return { connected: true, reconnecting: false };
    });

    const { default: FeedbackPage } = await import('@/app/(dashboard)/feedbacks/page');
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');

    render(
      <Wrapper qc={qc}>
        <FeedbackPage />
      </Wrapper>
    );

    await waitFor(() => {
      expect(capturedHandler).not.toBeNull();
    });

    const { act } = await import('@testing-library/react');
    act(() => {
      capturedHandler?.({ type: 'feedback:created', id: 99 });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['feedback'] })
      );
    });
  });
});
