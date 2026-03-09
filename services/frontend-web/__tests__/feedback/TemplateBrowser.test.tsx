import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('@/lib/api/responses', () => ({
  responsesAPI: {
    listTemplates: vi.fn(),
  },
}));

import { responsesAPI } from '@/lib/api/responses';
import { TemplateBrowser } from '@/components/feedback/TemplateBrowser';

const mockListTemplates = responsesAPI.listTemplates as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const systemTemplates = [
  {
    id: 1,
    name: 'Bug Report Acknowledgment',
    category: 'Bug Report',
    body: 'Hi {{customer_name}}, thank you for reporting this bug.',
    is_system: true,
    usage_count: 23,
  },
  {
    id: 2,
    name: 'Feature Request Acknowledgment',
    category: 'Feature Request',
    body: 'Hi {{customer_name}}, thank you for this suggestion.',
    is_system: true,
    usage_count: 15,
  },
];

const customTemplates = [
  {
    id: 10,
    name: 'Enterprise Welcome',
    category: 'Onboarding',
    body: 'Welcome to our enterprise plan!',
    is_system: false,
    usage_count: 3,
  },
];

const allTemplates = [...systemTemplates, ...customTemplates];

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('TemplateBrowser - rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListTemplates.mockResolvedValue(allTemplates);
  });

  it('renders system templates and custom templates in separate sections', async () => {
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('System Templates')).toBeInTheDocument();
      expect(screen.getByText('Custom Templates')).toBeInTheDocument();
    });
  });

  it('shows all system template names', async () => {
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('Bug Report Acknowledgment')).toBeInTheDocument();
      expect(screen.getByText('Feature Request Acknowledgment')).toBeInTheDocument();
    });
  });

  it('shows custom template names', async () => {
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('Enterprise Welcome')).toBeInTheDocument();
    });
  });

  it('shows a "Back" button', async () => {
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
  });

  it('shows "Use" buttons for each template', async () => {
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    await waitFor(() => {
      const useButtons = screen.getAllByRole('button', { name: /^use$/i });
      expect(useButtons.length).toBe(allTemplates.length);
    });
  });
});

describe('TemplateBrowser - search', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListTemplates.mockResolvedValue(allTemplates);
  });

  it('renders a search input', async () => {
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    expect(screen.getByPlaceholderText(/search templates/i)).toBeInTheDocument();
  });

  it('filters templates by name when searching', async () => {
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('Bug Report Acknowledgment')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search templates/i);
    fireEvent.change(searchInput, { target: { value: 'bug' } });

    await waitFor(() => {
      expect(screen.getByText('Bug Report Acknowledgment')).toBeInTheDocument();
      expect(screen.queryByText('Feature Request Acknowledgment')).not.toBeInTheDocument();
      expect(screen.queryByText('Enterprise Welcome')).not.toBeInTheDocument();
    });
  });

  it('shows all templates when search is cleared', async () => {
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('Bug Report Acknowledgment')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search templates/i);
    fireEvent.change(searchInput, { target: { value: 'bug' } });
    fireEvent.change(searchInput, { target: { value: '' } });

    await waitFor(() => {
      expect(screen.getByText('Bug Report Acknowledgment')).toBeInTheDocument();
      expect(screen.getByText('Feature Request Acknowledgment')).toBeInTheDocument();
      expect(screen.getByText('Enterprise Welcome')).toBeInTheDocument();
    });
  });
});

describe('TemplateBrowser - callbacks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListTemplates.mockResolvedValue(allTemplates);
  });

  it('"Use" button calls onSelect with the correct template', async () => {
    const onSelect = vi.fn();
    render(<TemplateBrowser onSelect={onSelect} onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /^use$/i }).length).toBeGreaterThan(0);
    });

    const useButtons = screen.getAllByRole('button', { name: /^use$/i });
    fireEvent.click(useButtons[0]);

    expect(onSelect).toHaveBeenCalledWith(systemTemplates[0]);
  });

  it('"Back" button calls onBack', async () => {
    const onBack = vi.fn();
    render(<TemplateBrowser onSelect={vi.fn()} onBack={onBack} />);
    fireEvent.click(screen.getByRole('button', { name: /back/i }));
    expect(onBack).toHaveBeenCalled();
  });
});

describe('TemplateBrowser - empty state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows empty state when no templates match search', async () => {
    mockListTemplates.mockResolvedValue(allTemplates);
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('Bug Report Acknowledgment')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/search templates/i);
    fireEvent.change(searchInput, { target: { value: 'xyzabcnonexistent' } });

    await waitFor(() => {
      expect(screen.getByText(/no templates found/i)).toBeInTheDocument();
    });
  });

  it('shows loading state while fetching templates', () => {
    mockListTemplates.mockReturnValue(new Promise(() => {})); // never resolves
    render(<TemplateBrowser onSelect={vi.fn()} onBack={vi.fn()} />);
    expect(screen.getByTestId('template-browser-loading')).toBeInTheDocument();
  });
});
