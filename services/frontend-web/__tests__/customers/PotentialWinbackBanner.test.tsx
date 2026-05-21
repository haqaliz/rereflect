import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

vi.mock('@/lib/api/churn-events', () => ({
  recoverCustomer: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { PotentialWinbackBanner } from '@/components/customers/PotentialWinbackBanner';

function renderBanner(props?: Partial<React.ComponentProps<typeof PotentialWinbackBanner>>) {
  const defaultProps = {
    has_potential_winback: true,
    customerEmail: 'winback@example.com',
    onRecovered: vi.fn(),
    ...props,
  };
  return render(<PotentialWinbackBanner {...defaultProps} />);
}

describe('PotentialWinbackBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when has_potential_winback=false', () => {
    const { container } = renderBanner({ has_potential_winback: false });
    expect(container).toBeEmptyDOMElement();
  });

  it('renders banner when has_potential_winback=true', () => {
    renderBanner();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('shows customer email in banner text', () => {
    renderBanner();
    expect(screen.getByText(/winback@example\.com/i)).toBeInTheDocument();
  });

  it('Confirm recovery button opens RecoverCustomerDialog', async () => {
    const user = userEvent.setup();
    renderBanner();
    await user.click(screen.getByRole('button', { name: /confirm recovery/i }));
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('Dismiss for now button hides banner', async () => {
    const user = userEvent.setup();
    renderBanner();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /dismiss for now/i }));
    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  it('banner re-appears when has_potential_winback prop changes after dismiss', async () => {
    const user = userEvent.setup();
    const { rerender } = renderBanner();
    await user.click(screen.getByRole('button', { name: /dismiss for now/i }));
    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
    rerender(
      <PotentialWinbackBanner
        has_potential_winback={false}
        customerEmail="winback@example.com"
        onRecovered={vi.fn()}
      />
    );
    rerender(
      <PotentialWinbackBanner
        has_potential_winback={true}
        customerEmail="winback@example.com"
        onRecovered={vi.fn()}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });
});
