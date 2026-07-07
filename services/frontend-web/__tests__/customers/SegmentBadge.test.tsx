import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SegmentBadge } from '../../components/customers/SegmentBadge';

describe('SegmentBadge', () => {
  it('renders the human label for a known slug', () => {
    render(<SegmentBadge segment="power_user" />);
    expect(screen.getByTestId('segment-badge')).toHaveTextContent('Power User');
  });

  it('renders "At Risk" label for at_risk slug', () => {
    render(<SegmentBadge segment="at_risk" />);
    expect(screen.getByTestId('segment-badge')).toHaveTextContent('At Risk');
  });

  it('renders a neutral "Unsegmented" chip when segment is null', () => {
    render(<SegmentBadge segment={null} />);
    expect(screen.getByTestId('segment-badge')).toHaveTextContent('Unsegmented');
  });

  it('renders a neutral "Unsegmented" chip when segment is undefined', () => {
    render(<SegmentBadge segment={undefined} />);
    expect(screen.getByTestId('segment-badge')).toHaveTextContent('Unsegmented');
  });

  it('renders a neutral "Unsegmented" chip for the literal "unsegmented" slug', () => {
    render(<SegmentBadge segment="unsegmented" />);
    expect(screen.getByTestId('segment-badge')).toHaveTextContent('Unsegmented');
  });

  it('does not crash on an unknown slug and falls back to unsegmented', () => {
    render(<SegmentBadge segment="something_unexpected" />);
    expect(screen.getByTestId('segment-badge')).toHaveAttribute('data-segment', 'unsegmented');
  });
});
