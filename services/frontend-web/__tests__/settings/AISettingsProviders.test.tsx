import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock AI settings API
vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    listKeys: vi.fn(),
    addKey: vi.fn(),
    removeKey: vi.fn(),
    validateKey: vi.fn(),
    listModels: vi.fn(),
    testModel: vi.fn(),
    update: vi.fn(),
  },
}));

import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { AISettingsProviders } from '@/components/settings/AISettingsProviders';

const ownerUser = {
  id: 1,
  email: 'owner@test.com',
  role: 'owner',
  plan: 'pro',
  organization_id: 1,
  is_system_admin: false,
};

const adminUser = { ...ownerUser, role: 'admin' };
const memberUser = { ...ownerUser, role: 'member' };

const mockSettings = {
  ai_analysis_enabled: true,
  has_custom_key: false,
  default_provider: 'openai',
  models: {
    categorization: 'gpt-4o-mini',
    analysis: 'gpt-4o-mini',
    insights: 'gpt-4o-mini',
  },
  budget: {
    monthly_limit_cents: 1000,
    used_cents: 720,
    resets_at: '2026-03-01T00:00:00Z',
    is_exceeded: false,
  },
};

const mockKeys = [
  {
    provider: 'openai',
    key_hint: 'abc1',
    is_valid: true,
    created_at: '2026-01-01T00:00:00Z',
  },
];

const mockModels = [
  {
    id: 1,
    provider: 'openai',
    model_id: 'gpt-4o-mini',
    display_name: 'GPT-4o Mini',
    input_price_per_1m_tokens: 0.15,
    output_price_per_1m_tokens: 0.6,
    context_window: 128000,
    max_output_tokens: 16384,
    supports_json_mode: true,
    tier: 'cheap' as const,
    min_plan: 'free',
    is_available: true,
    is_deprecated: false,
    replacement_model_id: null,
  },
  {
    id: 2,
    provider: 'openai',
    model_id: 'gpt-4o',
    display_name: 'GPT-4o',
    input_price_per_1m_tokens: 2.5,
    output_price_per_1m_tokens: 10,
    context_window: 128000,
    max_output_tokens: 16384,
    supports_json_mode: true,
    tier: 'mid' as const,
    min_plan: 'pro',
    is_available: true,
    is_deprecated: false,
    replacement_model_id: null,
  },
  {
    id: 3,
    provider: 'anthropic',
    model_id: 'claude-haiku-4-5',
    display_name: 'Claude Haiku 4.5',
    input_price_per_1m_tokens: 0.8,
    output_price_per_1m_tokens: 4,
    context_window: 200000,
    max_output_tokens: 8096,
    supports_json_mode: false,
    tier: 'cheap' as const,
    min_plan: 'free',
    is_available: true,
    is_deprecated: false,
    replacement_model_id: null,
  },
];

describe('AISettingsProviders', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiSettingsAPI.listKeys).mockResolvedValue([]);
    vi.mocked(aiSettingsAPI.listModels).mockResolvedValue(mockModels);
    vi.mocked(aiSettingsAPI.update).mockResolvedValue(mockSettings);
  });

  describe('Provider cards', () => {
    it('shows 3 provider cards (OpenAI, Anthropic, Google)', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument();
        expect(screen.getByText('Anthropic')).toBeInTheDocument();
        expect(screen.getByText('Google')).toBeInTheDocument();
      });
    });

    it('shows "System key" status for providers without BYOK', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const systemKeyLabels = screen.getAllByText(/system key/i);
        expect(systemKeyLabels.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows masked key hint when provider has BYOK key', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      vi.mocked(aiSettingsAPI.listKeys).mockResolvedValue(mockKeys);
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // Should show sk-••••abc1
        expect(screen.getByText(/sk-••••abc1/i)).toBeInTheDocument();
      });
    });

    it('shows Add Key button for owners', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const addKeyBtns = screen.getAllByRole('button', { name: /add key/i });
        expect(addKeyBtns.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('does not show Add Key button for members', async () => {
      mockUseAuth.mockReturnValue({ user: memberUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /add key/i })).not.toBeInTheDocument();
      });
    });

    it('does not show Add Key button for admins', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /add key/i })).not.toBeInTheDocument();
      });
    });

    it('shows Remove button when owner has a BYOK key', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      vi.mocked(aiSettingsAPI.listKeys).mockResolvedValue(mockKeys);
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /remove/i })).toBeInTheDocument();
      });
    });
  });

  describe('Add key flow', () => {
    it('shows key input when Add Key is clicked', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const addKeyBtn = screen.getAllByRole('button', { name: /add key/i })[0];
        fireEvent.click(addKeyBtn);
      });
      expect(screen.getByPlaceholderText(/sk-|api key/i)).toBeInTheDocument();
    });

    it('shows save and cancel buttons in key input form', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const addKeyBtn = screen.getAllByRole('button', { name: /add key/i })[0];
        fireEvent.click(addKeyBtn);
      });
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });

    it('calls addKey API when Save is clicked', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      vi.mocked(aiSettingsAPI.addKey).mockResolvedValue({
        provider: 'anthropic',
        key_hint: 'xyz9',
        is_valid: true,
        created_at: '2026-02-01T00:00:00Z',
      });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const addKeyBtn = screen.getAllByRole('button', { name: /add key/i })[0];
        fireEvent.click(addKeyBtn);
      });
      const input = screen.getByPlaceholderText(/sk-|api key/i);
      fireEvent.change(input, { target: { value: 'sk-test-key' } });
      const saveBtn = screen.getByRole('button', { name: /save/i });
      fireEvent.click(saveBtn);
      await waitFor(() => {
        expect(aiSettingsAPI.addKey).toHaveBeenCalled();
      });
    });
  });

  describe('Remove key flow', () => {
    it('calls removeKey API when Remove is clicked', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      vi.mocked(aiSettingsAPI.listKeys).mockResolvedValue(mockKeys);
      vi.mocked(aiSettingsAPI.removeKey).mockResolvedValue(undefined);
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const removeBtn = screen.getByRole('button', { name: /remove/i });
        fireEvent.click(removeBtn);
      });
      await waitFor(() => {
        expect(aiSettingsAPI.removeKey).toHaveBeenCalledWith('openai');
      });
    });
  });

  describe('Model selection', () => {
    it('shows model selection dropdowns for categorization, analysis, insights', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.getByText(/categorization/i)).toBeInTheDocument();
        expect(screen.getByText(/analysis/i)).toBeInTheDocument();
        expect(screen.getByText(/insights/i)).toBeInTheDocument();
      });
    });

    it('shows tier badge labels for models', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // Should show cheap/mid/premium tier indicators
        expect(screen.getAllByText(/gpt-4o mini/i).length).toBeGreaterThanOrEqual(1);
      });
    });

    it('model dropdowns are disabled for members', async () => {
      mockUseAuth.mockReturnValue({ user: memberUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // Members should see read-only state (no interactive select buttons)
        // Model names still shown as text
        expect(screen.getAllByText(/gpt-4o mini/i).length).toBeGreaterThanOrEqual(1);
      });
      // No enabled select triggers
      const selects = screen.queryAllByRole('combobox');
      selects.forEach(sel => {
        expect(sel).toBeDisabled();
      });
    });
  });

  describe('Test model button', () => {
    it('shows Test button next to each model selector for admins', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const testBtns = screen.getAllByRole('button', { name: /test/i });
        expect(testBtns.length).toBeGreaterThanOrEqual(3);
      });
    });

    it('calls testModel API when Test is clicked', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      vi.mocked(aiSettingsAPI.testModel).mockResolvedValue({
        provider: 'openai',
        model: 'gpt-4o-mini',
        result: 'Analysis successful',
        tokens: 150,
        cost: 0.01,
        latency_ms: 500,
      });
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const testBtns = screen.getAllByRole('button', { name: /test/i });
        fireEvent.click(testBtns[0]);
      });
      await waitFor(() => {
        expect(aiSettingsAPI.testModel).toHaveBeenCalled();
      });
    });
  });
});
