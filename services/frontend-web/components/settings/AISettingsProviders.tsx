'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { Check, X, Key, Lock, Loader2, FlaskConical } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import {
  aiSettingsAPI,
  type AISettings,
  type AIKey,
  type AIModel,
  type AIModelTestResponse,
} from '@/lib/api/ai-settings';
import {
  getProviderLogo,
  PROVIDER_NAMES,
  TierBadge,
} from '@/components/icons/ProviderLogos';

const PROVIDERS = ['openai', 'anthropic', 'google'];

const TASK_TYPES: Array<{ key: keyof AISettings['models']; label: string }> = [
  { key: 'categorization', label: 'Categorization' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'insights', label: 'Insights' },
];

const PLAN_HIERARCHY: Record<string, number> = { free: 0, pro: 1, business: 2, enterprise: 3 };

interface AISettingsProvidersProps {
  settings: AISettings;
  onUpdate: (updated: AISettings) => void;
}

interface ProviderCardProps {
  provider: string;
  keys: AIKey[];
  isOwner: boolean;
  onKeyAdded: (key: AIKey) => void;
  onKeyRemoved: (provider: string) => void;
}

function ProviderCard({ provider, keys, isOwner, onKeyAdded, onKeyRemoved }: ProviderCardProps) {
  const Logo = getProviderLogo(provider);
  const existingKey = keys.find(k => k.provider === provider);
  const [showInput, setShowInput] = useState(false);
  const [keyInput, setKeyInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!keyInput.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const added = await aiSettingsAPI.addKey(provider, keyInput.trim());
      onKeyAdded(added);
      setKeyInput('');
      setShowInput(false);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save key');
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async () => {
    setRemoving(true);
    try {
      await aiSettingsAPI.removeKey(provider);
      onKeyRemoved(provider);
    } catch (err) {
      console.error('Failed to remove key:', err);
    } finally {
      setRemoving(false);
    }
  };

  return (
    <div className="flex items-start justify-between p-4 border border-border rounded-lg">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-secondary rounded-lg">
          <Logo className="w-6 h-6" />
        </div>
        <div>
          <p className="font-medium text-foreground">{PROVIDER_NAMES[provider]}</p>
          {existingKey ? (
            <div className="flex items-center gap-1.5 mt-0.5">
              <Check className="w-3.5 h-3.5 text-green-500" />
              <span className="text-sm text-muted-foreground font-mono">
                BYOK: sk-••••{existingKey.key_hint}
              </span>
              {!existingKey.is_valid && (
                <Badge variant="destructive" className="text-xs">Invalid</Badge>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground mt-0.5">System key</p>
          )}
        </div>
      </div>

      <div className="flex flex-col items-end gap-2">
        {existingKey ? (
          isOwner && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRemove}
              disabled={removing}
            >
              {removing ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
              Remove
            </Button>
          )
        ) : (
          isOwner && !showInput && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowInput(true)}
            >
              <Key className="w-3.5 h-3.5 mr-1" />
              Add Key
            </Button>
          )
        )}

        {showInput && (
          <div className="flex flex-col gap-2 w-64">
            <Input
              type="password"
              placeholder="sk-... or API key"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              className="text-sm"
            />
            {error && <p className="text-xs text-destructive">{error}</p>}
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSave} disabled={!keyInput.trim() || saving}>
                {saving ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />}
                Save
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => { setShowInput(false); setKeyInput(''); setError(null); }}
              >
                <X className="w-3 h-3 mr-1" />
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface ModelSelectorProps {
  taskKey: keyof AISettings['models'];
  label: string;
  currentModel: string;
  models: AIModel[];
  isAdminOrOwner: boolean;
  userPlan: string;
  onModelChange: (taskKey: keyof AISettings['models'], modelId: string) => void;
}

function ModelSelector({
  taskKey,
  label,
  currentModel,
  models,
  isAdminOrOwner,
  userPlan,
  onModelChange,
}: ModelSelectorProps) {
  const [testResult, setTestResult] = useState<AIModelTestResponse | null>(null);
  const [testing, setTesting] = useState(false);

  const currentModelData = models.find(m => m.model_id === currentModel);
  const userPlanLevel = PLAN_HIERARCHY[userPlan] ?? 0;

  const handleTest = async () => {
    if (!currentModelData) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await aiSettingsAPI.testModel(currentModelData.provider, currentModel);
      setTestResult(result);
    } catch (err) {
      console.error('Test failed:', err);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <div className="flex items-center gap-2">
        <Select
          value={currentModel}
          onValueChange={(val) => onModelChange(taskKey, val)}
          disabled={!isAdminOrOwner}
        >
          <SelectTrigger className="flex-1">
            <SelectValue>
              {currentModelData && (
                <span className="flex items-center gap-1.5">
                  <TierBadge tier={currentModelData.tier} />
                  <span>{currentModelData.display_name}</span>
                </span>
              )}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {models.map((model) => {
              const modelPlanLevel = PLAN_HIERARCHY[model.min_plan] ?? 0;
              const isLocked = modelPlanLevel > userPlanLevel;
              return (
                <SelectItem
                  key={model.model_id}
                  value={model.model_id}
                  disabled={isLocked}
                >
                  <div className="flex items-center gap-1.5">
                    {isLocked ? (
                      <Lock className="w-3 h-3 text-muted-foreground" />
                    ) : (
                      <TierBadge tier={model.tier} />
                    )}
                    <span>{model.display_name}</span>
                    <span className="text-xs text-muted-foreground capitalize">({model.provider})</span>
                    {isLocked && (
                      <span className="text-xs text-muted-foreground ml-1">
                        {model.min_plan}+
                      </span>
                    )}
                  </div>
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>

        {isAdminOrOwner && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleTest}
                  disabled={testing}
                  aria-label={`Test ${label} model`}
                >
                  {testing ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <FlaskConical className="w-3.5 h-3.5" />
                  )}
                  <span className="ml-1">Test</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Run sample feedback through this model</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      {testResult && (
        <div className="p-3 bg-secondary/50 border border-border rounded-md text-xs space-y-1">
          <p className="font-medium text-foreground">Test result:</p>
          <pre className="text-muted-foreground whitespace-pre-wrap">{JSON.stringify(testResult.result, null, 2)}</pre>
          <p className="text-muted-foreground">
            {testResult.tokens} tokens &middot; {testResult.cost_cents.toFixed(4)}¢ &middot; {testResult.latency_ms}ms
          </p>
        </div>
      )}
    </div>
  );
}

export function AISettingsProviders({ settings, onUpdate }: AISettingsProvidersProps) {
  const { user } = useAuth();
  const [keys, setKeys] = useState<AIKey[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [loadingKeys, setLoadingKeys] = useState(true);
  const [loadingModels, setLoadingModels] = useState(true);

  const isOwner = user?.role === 'owner';
  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';
  const userPlan = user?.plan ?? 'free';

  useEffect(() => {
    aiSettingsAPI.listKeys()
      .then(setKeys)
      .catch(console.error)
      .finally(() => setLoadingKeys(false));

    aiSettingsAPI.listModels()
      .then(setModels)
      .catch(console.error)
      .finally(() => setLoadingModels(false));
  }, []);

  const handleKeyAdded = (key: AIKey) => {
    setKeys(prev => [...prev.filter(k => k.provider !== key.provider), key]);
  };

  const handleKeyRemoved = (provider: string) => {
    setKeys(prev => prev.filter(k => k.provider !== provider));
  };

  const handleModelChange = async (taskKey: keyof AISettings['models'], modelId: string) => {
    const field = `model_${taskKey}` as 'model_categorization' | 'model_analysis' | 'model_insights';
    try {
      const updated = await aiSettingsAPI.update({ [field]: modelId });
      onUpdate(updated);
    } catch (err) {
      console.error('Failed to update model:', err);
    }
  };

  if (loadingKeys || loadingModels) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-20 bg-muted animate-pulse rounded-lg" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Provider Cards */}
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>API Keys</CardTitle>
          <p className="text-sm text-muted-foreground mt-1">
            By default, Rereflect uses its own API keys. Bring your own key (BYOK) for direct billing and higher limits.
          </p>
        </CardHeader>
        <CardContent className="pt-4 space-y-3">
          {PROVIDERS.map(provider => (
            <ProviderCard
              key={provider}
              provider={provider}
              keys={keys}
              isOwner={isOwner}
              onKeyAdded={handleKeyAdded}
              onKeyRemoved={handleKeyRemoved}
            />
          ))}
          {!isOwner && (
            <p className="text-xs text-muted-foreground">Only owners can manage API keys.</p>
          )}
        </CardContent>
      </Card>

      {/* Model Selection */}
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Model Selection</CardTitle>
          <p className="text-sm text-muted-foreground mt-1">
            Choose which AI model to use per task type. Available models depend on your plan.
          </p>
          <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><TierBadge tier="cheap" /> Budget-friendly</span>
            <span className="flex items-center gap-1.5"><TierBadge tier="mid" /> Balanced</span>
            <span className="flex items-center gap-1.5"><TierBadge tier="premium" /> High performance</span>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-6">
          {TASK_TYPES.map(({ key, label }) => (
            <ModelSelector
              key={key}
              taskKey={key}
              label={label}
              currentModel={settings.models[key]}
              models={models}
              isAdminOrOwner={isAdminOrOwner}
              userPlan={userPlan}
              onModelChange={handleModelChange}
            />
          ))}
          {!isAdminOrOwner && (
            <p className="text-xs text-muted-foreground">Only admins and owners can change models.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
