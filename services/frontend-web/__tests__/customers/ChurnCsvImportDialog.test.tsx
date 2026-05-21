import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

vi.mock('@/lib/api/churn-events', () => ({
  importChurnEventsCsv: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { importChurnEventsCsv } from '@/lib/api/churn-events';
import { toast } from 'sonner';
import { ChurnCsvImportDialog } from '@/components/customers/ChurnCsvImportDialog';

const CSV_CONTENT = `email,churned_at,reason_code,reason_text
alice@example.com,2026-05-01,price,Too expensive
bob@example.com,2026-05-02,competitor,Switched to rival
carol@example.com,2026-05-03,product_quality,
dave@example.com,2026-05-04,no_longer_needed,
eve@example.com,2026-05-05,other,
frank@example.com,2026-05-06,silent_churn,`;

function makeFile(content: string, filename = 'churn.csv', type = 'text/csv') {
  return new File([content], filename, { type });
}

function renderDialog(props?: Partial<React.ComponentProps<typeof ChurnCsvImportDialog>>) {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onSuccess: vi.fn(),
    ...props,
  };
  return render(<ChurnCsvImportDialog {...defaultProps} />);
}

describe('ChurnCsvImportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows file picker input', () => {
    renderDialog();
    const input = screen.getByLabelText(/csv file/i);
    expect(input).toBeInTheDocument();
  });

  it('accepts only .csv files', () => {
    renderDialog();
    const input = screen.getByLabelText(/csv file/i) as HTMLInputElement;
    expect(input.accept).toContain('.csv');
  });

  it('shows preview of first 5 rows after upload', async () => {
    const user = userEvent.setup();
    renderDialog();

    const input = screen.getByLabelText(/csv file/i);
    const file = makeFile(CSV_CONTENT);
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
      expect(screen.getByText('bob@example.com')).toBeInTheDocument();
      expect(screen.getByText('carol@example.com')).toBeInTheDocument();
      expect(screen.getByText('dave@example.com')).toBeInTheDocument();
      expect(screen.getByText('eve@example.com')).toBeInTheDocument();
      // frank is row 6 — should be hidden in preview
      expect(screen.queryByText('frank@example.com')).not.toBeInTheDocument();
    });
  });

  it('shows column validation for required headers', async () => {
    const user = userEvent.setup();
    renderDialog();

    const badCsv = `name,date\nalice,2026-05-01`;
    const input = screen.getByLabelText(/csv file/i);
    await user.upload(input, makeFile(badCsv));

    await waitFor(() => {
      expect(screen.getByText(/missing.*email/i)).toBeInTheDocument();
    });
  });

  it('Import button calls importChurnEventsCsv with the File', async () => {
    const user = userEvent.setup();
    (importChurnEventsCsv as ReturnType<typeof vi.fn>).mockResolvedValue({
      created: 6,
      skipped: 0,
      errors: [],
    });
    renderDialog();

    const input = screen.getByLabelText(/csv file/i);
    const file = makeFile(CSV_CONTENT);
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /import/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /import/i }));

    await waitFor(() => {
      expect(importChurnEventsCsv).toHaveBeenCalledWith(expect.any(File));
    });
  });

  it('displays result summary after import', async () => {
    const user = userEvent.setup();
    (importChurnEventsCsv as ReturnType<typeof vi.fn>).mockResolvedValue({
      created: 5,
      skipped: 1,
      errors: [],
    });
    renderDialog();

    const input = screen.getByLabelText(/csv file/i);
    await user.upload(input, makeFile(CSV_CONTENT));

    await waitFor(() => screen.getByRole('button', { name: /import/i }));
    await user.click(screen.getByRole('button', { name: /import/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/5 imported/i));
    });
  });

  it('shows row-level errors when present', async () => {
    const user = userEvent.setup();
    (importChurnEventsCsv as ReturnType<typeof vi.fn>).mockResolvedValue({
      created: 4,
      skipped: 0,
      errors: ['row 3: invalid reason_code "bad_value"'],
    });
    renderDialog();

    const input = screen.getByLabelText(/csv file/i);
    await user.upload(input, makeFile(CSV_CONTENT));

    await waitFor(() => screen.getByRole('button', { name: /import/i }));
    await user.click(screen.getByRole('button', { name: /import/i }));

    await waitFor(() => {
      expect(screen.getByText(/row 3: invalid reason_code/i)).toBeInTheDocument();
    });
  });

  it('handles network failure gracefully', async () => {
    const user = userEvent.setup();
    (importChurnEventsCsv as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));
    renderDialog();

    const input = screen.getByLabelText(/csv file/i);
    await user.upload(input, makeFile(CSV_CONTENT));

    await waitFor(() => screen.getByRole('button', { name: /import/i }));
    await user.click(screen.getByRole('button', { name: /import/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });
});
