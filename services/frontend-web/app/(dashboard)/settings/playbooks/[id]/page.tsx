'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  getPlaybook,
  updatePlaybook,
  deletePlaybook,
  type PlaybookDetail,
  type Playbook,
} from '@/lib/api/playbooks';
import { PlaybookEditor } from '@/components/playbooks/PlaybookEditor';
import { PlaybookExecutionsList } from '@/components/playbooks/PlaybookExecutionsList';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { ArrowLeft, Loader2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { formatProbabilityRange } from '@/lib/api/playbooks';

export default function PlaybookDetailPage() {
  const router = useRouter();
  const params = useParams();
  const { user } = useAuth();

  const id = Number(params.id);
  const [detail, setDetail] = useState<PlaybookDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const isBusiness = user?.plan === 'business' || user?.plan === 'enterprise';

  useEffect(() => {
    if (!isBusiness) {
      router.replace('/settings/playbooks');
      return;
    }
    setLoading(true);
    getPlaybook(id)
      .then(setDetail)
      .catch(() => toast.error('Failed to load playbook'))
      .finally(() => setLoading(false));
  }, [id, isBusiness, router]);

  const handleSave = async (data: Partial<Playbook>) => {
    const updated = await updatePlaybook(id, data);
    setDetail((prev) => (prev ? { ...prev, ...updated } : null));
    toast.success('Playbook updated');
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deletePlaybook(id);
      toast.success('Playbook deleted');
      router.push('/settings/playbooks');
    } catch {
      toast.error('Failed to delete playbook');
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8 text-center text-muted-foreground">
        <p>Playbook not found.</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push('/settings/playbooks')}>
          Back to Playbooks
        </Button>
      </div>
    );
  }

  const isTemplate = detail.is_template;

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push('/settings/playbooks')}>
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back
          </Button>
          <div>
            <h1 className="text-2xl font-bold leading-tight">{detail.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <Badge variant="outline" className="text-xs">
                {formatProbabilityRange(detail.probability_min, detail.probability_max)}
              </Badge>
              {isTemplate && (
                <Badge variant="secondary" className="text-xs">System Template</Badge>
              )}
            </div>
          </div>
        </div>

        {!isTemplate && (
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:text-destructive border-destructive/30"
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 className="w-3.5 h-3.5 mr-1.5" />
            Delete
          </Button>
        )}
      </div>

      {/* Editor / read-only view */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isTemplate ? 'Template Details (read-only)' : 'Edit Playbook'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PlaybookEditor
            playbook={detail}
            onSave={handleSave}
            onCancel={() => router.push('/settings/playbooks')}
            readOnly={isTemplate}
          />
        </CardContent>
      </Card>

      {/* Recent executions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Executions</CardTitle>
        </CardHeader>
        <CardContent>
          <PlaybookExecutionsList executions={detail.recent_executions ?? []} />
        </CardContent>
      </Card>

      {/* Delete confirmation dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Playbook</DialogTitle>
            <DialogDescription>
              This will permanently delete &quot;{detail.name}&quot; and all its execution history.
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting && <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
