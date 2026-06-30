import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/customers', () => ({
  customersAPI: {
    getByEmail: vi.fn(),
  },
}));

import { customersAPI } from '@/lib/api/customers';
import { CrmCompanyCard } from '../../components/customers/CrmCompanyCard';

const mockGetByEmail = customersAPI.getByEmail as ReturnType<typeof vi.fn>;

const mockProfileWithCrm = {
  customer_email: 'alice@acme.com',
  customer_name: 'Alice',
  health_score: 80,
  risk_level: 'healthy',
  confidence_level: 'high',
  feedback_count: 10,
  last_feedback_at: null,
  churn_risk_component: 50,
  sentiment_component: 60,
  resolution_component: 70,
  frequency_component: 55,
  llm_analysis_summary: null,
  llm_recommended_actions: null,
  llm_risk_drivers: null,
  llm_urgency: null,
  llm_analysis_type: null,
  llm_analyzed_at: null,
  llm_actions: null,
  llm_analysis: null,
  is_archived: false,
  created_at: '2026-01-01T00:00:00Z',
  crm_company_name: 'Acme Corp',
  crm_lifecycle_stage: 'customer',
  crm_arr: 50000,
  crm_renewal_date: '2026-12-01T00:00:00Z',
  crm_deal_name: 'Enterprise Renewal',
  crm_deal_stage: 'negotiation',
  crm_deal_amount: 25000,
  confidence_score: null,
};

const mockProfileNoCrm = {
  ...mockProfileWithCrm,
  crm_company_name: null,
  crm_lifecycle_stage: null,
  crm_arr: null,
  crm_renewal_date: null,
  crm_deal_name: null,
  crm_deal_stage: null,
  crm_deal_amount: null,
};

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('CrmCompanyCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders company name when CRM data is present', async () => {
    mockGetByEmail.mockResolvedValue(mockProfileWithCrm);
    renderWithQueryClient(<CrmCompanyCard email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    });
  });

  it('renders lifecycle stage when CRM data is present', async () => {
    mockGetByEmail.mockResolvedValue(mockProfileWithCrm);
    renderWithQueryClient(<CrmCompanyCard email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/customer/i)).toBeInTheDocument();
    });
  });

  it('renders deal name when CRM data is present', async () => {
    mockGetByEmail.mockResolvedValue(mockProfileWithCrm);
    renderWithQueryClient(<CrmCompanyCard email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText('Enterprise Renewal')).toBeInTheDocument();
    });
  });

  it('shows empty state when all CRM fields are null', async () => {
    mockGetByEmail.mockResolvedValue(mockProfileNoCrm);
    renderWithQueryClient(<CrmCompanyCard email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/no crm data|connect hubspot|hubspot/i)).toBeInTheDocument();
    });
  });

  it('shows skeleton while loading', () => {
    mockGetByEmail.mockReturnValue(new Promise(() => {})); // never resolves
    renderWithQueryClient(<CrmCompanyCard email="alice@acme.com" />);
    expect(document.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('shows empty state on error (no crash, retry:false)', async () => {
    mockGetByEmail.mockRejectedValue(new Error('Network error'));
    renderWithQueryClient(<CrmCompanyCard email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/no crm data|connect hubspot|hubspot/i)).toBeInTheDocument();
    });
  });

  it('has CRM / Company title', async () => {
    mockGetByEmail.mockResolvedValue(mockProfileWithCrm);
    renderWithQueryClient(<CrmCompanyCard email="alice@acme.com" />);
    await waitFor(() => {
      expect(screen.getByText(/CRM/i)).toBeInTheDocument();
    });
  });
});
