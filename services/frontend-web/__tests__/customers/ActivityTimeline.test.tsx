import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/customers/john@acme.com',
}));

// Mock customers API
vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    getActivity: vi.fn(),
  },
}));

import { customersAPI } from '@/lib/api/customers';
import { ActivityTimeline } from '../../components/customers/ActivityTimeline';

const mockActivityResponse = {
  events: [
    {
      type: 'feedback_created' as const,
      description: 'New feedback submitted',
      feedback_id: 1234,
      timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
    },
    {
      type: 'status_changed' as const,
      description: 'Feedback #1230 moved to Resolved',
      feedback_id: 1230,
      timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // 1 day ago
    },
    {
      type: 'health_score_changed' as const,
      description: 'Health score dropped from 48 to 34',
      old_score: 48,
      new_score: 34,
      timestamp: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(), // 3 days ago
    },
    {
      type: 'llm_analysis_generated' as const,
      description: 'Weekly AI analysis generated',
      timestamp: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(), // 2 days ago
    },
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

describe('ActivityTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (customersAPI.getActivity as ReturnType<typeof vi.fn>).mockResolvedValue(mockActivityResponse);
  });

  it('renders events from the API', async () => {
    renderWithQueryClient(<ActivityTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('New feedback submitted')).toBeInTheDocument();
    });
  });

  it('renders status_changed event description', async () => {
    renderWithQueryClient(<ActivityTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('Feedback #1230 moved to Resolved')).toBeInTheDocument();
    });
  });

  it('renders health_score_changed event description', async () => {
    renderWithQueryClient(<ActivityTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/Health score dropped from 48 to 34/i)).toBeInTheDocument();
    });
  });

  it('renders llm_analysis_generated event', async () => {
    renderWithQueryClient(<ActivityTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/Weekly AI analysis generated/i)).toBeInTheDocument();
    });
  });

  it('renders relative timestamps', async () => {
    renderWithQueryClient(<ActivityTimeline email="john@acme.com" />);
    await waitFor(() => {
      // Should show "2 hours ago" or similar — multiple timestamps expected
      const timeElements = screen.getAllByText(/ago/i);
      expect(timeElements.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders a feedback link for feedback_created events', async () => {
    renderWithQueryClient(<ActivityTimeline email="john@acme.com" />);
    await waitFor(() => {
      const link = screen.getByRole('link', { name: /1234/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', '/feedbacks/1234');
    });
  });

  it('renders a playbook_auto_run event with its description', async () => {
    (customersAPI.getActivity as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [
        {
          type: 'playbook_auto_run' as const,
          description: "Auto-ran 'Win-back offer' playbook",
          timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
        },
      ],
    });
    renderWithQueryClient(<ActivityTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText("Auto-ran 'Win-back offer' playbook")).toBeInTheDocument();
    });
  });

  it('renders empty state when no events', async () => {
    (customersAPI.getActivity as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
    renderWithQueryClient(<ActivityTimeline email="john@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/No recent activity/i)).toBeInTheDocument();
    });
  });
});
