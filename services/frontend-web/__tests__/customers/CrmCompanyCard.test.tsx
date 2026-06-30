import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { CrmCompanyCard } from '../../components/customers/CrmCompanyCard';

const crmWithData = {
  crm_company_name: 'Acme Corp',
  crm_lifecycle_stage: 'customer',
  crm_arr: 50000,
  crm_renewal_date: '2026-12-01T00:00:00Z',
  crm_deal_name: 'Enterprise Renewal',
  crm_deal_stage: 'negotiation',
  crm_deal_amount: 25000,
};

const crmEmpty = {
  crm_company_name: null,
  crm_lifecycle_stage: null,
  crm_arr: null,
  crm_renewal_date: null,
  crm_deal_name: null,
  crm_deal_stage: null,
  crm_deal_amount: null,
};

describe('CrmCompanyCard', () => {
  it('renders company name when CRM data is present', () => {
    render(<CrmCompanyCard crm={crmWithData} />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });

  it('renders lifecycle stage when CRM data is present', () => {
    render(<CrmCompanyCard crm={crmWithData} />);
    expect(screen.getByText(/customer/i)).toBeInTheDocument();
  });

  it('renders deal name when CRM data is present', () => {
    render(<CrmCompanyCard crm={crmWithData} />);
    expect(screen.getByText('Enterprise Renewal')).toBeInTheDocument();
  });

  it('shows empty state when all CRM fields are null', () => {
    render(<CrmCompanyCard crm={crmEmpty} />);
    expect(screen.getByText(/no crm data|connect hubspot|hubspot/i)).toBeInTheDocument();
  });

  it('has CRM / Company title', () => {
    render(<CrmCompanyCard crm={crmWithData} />);
    expect(screen.getByText(/CRM/i)).toBeInTheDocument();
  });
});
