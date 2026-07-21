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

// Six-key default, matching categories.py's persisted defaults (churn35/sentiment25/
// resolution25/frequency15/usage0/crm0). `usage` and `crm` must round-trip through every
// save — see spec.md (D4) — even though `crm` is never rendered as an input.
const DEFAULT_WEIGHTS = { churn: 35, sentiment: 25, resolution: 25, frequency: 15, usage: 0, crm: 0 };

beforeEach(() => {
  vi.clearAllMocks();
  (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(DEFAULT_WEIGHTS);
});

describe('HealthWeightsEditor', () => {
  describe('initial render', () => {
    it('renders all five editable weight inputs with default values', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);

      await waitFor(() => {
        expect(screen.getByTestId('weight-input-churn')).toHaveValue(35);
        expect(screen.getByTestId('weight-input-sentiment')).toHaveValue(25);
        expect(screen.getByTestId('weight-input-resolution')).toHaveValue(25);
        expect(screen.getByTestId('weight-input-frequency')).toHaveValue(15);
        expect(screen.getByTestId('weight-input-usage')).toHaveValue(0);
      });
    });

    it('renders exactly five editable weight inputs, including usage, with no crm input (AC 10, 9)', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      expect(screen.getByTestId('weight-input-usage')).toBeInTheDocument();
      expect(screen.getByText('Usage Activity')).toBeInTheDocument();
      expect(screen.getByText(/usage-activity component/i)).toBeInTheDocument();
      expect(screen.queryByTestId('weight-input-crm')).not.toBeInTheDocument();
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

      // Change churn to 40 (total becomes 40+25+25+15+0+0 = 105)
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '40' } });

      await waitFor(() => {
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('105%');
        expect(screen.getByTestId('weights-error')).toBeInTheDocument();
      });
    });

    it('allows saving when weights are adjusted back to exactly 100', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      // Change churn to 40, frequency to 10 → total = 40+25+25+10+0+0 = 100
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '40' } });
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '10' } });

      await waitFor(() => {
        expect(screen.queryByTestId('weights-error')).not.toBeInTheDocument();
        expect(screen.getByTestId('save-weights-button')).not.toBeDisabled();
      });
    });

    it('editing the usage input updates the total and marks the form dirty (AC 14)', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-usage'));

      expect(screen.getByTestId('save-weights-button')).toBeDisabled();

      // Raise usage to 10, drop frequency to 5 → total stays 100 (35+25+25+5+10+0)
      fireEvent.change(screen.getByTestId('weight-input-usage'), { target: { value: '10' } });
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '5' } });

      await waitFor(() => {
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('100%');
        expect(screen.getByTestId('save-weights-button')).not.toBeDisabled();
      });
    });

    it('totals all six weights: base sum 80 + usage 10 + crm 10 reads 100 and Save is reachable (AC 11)', async () => {
      const loaded = { churn: 30, sentiment: 20, resolution: 20, frequency: 10, usage: 10, crm: 10 };
      (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(loaded);

      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => {
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('100%');
        expect(screen.queryByTestId('weights-error')).not.toBeInTheDocument();
      });

      // Net-zero edit so the form is dirty without changing the (already-correct) total.
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '31' } });
      fireEvent.change(screen.getByTestId('weight-input-resolution'), { target: { value: '19' } });

      await waitFor(() => {
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('100%');
        expect(screen.getByTestId('save-weights-button')).not.toBeDisabled();
      });
    });

    it('blocks save on a six-key sum != 100 caused only by the hidden crm weight, and names it in the error (AC 12)', async () => {
      // Five visible fields sum to 90; crm (hidden) is 10, so the six-key total is 100 until frequency drops.
      const loaded = { churn: 30, sentiment: 25, resolution: 25, frequency: 10, usage: 0, crm: 10 };
      (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(loaded);

      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      // Drop frequency by 10 → visible fields alone now read 90, six-key total also 90.
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '0' } });

      await waitFor(() => {
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('90%');
        expect(screen.getByTestId('weights-error')).toBeInTheDocument();
        expect(screen.getByTestId('weights-error')).toHaveTextContent(/CRM/i);
        expect(screen.getByTestId('save-weights-button')).toBeDisabled();
      });
    });
  });

  describe('save interaction', () => {
    it('calls updateHealthWeights and shows success toast on save', async () => {
      const updated = { churn: 40, sentiment: 25, resolution: 25, frequency: 10, usage: 0, crm: 0 };
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

    it('does not zero the usage weight on save (D4 fix, AC 8)', async () => {
      const loaded = { churn: 30, sentiment: 25, resolution: 25, frequency: 10, usage: 10, crm: 0 };
      (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(loaded);
      (categoriesAPI.updateHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(loaded);

      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => expect(screen.getByTestId('weight-input-usage')).toHaveValue(10));

      // Edit a base field only — usage is untouched — then save.
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '31' } });
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '9' } });

      await waitFor(() => expect(screen.getByTestId('save-weights-button')).not.toBeDisabled());
      fireEvent.click(screen.getByTestId('save-weights-button'));

      await waitFor(() => {
        expect(categoriesAPI.updateHealthWeights).toHaveBeenCalledWith({
          churn: 31, sentiment: 25, resolution: 25, frequency: 9, usage: 10, crm: 0,
        });
      });
    });

    it('does not zero the crm weight on save, even though no crm input is rendered (D4 fix, AC 9)', async () => {
      const loaded = { churn: 30, sentiment: 25, resolution: 15, frequency: 10, usage: 10, crm: 10 };
      (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(loaded);
      (categoriesAPI.updateHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(loaded);

      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('weight-input-churn'));

      expect(screen.queryByTestId('weight-input-crm')).not.toBeInTheDocument();

      // Edit visible fields only — crm is carried in state, never shown, never touched.
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '31' } });
      fireEvent.change(screen.getByTestId('weight-input-resolution'), { target: { value: '14' } });

      await waitFor(() => expect(screen.getByTestId('save-weights-button')).not.toBeDisabled());
      fireEvent.click(screen.getByTestId('save-weights-button'));

      await waitFor(() => {
        expect(categoriesAPI.updateHealthWeights).toHaveBeenCalledWith({
          churn: 31, sentiment: 25, resolution: 14, frequency: 10, usage: 10, crm: 10,
        });
      });
    });
  });

  describe('access control', () => {
    it('disables inputs when user is not admin/owner', async () => {
      render(<HealthWeightsEditor isAdminOrOwner={false} />);

      await waitFor(() => {
        expect(screen.getByTestId('weight-input-churn')).toBeDisabled();
        expect(screen.getByTestId('weight-input-sentiment')).toBeDisabled();
        expect(screen.getByTestId('weight-input-usage')).toBeDisabled();
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
        expect(screen.getByTestId('weight-input-usage')).toHaveValue(0);
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('100%');
      });
    });

    it('produces the six-key default object and keeps Save reachable on a subsequent save (AC 13)', async () => {
      const loaded = { churn: 30, sentiment: 20, resolution: 20, frequency: 10, usage: 10, crm: 10 };
      (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(loaded);
      (categoriesAPI.updateHealthWeights as ReturnType<typeof vi.fn>).mockResolvedValue(DEFAULT_WEIGHTS);

      render(<HealthWeightsEditor isAdminOrOwner={true} />);
      await waitFor(() => screen.getByTestId('reset-weights-button'));

      fireEvent.click(screen.getByTestId('reset-weights-button'));

      await waitFor(() => {
        expect(screen.getByTestId('weights-sum')).toHaveTextContent('100%');
        expect(screen.getByTestId('save-weights-button')).not.toBeDisabled();
      });

      fireEvent.click(screen.getByTestId('save-weights-button'));

      await waitFor(() => {
        expect(categoriesAPI.updateHealthWeights).toHaveBeenCalledWith(DEFAULT_WEIGHTS);
      });
    });
  });

  describe('failed load', () => {
    it('blocks save and surfaces the failure instead of saving from a defaulted-crm state', async () => {
      (categoriesAPI.getHealthWeights as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network error'));

      render(<HealthWeightsEditor isAdminOrOwner={true} />);

      await waitFor(() => {
        expect(screen.getByTestId('weights-load-error')).toBeInTheDocument();
      });

      // Net-zero edit so sum/dirty checks alone would otherwise allow a save.
      fireEvent.change(screen.getByTestId('weight-input-churn'), { target: { value: '36' } });
      fireEvent.change(screen.getByTestId('weight-input-frequency'), { target: { value: '14' } });

      await waitFor(() => expect(screen.getByTestId('weights-sum')).toHaveTextContent('100%'));
      expect(screen.getByTestId('save-weights-button')).toBeDisabled();
      expect(categoriesAPI.updateHealthWeights).not.toHaveBeenCalled();
    });
  });
});
