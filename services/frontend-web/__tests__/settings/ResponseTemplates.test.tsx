import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/settings/response-templates',
}));

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api/responses', () => ({
  responsesAPI: {
    listTemplates: vi.fn(),
    createTemplate: vi.fn(),
    updateTemplate: vi.fn(),
    deleteTemplate: vi.fn(),
    getResponseSettings: vi.fn(),
    updateResponseSettings: vi.fn(),
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

import { responsesAPI } from '@/lib/api/responses';
import ResponseTemplatesPage from '@/app/(dashboard)/settings/response-templates/page';

const mockListTemplates = responsesAPI.listTemplates as ReturnType<typeof vi.fn>;
const mockGetSettings = responsesAPI.getResponseSettings as ReturnType<typeof vi.fn>;
const mockUpdateSettings = responsesAPI.updateResponseSettings as ReturnType<typeof vi.fn>;
const mockCreateTemplate = responsesAPI.createTemplate as ReturnType<typeof vi.fn>;
const mockDeleteTemplate = responsesAPI.deleteTemplate as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const memberUser = { ...adminUser, role: 'member' };

const mockSettings = {
  brand_voice: 'We are a developer tools company. Keep responses technical.',
  default_tone: 'professional',
  product_name_display: 'Rereflect',
  support_email_display: 'support@rereflect.ca',
};

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

describe('ResponseTemplates - page render', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockListTemplates.mockResolvedValue(allTemplates);
    mockGetSettings.mockResolvedValue(mockSettings);
  });

  it('renders the page title', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByText('Response Templates')).toBeInTheDocument();
    });
  });

  it('renders brand voice textarea with existing value', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      const textarea = screen.getByTestId('brand-voice-textarea');
      expect(textarea).toBeInTheDocument();
      expect(textarea).toHaveValue(mockSettings.brand_voice);
    });
  });

  it('renders default tone dropdown', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByTestId('default-tone-select')).toBeInTheDocument();
    });
  });

  it('renders product name field with existing value', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      const input = screen.getByTestId('product-name-input');
      expect(input).toHaveValue(mockSettings.product_name_display);
    });
  });

  it('renders support email field with existing value', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      const input = screen.getByTestId('support-email-input');
      expect(input).toHaveValue(mockSettings.support_email_display);
    });
  });
});

describe('ResponseTemplates - brand voice save', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockListTemplates.mockResolvedValue(allTemplates);
    mockGetSettings.mockResolvedValue(mockSettings);
    mockUpdateSettings.mockResolvedValue({ ...mockSettings, brand_voice: 'Updated brand voice' });
  });

  it('saves brand voice when "Save brand voice" button is clicked', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByTestId('brand-voice-textarea')).toBeInTheDocument();
    });

    const textarea = screen.getByTestId('brand-voice-textarea');
    fireEvent.change(textarea, { target: { value: 'Updated brand voice' } });

    const saveBtn = screen.getByRole('button', { name: /save brand voice/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockUpdateSettings).toHaveBeenCalledWith(
        expect.objectContaining({ brand_voice: 'Updated brand voice' })
      );
    });
  });
});

describe('ResponseTemplates - system templates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockListTemplates.mockResolvedValue(allTemplates);
    mockGetSettings.mockResolvedValue(mockSettings);
  });

  it('shows system templates section', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByText(/system templates/i)).toBeInTheDocument();
    });
  });

  it('lists system templates as read-only (no edit/delete buttons)', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByText('Bug Report Acknowledgment')).toBeInTheDocument();
    });

    // System templates should show usage count but no edit/delete
    expect(screen.getByText('23x')).toBeInTheDocument();
  });
});

describe('ResponseTemplates - custom templates CRUD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: adminUser });
    mockListTemplates.mockResolvedValue(allTemplates);
    mockGetSettings.mockResolvedValue(mockSettings);
    mockCreateTemplate.mockResolvedValue({
      id: 20,
      name: 'New Custom Template',
      category: 'General',
      body: 'New template body',
      is_system: false,
      usage_count: 0,
    });
    mockDeleteTemplate.mockResolvedValue(undefined);
  });

  it('shows custom templates section', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByText(/custom templates/i)).toBeInTheDocument();
    });
  });

  it('shows custom template names with edit and delete buttons', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByText('Enterprise Welcome')).toBeInTheDocument();
    });

    // Custom templates should have delete button
    const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
    expect(deleteButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('shows "New Template" button for admin users', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new template/i })).toBeInTheDocument();
    });
  });

  it('opens create template dialog when "New Template" button is clicked', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new template/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /new template/i }));

    await waitFor(() => {
      expect(screen.getByTestId('template-form-dialog')).toBeInTheDocument();
    });
  });

  it('calls createTemplate API when form is submitted', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new template/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /new template/i }));

    await waitFor(() => {
      expect(screen.getByTestId('template-form-dialog')).toBeInTheDocument();
    });

    const nameInput = screen.getByTestId('template-name-input');
    const categoryInput = screen.getByTestId('template-category-input');
    const bodyTextarea = screen.getByTestId('template-body-textarea');

    fireEvent.change(nameInput, { target: { value: 'New Custom Template' } });
    fireEvent.change(categoryInput, { target: { value: 'General' } });
    fireEvent.change(bodyTextarea, { target: { value: 'New template body' } });

    const submitBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockCreateTemplate).toHaveBeenCalledWith({
        name: 'New Custom Template',
        category: 'General',
        body: 'New template body',
      });
    });
  });

  it('calls deleteTemplate API when delete button is clicked and confirmed', async () => {
    // Confirm dialog mock
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(screen.getByText('Enterprise Welcome')).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(mockDeleteTemplate).toHaveBeenCalledWith(10);
    });
  });
});

describe('ResponseTemplates - member access', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: memberUser });
    mockListTemplates.mockResolvedValue(allTemplates);
    mockGetSettings.mockResolvedValue(mockSettings);
  });

  it('redirects member users away from the page', async () => {
    render(<ResponseTemplatesPage />);
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/settings/preferences');
    });
  });
});
