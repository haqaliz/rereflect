'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  webhooksAPI,
  WEBHOOK_EVENTS,
  PLAN_WEBHOOK_LIMITS,
  type CreateWebhookRequest,
} from '@/lib/api/webhooks';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Plus, Trash2, Loader2, Copy, Check } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { toast } from 'sonner';

export default function NewWebhookPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [categoryFilters, setCategoryFilters] = useState<string[]>([]);
  const [categoryInput, setCategoryInput] = useState('');
  const [retryMode, setRetryMode] = useState<'fire_and_forget' | 'exponential_backoff'>('fire_and_forget');
  const [customHeaders, setCustomHeaders] = useState<{ key: string; value: string }[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  const plan = user?.plan || 'free';
  const isFree = plan === 'free';
  const headerLimit = isFree ? 2 : 5;

  const toggleEvent = (eventId: string) => {
    setSelectedEvents(prev =>
      prev.includes(eventId) ? prev.filter(e => e !== eventId) : [...prev, eventId]
    );
  };

  const addHeader = () => {
    if (customHeaders.length < headerLimit) {
      setCustomHeaders(prev => [...prev, { key: '', value: '' }]);
    }
  };

  const removeHeader = (index: number) => {
    setCustomHeaders(prev => prev.filter((_, i) => i !== index));
  };

  const updateHeader = (index: number, field: 'key' | 'value', val: string) => {
    setCustomHeaders(prev => prev.map((h, i) => i === index ? { ...h, [field]: val } : h));
  };

  const addCategoryFilter = () => {
    const tag = categoryInput.trim().toLowerCase();
    if (tag && !categoryFilters.includes(tag)) {
      setCategoryFilters(prev => [...prev, tag]);
      setCategoryInput('');
    }
  };

  const removeCategoryFilter = (tag: string) => {
    setCategoryFilters(prev => prev.filter(t => t !== tag));
  };

  const handleSubmit = useCallback(async () => {
    if (!name.trim() || !url.trim() || selectedEvents.length === 0) {
      toast.error('Name, URL, and at least one event are required');
      return;
    }

    setSubmitting(true);
    try {
      const headersObj = customHeaders.reduce<Record<string, string>>((acc, { key, value }) => {
        if (key.trim()) acc[key.trim()] = value;
        return acc;
      }, {});

      const payload: CreateWebhookRequest = {
        name: name.trim(),
        url: url.trim(),
        events: selectedEvents,
        retry_mode: retryMode,
        ...(categoryFilters.length > 0 ? { category_filters: categoryFilters } : {}),
        ...(Object.keys(headersObj).length > 0 ? { custom_headers: headersObj } : {}),
      };

      const result = await webhooksAPI.create(payload);
      setCreatedSecret(result.signing_secret);
      setCreatedId(result.id);
      toast.success('Webhook created');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create webhook');
    } finally {
      setSubmitting(false);
    }
  }, [name, url, selectedEvents, retryMode, categoryFilters, customHeaders]);

  const handleCopySecret = async () => {
    if (!createdSecret) return;
    await navigator.clipboard.writeText(createdSecret);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Success state — show signing secret
  if (createdSecret) {
    return (
      <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => router.push('/settings/webhooks')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Webhooks
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Webhook Created</CardTitle>
            <CardDescription>Save the signing secret below — it won't be shown again.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 bg-green-50 dark:bg-green-950 rounded-lg border border-green-200 dark:border-green-800">
              <p className="text-sm font-medium text-green-800 dark:text-green-200 mb-2">Signing Secret</p>
              <div className="flex items-center gap-2 p-3 bg-background rounded-md border font-mono text-sm break-all">
                <span className="flex-1">{createdSecret}</span>
                <Button variant="ghost" size="sm" onClick={handleCopySecret}>
                  {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => router.push('/settings/webhooks')}>
                Back to List
              </Button>
              <Button onClick={() => router.push(`/settings/webhooks/${createdId}`)}>
                View Webhook
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" onClick={() => router.push('/settings/webhooks')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-xl font-semibold">Add Webhook</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Webhook Configuration</CardTitle>
          <CardDescription>Configure the endpoint that will receive event notifications</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Name */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Name</label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g., Slack Bot, Internal Dashboard"
            />
          </div>

          {/* URL */}
          <div className="space-y-2">
            <label className="text-sm font-medium">URL</label>
            <Input
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://example.com/webhook"
            />
            <p className="text-xs text-muted-foreground">Must be HTTPS</p>
          </div>

          {/* Events */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Events</label>
            <div className="space-y-2">
              {WEBHOOK_EVENTS.map(ev => (
                <div key={ev.id} className="flex items-center gap-2">
                  <Checkbox
                    id={`event-${ev.id}`}
                    checked={selectedEvents.includes(ev.id)}
                    onCheckedChange={() => toggleEvent(ev.id)}
                  />
                  <label htmlFor={`event-${ev.id}`} className="text-sm cursor-pointer">{ev.label}</label>
                  <span className="text-xs text-muted-foreground font-mono">{ev.id}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Category Filters — only when category_match is selected */}
          {selectedEvents.includes('feedback.category_match') && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Category Filters</label>
              <p className="text-xs text-muted-foreground">Only fire when feedback matches these tags</p>
              <div className="flex gap-2">
                <Input
                  value={categoryInput}
                  onChange={e => setCategoryInput(e.target.value)}
                  placeholder="e.g., billing, authentication"
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addCategoryFilter())}
                />
                <Button variant="outline" size="sm" onClick={addCategoryFilter}>Add</Button>
              </div>
              {categoryFilters.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {categoryFilters.map(tag => (
                    <Badge key={tag} variant="secondary" className="cursor-pointer" onClick={() => removeCategoryFilter(tag)}>
                      {tag} &times;
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Retry Mode */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Retry Mode</label>
            <ToggleGroup
              type="single"
              value={retryMode}
              onValueChange={(val) => { if (val) setRetryMode(val as typeof retryMode); }}
              className="flex flex-col items-stretch gap-2"
            >
              <ToggleGroupItem
                value="fire_and_forget"
                variant="outline"
                className="justify-start gap-2 h-auto py-2 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground data-[state=on]:border-primary"
              >
                <span className="text-sm font-medium">Fire and forget</span>
                <span className="text-xs opacity-70">— single attempt, no retries</span>
              </ToggleGroupItem>
              <ToggleGroupItem
                value="exponential_backoff"
                variant="outline"
                disabled={isFree}
                className="justify-start gap-2 h-auto py-2 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground data-[state=on]:border-primary"
              >
                <span className="text-sm font-medium">Exponential backoff</span>
                <span className="text-xs opacity-70">— retry up to 3 times (1m, 5m, 30m)</span>
                {isFree && <Badge variant="secondary" className="text-xs">Pro+</Badge>}
              </ToggleGroupItem>
            </ToggleGroup>
          </div>

          {/* Custom Headers */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Custom Headers</label>
              <span className="text-xs text-muted-foreground">{customHeaders.length}/{headerLimit}</span>
            </div>
            {customHeaders.map((header, i) => (
              <div key={i} className="flex gap-2">
                <Input
                  value={header.key}
                  onChange={e => updateHeader(i, 'key', e.target.value)}
                  placeholder="Header name"
                  className="flex-1"
                />
                <Input
                  value={header.value}
                  onChange={e => updateHeader(i, 'value', e.target.value)}
                  placeholder="Value"
                  className="flex-1"
                />
                <Button variant="ghost" size="icon" onClick={() => removeHeader(i)}>
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            ))}
            {customHeaders.length < headerLimit && (
              <Button variant="outline" size="sm" onClick={addHeader}>
                <Plus className="w-4 h-4 mr-1" />
                Add Header
              </Button>
            )}
          </div>

          {/* Submit */}
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button variant="outline" onClick={() => router.push('/settings/webhooks')}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={submitting || !name.trim() || !url.trim() || selectedEvents.length === 0}
            >
              {submitting ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Creating...</>
              ) : (
                'Create Webhook'
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
      </main>
    </div>
  );
}
