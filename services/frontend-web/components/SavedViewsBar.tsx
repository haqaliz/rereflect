'use client';

import { useState, useEffect, useCallback } from 'react';
import { savedViewsAPI, type SavedView } from '@/lib/api/saved-views';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Plus, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';

interface SavedViewsBarProps {
  page: string;
  currentConfig: Record<string, unknown>;
  onApplyView: (config: Record<string, unknown>) => void;
}

export function SavedViewsBar({ page, currentConfig, onApplyView }: SavedViewsBarProps) {
  const [views, setViews] = useState<SavedView[]>([]);
  const [activeViewId, setActiveViewId] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [renameId, setRenameId] = useState<number | null>(null);
  const [renameName, setRenameName] = useState('');
  const [renameOpen, setRenameOpen] = useState(false);

  const fetchViews = useCallback(async () => {
    try {
      const data = await savedViewsAPI.list(page);
      setViews(data);
    } catch {
      // silently fail — views are optional
    }
  }, [page]);

  useEffect(() => { fetchViews(); }, [fetchViews]);

  const handleSave = async () => {
    if (!newName.trim()) return;
    try {
      await savedViewsAPI.create({ name: newName.trim(), page, config: currentConfig });
      setNewName('');
      setDialogOpen(false);
      fetchViews();
    } catch {
      // handle error silently or show toast
    }
  };

  const handleApply = (view: SavedView) => {
    setActiveViewId(view.id);
    onApplyView(view.config);
  };

  const handleClearView = () => {
    setActiveViewId(null);
  };

  const handleDelete = async (id: number) => {
    try {
      await savedViewsAPI.delete(id);
      if (activeViewId === id) setActiveViewId(null);
      fetchViews();
    } catch {
      // handle error
    }
  };

  const handleRename = async () => {
    if (!renameId || !renameName.trim()) return;
    try {
      await savedViewsAPI.update(renameId, { name: renameName.trim() });
      setRenameOpen(false);
      setRenameId(null);
      fetchViews();
    } catch {
      // handle error
    }
  };

  const startRename = (view: SavedView) => {
    setRenameId(view.id);
    setRenameName(view.name);
    setRenameOpen(true);
  };

  if (views.length === 0 && !dialogOpen) {
    return (
      <div className="flex items-center gap-2">
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="text-xs text-muted-foreground">
              <Plus className="w-3 h-3 mr-1" /> Save view
            </Button>
          </DialogTrigger>
          <SaveViewDialogContent
            name={newName}
            onNameChange={setNewName}
            onSave={handleSave}
          />
        </Dialog>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1 overflow-x-auto scrollbar-hide">
      <Button
        variant={activeViewId === null ? 'secondary' : 'ghost'}
        size="sm"
        className="text-xs shrink-0"
        onClick={handleClearView}
      >
        All
      </Button>

      {views.map(view => (
        <div key={view.id} className="flex items-center shrink-0">
          <Button
            variant={activeViewId === view.id ? 'secondary' : 'ghost'}
            size="sm"
            className="text-xs"
            onClick={() => handleApply(view)}
          >
            {view.name}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-6 w-6 p-0 ml-0.5">
                <MoreHorizontal className="w-3 h-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onClick={() => startRename(view)}>
                <Pencil className="w-3 h-3 mr-2" /> Rename
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleDelete(view.id)} className="text-destructive">
                <Trash2 className="w-3 h-3 mr-2" /> Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ))}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogTrigger asChild>
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0 shrink-0">
            <Plus className="w-3.5 h-3.5" />
          </Button>
        </DialogTrigger>
        <SaveViewDialogContent
          name={newName}
          onNameChange={setNewName}
          onSave={handleSave}
        />
      </Dialog>

      {/* Rename dialog */}
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="sm:max-w-[340px]">
          <DialogHeader>
            <DialogTitle>Rename View</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              value={renameName}
              onChange={e => setRenameName(e.target.value)}
              placeholder="View name"
              onKeyDown={e => e.key === 'Enter' && handleRename()}
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setRenameOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={handleRename} disabled={!renameName.trim()}>Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SaveViewDialogContent({
  name,
  onNameChange,
  onSave,
}: {
  name: string;
  onNameChange: (v: string) => void;
  onSave: () => void;
}) {
  return (
    <DialogContent className="sm:max-w-[340px]">
      <DialogHeader>
        <DialogTitle>Save Current View</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        <Input
          value={name}
          onChange={e => onNameChange(e.target.value)}
          placeholder="e.g. Weekly Snapshot"
          onKeyDown={e => e.key === 'Enter' && onSave()}
          autoFocus
        />
        <div className="flex justify-end gap-2">
          <Button size="sm" onClick={onSave} disabled={!name.trim()}>Save View</Button>
        </div>
      </div>
    </DialogContent>
  );
}
