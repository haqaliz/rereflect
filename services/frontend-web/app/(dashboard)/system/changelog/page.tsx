'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { changelogAPI, type ChangelogEntryAdmin, type ChangelogEntryUpdate } from '@/lib/api/changelog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
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
  DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertTriangle,
  Eye,
  EyeOff,
  Pencil,
  Trash2,
  Loader2,
  FileText,
} from 'lucide-react';

const TYPE_LABELS: Record<string, string> = {
  feature: 'Feature',
  fix: 'Fix',
  improvement: 'Improvement',
  breaking_change: 'Breaking Change',
  chore: 'Chore',
};

const BADGE_STYLES: Record<string, string> = {
  feature: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  fix: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  improvement: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  breaking_change: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  chore: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300',
};

export default function AdminChangelogPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [entries, setEntries] = useState<ChangelogEntryAdmin[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Edit dialog state
  const [editingEntry, setEditingEntry] = useState<ChangelogEntryAdmin | null>(null);
  const [editForm, setEditForm] = useState<ChangelogEntryUpdate>({});
  const [isSaving, setIsSaving] = useState(false);

  // Delete dialog state
  const [deletingEntry, setDeletingEntry] = useState<ChangelogEntryAdmin | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Redirect non-system-admins
  useEffect(() => {
    if (user && !user.is_system_admin) {
      router.push('/dashboard');
    }
  }, [user, router]);

  const fetchEntries = useCallback(async (offset = 0, append = false) => {
    try {
      if (!append) setIsLoading(true);
      const data = await changelogAPI.getAdmin({ offset, limit: 20 });
      if (append) {
        setEntries(prev => [...prev, ...data.items]);
      } else {
        setEntries(data.items);
      }
      setTotal(data.total);
      setHasMore(data.has_more);
    } catch {
      // Handle error
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.is_system_admin) {
      fetchEntries();
    }
  }, [user, fetchEntries]);

  const handleToggleVisibility = async (entry: ChangelogEntryAdmin) => {
    try {
      const updated = await changelogAPI.updateEntry(entry.id, { is_hidden: !entry.is_hidden });
      setEntries(prev => prev.map(e => e.id === updated.id ? updated : e));
    } catch {
      // Handle error
    }
  };

  const handleEdit = (entry: ChangelogEntryAdmin) => {
    setEditingEntry(entry);
    setEditForm({
      title: entry.title,
      description: entry.description,
      entry_type: entry.entry_type,
      is_breaking: entry.is_breaking,
    });
  };

  const handleSaveEdit = async () => {
    if (!editingEntry) return;
    setIsSaving(true);
    try {
      const updated = await changelogAPI.updateEntry(editingEntry.id, editForm);
      setEntries(prev => prev.map(e => e.id === updated.id ? updated : e));
      setEditingEntry(null);
    } catch {
      // Handle error
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingEntry) return;
    setIsDeleting(true);
    try {
      await changelogAPI.deleteEntry(deletingEntry.id);
      setEntries(prev => prev.filter(e => e.id !== deletingEntry.id));
      setTotal(prev => prev - 1);
      setDeletingEntry(null);
    } catch {
      // Handle error
    } finally {
      setIsDeleting(false);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  if (!user?.is_system_admin) {
    return null;
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Changelog Management</h1>
          <p className="text-muted-foreground">Manage public changelog entries. {total} total entries.</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5" />
            Changelog Entries
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : entries.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              No changelog entries. Run the sync script to populate from git commits.
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[100px]">Date</TableHead>
                    <TableHead className="w-[120px]">Type</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead className="w-[80px]">Status</TableHead>
                    <TableHead className="w-[120px] text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries.map(entry => (
                    <TableRow key={entry.id} className={entry.is_hidden ? 'opacity-50' : ''}>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatDate(entry.committed_at)}
                      </TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${BADGE_STYLES[entry.entry_type] || BADGE_STYLES.chore}`}>
                          {entry.is_breaking && <AlertTriangle className="w-3 h-3" />}
                          {TYPE_LABELS[entry.entry_type] || entry.entry_type}
                        </span>
                      </TableCell>
                      <TableCell className="font-medium">{entry.title}</TableCell>
                      <TableCell>
                        {entry.is_hidden ? (
                          <span className="text-xs text-muted-foreground">Hidden</span>
                        ) : (
                          <span className="text-xs text-green-600 dark:text-green-400">Visible</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleToggleVisibility(entry)}
                            title={entry.is_hidden ? 'Show' : 'Hide'}
                          >
                            {entry.is_hidden ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleEdit(entry)}
                            title="Edit"
                          >
                            <Pencil className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setDeletingEntry(entry)}
                            title="Delete"
                            className="text-destructive hover:text-destructive"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {hasMore && (
                <div className="flex justify-center pt-4">
                  <Button
                    variant="outline"
                    onClick={() => fetchEntries(entries.length, true)}
                  >
                    Load more ({total - entries.length} remaining)
                  </Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      <Dialog open={!!editingEntry} onOpenChange={(open) => !open && setEditingEntry(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Changelog Entry</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-foreground">Title</label>
              <Input
                value={editForm.title || ''}
                onChange={(e) => setEditForm(prev => ({ ...prev, title: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Description</label>
              <Input
                value={editForm.description || ''}
                onChange={(e) => setEditForm(prev => ({ ...prev, description: e.target.value || null }))}
                placeholder="Optional description"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Type</label>
              <Select
                value={editForm.entry_type}
                onValueChange={(value) => setEditForm(prev => ({ ...prev, entry_type: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(TYPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingEntry(null)}>Cancel</Button>
            <Button onClick={handleSaveEdit} disabled={isSaving}>
              {isSaving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingEntry} onOpenChange={(open) => !open && setDeletingEntry(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Changelog Entry</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground">
            Are you sure you want to delete &quot;{deletingEntry?.title}&quot;? This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingEntry(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={isDeleting}>
              {isDeleting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
