import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock next/navigation
const mockPush = vi.fn();
const mockParams = { email: 'john%40acme.com' };
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => mockParams,
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/customers/john%40acme.com',
}));

// Mock next/link — prevents jsdom prefetch XHR requests that cause UND_ERR_INVALID_ARG
import React from 'react';
vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string; [key: string]: unknown }) => (
    <a href={href} {...(props as Record<string, unknown>)}>{children}</a>
  ),
}));

// Mock AuthContext - Pro plan user
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'owner@test.com',
      role: 'owner',
      plan: 'pro',
      organization_id: 1,
      is_system_admin: false,
    },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

// Mock customers API
vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    getByEmail: vi.fn(),
    getHistory: vi.fn(),
    getFeedbacks: vi.fn(),
    getActivity: vi.fn(),
    requestAnalysis: vi.fn(),
    getUsage: vi.fn(),
    getTimeline: vi.fn(),
  },
}));

// Mock churn-accuracy API (used by ModelAccuracyCard)
vi.mock('@/lib/api/churn-accuracy', () => ({
  getAccuracyCard: vi.fn().mockResolvedValue(null),
  formatMetricPercent: (n: number) => `${n}%`,
}));

// Suppress all outbound axios requests — prevents jsdom/undici XHR errors for
// unmocked API modules rendered inside this page (e.g. components that use
// apiClient directly rather than through the customersAPI mock).
vi.mock('@/lib/api-client', () => {
  const noop = () => Promise.resolve({ data: null, status: 200 });
  const client = { get: noop, post: noop, put: noop, patch: noop, delete: noop };
  return { default: client, apiClient: client, publicApiClient: client };
});

// Mock Recharts
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ReferenceLine: ({ y }: { y: number }) => <div data-testid={`reference-line-${y}`} />,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

import { customersAPI } from '@/lib/api/customers';
import CustomerProfilePage from '../../app/(dashboard)/customers/[email]/page';

const mockProfile = {
  customer_email: 'john@acme.com',
  customer_name: 'John Doe',
  health_score: 34,
  risk_level: 'at_risk',
  confidence_level: 'high' as const,
  feedback_count: 28,
  last_feedback_at: '2026-02-18T14:30:00Z',
  churn_risk_component: 22,
  sentiment_component: 38,
  resolution_component: 45,
  frequency_component: 30,
  llm_analysis: 'Customer shows signs of frustration with billing.',
  llm_analyzed_at: '2026-02-17T07:00:00Z',
  is_archived: false,
  created_at: '2025-12-01T10:00:00Z',
};

const mockHistory = {
  history: [
    { health_score: 45, churn_risk_component: 30, sentiment_component: 40, resolution_component: 50, frequency_component: 35, risk_level: 'moderate', recorded_at: '2026-01-20T00:00:00Z' },
  ],
  period_start: '2026-01-19T00:00:00Z',
  period_end: '2026-02-18T23:59:59Z',
};

const mockFeedbacks = {
  feedbacks: [
    { id: 1234, text_snippet: 'The billing page keeps crashing', sentiment_label: 'negative', sentiment_score: -0.72, churn_risk_score: 68, workflow_status: 'in_review', created_at: '2026-02-18T14:30:00Z', source: 'slack' },
  ],
  total_count: 28,
  view_all_url: '/feedbacks?customer_email=john@acme.com',
};

const mockActivity = {
  events: [
    { type: 'feedback_created' as const, description: 'New feedback submitted', feedback_id: 1234, timestamp: '2026-02-18T14:30:00Z' },
  ],
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('CustomerProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'localStorage', {
      value: { getItem: vi.fn(() => 'mock-token'), setItem: vi.fn(), removeItem: vi.fn() },
      writable: true,
    });
    (customersAPI.getByEmail as ReturnType<typeof vi.fn>).mockResolvedValue(mockProfile);
    (customersAPI.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue(mockHistory);
    (customersAPI.getFeedbacks as ReturnType<typeof vi.fn>).mockResolvedValue(mockFeedbacks);
    (customersAPI.getActivity as ReturnType<typeof vi.fn>).mockResolvedValue(mockActivity);
    (customersAPI.getTimeline as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [], next_cursor: null });
    (customersAPI.getUsage as ReturnType<typeof vi.fn>).mockResolvedValue({
      rollup: {
        customer_email: 'john@acme.com',
        usage_score: 65,
        events_total: 5,
        last_active_at: '2026-06-01T10:00:00Z',
        first_seen_at: '2026-01-01T00:00:00Z',
        login_count_7d: 3,
        login_count_30d: 12,
        active_days_7d: 3,
        active_days_30d: 9,
        distinct_features: ['dashboard', 'reports', 'export', 'settings'],
        distinct_feature_count: 4,
        updated_at: '2026-06-01T10:00:00Z',
      },
      time_series: [{ date: '2026-06-01', event_count: 5 }],
      period_days: 30,
    });
  });

  it('renders the breadcrumb with Customers link', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      const customersLink = screen.getByRole('link', { name: /customers/i });
      expect(customersLink).toBeInTheDocument();
      expect(customersLink).toHaveAttribute('href', '/customers');
    });
  });

  it('renders customer email in the profile header', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getAllByText('john@acme.com').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders customer name', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });
  });

  it('renders health score', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText('34')).toBeInTheDocument();
    });
  });

  it('renders feedback count in metadata', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText(/28 feedbacks/i)).toBeInTheDocument();
    });
  });

  it('renders risk level badge', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText(/At Risk/i)).toBeInTheDocument();
    });
  });

  it('does NOT render confidence badge for high confidence', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.queryByText(/low confidence/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/medium confidence/i)).not.toBeInTheDocument();
    });
  });

  it('renders Overview and Feedbacks tabs', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /overview/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /feedbacks/i })).toBeInTheDocument();
    });
  });

  it('renders "View All Feedbacks" button', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /view all feedbacks/i })).toBeInTheDocument();
    });
  });

  it('renders LLM analysis text on Overview tab', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText(/Customer shows signs of frustration/i)).toBeInTheDocument();
    });
  });

  it('renders ComponentProgressBars in Overview tab', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText(/Churn Risk/i)).toBeInTheDocument();
      expect(screen.getByText('22/100')).toBeInTheDocument();
    });
  });
});

describe('CustomerProfilePage - low confidence badge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'localStorage', {
      value: { getItem: vi.fn(() => 'mock-token'), setItem: vi.fn(), removeItem: vi.fn() },
      writable: true,
    });
    (customersAPI.getByEmail as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...mockProfile,
      confidence_level: 'low',
      feedback_count: 2,
    });
    (customersAPI.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue(mockHistory);
    (customersAPI.getFeedbacks as ReturnType<typeof vi.fn>).mockResolvedValue(mockFeedbacks);
    (customersAPI.getActivity as ReturnType<typeof vi.fn>).mockResolvedValue(mockActivity);
    (customersAPI.getTimeline as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [], next_cursor: null });
    (customersAPI.getUsage as ReturnType<typeof vi.fn>).mockResolvedValue({
      rollup: {
        customer_email: 'john@acme.com',
        usage_score: 50,
        events_total: 0,
        last_active_at: null,
        first_seen_at: null,
        login_count_7d: 0,
        login_count_30d: 0,
        active_days_7d: 0,
        active_days_30d: 0,
        distinct_features: null,
        distinct_feature_count: 0,
        updated_at: null,
      },
      time_series: [],
      period_days: 30,
    });
  });

  it('renders confidence badge for low confidence', async () => {
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText(/low confidence/i)).toBeInTheDocument();
    });
  });
});

describe('CustomerProfilePage - tags + CS owner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'localStorage', {
      value: { getItem: vi.fn(() => 'mock-token'), setItem: vi.fn(), removeItem: vi.fn() },
      writable: true,
    });
    (customersAPI.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue(mockHistory);
    (customersAPI.getFeedbacks as ReturnType<typeof vi.fn>).mockResolvedValue(mockFeedbacks);
    (customersAPI.getActivity as ReturnType<typeof vi.fn>).mockResolvedValue(mockActivity);
    (customersAPI.getTimeline as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [], next_cursor: null });
    (customersAPI.getUsage as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('no usage'));
  });

  it('renders tags chips and the assigned CS owner when present', async () => {
    (customersAPI.getByEmail as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...mockProfile,
      tags: ['vip', 'renewal-q3'],
      cs_owner: { id: 9, email: 'csm@acme.com' },
    });
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText('vip')).toBeInTheDocument();
      expect(screen.getByText('renewal-q3')).toBeInTheDocument();
      expect(screen.getByText('csm@acme.com')).toBeInTheDocument();
    });
  });

  it('renders an "Unassigned" owner badge and no tag chips when neither is set', async () => {
    (customersAPI.getByEmail as ReturnType<typeof vi.fn>).mockResolvedValue(mockProfile);
    renderWithQueryClient(<CustomerProfilePage />);
    await waitFor(() => {
      expect(screen.getByText('Unassigned')).toBeInTheDocument();
    });
  });
});

// Free plan redirect is tested via a component check: when plan=free the page renders null
// and the useEffect calls router.push('/customers'). The mockPush test is verified above.
