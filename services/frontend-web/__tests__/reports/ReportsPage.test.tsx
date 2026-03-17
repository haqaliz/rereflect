import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReportsPage from '@/app/(dashboard)/reports/page';
import { Report } from '@/lib/api/reports';

// ─── Mock next/navigation ─────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/reports',
}));

// ─── Mock sonner ──────────────────────────────────────────────────────────────

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// ─── Mutable auth state (controlled per test) ─────────────────────────────────
// Using a mutable object so individual tests can override plan without
// re-importing the module (vi.mock is hoisted, so the factory runs once).

const authState = {
  user: {
    id: 1,
    email: 'test@example.com',
    organization_id: 1,
    role: 'owner' as const,
    plan: 'business',
    is_system_admin: false,
  },
};

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => authState,
}));

// ─── Mock reportsAPI ──────────────────────────────────────────────────────────

const mockReports: Report[] = [
  {
    id: 1,
    report_type: 'executive_summary',
    date_range_days: 30,
    title: 'Executive Summary — Feb 2026',
    sections: [
      {
        heading: 'Overview',
        narrative: 'This month we received 300 feedback items.',
      },
    ],
    metadata: {},
    pdf_generated: true,
    created_at: '2026-03-01T10:00:00Z',
  },
  {
    id: 2,
    report_type: 'churn_risk',
    date_range_days: 7,
    title: 'Churn Risk Report — Last 7 Days',
    sections: [],
    metadata: {},
    pdf_generated: false,
    created_at: '2026-03-10T14:00:00Z',
  },
];

const mockList = vi.fn().mockResolvedValue({ reports: mockReports, total: 2 });
const mockDelete = vi.fn().mockResolvedValue(undefined);
const mockDownloadPDF = vi.fn().mockResolvedValue(undefined);

vi.mock('@/lib/api/reports', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/reports')>();
  return {
    ...actual,
    reportsAPI: {
      list: mockList,
      get: vi.fn(),
      delete: mockDelete,
      downloadPDF: mockDownloadPDF,
    },
  };
});

// ─── Mock ReportPreview (avoid Recharts complexity) ───────────────────────────

vi.mock('@/components/copilot/ReportPreview', () => ({
  ReportPreview: ({ title }: { title?: string }) => (
    <div data-testid="report-preview-mock">{title}</div>
  ),
}));

// ─── Mock UpgradeCTA ──────────────────────────────────────────────────────────

vi.mock('@/components/copilot/UpgradeCTA', () => ({
  UpgradeCTA: ({ message }: { message: string }) => (
    <div data-testid="upgrade-cta-mock">{message}</div>
  ),
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset mocks to default resolved values
    mockList.mockResolvedValue({ reports: mockReports, total: 2 });
    mockDelete.mockResolvedValue(undefined);
    mockDownloadPDF.mockResolvedValue(undefined);
    // Reset user to business plan
    authState.user = {
      id: 1,
      email: 'test@example.com',
      organization_id: 1,
      role: 'owner',
      plan: 'business',
      is_system_admin: false,
    };
  });

  it('test_renders_empty_state', async () => {
    mockList.mockResolvedValueOnce({ reports: [], total: 0 });

    render(<ReportsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });

    expect(screen.getByText('No reports yet')).toBeInTheDocument();
  });

  it('test_renders_report_list', async () => {
    render(<ReportsPage />);

    await waitFor(() => {
      expect(screen.getByText('Executive Summary — Feb 2026')).toBeInTheDocument();
    });

    // Second report title
    expect(screen.getByText('Churn Risk Report — Last 7 Days')).toBeInTheDocument();

    // Type badges
    const badges = screen.getAllByTestId('report-type-badge');
    expect(badges.length).toBe(2);
    expect(badges[0]).toHaveTextContent('Executive Summary');
    expect(badges[1]).toHaveTextContent('Churn Risk');

    // Date range labels
    expect(screen.getByText('Last 30 days')).toBeInTheDocument();
    expect(screen.getByText('Last 7 days')).toBeInTheDocument();

    // Generated dates
    expect(screen.getByText('Mar 1, 2026')).toBeInTheDocument();
    expect(screen.getByText('Mar 10, 2026')).toBeInTheDocument();
  });

  it('test_plan_gating_shows_upgrade', async () => {
    // Override user to free plan via the mutable authState object
    authState.user = { ...authState.user, plan: 'free' };

    render(<ReportsPage />);

    // Upgrade CTA card visible immediately (no API call needed)
    expect(screen.getByTestId('upgrade-cta-card')).toBeInTheDocument();
    expect(screen.getByTestId('upgrade-cta-mock')).toBeInTheDocument();

    // Reports API should NOT have been called
    expect(mockList).not.toHaveBeenCalled();

    // Table should not be visible
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('test_delete_report', async () => {
    render(<ReportsPage />);

    // Wait for reports to load
    await waitFor(() => {
      expect(screen.getByTestId('report-row-1')).toBeInTheDocument();
    });

    // Click delete on the first report
    fireEvent.click(screen.getByTestId('delete-report-1'));

    // Confirmation dialog should appear
    await waitFor(() => {
      expect(screen.getByText('Delete Report')).toBeInTheDocument();
    });

    // Click confirm delete button in the dialog footer
    fireEvent.click(screen.getByTestId('confirm-delete-button'));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith(1);
    });

    // Report row 1 should be removed
    await waitFor(() => {
      expect(screen.queryByTestId('report-row-1')).not.toBeInTheDocument();
    });

    // Report row 2 should still be there
    expect(screen.getByTestId('report-row-2')).toBeInTheDocument();
  });
});
