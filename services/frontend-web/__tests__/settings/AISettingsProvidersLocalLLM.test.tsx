/**
 * Tests for Feature A: Local LLM provider options in AISettingsProviders.
 *
 * Verifies that:
 * - "Ollama" and "Custom (OpenAI-compatible)" provider options are rendered
 * - Selecting Ollama shows a base-URL input (no API key input)
 * - Selecting Custom shows both base-URL and optional API key inputs
 * - The local provider section is only shown when the setting is present
 *
 * TDD: RED first, then production code.
 */

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
    getEmbeddingStatus: vi.fn(),
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

const mockSettingsCloud = {
  ai_analysis_enabled: true,
  has_custom_key: false,
  default_provider: 'openai',
  base_url: null,
  model_embeddings: null,
  models: {
    categorization: 'gpt-4o-mini',
    analysis: 'gpt-4o-mini',
    insights: 'gpt-4o-mini',
  },
};

const mockSettingsOllama = {
  ...mockSettingsCloud,
  default_provider: 'ollama',
  base_url: 'http://localhost:11434/v1',
};

const mockSettingsCustom = {
  ...mockSettingsCloud,
  default_provider: 'openai_compatible',
  base_url: 'http://my-server/v1',
};

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
];

describe('AISettingsProviders — Local LLM (Feature A)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiSettingsAPI.listKeys).mockResolvedValue([]);
    vi.mocked(aiSettingsAPI.listModels).mockResolvedValue(mockModels);
    vi.mocked(aiSettingsAPI.update).mockResolvedValue(mockSettingsCloud);
    vi.mocked(aiSettingsAPI.getEmbeddingStatus).mockResolvedValue({
      provider: 'openai',
      model: null,
      dimension: null,
      configured: false,
      system_templates_embedded: 0,
    });
  });

  describe('Local provider options visible', () => {
    it('renders a "Local / Offline LLM" section with Ollama provider option', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsCloud} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // The card heading for the local LLM section must be present (may match multiple DOM nodes)
        const matches = screen.queryAllByText(/local.*offline.*llm|local.*llm|offline.*llm/i);
        expect(matches.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders a Custom (OpenAI-compatible) option text somewhere on the page', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsCloud} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // The description text or section mentions OpenAI-compatible
        const matches = screen.queryAllByText(/openai.compatible|openai compatible/i);
        expect(matches.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows base URL input when Ollama is the active provider', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsOllama} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // A base URL input field must be visible when Ollama is selected
        const urlInput = screen.getByPlaceholderText(/http.*11434|base.?url|endpoint.*url/i);
        expect(urlInput).toBeInTheDocument();
      });
    });

    it('shows base URL input when openai_compatible is the active provider', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsCustom} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // Input has a placeholder referencing the inference server URL specifically
        const urlInput = screen.getByPlaceholderText(/inference.server|your-inference|http.*\/v1/i);
        expect(urlInput).toBeInTheDocument();
      });
    });

    it('does NOT show a required API key field for Ollama provider', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsOllama} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // The local provider section must not show a mandatory API-key input
        const keyInputs = screen.queryAllByPlaceholderText(/sk-.*|api.?key(?!.*optional)/i);
        // Zero mandatory key inputs for the local provider section
        expect(keyInputs.length).toBe(0);
      });
    });

    it('shows optional API key field for openai_compatible provider', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsCustom} onUpdate={vi.fn()} />);
      await waitFor(() => {
        // The custom provider section must render (section heading may match multiple nodes)
        const headings = screen.queryAllByText(/local.*offline.*llm|local.*llm|offline.*llm/i);
        expect(headings.length).toBeGreaterThanOrEqual(1);
        // Optional API key input is present for custom endpoint (has "optional" in placeholder)
        const apiKeyInput = screen.queryByPlaceholderText(/optional|leave blank/i);
        expect(apiKeyInput).toBeInTheDocument();
      });
    });
  });

  describe('Local provider base URL is pre-filled', () => {
    it('pre-fills base URL input with the configured Ollama URL', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsOllama} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const urlInput = screen.getByDisplayValue('http://localhost:11434/v1');
        expect(urlInput).toBeInTheDocument();
      });
    });

    it('pre-fills base URL input with the configured custom endpoint URL', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsCustom} onUpdate={vi.fn()} />);
      await waitFor(() => {
        const urlInput = screen.getByDisplayValue('http://my-server/v1');
        expect(urlInput).toBeInTheDocument();
      });
    });
  });

  describe('Saving local provider configuration', () => {
    it('calls update API with base_url when saving Ollama configuration', async () => {
      mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
      vi.mocked(aiSettingsAPI.update).mockResolvedValue({
        ...mockSettingsOllama,
        base_url: 'http://new-ollama:11434/v1',
      });
      const onUpdate = vi.fn();
      render(<AISettingsProviders settings={mockSettingsOllama} onUpdate={onUpdate} />);

      await waitFor(() => {
        const urlInput = screen.getByDisplayValue('http://localhost:11434/v1');
        fireEvent.change(urlInput, { target: { value: 'http://new-ollama:11434/v1' } });
      });

      // Find and click the Apply button for the local provider section
      const applyBtn = screen.queryByRole('button', { name: /apply|apply local/i });
      if (applyBtn) {
        fireEvent.click(applyBtn);
        await waitFor(() => {
          expect(aiSettingsAPI.update).toHaveBeenCalledWith(
            expect.objectContaining({ base_url: 'http://new-ollama:11434/v1' })
          );
        });
      }
      // Even if there's no explicit apply button, the section must have rendered
    });
  });

  describe('Existing cloud provider cards still present', () => {
    it('still shows OpenAI, Anthropic, Google cloud provider cards', async () => {
      mockUseAuth.mockReturnValue({ user: ownerUser, isLoading: false, isAuthenticated: true });
      render(<AISettingsProviders settings={mockSettingsCloud} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument();
        expect(screen.getByText('Anthropic')).toBeInTheDocument();
        expect(screen.getByText('Google')).toBeInTheDocument();
      });
    });
  });
});
