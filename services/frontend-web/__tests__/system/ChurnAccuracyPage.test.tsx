import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({}),
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock churn-accuracy API — include formatMetricPercent so components can import it
vi.mock('@/lib/api/churn-accuracy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/churn-accuracy')>();
  return {
    ...actual,
    getSystemAccuracy: vi.fn(),
    getAccuracyCard: vi.fn(),
    getOrgAccuracyHistory: vi.fn(),
  };
});

import { getSystemAccuracy } from '@/lib/api/churn-accuracy';
import ChurnAccuracyPage from '@/app/(dashboard)/system/churn-accuracy/page';

const systemAdminUser = {
  id: 1,
  email: 'admin@system.com',
  role: 'owner',
  plan: 'enterprise',
  organization_id: 1,
  is_system_admin: true,
};

const regularUser = { ...systemAdminUser, is_system_admin: false };

const mockSystemAccuracy = {
  global_model_id: 1,
  global_f1: 0.72,
  global_label_count: 5420,
  total_orgs_using_global: 14,
  total_orgs_with_dedicated_model: 6,
  orgs: [
    {
      organization_id: 10,
      organization_name: 'Acme Corp',
      label_count: 300,
      f1: 0.85,
      last_refit_at: '2026-05-12T07:45:00Z',
      is_using_global_fallback: false,
    },
    {
      organization_id: 11,
      organization_name: 'Beta Inc',
      label_count: 50,
      f1: null,
      last_refit_at: null,
      is_using_global_fallback: true,
    },
    {
      organization_id: 12,
      organization_name: 'Gamma LLC',
      label_count: 180,
      f1: 0.78,
      last_refit_at: '2026-05-12T08:00:00Z',
      is_using_global_fallback: false,
    },
  ],
};

const emptySystemAccuracy = {
  global_model_id: null,
  global_f1: null,
  global_label_count: 0,
  total_orgs_using_global: 0,
  total_orgs_with_dedicated_model: 0,
  orgs: [],
};

describe('ChurnAccuracyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Test 9: redirects non-system-admin users
  it('redirects non-system-admin users to /dashboard', async () => {
    mockUseAuth.mockReturnValue({ user: regularUser });
    vi.mocked(getSystemAccuracy).mockResolvedValue(mockSystemAccuracy);

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/dashboard');
    });
  });

  // Test 10: fetches and renders system accuracy on mount
  it('fetches and renders system accuracy data on mount', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getSystemAccuracy).mockResolvedValue(mockSystemAccuracy);

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      expect(getSystemAccuracy).toHaveBeenCalledOnce();
      expect(screen.getByText(/Acme Corp/)).toBeInTheDocument();
    });
  });

  // Test 11: renders global model summary stats
  it('renders global model summary stats', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getSystemAccuracy).mockResolvedValue(mockSystemAccuracy);

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      // global_f1 = 0.72 → "72%"
      expect(screen.getByText(/72%/)).toBeInTheDocument();
      // global_label_count
      expect(screen.getByText(/5,?420/)).toBeInTheDocument();
    });
  });

  // Test 12: renders org table rows
  it('renders a table row for each organization', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getSystemAccuracy).mockResolvedValue(mockSystemAccuracy);

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument();
      expect(screen.getByText('Beta Inc')).toBeInTheDocument();
      expect(screen.getByText('Gamma LLC')).toBeInTheDocument();
    });
  });

  // Test 13: shows count of orgs using global vs dedicated
  it('shows count of orgs using global vs dedicated model', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getSystemAccuracy).mockResolvedValue(mockSystemAccuracy);

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      // total_orgs_using_global = 14 appears as stat card value
      expect(screen.getByText('14')).toBeInTheDocument();
      // total_orgs_with_dedicated_model = 6 appears as stat card value
      expect(screen.getByText('6')).toBeInTheDocument();
    });
  });

  // Test 14: drill-in link navigates to /system/churn-accuracy/[id]
  it('renders drill-in links to /system/churn-accuracy/[orgId]', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getSystemAccuracy).mockResolvedValue(mockSystemAccuracy);

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    });

    const drillLinks = screen.getAllByRole('link');
    const drillHrefs = drillLinks.map((l) => l.getAttribute('href'));
    expect(drillHrefs).toContain('/system/churn-accuracy/10');
  });

  // Test 15: empty state when no orgs have labels
  it('shows empty state when no orgs are returned', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getSystemAccuracy).mockResolvedValue(emptySystemAccuracy);

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      expect(screen.getByText(/no organizations/i)).toBeInTheDocument();
    });
  });

  // Test 16: error state on API failure
  it('shows error state when API call fails', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    vi.mocked(getSystemAccuracy).mockRejectedValue(new Error('Server error'));

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  // Test 17: orgs sorted by label_count desc
  it('renders orgs sorted by label_count descending', async () => {
    mockUseAuth.mockReturnValue({ user: systemAdminUser });
    // orgs come in unsorted order from API: 300, 50, 180
    vi.mocked(getSystemAccuracy).mockResolvedValue(mockSystemAccuracy);

    render(<ChurnAccuracyPage />);

    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    });

    const rows = screen.getAllByRole('row');
    // First data row (index 1 after header) should be Acme Corp (300 labels)
    expect(rows[1]).toHaveTextContent('Acme Corp');
    // Second should be Gamma LLC (180 labels)
    expect(rows[2]).toHaveTextContent('Gamma LLC');
    // Third should be Beta Inc (50 labels)
    expect(rows[3]).toHaveTextContent('Beta Inc');
  });
});
