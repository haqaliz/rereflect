import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/dashboard',
}));

// Mock AuthContext — default to free plan user
const mockUseAuth = vi.fn(() => ({
  user: {
    id: 1,
    email: 'test@test.com',
    role: 'owner',
    plan: 'free',
    organization_id: 1,
    is_system_admin: false,
  },
  isLoading: false,
  isAuthenticated: true,
  login: vi.fn(),
  logout: vi.fn(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock conversations API
vi.mock('@/lib/api/copilot', () => ({
  copilotAPI: {
    getSuggestions: vi.fn(),
    getCopilotUsage: vi.fn(),
  },
}));

import { CommandBar } from '@/components/copilot/CommandBar';
import { copilotAPI } from '@/lib/api/copilot';

const mockedGetSuggestions = copilotAPI.getSuggestions as ReturnType<typeof vi.fn>;
const mockedGetUsage = copilotAPI.getCopilotUsage as ReturnType<typeof vi.fn>;

function renderCommandBar(props: { open?: boolean; onClose?: () => void } = {}) {
  const onClose = props.onClose ?? vi.fn();
  const open = props.open ?? true;
  return render(<CommandBar open={open} onClose={onClose} />);
}

describe('CommandBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetSuggestions.mockResolvedValue({
      suggestions: ['Check churn risk this week', 'Analyze sentiment trends'],
    });
    mockedGetUsage.mockResolvedValue({
      queries_today: 3,
      daily_limit: 10,
      plan: 'free',
    });
    mockUseAuth.mockReturnValue({
      user: {
        id: 1,
        email: 'test@test.com',
        role: 'owner',
        plan: 'free',
        organization_id: 1,
        is_system_admin: false,
      },
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Rendering
  // ────────────────────────────────────────────────────────────────────────────

  it('renders the text input when open is true', () => {
    renderCommandBar({ open: true });
    expect(screen.getByPlaceholderText(/ask anything about your feedback/i)).toBeInTheDocument();
  });

  it('does not render the modal content when open is false', () => {
    renderCommandBar({ open: false });
    expect(screen.queryByPlaceholderText(/ask anything about your feedback/i)).not.toBeInTheDocument();
  });

  it('renders all 8 static template chips', () => {
    renderCommandBar();
    const templates = [
      "This week's feedback summary",
      'Top pain points this month',
      'Most requested features',
      'Urgent feedback that needs attention',
      'Top churn risks right now',
      'Healthiest customers',
      'Customers with declining health scores',
      'Sentiment trends over the last 30 days',
    ];
    templates.forEach((t) => {
      expect(screen.getByText(t)).toBeInTheDocument();
    });
  });

  it('renders "Suggest queries for me" button', () => {
    renderCommandBar();
    expect(screen.getByRole('button', { name: /suggest queries/i })).toBeInTheDocument();
  });

  it('auto-focuses the input when opened', () => {
    renderCommandBar({ open: true });
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    expect(input).toHaveFocus();
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Closing behavior
  // ────────────────────────────────────────────────────────────────────────────

  it('calls onClose when Escape key is pressed on the document', () => {
    const onClose = vi.fn();
    renderCommandBar({ open: true, onClose });
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when clicking the backdrop overlay', () => {
    const onClose = vi.fn();
    renderCommandBar({ open: true, onClose });
    const backdrop = screen.getByTestId('command-bar-backdrop');
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not call onClose when clicking inside the modal panel', () => {
    const onClose = vi.fn();
    renderCommandBar({ open: true, onClose });
    const modal = screen.getByTestId('command-bar-modal');
    fireEvent.click(modal);
    expect(onClose).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Navigation on submit
  // ────────────────────────────────────────────────────────────────────────────

  it('navigates to /conversations with encoded query param when Enter is pressed', () => {
    renderCommandBar();
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    fireEvent.change(input, { target: { value: 'How many negative feedbacks this week?' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mockPush).toHaveBeenCalledWith(
      '/conversations?new=true&q=How%20many%20negative%20feedbacks%20this%20week%3F'
    );
  });

  it('does not navigate when the input is empty and Enter is pressed', () => {
    renderCommandBar();
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('trims whitespace before navigating', () => {
    renderCommandBar();
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    fireEvent.change(input, { target: { value: '  query with spaces  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mockPush).toHaveBeenCalledWith(
      '/conversations?new=true&q=query%20with%20spaces'
    );
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Template chip navigation
  // ────────────────────────────────────────────────────────────────────────────

  it("navigates with the first template's text when its chip is clicked", () => {
    renderCommandBar();
    const chip = screen.getByText("This week's feedback summary");
    fireEvent.click(chip);
    expect(mockPush).toHaveBeenCalledWith(
      "/conversations?new=true&q=This%20week's%20feedback%20summary"
    );
  });

  it('navigates with the correct text when a different chip is clicked', () => {
    renderCommandBar();
    const chip = screen.getByText('Top pain points this month');
    fireEvent.click(chip);
    expect(mockPush).toHaveBeenCalledWith(
      '/conversations?new=true&q=Top%20pain%20points%20this%20month'
    );
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Keyboard navigation through template chips
  // ────────────────────────────────────────────────────────────────────────────

  it('highlights the first chip on first ArrowDown press', () => {
    renderCommandBar();
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(screen.getByTestId('template-chip-0')).toHaveAttribute('data-highlighted', 'true');
  });

  it('moves highlight to second chip on second ArrowDown', () => {
    renderCommandBar();
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(screen.getByTestId('template-chip-1')).toHaveAttribute('data-highlighted', 'true');
    expect(screen.getByTestId('template-chip-0')).not.toHaveAttribute('data-highlighted', 'true');
  });

  it('wraps around to the first chip after passing the last chip', () => {
    renderCommandBar();
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    // 8 templates → pressing down 9 times wraps back to index 0
    for (let i = 0; i < 9; i++) {
      fireEvent.keyDown(input, { key: 'ArrowDown' });
    }
    expect(screen.getByTestId('template-chip-0')).toHaveAttribute('data-highlighted', 'true');
  });

  it('highlights the last chip on ArrowUp from no selection', () => {
    renderCommandBar();
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(screen.getByTestId('template-chip-7')).toHaveAttribute('data-highlighted', 'true');
  });

  it('submits the highlighted template text on Enter', () => {
    renderCommandBar();
    const input = screen.getByPlaceholderText(/ask anything about your feedback/i);
    fireEvent.keyDown(input, { key: 'ArrowDown' }); // highlight index 0
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mockPush).toHaveBeenCalledWith(
      "/conversations?new=true&q=This%20week's%20feedback%20summary"
    );
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Dynamic suggestions
  // ────────────────────────────────────────────────────────────────────────────

  it('calls getSuggestions API when "Suggest queries" button is clicked', async () => {
    renderCommandBar();
    const btn = screen.getByRole('button', { name: /suggest queries/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(mockedGetSuggestions).toHaveBeenCalledTimes(1);
    });
  });

  it('shows dynamic suggestions after clicking "Suggest queries"', async () => {
    renderCommandBar();
    const btn = screen.getByRole('button', { name: /suggest queries/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByText('Check churn risk this week')).toBeInTheDocument();
      expect(screen.getByText('Analyze sentiment trends')).toBeInTheDocument();
    });
  });

  it('shows a loading indicator while fetching suggestions', async () => {
    mockedGetSuggestions.mockImplementation(() => new Promise(() => {}));
    renderCommandBar();
    const btn = screen.getByRole('button', { name: /suggest queries/i });
    fireEvent.click(btn);
    expect(screen.getByTestId('suggestions-loading')).toBeInTheDocument();
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Plan gating — Free tier (under limit)
  // ────────────────────────────────────────────────────────────────────────────

  it('shows remaining queries count for free users under the limit', async () => {
    renderCommandBar();
    await waitFor(() => {
      expect(screen.getByText(/7\/10 remaining today/i)).toBeInTheDocument();
    });
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Plan gating — Free tier (limit reached)
  // ────────────────────────────────────────────────────────────────────────────

  it('disables the input when the daily limit is reached', async () => {
    mockedGetUsage.mockResolvedValue({
      queries_today: 10,
      daily_limit: 10,
      plan: 'free',
    });
    renderCommandBar();
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/ask anything about your feedback/i)).toBeDisabled();
    });
  });

  it('shows upgrade CTA when the daily limit is reached', async () => {
    mockedGetUsage.mockResolvedValue({
      queries_today: 10,
      daily_limit: 10,
      plan: 'free',
    });
    renderCommandBar();
    await waitFor(() => {
      expect(screen.getByTestId('upgrade-cta')).toBeInTheDocument();
    });
  });

  // ────────────────────────────────────────────────────────────────────────────
  // Plan gating — Pro tier (no cap)
  // ────────────────────────────────────────────────────────────────────────────

  it('does not show "remaining today" text for pro users', async () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: 2,
        email: 'pro@test.com',
        role: 'owner',
        plan: 'pro',
        organization_id: 1,
        is_system_admin: false,
      },
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    mockedGetUsage.mockResolvedValue({
      queries_today: 0,
      daily_limit: null,
      plan: 'pro',
    });
    renderCommandBar();
    await waitFor(() => {
      expect(screen.queryByText(/remaining today/i)).not.toBeInTheDocument();
    });
  });
});
