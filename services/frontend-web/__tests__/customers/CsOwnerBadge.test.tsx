import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CsOwnerBadge } from '../../components/customers/CsOwnerBadge';

describe('CsOwnerBadge', () => {
  it('renders a clean "Unassigned" chip when owner is null', () => {
    render(<CsOwnerBadge owner={null} />);
    expect(screen.getByTestId('cs-owner-badge')).toHaveTextContent('Unassigned');
    expect(screen.getByTestId('cs-owner-badge')).toHaveAttribute('data-owner', 'unassigned');
  });

  it('renders a clean "Unassigned" chip when owner is undefined', () => {
    render(<CsOwnerBadge owner={undefined} />);
    expect(screen.getByTestId('cs-owner-badge')).toHaveTextContent('Unassigned');
  });

  it("renders the owner's email when assigned", () => {
    render(<CsOwnerBadge owner={{ id: 3, email: 'csm@acme.com' }} />);
    expect(screen.getByTestId('cs-owner-badge')).toHaveTextContent('csm@acme.com');
    expect(screen.getByTestId('cs-owner-badge')).toHaveAttribute('data-owner', 'csm@acme.com');
  });
});
