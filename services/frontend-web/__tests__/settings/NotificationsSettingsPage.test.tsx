import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/notifications',
}));

// Mock AuthContext - Pro plan user by default
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock notifications API
vi.mock('@/lib/api/notifications', () => ({
  notificationsAPI: {
    getPreferences: vi.fn(),
    updatePreferences: vi.fn(),
    getRetention: vi.fn(),
  },
}));

// Mock preferences API
vi.mock('@/lib/api/preferences', () => ({
  preferencesAPI: {
    get: vi.fn(),
    update: vi.fn(),
  },
}));

// Mock icon components
vi.mock('@/components/icons/SlackIcon', () => ({
  SlackIcon: ({ className }: { className?: string }) => (
    <svg data-testid="slack-icon" className={className} />
  ),
}));
vi.mock('@/components/icons/IntercomIcon', () => ({
  IntercomIcon: ({ className }: { className?: string }) => (
    <svg data-testid="intercom-icon" className={className} />
  ),
}));

import { notificationsAPI } from '@/lib/api/notifications';
import { preferencesAPI } from '@/lib/api/preferences';
import NotificationsSettingsPage from '../../app/(dashboard)/settings/notifications/page';

const mockRetention = {
  types: [],
  total_extra_days: 0,
  total_monthly_cost: 0,
  min_days: 30,
  max_days: 365,
  price_per_day: 0.10,
};

const mockUserPrefs = {
  daily_digest_enabled: true,
  daily_digest_hour: 8,
  weekly_digest_enabled: false,
  weekly_digest_hour: 9,
  weekly_digest_day: 1,
};

const basePreferences = [
  { alert_type: 'urgent_feedback', is_enabled: true, channel_email: false, channel_slack: true, channel_inapp: true, channel_intercom: false, threshold_value: null, retention_days: 30 },
  { alert_type: 'sentiment_spike', is_enabled: true, channel_email: false, channel_slack: true, channel_inapp: true, channel_intercom: false, threshold_value: 50, retention_days: 30 },
  { alert_type: 'churn_risk', is_enabled: true, channel_email: false, channel_slack: true, channel_inapp: true, channel_intercom: false, threshold_value: null, retention_days: 30 },
  { alert_type: 'volume_spike', is_enabled: true, channel_email: false, channel_slack: true, channel_inapp: true, channel_intercom: false, threshold_value: 2.0, retention_days: 30 },
  { alert_type: 'feedback_assigned', is_enabled: true, channel_email: false, channel_slack: false, channel_inapp: true, channel_intercom: false, threshold_value: null, retention_days: 30 },
  { alert_type: 'status_changed', is_enabled: true, channel_email: false, channel_slack: false, channel_inapp: true, channel_intercom: false, threshold_value: null, retention_days: 30 },
  { alert_type: 'note_added', is_enabled: true, channel_email: false, channel_slack: false, channel_inapp: true, channel_intercom: false, threshold_value: null, retention_days: 30 },
];

const customerHealthDropPref = {
  alert_type: 'customer_health_drop',
  is_enabled: true,
  channel_email: false,
  channel_slack: true,
  channel_inapp: true,
  channel_intercom: false,
  threshold_value: 50,
  drop_threshold: 15,
  retention_days: 30,
};

function setupMocks(plan = 'pro', includeHealthDropPref = true) {
  mockUseAuth.mockReturnValue({
    user: { id: 1, email: 'test@test.com', role: 'owner', plan, organization_id: 1, is_system_admin: false },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  });

  const prefs = includeHealthDropPref
    ? [...basePreferences, customerHealthDropPref]
    : basePreferences;

  (notificationsAPI.getPreferences as ReturnType<typeof vi.fn>).mockResolvedValue({
    preferences: prefs,
  });
  (notificationsAPI.updatePreferences as ReturnType<typeof vi.fn>).mockResolvedValue({
    preferences: prefs,
  });
  (notificationsAPI.getRetention as ReturnType<typeof vi.fn>).mockResolvedValue(mockRetention);
  (preferencesAPI.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockUserPrefs);
}

function setupLocalStorage() {
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: vi.fn(() => 'mock-token'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    },
    writable: true,
  });
}

function getAlertPreferencesRow(alertType: string) {
  return document.querySelector(`[data-testid="alert-row-${alertType}"]`);
}

async function openCustomizeDialog(alertType: string) {
  await waitFor(() => {
    expect(getAlertPreferencesRow(alertType)).toBeInTheDocument();
  });

  const row = getAlertPreferencesRow(alertType)!;
  // The row has a Switch (role=switch) and a Customize button — target the non-switch button
  const allButtons = row.querySelectorAll('button');
  const customizeBtn = Array.from(allButtons).find(
    (btn) => btn.getAttribute('role') !== 'switch'
  );
  expect(customizeBtn).toBeInTheDocument();
  fireEvent.click(customizeBtn!);

  await waitFor(() => {
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
}

describe('NotificationsSettingsPage - Customer Health Drop row', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupLocalStorage();
  });

  it('renders "Customer Health Drop" row in alert preferences table for Pro plan', async () => {
    setupMocks('pro');
    render(<NotificationsSettingsPage />);

    await waitFor(() => {
      expect(getAlertPreferencesRow('customer_health_drop')).toBeInTheDocument();
    });

    const row = getAlertPreferencesRow('customer_health_drop')!;
    expect(within(row).getByText('Customer Health Drop')).toBeInTheDocument();
  });

  it('does not render "Customer Health Drop" row for Free plan users', async () => {
    setupMocks('free', false);
    render(<NotificationsSettingsPage />);

    await waitFor(() => {
      // Wait for the page to finish loading (other alert types are visible)
      expect(getAlertPreferencesRow('urgent_feedback')).toBeInTheDocument();
    });

    expect(getAlertPreferencesRow('customer_health_drop')).not.toBeInTheDocument();
  });

  it('renders "Customer Health Drop" row for Business plan users', async () => {
    setupMocks('business');
    render(<NotificationsSettingsPage />);

    await waitFor(() => {
      expect(getAlertPreferencesRow('customer_health_drop')).toBeInTheDocument();
    });

    const row = getAlertPreferencesRow('customer_health_drop')!;
    expect(within(row).getByText('Customer Health Drop')).toBeInTheDocument();
  });

  it('renders "Customer Health Drop" row for Enterprise plan users', async () => {
    setupMocks('enterprise');
    render(<NotificationsSettingsPage />);

    await waitFor(() => {
      expect(getAlertPreferencesRow('customer_health_drop')).toBeInTheDocument();
    });

    const row = getAlertPreferencesRow('customer_health_drop')!;
    expect(within(row).getByText('Customer Health Drop')).toBeInTheDocument();
  });

  it('renders a toggle switch for the Customer Health Drop row', async () => {
    setupMocks('pro');
    render(<NotificationsSettingsPage />);

    await waitFor(() => {
      expect(getAlertPreferencesRow('customer_health_drop')).toBeInTheDocument();
    });

    const row = getAlertPreferencesRow('customer_health_drop')!;
    const toggle = row.querySelector('[role="switch"]');
    expect(toggle).toBeInTheDocument();
  });

  it('opens customize dialog when clicking Customize on Customer Health Drop row', async () => {
    setupMocks('pro');
    render(<NotificationsSettingsPage />);

    await openCustomizeDialog('customer_health_drop');

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('NotificationsSettingsPage - Customer Health Drop channel checkboxes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupLocalStorage();
    setupMocks('pro');
  });

  it('shows In-App channel in dialog', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('In-App')).toBeInTheDocument();
  });

  it('shows Slack channel in dialog', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Slack')).toBeInTheDocument();
  });

  it('shows Email channel in dialog', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Email')).toBeInTheDocument();
  });

  it('In-App channel switch is on by default (channel_inapp: true)', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const dialog = screen.getByRole('dialog');
    const switches = within(dialog).getAllByRole('switch');
    // Channel order: In-App, Slack, Intercom, Email
    // In-App is first and should be on (aria-checked="true")
    const inAppSwitch = switches[0];
    expect(inAppSwitch).toHaveAttribute('aria-checked', 'true');
  });

  it('Email channel switch is off by default (channel_email: false)', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const dialog = screen.getByRole('dialog');
    const switches = within(dialog).getAllByRole('switch');
    // Channel order: In-App, Slack, Intercom, Email
    // Email is last and should be off (aria-checked="false")
    const emailSwitch = switches[switches.length - 1];
    expect(emailSwitch).toHaveAttribute('aria-checked', 'false');
  });
});

describe('NotificationsSettingsPage - Customer Health Drop threshold inputs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupLocalStorage();
    setupMocks('pro');
  });

  it('renders absolute threshold input with label "Alert when score drops below"', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    expect(screen.getByLabelText('Alert when score drops below')).toBeInTheDocument();
  });

  it('renders absolute threshold input with default value 50', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const input = screen.getByLabelText('Alert when score drops below');
    expect(input).toHaveValue(50);
  });

  it('absolute threshold input has min=1 and max=99', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const input = screen.getByLabelText('Alert when score drops below');
    expect(input).toHaveAttribute('min', '1');
    expect(input).toHaveAttribute('max', '99');
  });

  it('renders drop threshold input with label "Alert on drop of"', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    expect(screen.getByLabelText('Alert on drop of')).toBeInTheDocument();
  });

  it('renders drop threshold input with default value 15', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const input = screen.getByLabelText('Alert on drop of');
    expect(input).toHaveValue(15);
  });

  it('renders "or more points" suffix next to drop threshold', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    expect(screen.getByText('or more points')).toBeInTheDocument();
  });

  it('drop threshold input has min=5 and max=50', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const input = screen.getByLabelText('Alert on drop of');
    expect(input).toHaveAttribute('min', '5');
    expect(input).toHaveAttribute('max', '50');
  });
});

describe('NotificationsSettingsPage - Customer Health Drop validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupLocalStorage();
    setupMocks('pro');
  });

  it('absolute threshold accepts values in range 1-99', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const input = screen.getByLabelText('Alert when score drops below');
    fireEvent.change(input, { target: { value: '75' } });
    expect(input).toHaveValue(75);
  });

  it('drop threshold accepts values in range 5-50', async () => {
    render(<NotificationsSettingsPage />);
    await openCustomizeDialog('customer_health_drop');

    const input = screen.getByLabelText('Alert on drop of');
    fireEvent.change(input, { target: { value: '25' } });
    expect(input).toHaveValue(25);
  });
});

describe('NotificationsSettingsPage - Customer Health Drop save behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupLocalStorage();
  });

  it('saving preferences calls PUT API with correct payload including drop_threshold', async () => {
    setupMocks('pro');
    render(<NotificationsSettingsPage />);

    await waitFor(() => {
      expect(getAlertPreferencesRow('customer_health_drop')).toBeInTheDocument();
    });

    // Toggle the switch in the main alert row to trigger hasChanges (no dialog involved)
    const row = getAlertPreferencesRow('customer_health_drop')!;
    const toggle = row.querySelector('[role="switch"]');
    fireEvent.click(toggle!);

    // Save Changes button should appear
    await waitFor(() => {
      expect(screen.getByText('Save Changes')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Save Changes'));

    await waitFor(() => {
      expect(notificationsAPI.updatePreferences).toHaveBeenCalled();
      const callArgs = (notificationsAPI.updatePreferences as ReturnType<typeof vi.fn>).mock.calls[0][0];
      const healthDropPref = callArgs.find((p: { alert_type: string }) => p.alert_type === 'customer_health_drop');
      expect(healthDropPref).toBeDefined();
      // threshold_value should be 50 (default), drop_threshold should be 15 (default)
      expect(healthDropPref.threshold_value).toBe(50);
      expect(healthDropPref.drop_threshold).toBe(15);
    });
  });

  it('loading preferences populates fields from GET API response', async () => {
    const customPref = {
      ...customerHealthDropPref,
      threshold_value: 35,
      drop_threshold: 20,
    };
    mockUseAuth.mockReturnValue({
      user: { id: 1, email: 'test@test.com', role: 'owner', plan: 'pro', organization_id: 1, is_system_admin: false },
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    (notificationsAPI.getPreferences as ReturnType<typeof vi.fn>).mockResolvedValue({
      preferences: [...basePreferences, customPref],
    });
    (notificationsAPI.updatePreferences as ReturnType<typeof vi.fn>).mockResolvedValue({
      preferences: [...basePreferences, customPref],
    });
    (notificationsAPI.getRetention as ReturnType<typeof vi.fn>).mockResolvedValue(mockRetention);
    (preferencesAPI.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockUserPrefs);

    render(<NotificationsSettingsPage />);

    await waitFor(() => {
      expect(getAlertPreferencesRow('customer_health_drop')).toBeInTheDocument();
    });

    await openCustomizeDialog('customer_health_drop');

    const absInput = screen.getByLabelText('Alert when score drops below');
    expect(absInput).toHaveValue(35);

    const dropInput = screen.getByLabelText('Alert on drop of');
    expect(dropInput).toHaveValue(20);
  });
});

describe('NotificationsSettingsPage - Customer Health Drop toggle disables inputs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupLocalStorage();
    setupMocks('pro');
  });

  it('disabling the toggle disables the row customize button', async () => {
    render(<NotificationsSettingsPage />);

    await waitFor(() => {
      expect(getAlertPreferencesRow('customer_health_drop')).toBeInTheDocument();
    });

    const row = getAlertPreferencesRow('customer_health_drop')!;
    const toggle = row.querySelector('[role="switch"]');
    expect(toggle).toBeInTheDocument();

    // Toggle off
    fireEvent.click(toggle!);

    await waitFor(() => {
      const allButtons = row.querySelectorAll('button');
      const customizeBtn = Array.from(allButtons).find(
        (btn) => btn.getAttribute('role') !== 'switch'
      );
      expect(customizeBtn).toBeDisabled();
    });
  });
});
