import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock admin AI models API
vi.mock('@/lib/api/ai-settings', () => ({
  adminAIModelsAPI: {
    list: vi.fn(),
    update: vi.fn(),
    syncPrices: vi.fn(),
  },
}));

import { adminAIModelsAPI } from '@/lib/api/ai-settings';
import AIModelsAdminPage from '@/app/(dashboard)/system/ai-models/page';

const systemAdminUser = {
  id: 1,
  email: 'admin@system.com',
  role: 'owner',
  plan: 'enterprise',
  organization_id: 1,
  is_system_admin: true,
};

const regularUser = { ...systemAdminUser, is_system_admin: false };

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
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    provider: 'anthropic',
    model_id: 'claude-haiku-4-5',
    display_name: 'Claude Haiku 4.5',
    input_price_per_1m_tokens: 0.8,
    output_price_per_1m_tokens: 4.0,
    context_window: 200000,
    max_output_tokens: 8096,
    supports_json_mode: false,
    tier: 'cheap' as const,
    min_plan: 'free',
    is_available: true,
    is_deprecated: false,
    replacement_model_id: null,
    updated_at: '2026-01-01T00:00:00Z',
  },
];

describe('AIModelsAdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(adminAIModelsAPI.list).mockResolvedValue(mockModels);
    vi.mocked(adminAIModelsAPI.update).mockResolvedValue({ ...mockModels[0], is_available: false });
    vi.mocked(adminAIModelsAPI.syncPrices).mockResolvedValue({ synced: 8 });
  });

  describe('Access control', () => {
    it('redirects non-system-admin users', async () => {
      mockUseAuth.mockReturnValue({ user: regularUser, isLoading: false, isAuthenticated: true });
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/dashboard');
      });
    });

    it('renders page for system admin users', async () => {
      mockUseAuth.mockReturnValue({ user: systemAdminUser, isLoading: false, isAuthenticated: true });
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        expect(screen.getByText(/AI Models/i)).toBeInTheDocument();
      });
    });
  });

  describe('Model table', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: systemAdminUser, isLoading: false, isAuthenticated: true });
    });

    it('shows model table with provider column', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        // PROVIDER_NAMES maps "openai" -> "OpenAI", "anthropic" -> "Anthropic"
        expect(screen.getByText('OpenAI')).toBeInTheDocument();
        expect(screen.getByText('Anthropic')).toBeInTheDocument();
      });
    });

    it('shows model display names', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        expect(screen.getByText('GPT-4o Mini')).toBeInTheDocument();
        expect(screen.getByText('Claude Haiku 4.5')).toBeInTheDocument();
      });
    });

    it('shows tier for each model', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        expect(screen.getAllByText(/cheap/i).length).toBeGreaterThanOrEqual(2);
      });
    });

    it('shows input price for each model', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        expect(screen.getByText(/0\.15/)).toBeInTheDocument();
      });
    });

    it('shows output price for each model', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        expect(screen.getByText(/0\.60|0\.6/)).toBeInTheDocument();
      });
    });

    it('shows availability toggle for each model', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        const switches = screen.getAllByRole('switch');
        expect(switches.length).toBeGreaterThanOrEqual(2);
      });
    });
  });

  describe('Sync Prices button', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: systemAdminUser, isLoading: false, isAuthenticated: true });
    });

    it('shows Sync Prices button', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /sync prices/i })).toBeInTheDocument();
      });
    });

    it('calls syncPrices API when button is clicked', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        const syncBtn = screen.getByRole('button', { name: /sync prices/i });
        fireEvent.click(syncBtn);
      });
      await waitFor(() => {
        expect(adminAIModelsAPI.syncPrices).toHaveBeenCalled();
      });
    });
  });

  describe('Availability toggle', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ user: systemAdminUser, isLoading: false, isAuthenticated: true });
    });

    it('calls update API when availability switch is toggled', async () => {
      render(<AIModelsAdminPage />);
      await waitFor(() => {
        const switches = screen.getAllByRole('switch');
        fireEvent.click(switches[0]);
      });
      await waitFor(() => {
        expect(adminAIModelsAPI.update).toHaveBeenCalledWith(
          expect.any(Number),
          expect.objectContaining({ is_available: expect.any(Boolean) })
        );
      });
    });
  });
});
