import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/customers',
}));

// Mutable auth mock so role can be flipped per-test
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

// Mock churn-suggestions API — the /customers StatCard row queries the
// pending count; unmocked, it would hit a real (unhandled) network call
// in jsdom. Resolve to 0 so pre-existing tests below are unaffected.
vi.mock('@/lib/api/churn-suggestions', () => ({
  listChurnSuggestions: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1 }),
}));

import { customersAPI } from '@/lib/api/customers';
import CustomersPage from '../../app/(dashboard)/customers/page';

// 5 total customers, only 2 on this page — so a fully-selected page can
// offer "select all N matching this filter".
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
      tags: ['vip', 'renewal-q3'],
      cs_owner: { id: 9, email: 'csm@acme.com' },
    },
    {
      customer_email: 'jane@corp.io',
      customer_name: null,
      health_score: 72,
      risk_level: 'healthy',
      confidence_level: 'medium',
      feedback_count: 12,
      last_feedback_at: '2026-02-17T10:00:00Z',
      sentiment_trend: { direction: 'improving', change_percent: 5.2 },
      is_archived: false,
    },
  ],
  total: 5,
  page: 1,
  page_size: 2,
  summary: {
    total_customers: 5,
    avg_health_score: 53,
    risk_distribution: { healthy: 1, moderate: 0, at_risk: 1, critical: 0 },
  },
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('CustomersPage — cohort mode + bulk-actions toolbar', () => {
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

  it('no bulk-actions toolbar when nothing is selected', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });
    expect(screen.queryByText(/Bulk Actions/i)).not.toBeInTheDocument();
  });

  it('selecting a row shows the Bulk Actions toolbar with the selection count', async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });

    const rowCheckboxes = screen.getAllByRole('checkbox', { name: 'Select row' });
    await user.click(rowCheckboxes[0]);

    expect(await screen.findByText(/Bulk Actions \(1\)/i)).toBeInTheDocument();
  });

  it('selecting every row on the page offers "Select all N matching this filter"', async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });

    const selectAllHeader = screen.getByRole('checkbox', { name: 'Select all' });
    await user.click(selectAllHeader);

    expect(await screen.findByText(/Select all 5 matching this filter/i)).toBeInTheDocument();
  });

  it('clicking "Select all N matching this filter" switches the cohort to filter mode', async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });

    const selectAllHeader = screen.getByRole('checkbox', { name: 'Select all' });
    await user.click(selectAllHeader);
    const filterLink = await screen.findByText(/Select all 5 matching this filter/i);
    await user.click(filterLink);

    const filterBanner = await screen.findByTestId('cohort-filter-banner');
    expect(filterBanner).toHaveTextContent(
      'All 5 customers matching the current filter are selected.'
    );
    expect(screen.getByText(/Bulk Actions \(5\)/i)).toBeInTheDocument();
  });

  it('Bulk Actions menu shows Tag/Assign owner for owner role', async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });
    const rowCheckboxes = screen.getAllByRole('checkbox', { name: 'Select row' });
    await user.click(rowCheckboxes[0]);
    await user.click(await screen.findByText(/Bulk Actions \(1\)/i));

    expect(await screen.findByText('Export CSV')).toBeInTheDocument();
    expect(screen.getByText('Tag')).toBeInTheDocument();
    expect(screen.getByText('Assign owner')).toBeInTheDocument();
    expect(screen.getByText('Run playbook')).toBeInTheDocument();
  });

  it('Bulk Actions menu hides Tag/Assign owner for member role', async () => {
    authMock.role = 'member';
    const user = userEvent.setup();
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });
    const rowCheckboxes = screen.getAllByRole('checkbox', { name: 'Select row' });
    await user.click(rowCheckboxes[0]);
    await user.click(await screen.findByText(/Bulk Actions \(1\)/i));

    expect(await screen.findByText('Export CSV')).toBeInTheDocument();
    expect(screen.queryByText('Tag')).not.toBeInTheDocument();
    expect(screen.queryByText('Assign owner')).not.toBeInTheDocument();
    // Run playbook has no role restriction on the backend
    expect(screen.getByText('Run playbook')).toBeInTheDocument();
  });

  it('clicking Export CSV calls customersAPI.exportCustomers with active filters', async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });
    const rowCheckboxes = screen.getAllByRole('checkbox', { name: 'Select row' });
    await user.click(rowCheckboxes[0]);
    await user.click(await screen.findByText(/Bulk Actions \(1\)/i));
    await user.click(await screen.findByText('Export CSV'));

    await waitFor(() => {
      expect(customersAPI.exportCustomers).toHaveBeenCalledWith(
        expect.objectContaining({ sort_by: 'health_score', sort_order: 'asc' })
      );
    });
  });

  it('renders tags chips and the assigned CS owner on the list', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });

    expect(screen.getByText('vip')).toBeInTheDocument();
    expect(screen.getByText('renewal-q3')).toBeInTheDocument();
    expect(screen.getByText('csm@acme.com')).toBeInTheDocument();
    // jane@corp.io has no tags/owner in the fixture — renders cleanly, no crash
    expect(screen.getByText('Unassigned')).toBeInTheDocument();
  });
});
