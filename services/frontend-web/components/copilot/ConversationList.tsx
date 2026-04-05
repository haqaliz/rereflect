'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Plus, FolderPlus, ChevronDown, ChevronRight, Folder, MessageSquare, Loader2, Trash2 } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { conversationsAPI } from '@/lib/api/conversations';
import type { Conversation, ConversationFolder } from '@/lib/api/conversations';

interface ConversationListProps {
  activeConversationId: string | null;
  onSelectConversation: (publicId: string) => void;
  onNewConversation: () => void;
  onDeleteConversation?: (publicId: string) => void;
  /** Change this value to trigger a re-fetch of the conversation list */
  refetchKey?: number;
}

interface ContextMenuState {
  type: 'conversation' | 'folder';
  id: string;
  x: number;
  y: number;
}

export function ConversationList({
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  refetchKey,
}: ConversationListProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [folders, setFolders] = useState<ConversationFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [collapsedFolders, setCollapsedFolders] = useState<Set<number>>(new Set());
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const newFolderInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [foldersRes, convsRes] = await Promise.all([
        conversationsAPI.getFolders(),
        conversationsAPI.getConversations(),
      ]);
      setFolders(foldersRes);
      setConversations(convsRes.conversations ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refetchKey]);

  // Focus rename input when entering edit mode
  useEffect(() => {
    if (renamingId !== null) {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    }
  }, [renamingId]);

  // Focus new folder input when creating
  useEffect(() => {
    if (creatingFolder) {
      newFolderInputRef.current?.focus();
    }
  }, [creatingFolder]);

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [contextMenu]);

  const handleContextMenu = (
    e: React.MouseEvent,
    type: 'conversation' | 'folder',
    id: string
  ) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ type, id, x: e.clientX, y: e.clientY });
  };

  const startRename = (conv: Conversation) => {
    setContextMenu(null);
    setRenamingId(conv.public_id);
    setRenameValue(conv.title);
  };

  const commitRename = async (publicId: string) => {
    const trimmed = renameValue.trim();
    if (trimmed) {
      const updated = await conversationsAPI.updateConversation(publicId, { title: trimmed });
      setConversations((prev) => prev.map((c) => (c.public_id === publicId ? { ...c, title: updated.title } : c)));
    }
    setRenamingId(null);
  };

  const handleDeleteConversation = async (publicId: string) => {
    setContextMenu(null);
    setConfirmDeleteId(null);
    await conversationsAPI.deleteConversation(publicId);
    setConversations((prev) => prev.filter((c) => c.public_id !== publicId));
    onDeleteConversation?.(publicId);
  };

  const handleDeleteFolder = async (folderId: number) => {
    setContextMenu(null);
    await conversationsAPI.deleteFolder(folderId);
    setFolders((prev) => prev.filter((f) => f.id !== folderId));
    // Move conversations to unfiled
    setConversations((prev) => prev.map((c) => (c.folder_id === folderId ? { ...c, folder_id: null } : c)));
  };

  const commitNewFolder = async () => {
    const name = newFolderName.trim();
    if (name) {
      const folder = await conversationsAPI.createFolder({ name });
      setFolders((prev) => [...prev, folder]);
    }
    setCreatingFolder(false);
    setNewFolderName('');
  };

  const toggleFolder = (id: number) => {
    setCollapsedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // Group conversations: unfiled + per folder
  const unfiled = conversations.filter((c) => c.folder_id === null);

  if (loading) {
    return (
      <div data-testid="conversation-list-loading" className="flex flex-col gap-2 p-3">
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading...</span>
        </div>
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-8 rounded-md bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  const hasAny = conversations.length > 0 || folders.length > 0;

  return (
    <div className="flex flex-col h-full" onClick={() => setContextMenu(null)}>
      {/* Header actions */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-border">
        <button
          onClick={onNewConversation}
          className="flex-1 flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg hover:bg-muted transition-colors"
          aria-label="New Chat"
        >
          <Plus className="w-4 h-4" />
          <span>New Chat</span>
        </button>
        <button
          onClick={() => setCreatingFolder(true)}
          className="flex items-center gap-1 px-2 py-2 text-sm text-muted-foreground rounded-lg hover:bg-muted transition-colors"
          aria-label="New Folder"
          title="New Folder"
        >
          <FolderPlus className="w-4 h-4" />
        </button>
      </div>

      {/* New folder input */}
      {creatingFolder && (
        <div className="px-3 py-2 border-b border-border">
          <input
            ref={newFolderInputRef}
            data-testid="new-folder-input"
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitNewFolder();
              if (e.key === 'Escape') { setCreatingFolder(false); setNewFolderName(''); }
            }}
            onBlur={commitNewFolder}
            placeholder="Folder name..."
            className="w-full text-sm px-2 py-1 rounded border border-border bg-background outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      )}

      {/* Conversation tree */}
      <ScrollArea className="flex-1">
      <div className="py-2 px-1">
        {!hasAny ? (
          <div data-testid="conversations-empty-state" className="px-4 py-6 text-center">
            <MessageSquare className="w-8 h-8 mx-auto text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">Start your first conversation</p>
            <p className="text-xs text-muted-foreground mt-1">
              Ask anything about your feedback data
            </p>
          </div>
        ) : (
          <>
            {/* Folders */}
            {folders.map((folder) => {
              const folderConvs = conversations
                .filter((c) => c.folder_id === folder.id)
                .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
              const isCollapsed = collapsedFolders.has(folder.id);

              return (
                <div key={folder.id} className="mb-1">
                  <button
                    data-testid={`folder-item-${folder.id}`}
                    className="w-full flex items-center gap-2 px-4 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                    onClick={() => toggleFolder(folder.id)}
                    onContextMenu={(e) => handleContextMenu(e, 'folder', String(folder.id))}
                  >
                    {isCollapsed ? (
                      <ChevronRight className="w-3 h-3 shrink-0" />
                    ) : (
                      <ChevronDown className="w-3 h-3 shrink-0" />
                    )}
                    <Folder className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{folder.name}</span>
                    <span className="ml-auto text-xs opacity-60">{folderConvs.length}</span>
                  </button>

                  {!isCollapsed && folderConvs.map((conv) => (
                    <ConversationItem
                      key={conv.public_id}
                      conv={conv}
                      isActive={conv.public_id === activeConversationId}
                      isRenaming={renamingId === conv.public_id}
                      renameValue={renameValue}
                      renameInputRef={renamingId === conv.public_id ? renameInputRef : undefined}
                      onSelect={() => onSelectConversation(conv.public_id)}
                      onContextMenu={(e) => handleContextMenu(e, 'conversation', conv.public_id)}
                      onDoubleClick={() => startRename(conv)}
                      onRenameChange={setRenameValue}
                      onRenameCommit={() => commitRename(conv.public_id)}
                      onRenameCancel={() => setRenamingId(null)}
                      onRequestDelete={() => setConfirmDeleteId(conv.public_id)}
                    />
                  ))}
                </div>
              );
            })}

            {/* Unfiled conversations */}
            {unfiled
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              .map((conv) => (
                <ConversationItem
                  key={conv.public_id}
                  conv={conv}
                  isActive={conv.public_id === activeConversationId}
                  isRenaming={renamingId === conv.public_id}
                  renameValue={renameValue}
                  renameInputRef={renamingId === conv.public_id ? renameInputRef : undefined}
                  onSelect={() => onSelectConversation(conv.public_id)}
                  onContextMenu={(e) => handleContextMenu(e, 'conversation', conv.public_id)}
                  onDoubleClick={() => startRename(conv)}
                  onRenameChange={setRenameValue}
                  onRenameCommit={() => commitRename(conv.public_id)}
                  onRenameCancel={() => setRenamingId(null)}
                  onRequestDelete={() => setConfirmDeleteId(conv.public_id)}
                />
              ))}
          </>
        )}
      </div>
      </ScrollArea>

      {/* Context menu */}
      {contextMenu && (
        <div
          data-testid="conversation-context-menu"
          className="fixed z-50 min-w-[140px] bg-popover border border-border rounded-lg shadow-lg py-1 text-sm"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          {contextMenu.type === 'conversation' ? (
            <>
              <button
                className="w-full text-left px-3 py-1.5 hover:bg-muted transition-colors"
                onClick={() => {
                  const conv = conversations.find((c) => c.public_id === contextMenu.id);
                  if (conv) startRename(conv);
                }}
              >
                Rename
              </button>
              <button
                className="w-full text-left px-3 py-1.5 hover:bg-muted text-destructive transition-colors"
                onClick={() => { setConfirmDeleteId(contextMenu.id); setContextMenu(null); }}
              >
                Delete
              </button>
            </>
          ) : (
            <>
              <button
                data-testid={`folder-delete-${contextMenu.id}`}
                className="w-full text-left px-3 py-1.5 hover:bg-muted text-destructive transition-colors"
                onClick={() => { setConfirmDeleteId(contextMenu.id); setContextMenu(null); }}
              >
                Delete
              </button>
            </>
          )}
        </div>
      )}

      {/* Delete confirmation dialog */}
      <Dialog open={confirmDeleteId !== null} onOpenChange={(open) => { if (!open) setConfirmDeleteId(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete conversation?</DialogTitle>
            <DialogDescription>
              This will permanently delete this conversation and all its messages. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setConfirmDeleteId(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              data-testid="confirm-delete-btn"
              onClick={() => { if (confirmDeleteId) handleDeleteConversation(confirmDeleteId); }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── ConversationItem ─────────────────────────────────────────────────────────

interface ConversationItemProps {
  conv: Conversation;
  isActive: boolean;
  isRenaming: boolean;
  renameValue: string;
  renameInputRef?: React.RefObject<HTMLInputElement | null>;
  onSelect: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
  onDoubleClick: () => void;
  onRenameChange: (val: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
  onRequestDelete: () => void;
}

function ConversationItem({
  conv,
  isActive,
  isRenaming,
  renameValue,
  renameInputRef,
  onSelect,
  onContextMenu,
  onDoubleClick,
  onRenameChange,
  onRenameCommit,
  onRenameCancel,
  onRequestDelete,
}: ConversationItemProps) {
  return (
    <div
      data-testid={`conversation-item-${conv.public_id}`}
      data-active={isActive ? 'true' : undefined}
      className={`group mx-2 flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors overflow-hidden min-w-0 ${
        isActive
          ? 'bg-primary/10 text-primary'
          : 'text-foreground hover:bg-muted'
      }`}
      onClick={onSelect}
      onContextMenu={onContextMenu}
      onDoubleClick={(e) => { e.preventDefault(); onDoubleClick(); }}
    >
      <MessageSquare className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
      {isRenaming ? (
        <input
          ref={renameInputRef}
          data-testid={`conversation-rename-input-${conv.public_id}`}
          type="text"
          value={renameValue}
          onChange={(e) => onRenameChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); onRenameCommit(); }
            if (e.key === 'Escape') onRenameCancel();
          }}
          onBlur={onRenameCommit}
          onClick={(e) => e.stopPropagation()}
          className="flex-1 bg-transparent border-b border-primary outline-none text-sm"
        />
      ) : (
        <span className="truncate flex-1">{conv.title}</span>
      )}
      {/* Delete button — visible on hover */}
      {!isRenaming && (
        <button
          data-testid={`conversation-delete-${conv.public_id}`}
          onClick={(e) => { e.stopPropagation(); onRequestDelete(); }}
          className="hidden group-hover:flex shrink-0 p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
          title="Delete conversation"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
