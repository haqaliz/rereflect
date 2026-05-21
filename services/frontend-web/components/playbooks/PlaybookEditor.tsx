'use client';

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent } from '@/components/ui/card';
import { Plus, Trash2 } from 'lucide-react';
import { type Playbook, type PlaybookAction, ACTION_TYPE_LABELS } from '@/lib/api/playbooks';

// ─── ActionCard ───────────────────────────────────────────────────────────────

interface ActionCardProps {
  action: PlaybookAction;
  index: number;
  readOnly: boolean;
  onChange: (index: number, action: PlaybookAction) => void;
  onRemove: (index: number) => void;
}

function ActionCard({ action, index, readOnly, onChange, onRemove }: ActionCardProps) {
  const actionTypes = Object.keys(ACTION_TYPE_LABELS);

  return (
    <div
      data-testid={`action-card-${index}`}
      className="flex items-center gap-3 p-3 rounded-lg border border-border bg-muted/30"
    >
      <span className="text-xs text-muted-foreground w-5 text-center shrink-0">
        {index + 1}
      </span>

      {readOnly ? (
        <span className="flex-1 text-sm">{ACTION_TYPE_LABELS[action.type] ?? action.type}</span>
      ) : (
        <Select
          value={action.type}
          onValueChange={(val) => onChange(index, { ...action, type: val })}
          disabled={readOnly}
        >
          <SelectTrigger className="flex-1 h-8 text-xs">
            <SelectValue placeholder="Select action type" />
          </SelectTrigger>
          <SelectContent>
            {actionTypes.map((t) => (
              <SelectItem key={t} value={t} className="text-xs">
                {ACTION_TYPE_LABELS[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {!readOnly && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
          onClick={() => onRemove(index)}
          aria-label="Remove action"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      )}
    </div>
  );
}

// ─── PlaybookEditor ───────────────────────────────────────────────────────────

interface PlaybookEditorProps {
  playbook?: Playbook;
  onSave: (data: Partial<Playbook>) => Promise<unknown> | void;
  onCancel: () => void;
  readOnly?: boolean;
}

export function PlaybookEditor({ playbook, onSave, onCancel, readOnly = false }: PlaybookEditorProps) {
  const [name, setName] = useState(playbook?.name ?? '');
  const [description, setDescription] = useState(playbook?.description ?? '');
  const [probMin, setProbMin] = useState(String(playbook?.probability_min ?? 0.3));
  const [probMax, setProbMax] = useState(String(playbook?.probability_max ?? 0.7));
  const [actions, setActions] = useState<PlaybookAction[]>(playbook?.action_sequence ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name is required';
    if (actions.length === 0) errs.actions = 'At least one action is required';
    const min = parseFloat(probMin);
    const max = parseFloat(probMax);
    if (!isNaN(min) && !isNaN(max) && min >= max) {
      errs.probability = 'Min must be less than max';
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        description: description.trim() || null,
        probability_min: parseFloat(probMin),
        probability_max: parseFloat(probMax),
        action_sequence: actions,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleAddAction = () => {
    setActions((prev) => [...prev, { type: 'send_notification' }]);
  };

  const handleRemoveAction = (index: number) => {
    setActions((prev) => prev.filter((_, i) => i !== index));
  };

  const handleChangeAction = (index: number, updated: PlaybookAction) => {
    setActions((prev) => prev.map((a, i) => (i === index ? updated : a)));
  };

  return (
    <div className="space-y-6">
      {/* Name */}
      <div className="space-y-1.5">
        <Label htmlFor="playbook-name">Name</Label>
        <Input
          id="playbook-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={readOnly}
          placeholder="e.g., Critical Save"
        />
        {errors.name && (
          <p className="text-xs text-destructive" role="alert">{errors.name}</p>
        )}
      </div>

      {/* Description */}
      <div className="space-y-1.5">
        <Label htmlFor="playbook-description">Description</Label>
        <Textarea
          id="playbook-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={readOnly}
          placeholder="Describe when to use this playbook..."
          rows={2}
        />
      </div>

      {/* Probability Range */}
      <div className="space-y-2">
        <Label>Probability Range</Label>
        <div className="flex items-center gap-3">
          <div className="flex-1 space-y-1">
            <Label htmlFor="prob-min" className="text-xs text-muted-foreground">Min (%)</Label>
            <Input
              id="prob-min"
              data-testid="prob-min-input"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={probMin}
              onChange={(e) => setProbMin(e.target.value)}
              disabled={readOnly}
              placeholder="0.30"
            />
          </div>
          <span className="text-muted-foreground mt-5">–</span>
          <div className="flex-1 space-y-1">
            <Label htmlFor="prob-max" className="text-xs text-muted-foreground">Max (%)</Label>
            <Input
              id="prob-max"
              data-testid="prob-max-input"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={probMax}
              onChange={(e) => setProbMax(e.target.value)}
              disabled={readOnly}
              placeholder="0.70"
            />
          </div>
        </div>
        {errors.probability && (
          <p className="text-xs text-destructive" role="alert">{errors.probability}</p>
        )}
      </div>

      {/* Action Sequence */}
      <div className="space-y-2">
        <Label>Action Sequence</Label>
        {actions.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-6 text-center text-muted-foreground text-sm">
              No actions yet. Add an action below.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {actions.map((action, i) => (
              <ActionCard
                key={i}
                action={action}
                index={i}
                readOnly={readOnly}
                onChange={handleChangeAction}
                onRemove={handleRemoveAction}
              />
            ))}
          </div>
        )}
        {errors.actions && (
          <p className="text-xs text-destructive" role="alert">{errors.actions}</p>
        )}
        {!readOnly && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-1 text-xs"
            onClick={handleAddAction}
          >
            <Plus className="w-3.5 h-3.5 mr-1" />
            Add action
          </Button>
        )}
      </div>

      {/* Footer Buttons */}
      {!readOnly && (
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-border">
          <Button variant="outline" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save playbook'}
          </Button>
        </div>
      )}
    </div>
  );
}
