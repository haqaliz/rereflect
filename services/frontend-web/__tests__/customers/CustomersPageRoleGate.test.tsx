import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

describe('CustomersPage - churn/playbook controls are admin/owner only', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'localStorage', {
      value: { getItem: vi.fn(() => 'mock-token'), setItem: vi.fn(), removeItem: vi.fn() },
      writable: true,
    });
    (customersAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockListResponse);
    (listChurnSuggestions as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [], total: 0, page: 1, page_size: 1,
    });
  });

  async function selectRow() {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => expect(screen.getByText('john@acme.com')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select row' }));
  }

  it('member: no Mark-as-churned, no Import CSV, no Run playbook item', async () => {
    authMock.role = 'member';
    await selectRow();
    expect(screen.queryByRole('button', { name: /as churned/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /import csv/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /bulk actions/i }));
    expect(await screen.findByText('Export CSV')).toBeInTheDocument();
    expect(screen.queryByText('Run playbook')).not.toBeInTheDocument();
  });

  it.each(['admin', 'owner'])('%s: sees Mark-as-churned, Import CSV and Run playbook', async (role) => {
    authMock.role = role;
    await selectRow();
    expect(screen.getByRole('button', { name: /as churned/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /import csv/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /bulk actions/i }));
    expect(await screen.findByText('Run playbook')).toBeInTheDocument();
  });
});
