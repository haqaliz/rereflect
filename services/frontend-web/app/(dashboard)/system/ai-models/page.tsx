'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  adminAIModelsAPI,
  type AdminAIModel,
  type AdminAIModelUpdate,
} from '@/lib/api/ai-settings';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Loader2, RefreshCw, Database } from 'lucide-react';
import { toast } from 'sonner';
import { TierBadge, PROVIDER_NAMES } from '@/components/icons/ProviderLogos';

const TIER_COLORS: Record<string, string> = {
  cheap: 'secondary',
  mid: 'default',
  premium: 'destructive',
};

function formatPrice(price: number): string {
  return price.toFixed(2);
}

function formatDate(isoStr: string): string {
  return new Date(isoStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

interface EditablePriceCellProps {
  value: number;
  onSave: (value: number) => void;
}

function EditablePriceCell({ value, onSave }: EditablePriceCellProps) {
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState(String(value));

  const handleBlur = () => {
    const parsed = parseFloat(inputVal);
    if (!isNaN(parsed) && parsed !== value) {
      onSave(parsed);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <Input
        type="number"
        step="0.01"
        min="0"
        value={inputVal}
        onChange={(e) => setInputVal(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleBlur();
          if (e.key === 'Escape') setEditing(false);
        }}
        className="h-7 w-24 text-sm"
        autoFocus
      />
    );
  }

  return (
    <button
      className="text-sm hover:underline cursor-pointer text-left"
      onClick={() => setEditing(true)}
      title="Click to edit"
    >
      ${formatPrice(value)}
    </button>
  );
}

export default function AIModelsAdminPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [models, setModels] = useState<AdminAIModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const isSystemAdmin = user?.is_system_admin === true;

  useEffect(() => {
    if (user !== null && !isSystemAdmin) {
      router.push('/dashboard');
      return;
    }
    if (!isSystemAdmin) return;

    adminAIModelsAPI.list()
      .then(setModels)
      .catch((err) => {
        console.error('Failed to load models:', err);
        toast.error('Failed to load AI models');
      })
      .finally(() => setLoading(false));
  }, [user, isSystemAdmin, router]);

  const handleUpdate = async (id: number, data: AdminAIModelUpdate) => {
    try {
      const updated = await adminAIModelsAPI.update(id, data);
      setModels(prev => prev.map(m => m.id === id ? updated : m));
      toast.success('Model updated');
    } catch (err) {
      console.error('Failed to update model:', err);
      toast.error('Failed to update model');
    }
  };

  const handleSyncPrices = async () => {
    setSyncing(true);
    try {
      const result = await adminAIModelsAPI.syncPrices();
      toast.success(`Synced ${result.synced} model prices`);
      // Refresh list
      const updated = await adminAIModelsAPI.list();
      setModels(updated);
    } catch (err) {
      console.error('Failed to sync prices:', err);
      toast.error('Failed to sync prices');
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-muted-foreground font-medium">Loading AI models...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-3 bg-secondary rounded-xl">
              <Database className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground">AI Models</h1>
              <p className="text-muted-foreground text-lg">Manage model pricing, availability, and deprecation</p>
            </div>
          </div>
          <Button onClick={handleSyncPrices} disabled={syncing} variant="outline">
            {syncing ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-2" />
            )}
            Sync Prices
          </Button>
        </div>

        {/* Models Table */}
        <Card>
          <CardHeader className="border-b border-border">
            <CardTitle>Model Registry</CardTitle>
            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5"><TierBadge tier="cheap" /> Budget-friendly</span>
              <span className="flex items-center gap-1.5"><TierBadge tier="mid" /> Balanced</span>
              <span className="flex items-center gap-1.5"><TierBadge tier="premium" /> High performance</span>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead>Model ID</TableHead>
                  <TableHead>Display Name</TableHead>
                  <TableHead>Tier</TableHead>
                  <TableHead>Min Plan</TableHead>
                  <TableHead>Input $/1M</TableHead>
                  <TableHead>Output $/1M</TableHead>
                  <TableHead>Available</TableHead>
                  <TableHead>Deprecated</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {models.map(model => (
                  <TableRow key={model.id} className={model.is_deprecated ? 'opacity-60' : ''}>
                    <TableCell>
                      <span className="capitalize text-sm font-medium">
                        {PROVIDER_NAMES[model.provider] ?? model.provider}
                      </span>
                    </TableCell>
                    <TableCell>
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                        {model.model_id}
                      </code>
                    </TableCell>
                    <TableCell className="font-medium">{model.display_name}</TableCell>
                    <TableCell>
                      <Badge variant={TIER_COLORS[model.tier] as any} className="capitalize flex items-center gap-1.5 w-fit">
                        <TierBadge tier={model.tier} />
                        <span>{model.tier}</span>
                      </Badge>
                    </TableCell>
                    <TableCell className="capitalize">{model.min_plan}</TableCell>
                    <TableCell>
                      <EditablePriceCell
                        value={model.input_price_per_1m_tokens}
                        onSave={(val) => handleUpdate(model.id, { input_price_per_1m_tokens: val })}
                      />
                    </TableCell>
                    <TableCell>
                      <EditablePriceCell
                        value={model.output_price_per_1m_tokens}
                        onSave={(val) => handleUpdate(model.id, { output_price_per_1m_tokens: val })}
                      />
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={model.is_available}
                        onCheckedChange={(checked) =>
                          handleUpdate(model.id, { is_available: checked })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={model.is_deprecated}
                        onCheckedChange={(checked) =>
                          handleUpdate(model.id, { is_deprecated: checked })
                        }
                      />
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {formatDate(model.updated_at)}
                    </TableCell>
                  </TableRow>
                ))}
                {models.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={10} className="text-center py-8 text-muted-foreground">
                      No models found. Sync prices to populate.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
