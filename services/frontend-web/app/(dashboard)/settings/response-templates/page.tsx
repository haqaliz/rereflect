'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  responsesAPI,
  TONE_OPTIONS,
  type ResponseTemplate,
  type ResponseSettings,
  type ToneOption,
} from '@/lib/api/responses';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  MessageSquarePlus,
  Plus,
  Trash2,
  Edit3,
  Lock,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';

// ─── Template Form Dialog ──────────────────────────────────────────────────────

interface TemplateFormDialogProps {
  open: boolean;
  onClose: () => void;
  onSave: (data: { name: string; category: string; body: string }) => Promise<void>;
  initial?: ResponseTemplate | null;
}

function TemplateFormDialog({ open, onClose, onSave, initial }: TemplateFormDialogProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [category, setCategory] = useState(initial?.category ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  const [saving, setSaving] = useState(false);

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setName(initial?.name ?? '');
      setCategory(initial?.category ?? '');
      setBody(initial?.body ?? '');
    }
  }, [open, initial]);

  const handleSubmit = async () => {
    if (!name.trim() || !category.trim() || !body.trim()) return;
    setSaving(true);
    try {
      await onSave({ name: name.trim(), category: category.trim(), body: body.trim() });
      onClose();
    } catch {
      toast.error('Failed to save template');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent data-testid="template-form-dialog" className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{initial ? 'Edit Template' : 'New Template'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Template Name</label>
            <Input
              data-testid="template-name-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Enterprise Welcome"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Category</label>
            <Input
              data-testid="template-category-input"
              value={category}
              onChange={e => setCategory(e.target.value)}
              placeholder="e.g. Onboarding, Bug Report"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Body</label>
            <Textarea
              data-testid="template-body-textarea"
              value={body}
              onChange={e => setBody(e.target.value)}
              placeholder="Template body with {{variables}} supported"
              rows={6}
              className="font-mono text-sm"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button
              onClick={handleSubmit}
              disabled={saving || !name.trim() || !category.trim() || !body.trim()}
            >
              {saving ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving…</>
              ) : initial ? 'Save changes' : 'Create'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function ResponseTemplatesPage() {
  const router = useRouter();
  const { user } = useAuth();

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState<ResponseSettings | null>(null);
  const [templates, setTemplates] = useState<ResponseTemplate[]>([]);

  // Settings form state
  const [brandVoice, setBrandVoice] = useState('');
  const [defaultTone, setDefaultTone] = useState<ToneOption>('professional');
  const [productName, setProductName] = useState('');
  const [supportEmail, setSupportEmail] = useState('');
  const [savingSettings, setSavingSettings] = useState(false);

  // Template form dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<ResponseTemplate | null>(null);

  useEffect(() => {
    if (!isAdminOrOwner) {
      router.push('/settings/preferences');
      return;
    }

    const fetchAll = async () => {
      try {
        const [templatesData, settingsData] = await Promise.all([
          responsesAPI.listTemplates(),
          responsesAPI.getResponseSettings(),
        ]);
        setTemplates(templatesData);
        setSettings(settingsData);
        setBrandVoice(settingsData.brand_voice ?? '');
        setDefaultTone((settingsData.default_tone as ToneOption) ?? 'professional');
        setProductName(settingsData.product_name_display ?? '');
        setSupportEmail(settingsData.support_email_display ?? '');
      } catch {
        toast.error('Failed to load response settings');
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, [isAdminOrOwner, router]);

  const handleSaveSettings = useCallback(async () => {
    setSavingSettings(true);
    try {
      const updated = await responsesAPI.updateResponseSettings({
        brand_voice: brandVoice,
        default_tone: defaultTone,
        product_name_display: productName,
        support_email_display: supportEmail,
      });
      setSettings(updated);
      toast.success('Settings saved');
    } catch {
      toast.error('Failed to save settings');
    } finally {
      setSavingSettings(false);
    }
  }, [brandVoice, defaultTone, productName, supportEmail]);

  const handleCreateTemplate = useCallback(async (data: { name: string; category: string; body: string }) => {
    const created = await responsesAPI.createTemplate(data);
    setTemplates(prev => [...prev, created]);
    toast.success('Template created');
  }, []);

  const handleUpdateTemplate = useCallback(async (data: { name: string; category: string; body: string }) => {
    if (!editingTemplate) return;
    const updated = await responsesAPI.updateTemplate(editingTemplate.id, data);
    setTemplates(prev => prev.map(t => t.id === updated.id ? updated : t));
    toast.success('Template updated');
    setEditingTemplate(null);
  }, [editingTemplate]);

  const handleDeleteTemplate = useCallback(async (template: ResponseTemplate) => {
    if (!confirm(`Delete "${template.name}"? This cannot be undone.`)) return;
    try {
      await responsesAPI.deleteTemplate(template.id);
      setTemplates(prev => prev.filter(t => t.id !== template.id));
      toast.success('Template deleted');
    } catch {
      toast.error('Failed to delete template');
    }
  }, []);

  const systemTemplates = templates.filter(t => t.is_system);
  const customTemplates = templates.filter(t => !t.is_system);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full" />
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
          <p className="text-muted-foreground font-medium">Loading response templates...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <MessageSquarePlus className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-foreground">Response Templates</h1>
                <p className="text-muted-foreground text-lg">Manage templates and brand voice for customer responses</p>
              </div>
            </div>
            <Button
              onClick={() => { setEditingTemplate(null); setDialogOpen(true); }}
              className="flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              New Template
            </Button>
          </div>
        </div>

        {/* Brand Voice + Settings */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <CardTitle>Brand Voice & Defaults</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-5">

            {/* Brand Voice */}
            <div className="space-y-2">
              <label className="text-sm font-medium">
                Brand Voice
                <span className="ml-2 text-xs text-muted-foreground">(org-wide AI instruction, max 500 chars)</span>
              </label>
              <Textarea
                data-testid="brand-voice-textarea"
                value={brandVoice}
                onChange={e => setBrandVoice(e.target.value)}
                placeholder="Describe your communication style, e.g. 'We are a developer tools company. Keep responses technical and concise.'"
                rows={4}
                maxLength={500}
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{brandVoice.length}/500</span>
                <Button
                  size="sm"
                  onClick={handleSaveSettings}
                  disabled={savingSettings}
                >
                  {savingSettings ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving…</>
                  ) : 'Save brand voice'}
                </Button>
              </div>
            </div>

            {/* Default Tone */}
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium shrink-0">Default Tone:</label>
              <Select
                value={defaultTone}
                onValueChange={v => setDefaultTone(v as ToneOption)}
              >
                <SelectTrigger data-testid="default-tone-select" className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TONE_OPTIONS.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Product Name & Support Email */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Product Name</label>
                <Input
                  data-testid="product-name-input"
                  value={productName}
                  onChange={e => setProductName(e.target.value)}
                  placeholder="e.g. Rereflect"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Support Email</label>
                <Input
                  data-testid="support-email-input"
                  value={supportEmail}
                  onChange={e => setSupportEmail(e.target.value)}
                  placeholder="e.g. support@yourapp.com"
                  type="email"
                />
              </div>
            </div>

          </CardContent>
        </Card>

        {/* System Templates */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <div className="flex items-center gap-2">
              <Lock className="w-4 h-4 text-muted-foreground" />
              <CardTitle>System Templates ({systemTemplates.length})</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground mb-4">
              Built-in templates covering common feedback scenarios. Read-only.
            </p>
            {systemTemplates.length === 0 ? (
              <p className="text-muted-foreground italic text-sm">No system templates</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-left">
                      <th className="pb-2 font-medium">Name</th>
                      <th className="pb-2 font-medium">Category</th>
                      <th className="pb-2 font-medium text-right">Used</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {systemTemplates.map(t => (
                      <tr key={t.id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-2.5 font-medium">{t.name}</td>
                        <td className="py-2.5 text-muted-foreground">{t.category}</td>
                        <td className="py-2.5 text-right font-mono text-muted-foreground">{t.usage_count}x</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Custom Templates */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <CardTitle>Custom Templates ({customTemplates.length})</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {customTemplates.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <MessageSquarePlus className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p>No custom templates yet</p>
                <p className="text-sm">Create templates tailored to your organization</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-left">
                      <th className="pb-2 font-medium">Name</th>
                      <th className="pb-2 font-medium">Category</th>
                      <th className="pb-2 font-medium text-right">Used</th>
                      <th className="pb-2 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {customTemplates.map(t => (
                      <tr key={t.id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-2.5 font-medium">{t.name}</td>
                        <td className="py-2.5 text-muted-foreground">{t.category}</td>
                        <td className="py-2.5 text-right font-mono text-muted-foreground">{t.usage_count}x</td>
                        <td className="py-2.5">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => { setEditingTemplate(t); setDialogOpen(true); }}
                              title="Edit template"
                            >
                              <Edit3 className="w-4 h-4" />
                              <span className="sr-only">Edit</span>
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteTemplate(t)}
                              className="text-destructive hover:text-destructive"
                              title="Delete template"
                            >
                              <Trash2 className="w-4 h-4" />
                              <span className="ml-1">Delete</span>
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

      </main>

      {/* Template Create/Edit Dialog */}
      <TemplateFormDialog
        open={dialogOpen}
        onClose={() => { setDialogOpen(false); setEditingTemplate(null); }}
        onSave={editingTemplate ? handleUpdateTemplate : handleCreateTemplate}
        initial={editingTemplate}
      />
    </div>
  );
}
