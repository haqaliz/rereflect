'use client';

import { useState } from 'react';
import { X, Loader2, Tag as TagIcon } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
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
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { customersAPI } from '@/lib/api/customers';
import type { Cohort, BulkTagMode } from '@/lib/api/customers';

interface BulkTagDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cohort: Cohort | null;
  /** Size of the resolved cohort — same value shown in the "Bulk Actions (N)" trigger. */
  cohortCount: number;
  onSuccess?: () => void;
}

export function BulkTagDialog({
  open,
  onOpenChange,
  cohort,
  cohortCount,
  onSuccess,
}: BulkTagDialogProps) {
  const queryClient = useQueryClient();
  const [tagInput, setTagInput] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [mode, setMode] = useState<BulkTagMode>('add');
  const [submitting, setSubmitting] = useState(false);

  const addTagFromInput = () => {
    const value = tagInput.trim();
    if (!value) return;
    setTags((prev) => (prev.includes(value) ? prev : [...prev, value]));
    setTagInput('');
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTagFromInput();
    }
  };

  const removeTag = (tag: string) => {
    setTags((prev) => prev.filter((t) => t !== tag));
  };

  const reset = () => {
    setTagInput('');
    setTags([]);
    setMode('add');
  };

  const handleSubmit = async () => {
    if (!cohort || tags.length === 0) return;
    setSubmitting(true);
    try {
      const result = await customersAPI.bulkTag(cohort, tags, mode);
      const verb = mode === 'add' ? 'tagged' : 'untagged';
      const msg = `${result.updated} customer${result.updated === 1 ? '' : 's'} ${verb}${
        result.skipped > 0 ? `, ${result.skipped} skipped` : ''
      }${result.errors.length > 0 ? `, ${result.errors.length} error${result.errors.length === 1 ? '' : 's'}` : ''}.`;
      toast.success(msg);
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      onSuccess?.();
      onOpenChange(false);
      reset();
    } catch {
      toast.error('Failed to update tags. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Tag Customers</DialogTitle>
          <DialogDescription>
            Add or remove tags across <strong>{cohortCount} customers</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="bulk-tag-mode">Mode</Label>
            <Select value={mode} onValueChange={(v) => setMode(v as BulkTagMode)}>
              <SelectTrigger id="bulk-tag-mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="add">Add tags</SelectItem>
                <SelectItem value="remove">Remove tags</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="bulk-tag-input">Tags</Label>
            <Input
              id="bulk-tag-input"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={handleInputKeyDown}
              onBlur={addTagFromInput}
              placeholder="Type a tag and press Enter"
              aria-label="Tag input"
            />
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {tags.map((tag) => (
                  <Badge
                    key={tag}
                    variant="secondary"
                    className="flex items-center gap-1 pr-1"
                  >
                    <TagIcon className="w-3 h-3" />
                    {tag}
                    <button
                      type="button"
                      onClick={() => removeTag(tag)}
                      className="ml-1 rounded-full hover:bg-muted-foreground/20"
                      aria-label={`Remove ${tag}`}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || tags.length === 0 || !cohort}>
            {submitting && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
            {mode === 'add' ? 'Add tags' : 'Remove tags'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
