import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

// Mock next/navigation — land directly on the accuracy tab.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams('tab=accuracy'),
}));

// Mock AuthContext — admin user (so isAdminOrOwner is true).
const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock AI settings API
vi.mock('@/lib/api/ai-settings', () => ({
  aiSettingsAPI: {
    get: vi.fn(),
    getSentimentStatus: vi.fn(),
  },
}));

// Mock categories API
vi.mock('@/lib/api/categories', () => ({
  categoriesAPI: {
    list: vi.fn(),
  },
}));

// Mock AI corrections API
vi.mock('@/lib/api/ai-corrections', () => ({
  aiCorrectionsAPI: {
    getStats: vi.fn(),
  },
}));

// Stub ClassifierAccuracyCard so the test can assert on the props each instance receives
// without needing to mock two levels of API calls deep.
vi.mock('@/components/settings/ClassifierAccuracyCard', () => ({
  ClassifierAccuracyCard: (props: { classifierType?: string; isAdminOrOwner?: boolean }) => (
    <div data-testid="classifier-card" data-type={props.classifierType ?? 'sentiment'} />
  ),
}));

// Stub SentimentAccuracyCard — unrelated to this test, keep it simple.
vi.mock('@/components/settings/SentimentAccuracyCard', () => ({
  SentimentAccuracyCard: () => <div data-testid="sentiment-accuracy-card" />,
}));

// Stub AISettingsGeneral/Providers/Usage/HealthWeightsEditor/AIReadinessCard — not under test
// here and would otherwise trigger unrelated fetch noise for other tabs.
vi.mock('@/components/settings/AISettingsGeneral', () => ({
  AISettingsGeneral: () => <div data-testid="ai-settings-general" />,
}));
vi.mock('@/components/settings/AISettingsProviders', () => ({
  AISettingsProviders: () => <div data-testid="ai-settings-providers" />,
}));
vi.mock('@/components/settings/AISettingsUsage', () => ({
  AISettingsUsage: () => <div data-testid="ai-settings-usage" />,
}));
vi.mock('@/components/settings/HealthWeightsEditor', () => ({
  HealthWeightsEditor: () => <div data-testid="health-weights-editor" />,
}));
vi.mock('@/components/settings/AIReadinessCard', () => ({
  AIReadinessCard: () => <div data-testid="ai-readiness-card" />,
}));

import { aiSettingsAPI } from '@/lib/api/ai-settings';
import { categoriesAPI } from '@/lib/api/categories';
import { aiCorrectionsAPI } from '@/lib/api/ai-corrections';
import AISettingsPage from '@/app/(dashboard)/settings/ai/page';

const adminUser = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  plan: 'business',
  organization_id: 1,
  is_system_admin: false,
};

const mockSettings = {
  ai_analysis_enabled: true,
  has_custom_key: false,
  default_provider: 'openai',
  base_url: null,
  model_embeddings: null,
  sentiment_provider: 'vader',
  classifier_mode: 'off',
  category_classifier_mode: 'off',
  models: {
    categorization: 'gpt-4o-mini',
    analysis: 'gpt-4o-mini',
    insights: 'gpt-4o-mini',
  },
};

describe('AISettingsPage — Accuracy tab renders both classifier accuracy cards', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(() => 'mock-token'),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      },
      writable: true,
    });
    mockUseAuth.mockReturnValue({
      user: adminUser,
      isLoading: false,
      isAuthenticated: true,
    });
    vi.mocked(aiSettingsAPI.get).mockResolvedValue(mockSettings);
    vi.mocked(categoriesAPI.list).mockResolvedValue([]);
    vi.mocked(aiCorrectionsAPI.getStats).mockResolvedValue({
      total: 0,
      this_month: 0,
      by_type: {},
      most_corrected: [],
    });
  });

  it('renders exactly two ClassifierAccuracyCards, sentiment first then category', async () => {
    render(<AISettingsPage />);

    await waitFor(() => {
      expect(screen.getAllByTestId('classifier-card')).toHaveLength(2);
    });

    const cards = screen.getAllByTestId('classifier-card');
    expect(cards[0]).toHaveAttribute('data-type', 'sentiment');
    expect(cards[1]).toHaveAttribute('data-type', 'category');
  });
});
