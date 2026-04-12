/**
 * TDD tests for Human-in-the-Loop thumbs rating on MessageBubble (Track B).
 *
 * Tests:
 *  7. test_thumbs_buttons_visible_on_ai_messages
 *  8. test_thumbs_down_shows_feedback_input
 *  9. test_thumbs_up_submits_correction
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Mock the AI corrections API module
const mockSubmit = vi.fn().mockResolvedValue({ id: 1, signal: 'thumbs_up' });
vi.mock('@/lib/api/ai-corrections', () => ({
  aiCorrectionsAPI: {
    submit: (...args: unknown[]) => mockSubmit(...args),
    getStats: vi.fn(),
    list: vi.fn(),
  },
}));

import { MessageBubble } from '@/components/copilot/MessageBubble';
import type { ChatMessage } from '@/components/copilot/ChatArea';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const userMessage: ChatMessage = {
  id: 10,
  role: 'user',
  content: 'What are the top pain points?',
  structured_data: null,
  created_at: new Date().toISOString(),
};

const aiMessage: ChatMessage = {
  id: 11,
  role: 'assistant',
  content: 'The top pain points are billing and onboarding.',
  structured_data: null,
  created_at: new Date().toISOString(),
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('MessageBubble — Rating buttons (Track B)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── 7. Thumbs buttons visible on AI messages ──────────────────────────────

  it('renders thumbs-up and thumbs-down buttons on assistant messages', () => {
    render(<MessageBubble message={aiMessage} />);

    expect(
      screen.getByTestId(`thumbs-up-btn-${aiMessage.id}`)
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(`thumbs-down-btn-${aiMessage.id}`)
    ).toBeInTheDocument();
  });

  it('does NOT render rating buttons on user messages', () => {
    render(<MessageBubble message={userMessage} />);

    expect(
      screen.queryByTestId(`thumbs-up-btn-${userMessage.id}`)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId(`thumbs-down-btn-${userMessage.id}`)
    ).not.toBeInTheDocument();
  });

  // ── 8. Thumbs-down reveals feedback text input ────────────────────────────

  it('shows optional feedback textarea after thumbs-down click', () => {
    render(<MessageBubble message={aiMessage} />);

    // Textarea should not be visible initially
    expect(
      screen.queryByTestId(`correction-feedback-input-${aiMessage.id}`)
    ).not.toBeInTheDocument();

    // Click thumbs-down
    fireEvent.click(screen.getByTestId(`thumbs-down-btn-${aiMessage.id}`));

    // Feedback input now visible
    expect(
      screen.getByTestId(`correction-feedback-input-${aiMessage.id}`)
    ).toBeInTheDocument();
  });

  it('shows placeholder text "What was wrong?" in feedback input', () => {
    render(<MessageBubble message={aiMessage} />);
    fireEvent.click(screen.getByTestId(`thumbs-down-btn-${aiMessage.id}`));

    const input = screen.getByTestId(`correction-feedback-input-${aiMessage.id}`);
    expect(input).toHaveAttribute('placeholder', 'What was wrong?');
  });

  it('submits correction with feedback text when send button clicked', async () => {
    render(<MessageBubble message={aiMessage} />);
    fireEvent.click(screen.getByTestId(`thumbs-down-btn-${aiMessage.id}`));

    const input = screen.getByTestId(`correction-feedback-input-${aiMessage.id}`);
    fireEvent.change(input, { target: { value: 'The sentiment was wrong.' } });

    // Click send/submit button
    fireEvent.click(screen.getByTestId(`correction-submit-btn-${aiMessage.id}`));

    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          correction_type: 'copilot_response',
          entity_type: 'conversation_message',
          entity_id: aiMessage.id,
          signal: 'thumbs_down',
          feedback_text: 'The sentiment was wrong.',
        })
      );
    });
  });

  // ── 9. Thumbs-up submits correction immediately ───────────────────────────

  it('calls aiCorrectionsAPI.submit with thumbs_up signal on click', async () => {
    render(<MessageBubble message={aiMessage} />);

    fireEvent.click(screen.getByTestId(`thumbs-up-btn-${aiMessage.id}`));

    await waitFor(() => {
      expect(mockSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          correction_type: 'copilot_response',
          entity_type: 'conversation_message',
          entity_id: aiMessage.id,
          signal: 'thumbs_up',
          original_value: aiMessage.content,
        })
      );
    });
  });

  it('disables thumbs-up button after it has been clicked (prevents double submission)', async () => {
    render(<MessageBubble message={aiMessage} />);

    const thumbsUp = screen.getByTestId(`thumbs-up-btn-${aiMessage.id}`);
    fireEvent.click(thumbsUp);

    await waitFor(() => {
      expect(thumbsUp).toBeDisabled();
    });
  });
});
