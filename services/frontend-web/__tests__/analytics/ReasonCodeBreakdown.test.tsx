import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReasonCodeBreakdown } from '../../components/analytics/ReasonCodeBreakdown';
import type { CohortBucket } from '../../lib/api/churn-analytics';
import type { ChurnReasonCode } from '../../lib/api/churn-events';

const makeCode = (code: ChurnReasonCode, count: number) => ({ code, count });

const makeBucket = (
  label: string,
  top_reason_codes: { code: ChurnReasonCode; count: number }[],
): CohortBucket => ({
  label,
  total_customers: 100,
  churned_customers: 10,
  churn_rate: 0.1,
  avg_probability: null,
  top_reason_codes,
});

describe('ReasonCodeBreakdown', () => {
  it('renders nothing when cohorts array is empty', () => {
    const { container } = render(<ReasonCodeBreakdown cohorts={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows a segment per unique reason code', () => {
    const cohorts = [
      makeBucket('Direct', [makeCode('price', 5), makeCode('competitor', 3)]),
    ];
    render(<ReasonCodeBreakdown cohorts={cohorts} />);
    expect(screen.getByTestId('reason-segment-price')).toBeInTheDocument();
    expect(screen.getByTestId('reason-segment-competitor')).toBeInTheDocument();
  });

  it('aggregates counts when same code appears across multiple cohorts', () => {
    const cohorts = [
      makeBucket('Direct', [makeCode('price', 5)]),
      makeBucket('Organic', [makeCode('price', 7)]),
    ];
    render(<ReasonCodeBreakdown cohorts={cohorts} />);
    // Price total = 12
    expect(screen.getByTestId('reason-count-price')).toHaveTextContent('12');
  });

  it('shows label using CHURN_REASON_LABELS', () => {
    const cohorts = [
      makeBucket('Direct', [makeCode('product_quality', 4)]),
    ];
    render(<ReasonCodeBreakdown cohorts={cohorts} />);
    expect(screen.getByTestId('reason-label-product_quality')).toHaveTextContent('Product Quality');
  });

  it('shows count in legend entry', () => {
    const cohorts = [
      makeBucket('Direct', [makeCode('silent_churn', 9)]),
    ];
    render(<ReasonCodeBreakdown cohorts={cohorts} />);
    expect(screen.getByTestId('reason-count-silent_churn')).toHaveTextContent('9');
  });
});
