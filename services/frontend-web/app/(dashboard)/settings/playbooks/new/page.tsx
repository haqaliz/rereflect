'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { getPlaybook, createPlaybook, type Playbook } from '@/lib/api/playbooks';
import { PlaybookEditor } from '@/components/playbooks/PlaybookEditor';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

function NewPlaybookInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();

  const templateId = searchParams.get('template');
  const [sourceTemplate, setSourceTemplate] = useState<Playbook | null>(null);
  const [loadingTemplate, setLoadingTemplate] = useState(!!templateId);

  useEffect(() => {
    if (!templateId) return;
    setLoadingTemplate(true);
    getPlaybook(Number(templateId))
      .then((tpl) => setSourceTemplate(tpl))
      .catch(() => toast.error('Failed to load template'))
      .finally(() => setLoadingTemplate(false));
  }, [templateId]);

  const isBusiness = user?.plan === 'business' || user?.plan === 'enterprise';

  if (!isBusiness) {
    router.replace('/settings/playbooks');
    return null;
  }

  const handleSave = async (data: Partial<Playbook>) => {
    const created = await createPlaybook({
      ...data,
      ...(templateId ? { source_template_id: Number(templateId) } : {}),
    });
    toast.success('Playbook created');
    router.push(`/settings/playbooks/${created.id}`);
  };

  const defaultPlaybook = sourceTemplate
    ? { ...sourceTemplate, id: undefined as unknown as number, is_template: false, organization_id: null }
    : undefined;

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => router.push('/settings/playbooks')}>
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back
        </Button>
        <h1 className="text-2xl font-bold">
          {templateId ? 'New Playbook from Template' : 'New Playbook'}
        </h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {templateId && sourceTemplate ? `Based on: ${sourceTemplate.name}` : 'Playbook Details'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loadingTemplate ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <PlaybookEditor
              playbook={defaultPlaybook as Playbook | undefined}
              onSave={handleSave}
              onCancel={() => router.push('/settings/playbooks')}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function NewPlaybookPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-[300px]"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>}>
      <NewPlaybookInner />
    </Suspense>
  );
}
