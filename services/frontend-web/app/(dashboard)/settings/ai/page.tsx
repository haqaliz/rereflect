'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { aiSettingsAPI, AISettings } from '@/lib/api/ai-settings';
import { categoriesAPI, CustomCategory, CustomCategoryCreate } from '@/lib/api/categories';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { SettingsTabs } from '@/components/SettingsTabs';
import {
  Settings as SettingsIcon,
  Brain,
  Key,
  Tag,
  Plus,
  Trash2,
  Check,
  X,
  Sparkles,
} from 'lucide-react';

type CategoryType = 'pain_point' | 'feature_request' | 'general';

const CATEGORY_TYPE_LABELS: Record<CategoryType, string> = {
  pain_point: 'Pain Point',
  feature_request: 'Feature Request',
  general: 'General',
};

export default function AISettingsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [aiSettings, setAiSettings] = useState<AISettings | null>(null);
  const [categories, setCategories] = useState<CustomCategory[]>([]);
  const [savingAI, setSavingAI] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showKeyInput, setShowKeyInput] = useState(false);

  // New category form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatDescription, setNewCatDescription] = useState('');
  const [newCatType, setNewCatType] = useState<CategoryType>('pain_point');
  const [savingCategory, setSavingCategory] = useState(false);

  const isOwner = user?.role === 'owner';
  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    // Redirect members to preferences
    if (user && user.role === 'member') {
      router.push('/settings/preferences');
      return;
    }

    const fetchData = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
          return;
        }

        const [settingsData, categoriesData] = await Promise.all([
          aiSettingsAPI.get(),
          categoriesAPI.list(),
        ]);

        setAiSettings(settingsData);
        setCategories(categoriesData);
      } catch (err) {
        console.error('Failed to load AI settings:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router, user]);

  const handleToggleAI = async (checked: boolean) => {
    setSavingAI(true);
    try {
      const updated = await aiSettingsAPI.update({ ai_analysis_enabled: checked });
      setAiSettings(updated);
    } catch (err) {
      console.error('Failed to update AI settings:', err);
    } finally {
      setSavingAI(false);
    }
  };

  const handleSaveApiKey = async () => {
    setSavingKey(true);
    try {
      const updated = await aiSettingsAPI.update({ openai_api_key: apiKeyInput });
      setAiSettings(updated);
      setApiKeyInput('');
      setShowKeyInput(false);
    } catch (err) {
      console.error('Failed to save API key:', err);
    } finally {
      setSavingKey(false);
    }
  };

  const handleRemoveApiKey = async () => {
    setSavingKey(true);
    try {
      const updated = await aiSettingsAPI.update({ openai_api_key: '' });
      setAiSettings(updated);
    } catch (err) {
      console.error('Failed to remove API key:', err);
    } finally {
      setSavingKey(false);
    }
  };

  const handleAddCategory = async () => {
    if (!newCatName.trim()) return;
    setSavingCategory(true);
    try {
      const created = await categoriesAPI.create({
        name: newCatName.trim(),
        description: newCatDescription.trim() || undefined,
        category_type: newCatType,
      });
      setCategories([...categories, created]);
      setNewCatName('');
      setNewCatDescription('');
      setShowAddForm(false);
    } catch (err: any) {
      console.error('Failed to create category:', err);
      if (err?.response?.status === 409) {
        alert('A category with this name already exists');
      }
    } finally {
      setSavingCategory(false);
    }
  };

  const handleDeleteCategory = async (id: number) => {
    try {
      await categoriesAPI.delete(id);
      setCategories(categories.filter(c => c.id !== id));
    } catch (err) {
      console.error('Failed to delete category:', err);
    }
  };

  const handleToggleCategoryActive = async (cat: CustomCategory) => {
    try {
      const updated = await categoriesAPI.update(cat.id, { is_active: !cat.is_active });
      setCategories(categories.map(c => c.id === cat.id ? updated : c));
    } catch (err) {
      console.error('Failed to toggle category:', err);
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
          <p className="text-muted-foreground font-medium">Loading AI settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Page Header */}
        <div className="animate-fade-in">
          <div className="flex items-center space-x-3 mb-6">
            <div className="p-3 bg-secondary rounded-xl">
              <SettingsIcon className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground">Settings</h1>
              <p className="text-muted-foreground text-lg">Manage your organization and preferences</p>
            </div>
          </div>
          <SettingsTabs />
        </div>

        {/* AI Analysis Toggle */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-secondary rounded-lg">
                <Brain className="w-5 h-5 text-primary" />
              </div>
              <CardTitle>AI-Powered Analysis</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-foreground">Enable AI Analysis</p>
                <p className="text-sm text-muted-foreground">
                  Use GPT-4o-mini for intelligent feedback categorization, churn risk scoring, and suggested actions
                </p>
              </div>
              <Switch
                checked={aiSettings?.ai_analysis_enabled ?? true}
                onCheckedChange={handleToggleAI}
                disabled={savingAI}
              />
            </div>
          </CardContent>
        </Card>

        {/* BYOK API Key (Owner only) */}
        {isOwner && (
          <Card className="animate-slide-up stagger-2">
            <CardHeader className="border-b border-border">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <Key className="w-5 h-5 text-primary" />
                </div>
                <CardTitle>Custom API Key (Enterprise)</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-4">
                By default, Rereflect uses its own OpenAI API key. Enterprise customers can provide their own key for direct billing.
              </p>

              {aiSettings?.has_custom_key ? (
                <div className="flex items-center justify-between p-3 bg-secondary/50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <Check className="w-4 h-4 text-green-500" />
                    <span className="text-sm font-medium">Custom API key configured</span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRemoveApiKey}
                    disabled={savingKey}
                  >
                    Remove Key
                  </Button>
                </div>
              ) : showKeyInput ? (
                <div className="space-y-3">
                  <Input
                    type="password"
                    placeholder="sk-..."
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button
                      onClick={handleSaveApiKey}
                      disabled={!apiKeyInput.trim() || savingKey}
                      size="sm"
                    >
                      <Check className="w-4 h-4 mr-1" />
                      Save Key
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => { setShowKeyInput(false); setApiKeyInput(''); }}
                    >
                      <X className="w-4 h-4 mr-1" />
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => setShowKeyInput(true)}
                >
                  <Key className="w-4 h-4 mr-2" />
                  Set Custom API Key
                </Button>
              )}
            </CardContent>
          </Card>
        )}

        {/* Custom Categories */}
        <Card className="animate-slide-up stagger-3">
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <Tag className="w-5 h-5 text-primary" />
                </div>
                <CardTitle>Custom Categories</CardTitle>
              </div>
              {isAdminOrOwner && !showAddForm && (
                <Button
                  onClick={() => setShowAddForm(true)}
                  variant="outline"
                  size="sm"
                >
                  <Plus className="w-4 h-4 mr-1" />
                  Add Category
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-4">
              Define custom categories for the AI to use when analyzing feedback. These extend the built-in categories.
            </p>

            {/* Add Category Form */}
            {showAddForm && (
              <div className="p-4 border border-border rounded-lg mb-4 space-y-3 bg-secondary/30">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium mb-1">Category Name</label>
                    <Input
                      placeholder="e.g., Onboarding Issues"
                      value={newCatName}
                      onChange={(e) => setNewCatName(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Type</label>
                    <select
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={newCatType}
                      onChange={(e) => setNewCatType(e.target.value as CategoryType)}
                    >
                      <option value="pain_point">Pain Point</option>
                      <option value="feature_request">Feature Request</option>
                      <option value="general">General</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Description (optional)</label>
                  <Input
                    placeholder="Help the AI understand when to use this category"
                    value={newCatDescription}
                    onChange={(e) => setNewCatDescription(e.target.value)}
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={handleAddCategory}
                    disabled={!newCatName.trim() || savingCategory}
                    size="sm"
                  >
                    <Check className="w-4 h-4 mr-1" />
                    Create
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => { setShowAddForm(false); setNewCatName(''); setNewCatDescription(''); }}
                  >
                    <X className="w-4 h-4 mr-1" />
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {/* Categories List */}
            {categories.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Sparkles className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No custom categories yet</p>
                <p className="text-sm">Add categories to help the AI better classify your feedback</p>
              </div>
            ) : (
              <div className="space-y-2">
                {categories.map(cat => (
                  <div
                    key={cat.id}
                    className={`flex items-center justify-between p-3 rounded-lg border ${
                      cat.is_active ? 'bg-background border-border' : 'bg-muted/50 border-muted opacity-60'
                    }`}
                  >
                    <div className="flex items-center space-x-3">
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          backgroundColor: 'color-mix(in oklch, var(--primary) 15%, transparent)',
                          color: 'var(--primary)',
                        }}
                      >
                        {CATEGORY_TYPE_LABELS[cat.category_type]}
                      </span>
                      <div>
                        <p className="font-medium text-foreground">{cat.name}</p>
                        {cat.description && (
                          <p className="text-xs text-muted-foreground">{cat.description}</p>
                        )}
                      </div>
                    </div>
                    {isAdminOrOwner && (
                      <div className="flex items-center space-x-2">
                        <Switch
                          checked={cat.is_active}
                          onCheckedChange={() => handleToggleCategoryActive(cat)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteCategory(cat.id)}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
