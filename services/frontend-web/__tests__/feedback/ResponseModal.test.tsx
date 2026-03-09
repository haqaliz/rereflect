import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/responses', () => ({
  responsesAPI: {
    suggestTemplate: vi.fn(),
    generateResponse: vi.fn(),
    sendResponse: vi.fn(),
    getResponseUsage: vi.fn(),
  },
  TONE_OPTIONS: [
    { value: 'professional', label: 'Professional' },
    { value: 'friendly', label: 'Friendly' },
    { value: 'empathetic', label: 'Empathetic' },
    { value: 'concise', label: 'Concise' },
    { value: 'technical', label: 'Technical' },
  ],
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// clipboard mock
Object.assign(navigator, {
  clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
});

import { responsesAPI } from '@/lib/api/responses';
import { ResponseModal } from '@/components/feedback/ResponseModal';

const mockSuggest = responsesAPI.suggestTemplate as ReturnType<typeof vi.fn>;
const mockGenerate = responsesAPI.generateResponse as ReturnType<typeof vi.fn>;
const mockSend = responsesAPI.sendResponse as ReturnType<typeof vi.fn>;
const mockUsage = responsesAPI.getResponseUsage as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const proUser = {
  id: 1, email: 'alex@test.com', role: 'owner', plan: 'pro', organization_id: 1, is_system_admin: false,
};

const freeUser = { ...proUser, plan: 'free' };

const mockFeedback = {
  id: 42,
  text: 'The export feature keeps failing when I try to download more than 1000 rows.',
  sentiment_label: 'negative',
  pain_point_category: 'functionality_broken',
  customer_email: 'sarah@acme.com',
  source: 'slack',
  source_metadata: { channel_id: 'C123', thread_ts: '1234567890.000' },
};

const mockTemplate = {
  id: 1,
  name: 'Bug Report Acknowledgment',
  category: 'Bug Report',
  body: 'Hi {{customer_name}}, thank you for reporting this issue.',
  is_system: true,
  usage_count: 23,
};

const mockUsageData = {
  ai_responses_generated: 12,
  monthly_limit: 50,
  templates_used: 8,
  responses_sent: 20,
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ResponseModal - basic rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockSuggest.mockResolvedValue({ template: null, score: 0 });
    mockUsage.mockResolvedValue(mockUsageData);
  });

  it('renders with "Respond to Feedback" title when open', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('Respond to Feedback')).toBeInTheDocument();
    });
  });

  it('does not render content when closed', () => {
    render(
      <ResponseModal
        open={false}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    expect(screen.queryByText('Respond to Feedback')).not.toBeInTheDocument();
  });
});

describe('ResponseModal - template suggestion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockUsage.mockResolvedValue(mockUsageData);
  });

  it('shows suggested template when provided', async () => {
    mockSuggest.mockResolvedValue({ template: mockTemplate, score: 70 });
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('Bug Report Acknowledgment')).toBeInTheDocument();
    });
  });

  it('shows "Use this" button when template suggestion is present', async () => {
    mockSuggest.mockResolvedValue({ template: mockTemplate, score: 70 });
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /use this/i })).toBeInTheDocument();
    });
  });

  it('"Use this" button loads template body into editor', async () => {
    mockSuggest.mockResolvedValue({ template: mockTemplate, score: 70 });
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /use this/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /use this/i }));
    await waitFor(() => {
      const textarea = screen.getByRole('textbox', { name: /response/i });
      expect(textarea).toHaveValue(mockTemplate.body);
    });
  });

  it('shows no template suggestion section when score is too low', async () => {
    mockSuggest.mockResolvedValue({ template: null, score: 0 });
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('Respond to Feedback')).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /use this/i })).not.toBeInTheDocument();
  });
});

describe('ResponseModal - AI generation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockSuggest.mockResolvedValue({ template: null, score: 0 });
    mockUsage.mockResolvedValue(mockUsageData);
  });

  it('"Generate with AI" button calls generateResponse API', async () => {
    mockGenerate.mockResolvedValue({
      response_text: 'AI-generated response text',
      tokens_used: 120,
      remaining_this_month: 38,
    });
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /generate with ai/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /generate with ai/i }));
    await waitFor(() => {
      expect(mockGenerate).toHaveBeenCalledWith(42, expect.any(String));
    });
  });

  it('AI response text appears in editor textarea after generation', async () => {
    mockGenerate.mockResolvedValue({
      response_text: 'AI-generated response text',
      tokens_used: 120,
      remaining_this_month: 38,
    });
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /generate with ai/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /generate with ai/i }));
    await waitFor(() => {
      const textarea = screen.getByRole('textbox', { name: /response/i });
      expect(textarea).toHaveValue('AI-generated response text');
    });
  });
});

describe('ResponseModal - tone dropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockSuggest.mockResolvedValue({ template: null, score: 0 });
    mockUsage.mockResolvedValue(mockUsageData);
  });

  it('renders tone dropdown', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByTestId('tone-select')).toBeInTheDocument();
    });
  });

  it('defaults tone to "professional"', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
        defaultTone="professional"
      />
    );
    await waitFor(() => {
      expect(screen.getByTestId('tone-select')).toHaveTextContent('Professional');
    });
  });
});

describe('ResponseModal - copy to clipboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockSuggest.mockResolvedValue({ template: null, score: 0 });
    mockUsage.mockResolvedValue(mockUsageData);
    mockSend.mockResolvedValue({ success: true, response_id: 99, channel: 'clipboard', error: null });
  });

  it('"Copy to clipboard" button is present', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /copy to clipboard/i })).toBeInTheDocument();
    });
  });

  it('"Copy to clipboard" copies textarea content', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /response/i })).toBeInTheDocument();
    });
    const textarea = screen.getByRole('textbox', { name: /response/i });
    fireEvent.change(textarea, { target: { value: 'My response text' } });
    fireEvent.click(screen.getByRole('button', { name: /copy to clipboard/i }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('My response text');
    });
  });
});

describe('ResponseModal - send via channels', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockSuggest.mockResolvedValue({ template: null, score: 0 });
    mockUsage.mockResolvedValue(mockUsageData);
  });

  it('shows "Send via" dropdown with connected channels', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={['slack']}
      />
    );
    await waitFor(() => {
      expect(screen.getByTestId('send-via-button')).toBeInTheDocument();
    });
  });

  it('does not show "Send via" button when no channels connected', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('Respond to Feedback')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('send-via-button')).not.toBeInTheDocument();
  });
});

describe('ResponseModal - usage counter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: proUser });
    mockSuggest.mockResolvedValue({ template: null, score: 0 });
  });

  it('displays usage counter after AI generation', async () => {
    mockUsage.mockResolvedValue(mockUsageData);
    mockGenerate.mockResolvedValue({
      response_text: 'Generated text',
      tokens_used: 100,
      remaining_this_month: 38,
    });
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /generate with ai/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /generate with ai/i }));
    await waitFor(() => {
      expect(screen.getByTestId('usage-counter')).toBeInTheDocument();
    });
  });

  it('usage counter shows correct text (e.g. "13/50 AI responses used this month")', async () => {
    mockUsage.mockResolvedValue(mockUsageData);
    mockGenerate.mockResolvedValue({
      response_text: 'Generated text',
      tokens_used: 100,
      remaining_this_month: 37,
    });
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /generate with ai/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /generate with ai/i }));
    await waitFor(() => {
      expect(screen.getByTestId('usage-counter')).toHaveTextContent(/ai responses used this month/i);
    });
  });
});

describe('ResponseModal - free plan upgrade CTA', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: freeUser });
    mockSuggest.mockResolvedValue({ template: null, score: 0 });
    mockUsage.mockResolvedValue({ ai_responses_generated: 0, monthly_limit: 0, templates_used: 0, responses_sent: 0 });
  });

  it('shows upgrade CTA for free plan users', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByTestId('upgrade-cta')).toBeInTheDocument();
    });
  });

  it('upgrade CTA contains link to billing page', async () => {
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByTestId('upgrade-cta')).toBeInTheDocument();
    });
    expect(screen.getByText(/upgrade to pro/i)).toBeInTheDocument();
  });

  it('does not show upgrade CTA for pro plan users', async () => {
    mockUseAuth.mockReturnValue({ user: proUser });
    mockUsage.mockResolvedValue(mockUsageData);
    render(
      <ResponseModal
        open={true}
        onClose={vi.fn()}
        feedback={mockFeedback as any}
        connectedChannels={[]}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('Respond to Feedback')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('upgrade-cta')).not.toBeInTheDocument();
  });
});
