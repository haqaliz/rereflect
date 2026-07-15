import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/customers',
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

vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    list: vi.fn(),
    exportCustomers: vi.fn(),
  },
}));

vi.mock('@/lib/api/churn-suggestions', () => ({
  listChurnSuggestions: vi.fn(),
}));

import { customersAPI } from '@/lib/api/customers';
import { listChurnSuggestions } from '@/lib/api/churn-suggestions';
import CustomersPage from '../../app/(dashboard)/customers/page';

const mockListResponse = {
  items: [
    {
      customer_email: 'john@acme.com',
      customer_name: 'John Doe',
      health_score: 34,
      risk_level: 'at_risk',
      confidence_level: 'high',
      feedback_count: 28,
      last_feedback_at: '2026-02-18T14:30:00Z',
      sentiment_trend: { direction: 'declining', change_percent: -12.5 },
      is_archived: false,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
  summary: {
    total_customers: 1,
    avg_health_score: 34,
    risk_distribution: { healthy: 0, moderate: 0, at_risk: 1, critical: 0 },
  },
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('CustomersPage — CRM churn suggestions StatCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.role = 'owner';
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(() => 'mock-token'),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      },
      writable: true,
    });
    (customersAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockListResponse);
  });

  it('is absent when there are 0 pending suggestions', async () => {
    (listChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 1,
    });
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });
    expect(screen.queryByText(/CRM churn suggestions/i)).not.toBeInTheDocument();
  });

  it('is visible with the pending count and links to the review view', async () => {
    (listChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 7,
      page: 1,
      page_size: 1,
    });
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText(/CRM churn suggestions/i)).toBeInTheDocument();
    });
    expect(screen.getByText('7')).toBeInTheDocument();
    const link = screen.getByText(/CRM churn suggestions/i).closest('a');
    expect(link).toHaveAttribute('href', '/customers/churn-suggestions');
  });

  it('renders nothing (not a broken card) when the suggestions request errors', async () => {
    (listChurnSuggestions as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('403'));
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });
    expect(screen.queryByText(/CRM churn suggestions/i)).not.toBeInTheDocument();
  });

  it('is hidden for a member (destination would 403)', async () => {
    authMock.role = 'member';
    (listChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 5,
      page: 1,
      page_size: 1,
    });
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });
    expect(screen.queryByText(/CRM churn suggestions/i)).not.toBeInTheDocument();
  });
});
