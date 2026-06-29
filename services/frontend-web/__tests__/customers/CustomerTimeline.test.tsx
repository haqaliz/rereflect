import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// Mock the customers API
vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    getTimeline: vi.fn(),
  },
}));

import { customersAPI } from '@/lib/api/customers';
import { CustomerTimeline } from '../../components/customers/CustomerTimeline';

const mockGetTimeline = customersAPI.getTimeline as ReturnType<typeof vi.fn>;

const event1 = {
  type: 'feedback_created' as const,
  description: 'New feedback submitted',
  feedback_id: 1,
  timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
};

const event2 = {
  type: 'churned' as const,
  description: 'Customer marked as churned',
  timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
};

const event3 = {
  type: 'usage_feature_adopted' as const,
  description: 'Adopted feature: reports',
  feature_name: 'reports',
  timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('CustomerTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Initial fetch ---
  it('calls getTimeline without a cursor on initial render', async () => {
    mockGetTimeline.mockResolvedValue({ events: [event1], next_cursor: null });
    renderWithQueryClient(<CustomerTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(mockGetTimeline).toHaveBeenCalledWith('alice@acme.com', {});
    });
  });

  it('renders events returned from the initial fetch', async () => {
    mockGetTimeline.mockResolvedValue({ events: [event1, event2], next_cursor: null });
    renderWithQueryClient(<CustomerTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('New feedback submitted')).toBeInTheDocument();
      expect(screen.getByText('Customer marked as churned')).toBeInTheDocument();
    });
  });

  // --- Load more ---
  it('hides Load more button when next_cursor is null', async () => {
    mockGetTimeline.mockResolvedValue({ events: [event1], next_cursor: null });
    renderWithQueryClient(<CustomerTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('New feedback submitted')).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument();
  });

  it('shows Load more button when next_cursor is present', async () => {
    mockGetTimeline.mockResolvedValue({ events: [event1], next_cursor: 'cursor-abc' });
    renderWithQueryClient(<CustomerTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /load more/i })).toBeInTheDocument();
    });
  });

  it('appends events on Load more click and calls getTimeline with before=cursor', async () => {
    mockGetTimeline
      .mockResolvedValueOnce({ events: [event1], next_cursor: 'cursor-abc' })
      .mockResolvedValueOnce({ events: [event2, event3], next_cursor: null });

    renderWithQueryClient(<CustomerTimeline email="alice@acme.com" />);

    await waitFor(() => {
      expect(screen.getByText('New feedback submitted')).toBeInTheDocument();
    });

    const loadMoreBtn = screen.getByRole('button', { name: /load more/i });
    fireEvent.click(loadMoreBtn);

    await waitFor(() => {
      expect(mockGetTimeline).toHaveBeenCalledWith('alice@acme.com', { before: 'cursor-abc' });
    });

    await waitFor(() => {
      // Both pages of events should be present
      expect(screen.getByText('New feedback submitted')).toBeInTheDocument();
      expect(screen.getByText('Customer marked as churned')).toBeInTheDocument();
      expect(screen.getByText('Adopted feature: reports')).toBeInTheDocument();
    });
  });

  it('hides Load more after the last page is loaded (next_cursor null)', async () => {
    mockGetTimeline
      .mockResolvedValueOnce({ events: [event1], next_cursor: 'cursor-abc' })
      .mockResolvedValueOnce({ events: [event2], next_cursor: null });

    renderWithQueryClient(<CustomerTimeline email="alice@acme.com" />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /load more/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /load more/i }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument();
    });
  });

  // --- Empty state ---
  it('shows empty state when no events are returned', async () => {
    mockGetTimeline.mockResolvedValue({ events: [], next_cursor: null });
    renderWithQueryClient(<CustomerTimeline email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/no activity yet/i)).toBeInTheDocument();
    });
  });

  // --- Loading state ---
  it('shows a skeleton while loading', () => {
    // Never resolves so we stay in loading state
    mockGetTimeline.mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<CustomerTimeline email="alice@acme.com" />);
    // Skeletons are rendered (look for animate-pulse elements via aria or test-id)
    expect(document.querySelector('.animate-pulse')).not.toBeNull();
  });
});
