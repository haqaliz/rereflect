'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { categoriesAPI, type HealthWeights } from '@/lib/api/categories';
import { toast } from 'sonner';
import { Loader2, Save } from 'lucide-react';

const DEFAULT_WEIGHTS: HealthWeights = {
  churn: 35,
  sentiment: 25,
  resolution: 25,
  frequency: 15,
  usage: 0,
  crm: 0,
};

/** `crm` is intentionally excluded here: it round-trips through state and the save payload
 *  (see HealthWeights in lib/api/categories.ts) but is not yet an editable field in this UI. */
type EditableWeightKey = Exclude<keyof HealthWeights, 'crm'>;

const EDITABLE_KEYS: EditableWeightKey[] = ['churn', 'sentiment', 'resolution', 'frequency', 'usage'];

const WEIGHT_LABELS: Record<EditableWeightKey, string> = {
  churn: 'Churn Risk',
  sentiment: 'Sentiment',
  resolution: 'Resolution Time',
  frequency: 'Feedback Frequency',
  usage: 'Usage Activity',
};

const WEIGHT_DESCRIPTIONS: Record<EditableWeightKey, string> = {
  churn: 'Weight applied to the inverted average churn-risk score',
  sentiment: 'Weight applied to the average sentiment score',
  resolution: 'Weight applied to the average issue resolution speed',
  frequency: 'Weight applied to the complaint frequency trend',
  usage: 'Weight applied to the usage-activity component (login recency, frequency, feature breadth)',
};

interface HealthWeightsEditorProps {
  isAdminOrOwner: boolean;
}

export function HealthWeightsEditor({ isAdminOrOwner }: HealthWeightsEditorProps) {
  const [weights, setWeights] = useState<HealthWeights>(DEFAULT_WEIGHTS);
  const [saved, setSaved] = useState<HealthWeights>(DEFAULT_WEIGHTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    categoriesAPI.getHealthWeights()
      .then((w) => {
        setWeights(w);
        setSaved(w);
      })
      .catch((err) => {
        // A failed load must never leave DEFAULT_WEIGHTS (crm: 0, usage: 0) saveable — that is
        // the exact zeroing shape this fix removes. Block Save and surface the failure instead.
        console.error('Failed to load health weights:', err);
        setLoadError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  const total = weights.churn + weights.sentiment + weights.resolution + weights.frequency + weights.usage + weights.crm;
  const isDirty = JSON.stringify(weights) !== JSON.stringify(saved);
  const isValid = total === 100;

  const handleChange = (key: EditableWeightKey, raw: string) => {
    const parsed = parseInt(raw, 10);
    setWeights((prev) => ({ ...prev, [key]: isNaN(parsed) ? 0 : Math.max(0, Math.min(100, parsed)) }));
  };

  const handleSave = async () => {
    if (!isValid || loadError) return;
    setSaving(true);
    try {
      const updated = await categoriesAPI.updateHealthWeights(weights);
      setSaved(updated);
      setWeights(updated);
      toast.success('Health score weights saved');
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Failed to save weights';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => setWeights(DEFAULT_WEIGHTS);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="health-weights-editor">
      <p className="text-sm text-muted-foreground">
        Configure how each component contributes to the customer health score. Values must sum to exactly 100.
      </p>

      {loadError && (
        <div
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          data-testid="weights-load-error"
        >
          <span>
            Couldn&apos;t load your organization&apos;s current health score weights. Saving is
            disabled until this loads successfully, so an existing usage or CRM weight isn&apos;t
            overwritten with 0.
          </span>
        </div>
      )}

      <div className="space-y-3">
        {EDITABLE_KEYS.map((key) => (
          <div key={key} className="grid grid-cols-1 sm:grid-cols-3 gap-2 items-start">
            <div className="sm:col-span-2">
              <p className="text-sm font-medium text-foreground">{WEIGHT_LABELS[key]}</p>
              <p className="text-xs text-muted-foreground">{WEIGHT_DESCRIPTIONS[key]}</p>
            </div>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                min={0}
                max={100}
                value={weights[key]}
                onChange={(e) => handleChange(key, e.target.value)}
                disabled={!isAdminOrOwner}
                className="w-20 text-right tabular-nums"
                data-testid={`weight-input-${key}`}
              />
              <span className="text-sm text-muted-foreground">%</span>
            </div>
          </div>
        ))}
      </div>

      {/* Sum indicator */}
      <div
        className={`flex items-center justify-between px-3 py-2 rounded-lg border text-sm font-medium ${
          isValid
            ? 'border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400'
            : 'border-destructive/30 bg-destructive/10 text-destructive'
        }`}
        data-testid="weights-sum-indicator"
      >
        <span>Total</span>
        <span data-testid="weights-sum">{total}%</span>
      </div>

      {!isValid && (
        <p className="text-xs text-destructive" data-testid="weights-error">
          Weights must sum to exactly 100 (currently {total}
          {weights.crm > 0 && `, including a ${weights.crm}% CRM weight not shown here`})
        </p>
      )}

      {isAdminOrOwner && (
        <div className="flex gap-2">
          <Button
            onClick={handleSave}
            disabled={!isDirty || !isValid || saving || loadError}
            size="sm"
            data-testid="save-weights-button"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 mr-1 animate-spin" />
            ) : (
              <Save className="w-4 h-4 mr-1" />
            )}
            Save Weights
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={saving}
            data-testid="reset-weights-button"
          >
            Reset to Default
          </Button>
        </div>
      )}
    </div>
  );
}
