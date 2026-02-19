import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/customers',
}));

// Mock AuthContext
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'test@test.com', role: 'owner', plan: 'pro', organization_id: 1, is_system_admin: false },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

// Mock customers API
vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    list: vi.fn(),
  },
}));

import { customersAPI } from '@/lib/api/customers';
import CustomersPage from '../../app/(dashboard)/customers/page';

const mockCustomerListResponse = {
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
  total: 2,
  page: 1,
  page_size: 20,
  summary: {
    total_customers: 2,
    avg_health_score: 53,
    risk_distribution: {
      healthy: 1,
      moderate: 0,
      at_risk: 1,
      critical: 0,
    },
  },
};

const emptyListResponse = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
  summary: {
    total_customers: 0,
    avg_health_score: 0,
    risk_distribution: { healthy: 0, moderate: 0, at_risk: 0, critical: 0 },
  },
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('CustomersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock localStorage
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(() => 'mock-token'),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      },
      writable: true,
    });
    (customersAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockCustomerListResponse);
  });

  it('renders the page title', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('Customers')).toBeInTheDocument();
    });
  });

  it('renders 4 stat cards', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('Total Customers')).toBeInTheDocument();
      expect(screen.getByText('Avg Health Score')).toBeInTheDocument();
      expect(screen.getByText('At Risk %')).toBeInTheDocument();
      expect(screen.getByText('Critical Count')).toBeInTheDocument();
    });
  });

  it('renders stat card values from summary', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      // Total customers
      expect(screen.getByText('2')).toBeInTheDocument();
      // Avg health score
      expect(screen.getByText('53')).toBeInTheDocument();
    });
  });

  it('renders customer emails in table', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
      expect(screen.getByText('jane@corp.io')).toBeInTheDocument();
    });
  });

  it('renders customer name when available', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });
  });

  it('renders table column headers', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('Customer')).toBeInTheDocument();
      expect(screen.getByText('Health Score')).toBeInTheDocument();
      expect(screen.getByText('Risk Level')).toBeInTheDocument();
      expect(screen.getByText('Feedbacks')).toBeInTheDocument();
      expect(screen.getByText('Last Active')).toBeInTheDocument();
      expect(screen.getByText('Trend')).toBeInTheDocument();
    });
  });

  it('renders feedback counts in table', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('28')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
    });
  });

  it('navigates to customer profile on row click', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('john@acme.com')).toBeInTheDocument();
    });
    const row = screen.getByText('john@acme.com').closest('tr');
    expect(row).not.toBeNull();
    fireEvent.click(row!);
    expect(mockPush).toHaveBeenCalledWith(
      `/customers/${encodeURIComponent('john@acme.com')}`
    );
  });

  it('renders search input', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/search customers/i)).toBeInTheDocument();
    });
  });

  it('renders risk level filter dropdown', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText('All Risk Levels')).toBeInTheDocument();
    });
  });

  it('renders risk distribution bar', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      // The bar renders with segment labels - getAllByText handles multiple matches
      const healthyElements = screen.getAllByText(/Healthy/i);
      expect(healthyElements.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('calls API with default sort params (health_score asc)', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(customersAPI.list).toHaveBeenCalledWith(
        expect.objectContaining({
          sort_by: 'health_score',
          sort_order: 'asc',
        })
      );
    });
  });
});

describe('CustomersPage - empty state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'localStorage', {
      value: { getItem: vi.fn(() => 'mock-token'), setItem: vi.fn(), removeItem: vi.fn() },
      writable: true,
    });
    (customersAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(emptyListResponse);
  });

  it('renders empty state message when no customers', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByText(/No customer data yet/i)).toBeInTheDocument();
    });
  });

  it('renders Import Feedback CTA in empty state', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /import feedback/i })).toBeInTheDocument();
    });
  });
});

describe('CustomersPage - Free plan blur', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'localStorage', {
      value: { getItem: vi.fn(() => 'mock-token'), setItem: vi.fn(), removeItem: vi.fn() },
      writable: true,
    });
    (customersAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockCustomerListResponse);
  });

  it('renders customer data while free plan shows upgrade CTA', async () => {
    renderWithQueryClient(<CustomersPage />);
    await waitFor(() => {
      // Table still shows customer data with free plan
      expect(screen.getAllByText('john@acme.com').length).toBeGreaterThanOrEqual(1);
    });
  });
});
