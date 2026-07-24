import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EvidenceCell } from '../../app/(dashboard)/customers/churn-suggestions/page';

const usageDeclineEvidence = {
  trend_state: 'declining',
  trend_pct: -42,
  baseline_active_days_14d: 12,
  current_active_days_14d: 5,
  streak_days: 9,
  streak_start_date: '2026-06-10',
  last_active_at: '2026-06-19T00:00:00Z',
  snapshot_series: [
    { date: '2026-06-01', active_days_14d: 12 },
    { date: '2026-06-08', active_days_14d: 8 },
    { date: '2026-06-15', active_days_14d: 5 },
  ],
};

describe('EvidenceCell — usage_decline evidence rendering', () => {
  it('renders the decline summary, NOT the "No CRM detail captured" fallback', () => {
    render(<EvidenceCell evidence={usageDeclineEvidence} />);
    expect(screen.queryByText(/No CRM detail captured/i)).not.toBeInTheDocument();
  });

  it('renders the trend percentage', () => {
    const { container } = render(<EvidenceCell evidence={usageDeclineEvidence} />);
    expect(container.textContent).toMatch(/-?42%/);
  });

  it('renders the baseline -> current active_days_14d transition', () => {
    const { container } = render(<EvidenceCell evidence={usageDeclineEvidence} />);
    expect(container.textContent).toMatch(/12.*(→|->).*5/);
  });

  it('renders the streak length in days', () => {
    const { container } = render(<EvidenceCell evidence={usageDeclineEvidence} />);
    expect(container.textContent).toMatch(/9-day streak/i);
  });

  it('renders the last active date', () => {
    const { container } = render(<EvidenceCell evidence={usageDeclineEvidence} />);
    const expectedDate = new Date(usageDeclineEvidence.last_active_at).toLocaleDateString();
    expect(container.textContent).toContain(expectedDate);
  });

  it('renders "n/a" (never the literal string "null") when trend_pct is null', () => {
    const { container } = render(
      <EvidenceCell evidence={{ ...usageDeclineEvidence, trend_pct: null }} />
    );
    expect(container.textContent).toMatch(/n\/a/i);
    expect(container.textContent).not.toMatch(/\bnull\b/i);
  });

  it('does NOT smuggle usage data through deal_name/opportunity_name (separate branch)', () => {
    const { container } = render(<EvidenceCell evidence={usageDeclineEvidence} />);
    // A usage_decline payload has no deal_name/opportunity_name — if the CRM
    // branch were reused, the bare trend value would render unlabeled the
    // way a deal name does. The dedicated branch always prefixes it.
    expect(container.textContent).toMatch(/usage decline/i);
  });
});
