import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { MessageBubble } from '@/components/copilot/MessageBubble';
import type { ChatMessage } from '@/components/copilot/ChatArea';

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const userMessage: ChatMessage = {
  id: 1,
  role: 'user',
  content: 'Show me feedback trends',
  structured_data: null,
  created_at: new Date().toISOString(),
};

const aiMessage: ChatMessage = {
  id: 2,
  role: 'assistant',
  content: '## Results\n\nHere are the **feedback trends**:\n\n- Item 1\n- Item 2\n\n```sql\nSELECT * FROM feedbacks\n```',
  structured_data: null,
  created_at: new Date().toISOString(),
};

const aiTableMessage: ChatMessage = {
  id: 3,
  role: 'assistant',
  content: 'Here is the data:',
  structured_data: {
    kind: 'table',
    columns: ['Date', 'Count', 'Sentiment'],
    rows: [
      ['2026-01-01', 42, 'positive'],
      ['2026-01-02', 35, 'negative'],
    ],
  },
  created_at: new Date().toISOString(),
};

const aiChartMessage: ChatMessage = {
  id: 4,
  role: 'assistant',
  content: 'Trend chart:',
  structured_data: {
    kind: 'bar_chart',
    title: 'Feedback by Day',
    data: [
      { name: 'Mon', value: 10 },
      { name: 'Tue', value: 20 },
    ],
    x_key: 'name',
    value_key: 'value',
  },
  created_at: new Date().toISOString(),
};

const aiLinkMessage: ChatMessage = {
  id: 5,
  role: 'assistant',
  content: 'View the [urgent feedbacks](/urgent-feedbacks) for details.',
  structured_data: null,
  created_at: new Date().toISOString(),
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('MessageBubble', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Layout ─────────────────────────────────────────────────────────────────

  describe('Layout', () => {
    it('renders user message right-aligned', () => {
      render(<MessageBubble message={userMessage} />);
      const bubble = screen.getByTestId('message-bubble-1');
      expect(bubble).toHaveAttribute('data-role', 'user');
    });

    it('renders assistant message left-aligned', () => {
      render(<MessageBubble message={aiMessage} />);
      const bubble = screen.getByTestId('message-bubble-2');
      expect(bubble).toHaveAttribute('data-role', 'assistant');
    });

    it('renders user message text content', () => {
      render(<MessageBubble message={userMessage} />);
      expect(screen.getByText('Show me feedback trends')).toBeInTheDocument();
    });
  });

  // ── Markdown rendering ─────────────────────────────────────────────────────

  describe('Markdown rendering', () => {
    it('renders markdown headings', () => {
      render(<MessageBubble message={aiMessage} />);
      expect(screen.getByRole('heading', { name: /results/i })).toBeInTheDocument();
    });

    it('renders markdown bold text', () => {
      render(<MessageBubble message={aiMessage} />);
      expect(screen.getByText('feedback trends')).toBeInTheDocument();
    });

    it('renders markdown list items', () => {
      render(<MessageBubble message={aiMessage} />);
      expect(screen.getByText('Item 1')).toBeInTheDocument();
      expect(screen.getByText('Item 2')).toBeInTheDocument();
    });

    it('renders code block with SQL syntax highlighting', () => {
      render(<MessageBubble message={aiMessage} />);
      // Code block should be present
      expect(screen.getByTestId('code-block-2')).toBeInTheDocument();
    });
  });

  // ── Structured data — table ────────────────────────────────────────────────

  describe('Structured data — table', () => {
    it('renders a table with column headers', () => {
      render(<MessageBubble message={aiTableMessage} />);
      expect(screen.getByTestId('structured-table-3')).toBeInTheDocument();
      expect(screen.getByText('Date')).toBeInTheDocument();
      expect(screen.getByText('Count')).toBeInTheDocument();
      expect(screen.getByText('Sentiment')).toBeInTheDocument();
    });

    it('renders table rows from structured_data', () => {
      render(<MessageBubble message={aiTableMessage} />);
      expect(screen.getByText('2026-01-01')).toBeInTheDocument();
      expect(screen.getByText('42')).toBeInTheDocument();
      expect(screen.getByText('positive')).toBeInTheDocument();
    });
  });

  // ── Structured data — chart ────────────────────────────────────────────────

  describe('Structured data — chart', () => {
    it('renders a chart container for bar_chart data', () => {
      render(<MessageBubble message={aiChartMessage} />);
      expect(screen.getByTestId('structured-chart-4')).toBeInTheDocument();
    });

    it('renders chart title', () => {
      render(<MessageBubble message={aiChartMessage} />);
      expect(screen.getByText('Feedback by Day')).toBeInTheDocument();
    });
  });

  // ── Deep links ────────────────────────────────────────────────────────────

  describe('Deep links', () => {
    it('renders markdown link as clickable element', () => {
      render(<MessageBubble message={aiLinkMessage} />);
      const link = screen.getByRole('link', { name: /urgent feedbacks/i });
      expect(link).toBeInTheDocument();
    });

    it('navigates via router.push on deep link click', () => {
      render(<MessageBubble message={aiLinkMessage} />);
      const link = screen.getByRole('link', { name: /urgent feedbacks/i });
      fireEvent.click(link);
      expect(mockPush).toHaveBeenCalledWith('/urgent-feedbacks');
    });
  });

  // ── Actions ───────────────────────────────────────────────────────────────

  describe('Message actions', () => {
    it('shows copy button on assistant messages', () => {
      render(<MessageBubble message={aiMessage} />);
      expect(screen.getByTestId('copy-btn-2')).toBeInTheDocument();
    });

    it('does not show copy button on user messages', () => {
      render(<MessageBubble message={userMessage} />);
      expect(screen.queryByTestId('copy-btn-1')).not.toBeInTheDocument();
    });

    it('shows regenerate button on completed assistant messages', () => {
      render(<MessageBubble message={aiMessage} onRegenerate={vi.fn()} />);
      expect(screen.getByTestId('regenerate-btn-2')).toBeInTheDocument();
    });

    it('calls onRegenerate with message id when regenerate is clicked', () => {
      const onRegenerate = vi.fn();
      render(<MessageBubble message={aiMessage} onRegenerate={onRegenerate} />);
      fireEvent.click(screen.getByTestId('regenerate-btn-2'));
      expect(onRegenerate).toHaveBeenCalledWith(2);
    });
  });
});
