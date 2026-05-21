'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  listPlaybooks,
  updatePlaybook,
  type Playbook,
  PLAN_PLAYBOOK_LIMITS,
} from '@/lib/api/playbooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PlaybookTemplateCard } from '@/components/playbooks/PlaybookTemplateCard';
import { Plus, ListChecks, Lock } from 'lucide-react';
import { toast } from 'sonner';

// ─── Upgrade Banner ────────────────────────────────────────────────────────────

function UpgradeBanner() {
  return (
    <Card
      data-testid="upgrade-banner"
      className="border-dashed border-2"
      style={{ borderColor: 'var(--chart-2)' }}
    >
      <CardContent className="py-8 text-center space-y-3">
        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-secondary mx-auto">
          <Lock className="w-6 h-6 text-primary" />
        </div>
        <h2 className="text-lg font-semibold">Playbooks is a Business feature</h2>
        <p className="text-sm text-muted-foreground max-w-sm mx-auto">
          Upgrade to Business to create reusable prevention playbooks triggered by churn probability
          ranges.
        </p>
        <Button asChild>
          <a href="/settings/billing">Upgrade to Business</a>
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PlaybooksPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const plan = user?.plan ?? 'free';
  const isBusiness = plan === 'business' || plan === 'enterprise';
  const planLimit = PLAN_PLAYBOOK_LIMITS[plan];

  useEffect(() => {
    async function load() {
      try {
        const all = await listPlaybooks();
        setPlaybooks(all);
      } catch {
        setError(true);
        toast.error('Failed to load playbooks');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const orgPlaybooks = playbooks.filter((p) => !p.is_template);
  const templates = playbooks.filter((p) => p.is_template);

  const handleToggleActive = useCallback(
    async (pb: Playbook, newValue: boolean) => {
      setTogglingId(pb.id);
      try {
        const updated = await updatePlaybook(pb.id, { is_active: newValue });
        setPlaybooks((prev) => prev.map((p) => (p.id === pb.id ? updated : p)));
        toast.success(updated.is_active ? 'Playbook activated' : 'Playbook paused');
      } catch {
        toast.error('Failed to update playbook');
      } finally {
        setTogglingId(null);
      }
    },
    []
  );

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="relative w-12 h-12">
          <div className="absolute inset-0 border-4 border-primary/20 rounded-full" />
          <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div data-testid="error-state" className="text-center py-12 text-muted-foreground">
          <p className="font-medium text-destructive">Failed to load playbooks</p>
          <Button variant="outline" className="mt-4" onClick={() => window.location.reload()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-secondary rounded-xl">
              <ListChecks className="w-7 h-7 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-foreground">Playbooks</h1>
              <p className="text-muted-foreground text-sm">
                Reusable prevention sequences triggered by churn probability
              </p>
            </div>
          </div>

          {isBusiness && (
            <div className="flex items-center gap-3">
              <span
                className="text-sm text-muted-foreground"
                data-testid="playbook-count"
              >
                {orgPlaybooks.length}/{planLimit ?? '∞'} playbooks
              </span>
              <Button
                onClick={() => router.push('/settings/playbooks/new')}
                className="flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                New playbook
              </Button>
            </div>
          )}
        </div>

        {/* Plan gate */}
        {!isBusiness && <UpgradeBanner />}

        {isBusiness && (
          <>
            {/* Your Playbooks section */}
            <section data-testid="section-org-playbooks" className="space-y-3">
              <h2 className="text-base font-semibold text-foreground">Your Playbooks</h2>
              {orgPlaybooks.length === 0 ? (
                <Card className="border-dashed">
                  <CardContent
                    data-testid="empty-org-playbooks"
                    className="py-10 text-center text-muted-foreground"
                  >
                    <ListChecks className="w-8 h-8 mx-auto mb-3 opacity-30" />
                    <p className="font-medium text-sm">No playbooks yet</p>
                    <p className="text-xs mt-1">
                      Create a playbook or clone a template below.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {orgPlaybooks.map((pb) => (
                    <div
                      key={pb.id}
                      className="cursor-pointer"
                      onClick={() => router.push(`/settings/playbooks/${pb.id}`)}
                    >
                      <PlaybookTemplateCard
                        playbook={pb}
                        onUse={() => {}}
                        onToggleActive={
                          togglingId === pb.id
                            ? undefined
                            : (val) => {
                                handleToggleActive(pb, val);
                              }
                        }
                      />
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Templates section */}
            <section data-testid="section-templates" className="space-y-3">
              <div>
                <h2 className="text-base font-semibold text-foreground">Templates</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  System-provided playbooks. Clone to customize.
                </p>
              </div>
              {templates.length === 0 ? (
                <p className="text-sm text-muted-foreground">No templates available.</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {templates.map((tpl) => (
                    <PlaybookTemplateCard
                      key={tpl.id}
                      playbook={tpl}
                      onUse={(p) =>
                        router.push(`/settings/playbooks/new?template=${p.id}`)
                      }
                    />
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
