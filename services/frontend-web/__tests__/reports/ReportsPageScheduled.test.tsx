import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ReportsPage from '@/app/(dashboard)/reports/page';
import type { Report } from '@/lib/api/reports';
import type { ScheduledReport } from '@/lib/api/scheduled-reports';

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

// ─── Mock auth context ────────────────────────────────────────────────────────

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// ─── Mock reportsAPI (same structure as ReportsPage.test.tsx) ─────────────────

const mockReports: Report[] = [
  {
    id: 1,
    report_type: 'executive_summary',
    date_range_days: 30,
    title: 'Executive Summary — Feb 2026',
    sections: [],
    metadata: {},
    pdf_generated: true,
    created_at: '2026-03-01T10:00:00Z',
  },
];

const { mockReportsList, mockReportsDelete, mockReportsDownloadPDF } = vi.hoisted(() => ({
  mockReportsList: vi.fn(),
  mockReportsDelete: vi.fn(),
  mockReportsDownloadPDF: vi.fn(),
}));

vi.mock('@/lib/api/reports', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/reports')>();
  return {
    ...actual,
    reportsAPI: {
      list: mockReportsList,
      get: vi.fn(),
      delete: mockReportsDelete,
      downloadPDF: mockReportsDownloadPDF,
    },
  };
});

// ─── Mock scheduledReportsAPI ─────────────────────────────────────────────────

const { mockList, mockCreate, mockUpdate, mockDelete, mockToggle } = vi.hoisted(() => ({
  mockList: vi.fn(),
  mockCreate: vi.fn(),
  mockUpdate: vi.fn(),
  mockDelete: vi.fn(),
  mockToggle: vi.fn(),
}));

vi.mock('@/lib/api/scheduled-reports', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/scheduled-reports')>();
  return {
    ...actual,
    scheduledReportsAPI: {
      list: mockList,
      create: mockCreate,
      update: mockUpdate,
      delete: mockDelete,
      toggle: mockToggle,
    },
  };
});

// ─── Mock ReportPreview (avoid Recharts complexity) ───────────────────────────

vi.mock('@/components/copilot/ReportPreview', () => ({
  ReportPreview: ({ title }: { title?: string }) => (
    <div data-testid="report-preview-mock">{title}</div>
  ),
}));

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const adminUser = {
  id: 1,
  email: 'owner@test.com',
  organization_id: 1,
  role: 'admin',
  plan: 'enterprise',
  is_system_admin: false,
};

const memberUser = {
  ...adminUser,
  email: 'member@test.com',
  role: 'member',
};

const mockSchedules: ScheduledReport[] = [
  {
    id: 1,
    report_type: 'executive_summary',
    date_range_days: 30,
    cadence: 'weekly',
    hour_utc: 9,
    day_of_week: 1,
    day_of_month: null,
    recipients: ['owner@test.com'],
    enabled: true,
    last_run_at: '2026-08-25T09:00:00Z',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  },
  {
    id: 2,
    report_type: 'customer_health',
    date_range_days: 7,
    cadence: 'monthly',
    hour_utc: 9,
    day_of_week: null,
    day_of_month: 15,
    recipients: ['owner@test.com', 'cs@test.com'],
    enabled: false,
    last_run_at: null,
    created_at: '2026-08-02T00:00:00Z',
    updated_at: '2026-08-02T00:00:00Z',
  },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function openScheduledTab() {
  const user = userEvent.setup();
  await user.click(screen.getByRole('tab', { name: 'Scheduled' }));
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ReportsPage — Scheduled tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: adminUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    mockReportsList.mockResolvedValue(mockReports);
    mockReportsDelete.mockResolvedValue(undefined);
    mockReportsDownloadPDF.mockResolvedValue(undefined);
    mockList.mockResolvedValue(mockSchedules);
    mockCreate.mockResolvedValue({
      ...mockSchedules[0],
      id: 99,
      report_type: 'customer_health',
    });
    mockDelete.mockResolvedValue(undefined);
    mockToggle.mockResolvedValue({ ...mockSchedules[0], enabled: false });
  });

  it('test_scheduled_tab_empty_state', async () => {
    mockList.mockResolvedValueOnce([]);

    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
    expect(screen.getByText('No schedules yet')).toBeInTheDocument();
  });

  it('test_scheduled_tab_renders_rows_with_type_cadence_recipients_last_run', async () => {
    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('schedule-row-1')).toBeInTheDocument();
    });
    expect(screen.getByTestId('schedule-row-2')).toBeInTheDocument();

    const badges = screen.getAllByTestId('schedule-type-badge');
    expect(badges[0]).toHaveTextContent('Executive Summary');
    expect(badges[1]).toHaveTextContent('Customer Health');

    expect(screen.getByText('Weekly · Mon 09:00 UTC')).toBeInTheDocument();
    expect(screen.getByText('Monthly · 15th · 09:00 UTC')).toBeInTheDocument();

    expect(screen.getByText('1 recipient')).toBeInTheDocument();
    expect(screen.getByText('2 recipients')).toBeInTheDocument();

    expect(screen.getByText('Aug 25, 2026')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('test_toggle_schedule_calls_toggle_and_updates_state_with_toast', async () => {
    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('toggle-schedule-1')).toBeInTheDocument();
    });
    expect(screen.getByTestId('toggle-schedule-1')).toHaveAttribute('data-state', 'checked');

    const user = userEvent.setup();
    await user.click(screen.getByTestId('toggle-schedule-1'));

    await waitFor(() => {
      expect(mockToggle).toHaveBeenCalledWith(1);
    });
    await waitFor(() => {
      expect(screen.getByTestId('toggle-schedule-1')).toHaveAttribute(
        'data-state',
        'unchecked'
      );
    });
    const toastModule = await import('sonner');
    await waitFor(() => {
      expect(toastModule.toast.success).toHaveBeenCalledWith('Schedule paused');
    });
  });

  it('test_toggle_schedule_updates_optimistically_while_pending', async () => {
    mockToggle.mockReturnValue(new Promise(() => {}));

    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('toggle-schedule-1')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId('toggle-schedule-1'));

    await waitFor(() => {
      expect(screen.getByTestId('toggle-schedule-1')).toHaveAttribute(
        'data-state',
        'unchecked'
      );
    });
    expect(mockToggle).toHaveBeenCalledWith(1);
  });

  it('test_delete_schedule_flows_through_confirm_dialog', async () => {
    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('delete-schedule-2')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId('delete-schedule-2'));

    await waitFor(() => {
      expect(screen.getByText('Delete Schedule')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('confirm-delete-schedule-button'));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith(2);
    });
    await waitFor(() => {
      expect(screen.queryByTestId('schedule-row-2')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('schedule-row-1')).toBeInTheDocument();
  });

  it('test_create_schedule_weekly_sends_day_of_week', async () => {
    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('new-schedule-button')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId('new-schedule-button'));
    await screen.findByRole('heading', { name: 'New Schedule' });

    await user.click(screen.getByTestId('report-type-select'));
    await user.click(await screen.findByRole('option', { name: 'Customer Health' }));

    await user.click(screen.getByTestId('create-schedule-submit'));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith({
        report_type: 'customer_health',
        date_range_days: 30,
        cadence: 'weekly',
        hour_utc: 9,
        day_of_week: 1,
        recipients: ['owner@test.com'],
      });
    });
    const payload = mockCreate.mock.calls[0][0];
    expect(payload).not.toHaveProperty('day_of_month');

    await waitFor(() => {
      expect(screen.getByTestId('schedule-row-99')).toBeInTheDocument();
    });
  });

  it('test_create_schedule_monthly_sends_day_of_month', async () => {
    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('new-schedule-button')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId('new-schedule-button'));
    await screen.findByRole('heading', { name: 'New Schedule' });

    await user.click(screen.getByTestId('cadence-select'));
    await user.click(await screen.findByRole('option', { name: 'Monthly' }));

    await waitFor(() => {
      expect(screen.getByTestId('day-of-month-select')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('day-of-week-select')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('day-of-month-select'));
    await user.click(await screen.findByRole('option', { name: '15' }));

    await user.click(screen.getByTestId('create-schedule-submit'));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith({
        report_type: 'executive_summary',
        date_range_days: 30,
        cadence: 'monthly',
        hour_utc: 9,
        day_of_month: 15,
        recipients: ['owner@test.com'],
      });
    });
    const payload = mockCreate.mock.calls[0][0];
    expect(payload).not.toHaveProperty('day_of_week');
  });

  it('test_create_schedule_daily_sends_neither_day_field', async () => {
    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('new-schedule-button')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId('new-schedule-button'));
    await screen.findByRole('heading', { name: 'New Schedule' });

    await user.click(screen.getByTestId('cadence-select'));
    await user.click(await screen.findByRole('option', { name: 'Daily' }));

    expect(screen.queryByTestId('day-of-week-select')).not.toBeInTheDocument();
    expect(screen.queryByTestId('day-of-month-select')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('create-schedule-submit'));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith({
        report_type: 'executive_summary',
        date_range_days: 30,
        cadence: 'daily',
        hour_utc: 9,
        recipients: ['owner@test.com'],
      });
    });
    const payload = mockCreate.mock.calls[0][0];
    expect(payload).not.toHaveProperty('day_of_week');
    expect(payload).not.toHaveProperty('day_of_month');
  });

  it('test_create_schedule_parses_and_dedupes_recipients', async () => {
    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('new-schedule-button')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId('new-schedule-button'));
    await screen.findByRole('heading', { name: 'New Schedule' });

    const recipientsInput = screen.getByTestId('schedule-recipients-input');
    expect((recipientsInput as HTMLTextAreaElement).value).toBe('owner@test.com');

    fireEvent.change(recipientsInput, {
      target: { value: 'a@b.com, a@b.com\nc@d.com' },
    });

    await user.click(screen.getByTestId('create-schedule-submit'));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          recipients: ['a@b.com', 'c@d.com'],
        })
      );
    });
  });

  it('test_member_sees_read_only_list_without_controls', async () => {
    mockUseAuth.mockReturnValue({
      user: memberUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(<ReportsPage />);
    await openScheduledTab();

    await waitFor(() => {
      expect(screen.getByTestId('schedule-row-1')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('new-schedule-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('toggle-schedule-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('delete-schedule-1')).not.toBeInTheDocument();
  });
});