/**
 * Render tests for the Salesforce tile on the integrations index page (Phase 2).
 *
 * Verifies:
 * 1. When disconnected, an "Available" Salesforce tile renders under Available
 *    Integrations, linking to /settings/integrations/salesforce.
 * 2. When connected, an "Active"/"Connected" Salesforce card renders instead,
 *    and the Available tile is hidden.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const mockReplace = vi.fn();
const mockPush = vi.fn();

const stableSearchParams = new URLSearchParams();
const stableRouter = { replace: mockReplace, push: mockPush };

vi.mock('next/navigation', () => ({
  useRouter: () => stableRouter,
  useSearchParams: () => stableSearchParams,
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/lib/api/integrations', () => ({
  integrationsAPI: {
    list: vi.fn(),
  },
  TRIGGER_OPTIONS: [],
}));

vi.mock('@/lib/api/linear', () => ({
  linearAPI: {
    getStatus: vi.fn(),
    testConnection: vi.fn(),
    disconnect: vi.fn(),
  },
}));

vi.mock('@/lib/api/hubspot', () => ({
  hubspotAPI: {
    getStatus: vi.fn(),
  },
}));

vi.mock('@/lib/api/salesforce', () => ({
  salesforceAPI: {
    getStatus: vi.fn(),
    getConnectUrl: vi.fn(),
    disconnect: vi.fn(),
    test: vi.fn(),
  },
}));

vi.mock('@/lib/api/jira', () => ({
  jiraAPI: {
    getStatus: vi.fn(),
    disconnect: vi.fn(),
    testConnection: vi.fn(),
  },
}));

vi.mock('@/lib/api/zendesk', () => ({
  zendeskAPI: {
    getStatus: vi.fn(),
    disconnect: vi.fn(),
    testConnection: vi.fn(),
  },
}));

import { useAuth } from '@/contexts/AuthContext';
import { integrationsAPI } from '@/lib/api/integrations';
import { linearAPI } from '@/lib/api/linear';
import { hubspotAPI } from '@/lib/api/hubspot';
import { salesforceAPI } from '@/lib/api/salesforce';
import { jiraAPI } from '@/lib/api/jira';
import { zendeskAPI } from '@/lib/api/zendesk';
import IntegrationsPage from '../page';

function makeAuthContext(role: string) {
  return {
    user: { id: 1, email: `${role}@test.com`, role, plan: 'business', organization_id: 1, is_system_admin: false },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  };
}

describe('IntegrationsPage — Salesforce tile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (useAuth as any).mockReturnValue(makeAuthContext('owner'));
    (integrationsAPI.list as any).mockResolvedValue({ integrations: [], total: 0 });
    (linearAPI.getStatus as any).mockResolvedValue({ connected: false });
    (jiraAPI.getStatus as any).mockResolvedValue({ connected: false });
    (zendeskAPI.getStatus as any).mockResolvedValue({ connected: false });
  });

  it('shows an Available Salesforce tile linking to the detail page when disconnected', async () => {
    (hubspotAPI.getStatus as any).mockResolvedValue({ connected: false });
    (salesforceAPI.getStatus as any).mockResolvedValue({ connected: false });

    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Salesforce/i)).toBeInTheDocument();
    });

    const link = screen.getByText(/Salesforce/i).closest('a');
    expect(link).toHaveAttribute('href', '/settings/integrations/salesforce');
  });

  it('shows a Connected Salesforce card when connected, and hides the Available tile', async () => {
    (hubspotAPI.getStatus as any).mockResolvedValue({ connected: false });
    (salesforceAPI.getStatus as any).mockResolvedValue({
      connected: true,
      instance_url: 'https://acme.my.salesforce.com',
      sf_org_id: '00D000000000EXAMPLE',
      contacts_synced: 42,
      contacts_matched: 30,
      connected_at: '2026-06-01T00:00:00Z',
    });

    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getAllByText(/Connected/i).length).toBeGreaterThan(0);
    });

    // The "Available" Salesforce tile (badge text "Available" next to the
    // Salesforce label) must not render once connected — only one
    // Salesforce link (the active card) should point at the detail page.
    const links = screen.getAllByText('Salesforce').map((el) => el.closest('a'));
    const hrefs = links.filter(Boolean).map((a) => a!.getAttribute('href'));
    expect(hrefs.filter((h) => h === '/settings/integrations/salesforce')).toHaveLength(1);
  });
});
