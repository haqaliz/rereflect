import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

let searchParams = new URLSearchParams('?token=abc');

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}));

vi.mock('@/lib/api/outreach', () => ({
  unsubscribe: vi.fn(),
}));

import { unsubscribe } from '@/lib/api/outreach';
import UnsubscribePage from '../page';

const mockUnsubscribe = unsubscribe as ReturnType<typeof vi.fn>;

describe('UnsubscribePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchParams = new URLSearchParams('?token=abc');
    mockUnsubscribe.mockResolvedValue(undefined);
  });

  it('renders a success state when the token is valid', async () => {
    render(<UnsubscribePage />);

    expect(await screen.findByText(/you'?re unsubscribed/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockUnsubscribe).toHaveBeenCalledWith('abc');
    });
  });

  it('renders an honest failure state when the token is rejected (400)', async () => {
    mockUnsubscribe.mockRejectedValue(new Error('Invalid unsubscribe token.'));
    render(<UnsubscribePage />);

    expect(await screen.findByText(/this link is invalid/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockUnsubscribe).toHaveBeenCalledWith('abc');
    });
  });

  it('renders a failure state without calling the API when no token is present', async () => {
    searchParams = new URLSearchParams('');
    render(<UnsubscribePage />);

    expect(await screen.findByText(/this link is invalid/i)).toBeInTheDocument();
    expect(mockUnsubscribe).not.toHaveBeenCalled();
  });
});
