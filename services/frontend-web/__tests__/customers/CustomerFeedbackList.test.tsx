import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

// Mock customers API
vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    getFeedbacks: vi.fn(),
  },
}));

import { customersAPI } from '@/lib/api/customers';
import { CustomerFeedbackList } from '../../components/customers/CustomerFeedbackList';

const mockFeedbacksResponse = {
  feedbacks: [
    {
      id: 1234,
      text_snippet: 'The billing page keeps crashing when I try to update my payment method',
      sentiment_label: 'negative',
      sentiment_score: -0.72,
      churn_risk_score: 68,
      workflow_status: 'in_review',
      created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      source: 'slack',
    },
    {
      id: 1235,
      text_snippet: 'Would be nice to have dark mode on the dashboard',
      sentiment_label: 'neutral',
      sentiment_score: 0.1,
      churn_risk_score: 0,
      workflow_status: 'resolved',
      created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
      source: 'csv_import',
    },
  ],
  total_count: 28,
  view_all_url: '/feedbacks?customer_email=john@acme.com',
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('CustomerFeedbackList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (customersAPI.getFeedbacks as ReturnType<typeof vi.fn>).mockResolvedValue(mockFeedbacksResponse);
  });

  it('renders feedback text snippets', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/The billing page keeps crashing/i)).toBeInTheDocument();
    });
  });

  it('renders second feedback text snippet', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/Would be nice to have dark mode/i)).toBeInTheDocument();
    });
  });

  it('renders churn risk score when > 0', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/68/)).toBeInTheDocument();
    });
  });

  it('does not show churn risk score when = 0', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.queryByText('Churn: 0')).not.toBeInTheDocument();
    });
  });

  it('renders workflow status badges', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/in.review/i)).toBeInTheDocument();
    });
  });

  it('renders sentiment labels', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/negative/i)).toBeInTheDocument();
    });
  });

  it('renders footer with count and total', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/Showing 2 of 28/i)).toBeInTheDocument();
    });
  });

  it('renders "View All" link pointing to feedbacks filtered by email', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      const link = screen.getByRole('link', { name: /view all/i });
      expect(link).toBeInTheDocument();
      // The email is URL-encoded in the href
      expect(link).toHaveAttribute('href', expect.stringContaining('customer_email='));
    });
  });

  it('navigates to feedback detail on row click', async () => {
    renderWithQueryClient(<CustomerFeedbackList email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/The billing page keeps crashing/i)).toBeInTheDocument();
    });
    const row = screen.getByText(/The billing page keeps crashing/i).closest('[data-testid="feedback-row"]');
    expect(row).not.toBeNull();
    fireEvent.click(row!);
    expect(mockPush).toHaveBeenCalledWith('/feedbacks/1234');
  });
});
