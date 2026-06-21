import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock categories API
vi.mock('@/lib/api/categories', () => ({
  categoriesAPI: {
    getHealthWeights: vi.fn(),
    updateHealthWeights: vi.fn(),
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { categoriesAPI } from '@/lib/api/categories';
import { toast } from 'sonner';
import { HealthWeightsEditor } from '@/components/settings/HealthWeightsEditor';

const DEFAULT_WEIGHTS = { churn: 35, sentiment: 25, resolution: 25, frequency: 15 };

beforeEach(() => {
  vi.clearAllMocks();
  (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(DEFAULT_WEIGHTS);
});

describe('HealthWeightsEditor', () => {
  describe('initial render', () => {
    it('renders all four weight inputs with default values', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);

      await waitFor(() => {
        expect(screen.getByTestId('weight-input-churn')).toHaveValue(35);
        expect(screen.getByTestId('weight-input-sentiment')).toHaveValue(25);
        expect(screen.getByTestId('weight-input-resolution')).toHaveValue(25);
        expect(screen.getByTestId('weight-input-frequency')).toHaveValue(15);
      });
    });

    it('shows the total sum as 100 initially', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);

      await waitFor(() => {
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('100%');
      });
    });

    it('does not show validation error when sum is 100', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);

      await waitFor(() => {
        expect(screen.queryByTestId('weights-error')).not.toBeInTheDocument();
      });
    });
  });

  describe('validation', () => {
    it('shows error and blocks save when weights do not sum to 100', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);

      await waitFor(() => screen.getByTestId('weight-input-churn'));

      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '50' } });

      await waitFor(() => {
        // Error message should appear
        expect(screen.getByTestId('weights-error')).toBeInTheDocument();
        // Save button should be disabled
        expect(screen.getByTestId('save-weights-button')).toBeDisabled();
      });
    });

    it('sum indicator reflects total across all inputs', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      // Change churn to 40 (total becomes 40+25+25+15 = 105)
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '40' } });

      await waitFor(() => {
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('105%');
        expect(screen.getByTestId('weights-error')).toBeInTheDocument();
      });
    });

    it('allows saving when weights are adjusted back to exactly 100', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      // Change churn to 40, frequency to 10 → total = 40+25+25+10 = 100
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '40' } });
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '10' } });

      await waitFor(() => {
        expect(screen.queryByTestId('weights-error')).not.toBeInTheDocument();
        expect(screen.getByTestId('save-weights-button')).not.toBeDisabled();
      });
    });
  });

  describe('save interaction', () => {
    it('calls updateHealthWeights and shows success toast on save', async () => {
      const updated = { churn: 40, sentiment: 25, resolution: 25, frequency: 10 };
      (categoriesAPI.updateHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(updated);

      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '40' } });
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '10' } });

      await waitFor(() => screen.getByTestId('save-weights-button'));
      fireEvent.click(screen.getByTestId('save-weights-button'));

      await waitFor(() => {
        expect(categoriesAPI.updateHealthWeights).toHaveBeenCalledWith(updated);
        expect(toast.success).toHaveBeenCalledWith('Health score weights saved');
      });
    });

    it('shows error toast when save fails', async () => {
      (categoriesAPI.updateHealthWeights as ReturnType<typeof vi.fn>).mockRejectedValue({
        response: { data: { detail: 'Weights must sum to 100' } },
      });

      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      // Make weights sum to 100 differently (so isDirty = true and isValid = true)
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '40' } });
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '10' } });

      await waitFor(() => expect(screen.getByTestId('save-weights-button')).not.toBeDisabled());
      fireEvent.click(screen.getByTestId('save-weights-button'));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Weights must sum to 100');
      });
    });
  });

  describe('access control', () => {
    it('disables inputs when user is not admin/owner', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={false} />);

      await waitFor(() => {
        expect(screen.getByTestId('weight-input-churn')).toBeDisabled();
        expect(screen.getByTestId('weight-input-sentiment')).toBeDisabled();
      });
    });

    it('hides save and reset buttons when user is not admin/owner', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={false} />);

      await waitFor(() => screen.getByTestId('weights-sum'));

      expect(screen.queryByTestId('save-weights-button')).not.toBeInTheDocument();
      expect(screen.queryByTestId('reset-weights-button')).not.toBeInTheDocument();
    });
  });

  describe('reset to default', () => {
    it('resets weights to defaults when Reset to Default is clicked', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '50' } });
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '0' } });

      await waitFor(() => screen.getByTestId('reset-weights-button'));
      fireEvent.click(screen.getByTestId('reset-weights-button'));

      await waitFor(() => {
        expect(screen.getByTestId('weight-input-churn')).toHaveValue(35);
        expect(screen.getByTestId('weight-input-frequency')).toHaveValue(15);
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('100%');
      });
    });
  });
});
