'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';
import { REREFLECT_STATUSES } from '@/lib/constants/workflow-status';

export interface StatusMappingForeignKey {
  key: string;
  label: string;
}

interface StatusMappingEditorProps {
  /** Ordered list of the provider's foreign statuses/categories to map. */
  foreignKeys: StatusMappingForeignKey[];
  /** The currently-stored override (null when unset — server default applies). */
  currentMapping: Record<string, string> | null;
  /** Persists the full mapping object (backend merges partial overrides over the default). */
  onSave: (mapping: Record<string, string>) => Promise<void>;
  /** Read-only mode — hides Save/Reset and disables every row's Select. */
  disabled?: boolean;
  /** Optional copy shown above the table (e.g. clarifying "category" granularity). */
  description?: string;
}

// Shared, generalized status-mapping editor (mapping-editor aspect of
// status-sync-realtime-mapping) — table-agnostic version of the "Status
// Mapping" tab in LinearSettings.tsx, usable by Jira/Asana/Zendesk cards.
export function StatusMappingEditor({
  foreignKeys,
  currentMapping,
  onSave,
  disabled = false,
  description,
}: StatusMappingEditorProps) {
  const [mapping, setMapping] = useState<Record<string, string>>(currentMapping ?? {});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleChange = (key: string, value: string) => {
    setMapping((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const persist = async (next: Record<string, string>, successMessage: string, failureMessage: string) => {
    setSaving(true);
    try {
      await onSave(next);
      setDirty(false);
      toast.success(successMessage);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : failureMessage;
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleSave = () => persist(mapping, 'Status mapping saved.', 'Failed to save status mapping.');

  const handleReset = () => {
    setMapping({});
    return persist({}, 'Status mapping reset to defaults.', 'Failed to reset status mapping.');
  };

  return (
    <div className="space-y-4">
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Foreign Status</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Rereflect Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {foreignKeys.map((fk) => (
              <tr key={fk.key}>
                <td className="px-4 py-3 font-medium">{fk.label}</td>
                <td className="px-4 py-3">
                  <Select
                    value={mapping[fk.key] ?? ''}
                    onValueChange={(val) => handleChange(fk.key, val)}
                    disabled={disabled || saving}
                  >
                    <SelectTrigger className="w-40">
                      <SelectValue placeholder="Select status…" />
                    </SelectTrigger>
                    <SelectContent>
                      {REREFLECT_STATUSES.map((s) => (
                        <SelectItem key={s.value} value={s.value}>
                          {s.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!disabled && (
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={handleReset} disabled={saving}>
            Reset to defaults
          </Button>
          <Button onClick={handleSave} disabled={!dirty || saving}>
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving…
              </>
            ) : (
              'Save Mapping'
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
