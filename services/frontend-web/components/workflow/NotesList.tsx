'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { workflowAPI, FeedbackNote } from '@/lib/api/workflow';
import { formatRelativeTime } from '@/lib/workflow-utils';
import { Pencil, Trash2, X, Check } from 'lucide-react';
import { MarkdownEditor } from './MarkdownEditor';
import { MarkdownContent } from './MarkdownContent';

interface NotesListProps {
  feedbackId: number;
  currentUserId: number;
}

export function NotesList({ feedbackId, currentUserId }: NotesListProps) {
  const [notes, setNotes] = useState<FeedbackNote[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [newNoteContent, setNewNoteContent] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);
  const [deletingNoteId, setDeletingNoteId] = useState<number | null>(null);

  // Fetch notes on mount
  useEffect(() => {
    const fetchNotes = async () => {
      try {
        const fetchedNotes = await workflowAPI.getNotes(feedbackId);
        setNotes(fetchedNotes);
      } catch (error) {
        console.error('Failed to fetch notes:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchNotes();
  }, [feedbackId]);

  const handleCreateNote = async () => {
    if (!newNoteContent.trim()) return;

    try {
      setIsCreating(true);
      const newNote = await workflowAPI.createNote(feedbackId, newNoteContent.trim());
      setNotes((prev) => [newNote, ...prev]);
      setNewNoteContent('');
    } catch (error) {
      console.error('Failed to create note:', error);
    } finally {
      setIsCreating(false);
    }
  };

  const startEditing = (note: FeedbackNote) => {
    setEditingNoteId(note.id);
    setEditingContent(note.content);
  };

  const cancelEditing = () => {
    setEditingNoteId(null);
    setEditingContent('');
  };

  const handleUpdateNote = async (noteId: number) => {
    if (!editingContent.trim()) return;

    try {
      setIsUpdating(true);
      const updatedNote = await workflowAPI.updateNote(noteId, editingContent.trim());
      setNotes((prev) =>
        prev.map((note) => (note.id === noteId ? updatedNote : note))
      );
      setEditingNoteId(null);
      setEditingContent('');
    } catch (error) {
      console.error('Failed to update note:', error);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDeleteNote = async (noteId: number) => {
    if (!confirm('Are you sure you want to delete this note?')) return;

    try {
      setDeletingNoteId(noteId);
      await workflowAPI.deleteNote(noteId);
      setNotes((prev) => prev.filter((note) => note.id !== noteId));
    } catch (error) {
      console.error('Failed to delete note:', error);
    } finally {
      setDeletingNoteId(null);
    }
  };

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading notes...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Create Note Form */}
      <div className="space-y-2">
        <MarkdownEditor
          value={newNoteContent}
          onChange={setNewNoteContent}
          placeholder="Add a note..."
          rows={3}
        />
        <Button
          onClick={handleCreateNote}
          disabled={isCreating || !newNoteContent.trim()}
          size="sm"
        >
          {isCreating ? 'Adding...' : 'Add Note'}
        </Button>
      </div>

      {/* Notes List */}
      {notes.length === 0 ? (
        <p className="text-sm text-muted-foreground">No notes yet.</p>
      ) : (
        <div className="space-y-3">
          {notes.map((note) => {
            const isAuthor = note.author_id === currentUserId;
            const isEditing = editingNoteId === note.id;

            return (
              <div
                key={note.id}
                className="p-3 border border-border rounded-lg bg-card space-y-2"
              >
                {/* Note Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {note.author_email}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatRelativeTime(note.created_at)}
                      {note.updated_at && note.updated_at !== note.created_at && (
                        <span className="ml-1">(edited)</span>
                      )}
                    </p>
                  </div>

                  {/* Edit/Delete Actions (only for author) */}
                  {isAuthor && !isEditing && (
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => startEditing(note)}
                        className="h-7 w-7"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteNote(note.id)}
                        disabled={deletingNoteId === note.id}
                        className="h-7 w-7 text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  )}
                </div>

                {/* Note Content */}
                {isEditing ? (
                  <div className="space-y-2">
                    <MarkdownEditor
                      value={editingContent}
                      onChange={setEditingContent}
                      rows={3}
                    />
                    <div className="flex gap-2">
                      <Button
                        onClick={() => handleUpdateNote(note.id)}
                        disabled={isUpdating || !editingContent.trim()}
                        size="sm"
                      >
                        <Check className="h-4 w-4" />
                      </Button>
                      <Button
                        onClick={cancelEditing}
                        variant="outline"
                        size="sm"
                        disabled={isUpdating}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ) : (
                  <MarkdownContent content={note.content} />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
