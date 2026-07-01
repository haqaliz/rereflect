/**
 * Tests for S3: surfacing the embedding provider/model in AI Settings.
 *
 * Verifies that:
 * - The editable "Embedding model" input renders, bound to model_embeddings,
 *   and its value round-trips through the existing PATCH settings flow.
 * - The read-only status line shows the embedded-template count + provider
 *   when the embedding provider is configured.
 * - The unconfigured/degraded states render an honest hint instead of
 *   crashing (no configured provider, or the status fetch fails).
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
  ai_analysis_enabled: true,
  has_custom_key: false,
  default_provider: 'ollama',
  base_url: 'http://localhost:11434/v1',
  model_embeddings: null,
  models: {
    categorization: 'gpt-4o-mini',
    analysis: 'gpt-4o-mini',
    insights: 'gpt-4o-mini',
  },
};

const mockModels: any[] = [];

const configuredStatus = {
  provider: 'openai_compatible',
  model: 'nomic-embed-text',
  dimension: 768,
  configured: true,
  system_templates_embedded: 2,
};

const unconfiguredStatus = {
  provider: 'openai',
  model: null,
  dimension: null,
  configured: false,
  system_templates_embedded: 0,
};

describe('AISettingsProviders — Embeddings status (S3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiSettingsAPI.listKeys).mockResolvedValue([]);
    vi.mocked(aiSettingsAPI.listModels).mockResolvedValue(mockModels);
    mockUseAuth.mockReturnValue({ user: adminUser, isLoading: false, isAuthenticated: true });
  });

  describe('Editable embedding-model field', () => {
    it('renders an Embedding model input', async () => {
      vi.mocked(aiSettingsAPI.getEmbeddingStatus).mockResolvedValue(configuredStatus);
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.getByLabelText('Embedding model')).toBeInTheDocument();
      });
    });

    it('pre-fills the input with the saved model_embeddings value', async () => {
      vi.mocked(aiSettingsAPI.getEmbeddingStatus).mockResolvedValue(configuredStatus);
      render(
        <AISettingsProviders
          settings={{ ...mockSettings, model_embeddings: 'nomic-embed-text' }}
          onUpdate={vi.fn()}
        />
      );
      await waitFor(() => {
        expect(screen.getByDisplayValue('nomic-embed-text')).toBeInTheDocument();
      });
    });

    it('round-trips a new value through the PATCH settings flow on save', async () => {
      vi.mocked(aiSettingsAPI.getEmbeddingStatus).mockResolvedValue(configuredStatus);
      vi.mocked(aiSettingsAPI.update).mockResolvedValue({
        ...mockSettings,
        model_embeddings: 'mxbai-embed-large',
      });
      const onUpdate = vi.fn();
      render(<AISettingsProviders settings={mockSettings} onUpdate={onUpdate} />);

      const input = await screen.findByLabelText('Embedding model');
      fireEvent.change(input, { target: { value: 'mxbai-embed-large' } });
      fireEvent.click(screen.getByRole('button', { name: /save embedding model/i }));

      await waitFor(() => {
        expect(aiSettingsAPI.update).toHaveBeenCalledWith({ model_embeddings: 'mxbai-embed-large' });
        expect(onUpdate).toHaveBeenCalledWith(
          expect.objectContaining({ model_embeddings: 'mxbai-embed-large' })
        );
      });
    });

    it('disables the input for members (non admin/owner)', async () => {
      mockUseAuth.mockReturnValue({ user: memberUser, isLoading: false, isAuthenticated: true });
      vi.mocked(aiSettingsAPI.getEmbeddingStatus).mockResolvedValue(configuredStatus);
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.getByLabelText('Embedding model')).toBeDisabled();
      });
    });
  });

  describe('Embedding status line', () => {
    it('shows the embedded-template count and provider when configured', async () => {
      vi.mocked(aiSettingsAPI.getEmbeddingStatus).mockResolvedValue(configuredStatus);
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(
          screen.getByText(/2 system templates embedded for provider openai_compatible/i)
        ).toBeInTheDocument();
      });
    });

    it('shows an honest hint when no embedding provider is configured', async () => {
      vi.mocked(aiSettingsAPI.getEmbeddingStatus).mockResolvedValue(unconfiguredStatus);
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(
          screen.getByText(/no embedding provider configured.*copilot template matching is disabled/i)
        ).toBeInTheDocument();
      });
    });

    it('degrades to a neutral message when the status fetch fails, without crashing', async () => {
      vi.mocked(aiSettingsAPI.getEmbeddingStatus).mockRejectedValue(new Error('network error'));
      render(<AISettingsProviders settings={mockSettings} onUpdate={vi.fn()} />);
      await waitFor(() => {
        expect(screen.getByText(/embedding status unavailable/i)).toBeInTheDocument();
      });
      // Editable field must still be usable even when status fetch failed
      expect(screen.getByLabelText('Embedding model')).toBeInTheDocument();
    });
  });
});
