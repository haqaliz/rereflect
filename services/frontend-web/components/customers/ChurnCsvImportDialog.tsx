'use client';

import { useState, useRef } from 'react';
import { Upload, Loader2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { importChurnEventsCsv } from '@/lib/api/churn-events';
import type { BulkCreateResult } from '@/lib/api/churn-events';

const REQUIRED_COLUMNS = ['email', 'churned_at'];
const PREVIEW_ROW_LIMIT = 5;

interface CsvPreview {
  headers: string[];
  rows: string[][];
  missingColumns: string[];
}

interface ChurnCsvImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (result: BulkCreateResult) => void;
}

function parseCsvPreview(text: string): CsvPreview {
  const lines = text.split('\n').filter((l) => l.trim().length > 0);
  if (lines.length === 0) {
    return { headers: [], rows: [], missingColumns: REQUIRED_COLUMNS };
  }
  const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
  const missingColumns = REQUIRED_COLUMNS.filter((col) => !headers.includes(col));
  const dataLines = lines.slice(1, PREVIEW_ROW_LIMIT + 1);
  const rows = dataLines.map((line) => line.split(',').map((c) => c.trim()));
  return { headers, rows, missingColumns };
}

export function ChurnCsvImportDialog({
  open,
  onOpenChange,
  onSuccess,
}: ChurnCsvImportDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    if (!selected) return;
    setFile(selected);
    setImportErrors([]);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setPreview(parseCsvPreview(text));
    };
    reader.readAsText(selected);
  };

  const handleImport = async () => {
    if (!file || !preview || preview.missingColumns.length > 0) return;
    setSubmitting(true);
    try {
      const result = await importChurnEventsCsv(file);
      setImportErrors(result.errors);
      const msg = `${result.created} imported${result.skipped > 0 ? `, ${result.skipped} skipped` : ''}.`;
      toast.success(msg);
      onSuccess?.(result);
      if (result.errors.length === 0) {
        onOpenChange(false);
      }
    } catch {
      toast.error('Import failed. Please check the file and try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const emailColIndex = preview?.headers.indexOf('email') ?? -1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import Churn Events from CSV</DialogTitle>
          <DialogDescription>
            Required columns: <code>email</code>, <code>churned_at</code>. Optional:{' '}
            <code>reason_code</code>, <code>reason_text</code>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="csv-file-input">CSV File</Label>
            <input
              id="csv-file-input"
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleFileChange}
              className="block w-full text-sm text-muted-foreground file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border file:border-border file:text-sm file:font-medium file:bg-secondary file:text-foreground hover:file:bg-secondary/80 cursor-pointer"
              aria-label="CSV file"
            />
          </div>

          {/* Column validation errors */}
          {preview && preview.missingColumns.length > 0 && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2">
              <AlertTriangle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
              <p className="text-sm text-destructive">
                CSV is missing required {preview.missingColumns.length === 1 ? 'column' : 'columns'}:{' '}
                {preview.missingColumns.join(', ')}
              </p>
            </div>
          )}

          {/* Preview table */}
          {preview && preview.missingColumns.length === 0 && preview.rows.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                Preview (first {preview.rows.length} rows)
              </p>
              <div className="rounded-md border border-border overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      {preview.headers.map((h) => (
                        <th key={h} className="px-3 py-1.5 text-left font-medium text-muted-foreground">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i} className="border-t border-border">
                        {row.map((cell, j) => (
                          <td key={j} className="px-3 py-1.5 text-foreground truncate max-w-[160px]">
                            {emailColIndex === j ? (
                              <span data-testid="preview-email">{cell}</span>
                            ) : (
                              cell
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Row-level errors from import */}
          {importErrors.length > 0 && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 space-y-1">
              <p className="text-sm font-medium text-destructive">Import errors:</p>
              {importErrors.map((err, i) => (
                <p key={i} className="text-xs text-destructive font-mono">
                  {err}
                </p>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button
            onClick={handleImport}
            disabled={submitting || !file || !preview || preview.missingColumns.length > 0}
          >
            {submitting ? (
              <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
            ) : (
              <Upload className="w-3.5 h-3.5 mr-2" />
            )}
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
