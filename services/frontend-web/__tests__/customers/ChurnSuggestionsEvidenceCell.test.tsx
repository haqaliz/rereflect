import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { EvidenceCell } from '../../app/(dashboard)/customers/churn-suggestions/page';

// CHARACTERIZATION (non-negotiable, per plan): EvidenceCell is a shared
// component read by every provider's row. This test locks in today's CRM
// rendering byte-for-byte BEFORE the usage_decline branch is added, so a
// later refactor can't silently regress hubspot/salesforce orgs.

describe('EvidenceCell — CRM characterization (must not regress)', () => {
  it('renders a hubspot deal_name/amount/stage payload identically to today', () => {
    const { container } = render(
      <EvidenceCell
        evidence={{ deal_name: 'Acme Renewal', amount: 5000, stage: 'Closed Lost' }}
      />
    );
    expect(container.innerHTML).toBe(
      '<div class="text-sm"><p class="font-medium text-foreground">Acme Renewal</p><p class="text-xs text-muted-foreground">$5,000 · Closed Lost</p></div>'
    );
  });

  it('renders a salesforce opportunity_name/type payload identically to today', () => {
    const { container } = render(
      <EvidenceCell evidence={{ opportunity_name: 'Globex Deal', type: 'New Business' }} />
    );
    expect(container.innerHTML).toBe(
      '<div class="text-sm"><p class="font-medium text-foreground">Globex Deal</p><p class="text-xs text-muted-foreground">New Business</p></div>'
    );
  });

  it('renders the "No CRM detail captured" fallback for null evidence, unchanged', () => {
    const { container } = render(<EvidenceCell evidence={null} />);
    expect(container.innerHTML).toBe(
      '<span class="text-sm text-muted-foreground italic">No CRM detail captured</span>'
    );
  });

  it('renders the "No CRM detail captured" fallback for empty-object evidence, unchanged', () => {
    const { container } = render(<EvidenceCell evidence={{}} />);
    expect(container.innerHTML).toBe(
      '<span class="text-sm text-muted-foreground italic">No CRM detail captured</span>'
    );
  });
});
