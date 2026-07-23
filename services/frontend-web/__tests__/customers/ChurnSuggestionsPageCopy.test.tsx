import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/customers/churn-suggestions',
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'test@test.com',
      role: 'owner',
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

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('ChurnSuggestionsPage — source-neutral copy (queue is multi-source, not CRM-only)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
  });

  it('header no longer says "CRM churn suggestions"', async () => {
    renderWithQueryClient(<ChurnSuggestionsPage />);
    await waitFor(() => {
      expect(screen.getByText('Churn suggestions')).toBeInTheDocument();
    });
    expect(screen.queryByText('CRM churn suggestions')).not.toBeInTheDocument();
  });

  it('subtitle no longer says "CRM-sourced closed-lost deals" and mentions connected sources + product usage', async () => {
    renderWithQueryClient(<ChurnSuggestionsPage />);
    await waitFor(() => {
      expect(
        screen.getByText(/connected sources and product usage/i)
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/CRM-sourced closed-lost deals/i)).not.toBeInTheDocument();
  });

  it('subtitle still states confirming writes a real churn label that only trains the model once a human confirms', async () => {
    renderWithQueryClient(<ChurnSuggestionsPage />);
    await waitFor(() => {
      expect(
        screen.getByText(/confirming writes a real churn label/i)
      ).toBeInTheDocument();
    });
  });
});
