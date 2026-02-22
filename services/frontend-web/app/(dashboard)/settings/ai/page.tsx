'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { aiSettingsAPI, type AISettings } from '@/lib/api/ai-settings';
import { categoriesAPI, type CustomCategory } from '@/lib/api/categories';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Settings as SettingsIcon,
  Tag,
  Plus,
  Trash2,
  Check,
  X,
  Sparkles,
} from 'lucide-react';
import { AISettingsGeneral } from '@/components/settings/AISettingsGeneral';
import { AISettingsProviders } from '@/components/settings/AISettingsProviders';
import { AISettingsUsage } from '@/components/settings/AISettingsUsage';

type CategoryType = 'pain_point' | 'feature_request' | 'general';

const CATEGORY_TYPE_LABELS: Record<CategoryType, string> = {
  pain_point: 'Pain Point',
  feature_request: 'Feature Request',
  general: 'General',
};

const VALID_TABS = ['general', 'providers', 'usage', 'categories'] as const;
type TabValue = typeof VALID_TABS[number];

function AISettingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();

  const tabParam = searchParams.get('tab') as TabValue | null;
  const activeTab: TabValue = tabParam && VALID_TABS.includes(tabParam) ? tabParam : 'general';

  const [loading, setLoading] = useState(true);
  const [aiSettings, setAiSettings] = useState<AISettings | null>(null);
  const [categories, setCategories] = useState<CustomCategory[]>([]);

  // New category form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [newCatDescription, setNewCatDescription] = useState('');
  const [newCatType, setNewCatType] = useState<CategoryType>('pain_point');
  const [savingCategory, setSavingCategory] = useState(false);

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }

    const fetchData = async () => {
      try {
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
  }, [router]);

  const handleTabChange = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', value);
    router.push(`/settings/ai?${params.toString()}`, { scroll: false });
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

  if (!aiSettings) return null;

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
              <h1 className="text-4xl font-bold text-foreground">AI Settings</h1>
              <p className="text-muted-foreground text-lg">Manage your AI providers, models, and usage</p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList className="w-full justify-start">
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="providers">Providers</TabsTrigger>
            <TabsTrigger value="usage">Usage</TabsTrigger>
            <TabsTrigger value="categories">Categories</TabsTrigger>
          </TabsList>

          {/* General Tab */}
          <TabsContent value="general" className="mt-6">
            <AISettingsGeneral
              settings={aiSettings}
              onUpdate={setAiSettings}
            />
          </TabsContent>

          {/* Providers Tab */}
          <TabsContent value="providers" className="mt-6">
            <AISettingsProviders
              settings={aiSettings}
              onUpdate={setAiSettings}
            />
          </TabsContent>

          {/* Usage Tab */}
          <TabsContent value="usage" className="mt-6">
            <AISettingsUsage />
          </TabsContent>

          {/* Categories Tab */}
          <TabsContent value="categories" className="mt-6">
            <Card>
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
                        <Select
                          value={newCatType}
                          onValueChange={(value) => setNewCatType(value as CategoryType)}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="pain_point">Pain Point</SelectItem>
                            <SelectItem value="feature_request">Feature Request</SelectItem>
                            <SelectItem value="general">General</SelectItem>
                          </SelectContent>
                        </Select>
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
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

export default function AISettingsPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
          <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
        </div>
      </div>
    }>
      <AISettingsContent />
    </Suspense>
  );
}
