import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/customers/churn-suggestions',
}));

const authMock = vi.hoisted(() => ({ role: 'owner' as string }));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'test@test.com',
      role: authMock.role,
      plan: 'business',
      organization_id: 1,
      is_system_admin: false,
    },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock('@/lib/api/churn-suggestions', () => ({
  listChurnSuggestions: vi.fn(),
  confirmChurnSuggestion: vi.fn(),
  rejectChurnSuggestion: vi.fn(),
  bulkReviewChurnSuggestions: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { listChurnSuggestions } from '@/lib/api/churn-suggestions';
import ChurnSuggestionsPage from '../../app/(dashboard)/customers/churn-suggestions/page';

const mockResponse = {
  items: [
    {
      id: 1,
      organization_id: 1,
      customer_email: 'alice@example.com',
      provider: 'hubspot',
      external_opportunity_id: 'deal-1',
      suggested_churned_at: '2026-05-01T00:00:00Z',
      evidence: { deal_name: 'Acme Renewal', amount: 5000, stage: 'Closed Lost' },
      status: 'pending',
      reviewed_by_user_id: null,
      reviewed_at: null,
      churn_event_id: null,
      created_at: '2026-05-01T00:00:00Z',
      updated_at: '2026-05-01T00:00:00Z',
    },
    {
      id: 2,
      organization_id: 1,
      customer_email: 'bob@example.com',
      provider: 'salesforce',
      external_opportunity_id: 'opp-2',
      suggested_churned_at: '2026-05-02T00:00:00Z',
      evidence: null,
      status: 'pending',
      reviewed_by_user_id: null,
      reviewed_at: null,
      churn_event_id: null,
      created_at: '2026-05-02T00:00:00Z',
      updated_at: '2026-05-02T00:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('ChurnSuggestionsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.role = 'owner';
    (listChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);
  });

  it('renders suggestion rows with evidence', async () => {
    renderWithQueryClient(<ChurnSuggestionsPage />);
    await waitFor(() => {
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    });
    expect(screen.getByText(/Acme Renewal/)).toBeInTheDocument();
  });

  it('shows an explicit "No CRM detail captured" cell for thin/null evidence', async () => {
    renderWithQueryClient(<ChurnSuggestionsPage />);
    await waitFor(() => {
      expect(screen.getByText('bob@example.com')).toBeInTheDocument();
    });
    expect(screen.getByText(/No CRM detail captured/i)).toBeInTheDocument();
  });

  it('shows the Bulk Actions dropdown for an owner once rows are selected', async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ChurnSuggestionsPage />);
    await waitFor(() => {
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    });
    const rowCheckboxes = screen.getAllByRole('checkbox', { name: 'Select row' });
    await user.click(rowCheckboxes[0]);

    const bulkActionsButton = screen.getByRole('button', { name: /bulk actions/i });
    expect(bulkActionsButton).toBeInTheDocument();
    await user.click(bulkActionsButton);

    expect(await screen.findByText(/confirm selected/i)).toBeInTheDocument();
    expect(screen.getByText(/reject selected/i)).toBeInTheDocument();
  });

  it('hides the Bulk Actions dropdown for a member', async () => {
    authMock.role = 'member';
    const user = userEvent.setup();
    renderWithQueryClient(<ChurnSuggestionsPage />);
    await waitFor(() => {
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    });
    const rowCheckboxes = screen.getAllByRole('checkbox', { name: 'Select row' });
    await user.click(rowCheckboxes[0]);
    expect(screen.queryByRole('button', { name: /bulk actions/i })).not.toBeInTheDocument();
  });
});
