import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React, { Suspense } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const router = { push: vi.fn(), replace: vi.fn() };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/feedbacks',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ category: 'billing' }),
}));

const authMock = vi.hoisted(() => ({ role: 'member' as string }));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'u@t.c', role: authMock.role, plan: 'free', organization_id: 1, is_system_admin: false },
    isLoading: false,
    isAuthenticated: true,
  }),
}));

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
vi.mock('@/lib/analytics', () => ({ analytics: { csvUploaded: vi.fn() } }));
vi.mock('@/components/integrations/CreateIssueDialog', () => ({ CreateIssueDialog: () => null }));
vi.mock('@/hooks/useRealtimeEvents', () => ({
  useRealtimeEvents: () => ({ connected: true, reconnecting: false }),
}));
vi.mock('@/contexts/FeedbackPageContext', () => ({
  FeedbackPageProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useFeedbackPage: () => ({
    searchQuery: '', sentimentFilter: '', urgentFilter: '', churnRiskFilter: '',
    customerEmailFilter: '', currentPage: 1,
    setSearchQuery: vi.fn(), setSentimentFilter: vi.fn(), setUrgentFilter: vi.fn(),
    setChurnRiskFilter: vi.fn(), setCustomerEmailFilter: vi.fn(), setCurrentPage: vi.fn(),
  }),
}));

// The table stub exposes whether the bulk-delete control would be offered.
vi.mock('@/components/shared/data-table', () => ({
  DataTable: (props: { onBulkDelete?: unknown }) => (
    <div data-testid="data-table" data-bulk-delete={String(!!props.onBulkDelete)} />
  ),
}));

const feedbackColumns = vi.hoisted(() => vi.fn(() => []));
vi.mock('@/app/(dashboard)/feedbacks/columns', () => ({ createColumns: feedbackColumns }));

vi.stubGlobal('localStorage', {
  getItem: vi.fn(() => 'test-token'),
  setItem: vi.fn(),
  removeItem: vi.fn(),
});

import { feedbackAPI } from '@/lib/api/feedback';
import FeedbacksPage from '@/app/(dashboard)/feedbacks/page';
import PainPointsPage from '@/app/(dashboard)/pain-points/page';
import UrgentPage from '@/app/(dashboard)/urgent-feedbacks/page';
import FeatureRequestsPage from '@/app/(dashboard)/feature-requests/page';
import ChurnRisksPage from '@/app/(dashboard)/churn-risks/page';
import CategoryPage from '@/app/(dashboard)/categories/[category]/page';

function renderPage(Page: React.ComponentType) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Suspense fallback={<div>Loading...</div>}>
        <Page />
      </Suspense>
    </QueryClientProvider>
  );
}

const pages: [string, React.ComponentType][] = [
  ['feedbacks', FeedbacksPage],
  ['pain-points', PainPointsPage],
  ['urgent-feedbacks', UrgentPage],
  ['feature-requests', FeatureRequestsPage],
  ['churn-risks', ChurnRisksPage],
  ['categories/[category]', CategoryPage],
];

describe.each(pages)('%s: bulk delete is admin/owner only', (_name, Page) => {
  beforeEach(() => {
    vi.clearAllMocks();
    (feedbackAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [], total: 0, total_pages: 1, page: 1, page_size: 20,
    });
  });

  it('member is not offered bulk delete', async () => {
    authMock.role = 'member';
    renderPage(Page);
    const table = await screen.findByTestId('data-table');
    expect(table).toHaveAttribute('data-bulk-delete', 'false');
  });

  it.each(['admin', 'owner'])('%s is offered bulk delete', async (role) => {
    authMock.role = role;
    renderPage(Page);
    const table = await screen.findByTestId('data-table');
    expect(table).toHaveAttribute('data-bulk-delete', 'true');
  });
});

describe('feedbacks: per-row delete is admin/owner only', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (feedbackAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [], total: 0, total_pages: 1, page: 1, page_size: 20,
    });
  });

  const lastDeleteArg = () => {
    const calls = feedbackColumns.mock.calls as unknown as unknown[][];
    return calls[calls.length - 1][1];
  };

  it('member gets no row delete handler (edit is kept)', async () => {
    authMock.role = 'member';
    renderPage(FeedbacksPage);
    await screen.findByTestId('data-table');
    expect(typeof feedbackColumns.mock.calls[0][0]).toBe('function');
    expect(lastDeleteArg()).toBeUndefined();
  });

  it('admin gets a row delete handler', async () => {
    authMock.role = 'admin';
    renderPage(FeedbacksPage);
    await waitFor(() => expect(feedbackColumns).toHaveBeenCalled());
    expect(typeof lastDeleteArg()).toBe('function');
  });
});
