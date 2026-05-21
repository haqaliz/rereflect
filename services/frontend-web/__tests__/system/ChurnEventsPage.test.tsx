import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock churn-events API
vi.mock('@/lib/api/churn-events', () => ({
  listChurnEvents: vi.fn(),
  exportChurnEventsCsv: vi.fn(),
}));

import { listChurnEvents, exportChurnEventsCsv } from '@/lib/api/churn-events';
import ChurnEventsPage from '@/app/(dashboard)/system/churn-events/page';

const systemAdminUser = {
  id: 1,
  email: 'admin@system.com',
  role: 'owner',
  plan: 'enterprise',
  organization_id: 1,
  is_system_admin: true,
};

const regularUser = { ...systemAdminUser, is_system_admin: false };

const mockChurnEvents = [
  {
    id: 1,
    organization_id: 10,
    customer_email: 'alice@acme.com',
    churned_at: '2026-04-01T00:00:00Z',
    reason_code: 'price' as const,
    reason_text: 'Too expensive',
    recovered_at: null,
    source: 'manual' as const,
    marked_by_user_id: 5,
    created_at: '2026-04-01T10:00:00Z',
  },
  {
    id: 2,
    organization_id: 11,
    customer_email: 'bob@beta.com',
    churned_at: '2026-03-15T00:00:00Z',
    reason_code: 'competitor' as const,
    reason_text: null,
    recovered_at: '2026-04-10T00:00:00Z',
    source: 'csv_import' as const,
    marked_by_user_id: null,
    created_at: '2026-03-15T08:00:00Z',
  },
];

const mockListResponse = {
  items: mockChurnEvents,
  total: 2,
  page: 1,
  page_size: 25,
};

const emptyListResponse = {
  items: [],
  total: 0,
  page: 1,
  page_size: 25,
};

describe('ChurnEventsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listChurnEvents).mockResolvedValue(mockListResponse);
    vi.mocked(exportChurnEventsCsv).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // Test 1
  it('renders page heading and description', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Churn Events/i })).toBeInTheDocument();
    });
    expect(screen.getByText(/churn events across all organizations/i)).toBeInTheDocument();
  });

  // Test 2
  it('redirects non-system-admin users to /dashboard', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/dashboard');
    });
  });

  // Test 3
  it('fetches and renders churn events on mount', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(listChurnEvents).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1, page_size: 25 })
      );
      expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
      expect(screen.getByText('bob@beta.com')).toBeInTheDocument();
    });
  });

  // Test 4
  it('renders all expected columns', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
    });
    expect(screen.getByText(/customer email/i)).toBeInTheDocument();
    // "Reason" appears as a table column header
    expect(screen.getByRole('columnheader', { name: /^reason$/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /^status$/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /^source$/i })).toBeInTheDocument();
    expect(screen.getByText(/churned at/i)).toBeInTheDocument();
  });

  // Test 5
  it('shows Active status badge when recovered_at is null', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
    });
  });

  // Test 6
  it('shows Recovered status badge when recovered_at is set', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(screen.getByText('Recovered')).toBeInTheDocument();
    });
  });

  // Test 7
  it('filters by status when status dropdown changes', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
    });

    const statusTrigger = screen.getByRole('combobox', { name: /status/i });
    fireEvent.click(statusTrigger);
    await waitFor(() => {
      const activeOption = screen.getByRole('option', { name: /^active$/i });
      fireEvent.click(activeOption);
    });

    await waitFor(() => {
      expect(listChurnEvents).toHaveBeenCalledWith(
        expect.objectContaining({ active: true })
      );
    });
  });

  // Test 8
  it('filters by reason_code via multi-select', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
    });

    const reasonTrigger = screen.getByRole('combobox', { name: /reason/i });
    fireEvent.click(reasonTrigger);
    await waitFor(() => {
      const priceOption = screen.getByRole('option', { name: /^price$/i });
      fireEvent.click(priceOption);
    });

    await waitFor(() => {
      expect(listChurnEvents).toHaveBeenCalledWith(
        expect.objectContaining({ reason_code: 'price' })
      );
    });
  });

  // Test 9
  it('debounces email search input by 300ms', async () => {
    // Use real timers; test via call counting before/after timeout
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);

    // Wait for initial fetch to complete
    await waitFor(() => {
      expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
    });

    const callsAfterMount = vi.mocked(listChurnEvents).mock.calls.length;

    const emailInput = screen.getByPlaceholderText(/search by email/i);
    fireEvent.change(emailInput, { target: { value: 'ali' } });
    fireEvent.change(emailInput, { target: { value: 'alic' } });
    fireEvent.change(emailInput, { target: { value: 'alice' } });

    // After rapid typing, should not have fired extra calls yet
    expect(vi.mocked(listChurnEvents).mock.calls.length).toBe(callsAfterMount);

    // After debounce window, should fire exactly one new call
    await waitFor(
      () => {
        expect(vi.mocked(listChurnEvents).mock.calls.length).toBeGreaterThan(callsAfterMount);
      },
      { timeout: 1000 }
    );

    // Only one call was fired despite multiple keystrokes
    expect(vi.mocked(listChurnEvents).mock.calls.length).toBe(callsAfterMount + 1);
  });

  // Test 10
  it('paginates server-side and calls listChurnEvents with new page', async () => {
    vi.mocked(listChurnEvents).mockResolvedValue({
      items: mockChurnEvents,
      total: 30,
      page: 1,
      page_size: 25,
    });
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);

    await waitFor(() => {
      expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
    });

    // With total=30 and page_size=25, totalPages=2, Next button should be enabled
    const nextButton = screen.getByLabelText('Next page');
    expect(nextButton).not.toBeDisabled();
    fireEvent.click(nextButton);

    await waitFor(() => {
      expect(listChurnEvents).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 })
      );
    });
  });

  // Test 11
  it('Export CSV button triggers file download', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });

    const mockCreateObjectURL = vi.fn(() => 'blob:mock-url');
    const mockRevokeObjectURL = vi.fn();
    global.URL.createObjectURL = mockCreateObjectURL;
    global.URL.revokeObjectURL = mockRevokeObjectURL;

    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(screen.getByText('alice@acme.com')).toBeInTheDocument();
    });

    const exportButton = screen.getByRole('button', { name: /export csv/i });
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(exportChurnEventsCsv).toHaveBeenCalled();
    });
  });

  // Test 12
  it('empty state shows "No churn events found" when list is empty', async () => {
    vi.mocked(listChurnEvents).mockResolvedValue(emptyListResponse);
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    render(<ChurnEventsPage />);
    await waitFor(() => {
      expect(screen.getByText(/no churn events found/i)).toBeInTheDocument();
    });
  });
});
