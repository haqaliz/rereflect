'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Loader2, Send, X } from 'lucide-react';
import { conversationsAPI, type ConversationMessage, type CopilotUsageResponse } from '@/lib/api/conversations';
import { useCopilotWebSocket, type CopilotMessage } from '@/hooks/useCopilotWebSocket';
import { MessageBubble } from './MessageBubble';
import { SCOPE_OPTIONS, type ContextScope } from './ContextScopeSelector';
import { MentionAutocomplete, detectMention, isScopeOption, extractScope, type MentionMatch } from './MentionAutocomplete';
import { StopButton } from './MessageActions';
import { ScrollArea } from '@/components/ui/scroll-area';

// ─── ChatMessage type (superset of ConversationMessage for optimistic updates) ─

export interface ChatMessage {
  id: number | string;
  role: 'user' | 'assistant';
  content: string;
  structured_data: Record<string, unknown> | null;
  created_at: string;
}

function fromConversationMessage(m: ConversationMessage): ChatMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    structured_data: m.structured_data,
    created_at: m.created_at,
  };
}

// ─── Scope chip ──────────────────────────────────────────────────────────────

function ScopeChip({ scope, onRemove }: { scope: ContextScope; onRemove: () => void }) {
  const opt = SCOPE_OPTIONS.find((o) => o.value === scope);
  if (!opt) return null;
  return (
    <span
      data-testid={`scope-chip-${scope}`}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${opt.color}`}
    >
      {opt.label}
      <button
        data-testid={`scope-chip-remove-${scope}`}
        onClick={(e) => { e.stopPropagation(); onRemove(); }}
        className="hover:opacity-70 transition-opacity"
        aria-label={`Remove ${opt.label} scope`}
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}

// ─── Streaming bubble ─────────────────────────────────────────────────────────

const STATUS_LABELS: Record<string, string> = {
  processing: 'Analyzing your question...',
  generating: 'Generating response...',
};

function StreamingBubble({ content, statusText }: { content: string; statusText: string }) {
  const displayStatus = STATUS_LABELS[statusText] ?? statusText;
  return (
    <div data-testid="streaming-indicator" className="flex justify-start mb-4">
      <div className="max-w-[75%] bg-muted/50 text-foreground rounded-2xl rounded-tl-sm px-4 py-3 w-full">
        {displayStatus && !content && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce [animation-delay:300ms]" />
            </span>
            <span>{displayStatus}</span>
          </div>
        )}
        {content && (
          <p className="text-sm whitespace-pre-wrap">{content}</p>
        )}
      </div>
    </div>
  );
}

// ─── Main ChatArea ────────────────────────────────────────────────────────────

interface ChatAreaProps {
  conversationId: string;
  copilotUsage?: CopilotUsageResponse;
  /** If set, auto-send this query as the first message after loading */
  initialQuery?: string;
}

export function ChatArea({ conversationId, copilotUsage, initialQuery }: ChatAreaProps) {
  // Token budget exceeded: tokens_used_month >= tokens_budget_month (when budget exists)
  const tokenBudgetExceeded =
    copilotUsage != null &&
    copilotUsage.tokens_budget_month != null &&
    copilotUsage.tokens_used_month != null &&
    copilotUsage.tokens_used_month >= copilotUsage.tokens_budget_month;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [inputValue, setInputValue] = useState('');
  const [contextScopes, setContextScopes] = useState<ContextScope[]>([]);
  const [pendingStopMessageId, setPendingStopMessageId] = useState<number | string | null>(null);
  const [mentionMatch, setMentionMatch] = useState<MentionMatch | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const nextOptimisticId = useRef(-1);
  const initialQuerySentForConv = useRef<string | null>(null);

  // WebSocket
  const { connected: _connected, streaming, streamingContent, statusText, reconnecting, error: wsError, sendQuery, stopGeneration, regenerate } =
    useCopilotWebSocket({
      onMessage: useCallback((msg: CopilotMessage) => {
        if (msg.type === 'assistant_message') {
          setMessages((prev) => [
            ...prev,
            {
              id: msg.message_id,
              role: 'assistant',
              content: msg.content,
              structured_data: null,
              created_at: new Date().toISOString(),
            },
          ]);
        } else if (msg.type === 'structured_data') {
          // Attach structured_data to last assistant message
          setMessages((prev) => {
            const last = prev.findIndex((m) => m.id === msg.message_id);
            if (last === -1) return prev;
            const updated = [...prev];
            updated[last] = { ...updated[last], structured_data: msg.data };
            return updated;
          });
        }
      }, []),
    });

  // Load existing messages
  useEffect(() => {
    setLoading(true);
    conversationsAPI
      .getConversation(conversationId)
      .then((conv) => {
        const apiMessages = conv.messages.map(fromConversationMessage);
        // Merge: keep optimistic messages (negative ids) that haven't been
        // persisted yet, so they don't flash away during loading.
        setMessages((prev) => {
          const optimistic = prev.filter((m) => typeof m.id === 'number' && m.id < 0);
          // If the API already returned messages, use those + any pending optimistic ones
          if (apiMessages.length > 0) {
            const apiIds = new Set(apiMessages.map((m: ChatMessage) => m.id));
            const remaining = optimistic.filter((m) => !apiIds.has(m.id));
            return [...apiMessages, ...remaining];
          }
          // API returned empty — keep optimistic messages (new conversation, message not persisted yet)
          return optimistic.length > 0 ? optimistic : apiMessages;
        });
        // Parse saved context_scope (could be comma-separated)
        const saved = (conv.context_scope as string) ?? 'all_data';
        if (saved && saved !== 'all_data') {
          setContextScopes(saved.split(',').filter(Boolean) as ContextScope[]);
        } else {
          setContextScopes([]);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [conversationId]);

  // Auto-send initialQuery once after loading completes (guard by conversationId to prevent Strict Mode double-send)
  useEffect(() => {
    if (loading || !initialQuery || initialQuerySentForConv.current === conversationId) return;
    initialQuerySentForConv.current = conversationId;
    sendMessageText(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, initialQuery, conversationId]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  // Handle input change + @mention detection
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInputValue(val);
    setMentionMatch(detectMention(val));
  };

  // Core send logic — used by both manual send and initialQuery auto-send
  const sendMessageText = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const optimisticId = nextOptimisticId.current--;
    setMessages((prev) => [
      ...prev,
      {
        id: optimisticId,
        role: 'user',
        content: trimmed,
        structured_data: null,
        created_at: new Date().toISOString(),
      },
    ]);

    const scopeStr = contextScopes.length > 0 ? contextScopes.join(',') : 'all_data';
    sendQuery(conversationId, trimmed, scopeStr);
  }, [conversationId, contextScopes, sendQuery]);

  // Send message from input
  const handleSend = useCallback(() => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    sendMessageText(trimmed);
    setInputValue('');
    setMentionMatch(null);
  }, [inputValue, sendMessageText]);

  // Keyboard handler
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Mention / scope selection
  const handleMentionSelect = (value: string) => {
    const match = mentionMatch;
    if (!match) return;

    if (isScopeOption(value)) {
      // Scope chip selected — add to scopes array and remove the @ trigger from text
      const scope = extractScope(value);
      if (scope && !contextScopes.includes(scope)) {
        setContextScopes((prev) => [...prev, scope]);
      }
      // Remove the bare @ (and any partial query) from the input text
      const atIdx = inputValue.lastIndexOf('@');
      if (atIdx !== -1) {
        const before = inputValue.slice(0, atIdx);
        setInputValue(before);
      }
    } else {
      // Regular mention — replace the @mention portion in the input
      const idx = inputValue.lastIndexOf(match.prefix);
      if (idx === -1) return;
      const before = inputValue.slice(0, idx);
      setInputValue(before + value + ' ');
    }

    setMentionMatch(null);
    inputRef.current?.focus();
  };

  // Remove a scope chip
  const handleRemoveScope = (scope: ContextScope) => {
    setContextScopes((prev) => prev.filter((s) => s !== scope));
    inputRef.current?.focus();
  };

  if (loading) {
    return (
      <div data-testid="chat-area-container" className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div data-testid="chat-area-container" className="flex flex-col h-full overflow-hidden">
      {/* Token budget exceeded banner */}
      {tokenBudgetExceeded && (
        <div
          data-testid="token-budget-banner"
          className="px-4 py-2.5 bg-amber-500/10 border-b border-amber-500/20 text-amber-700 dark:text-amber-400 text-sm text-center"
        >
          Monthly token budget reached. Add your API key in AI settings to continue.
        </div>
      )}

      {/* Reconnecting banner */}
      {reconnecting && (
        <div
          data-testid="reconnecting-banner"
          className="px-4 py-2 bg-yellow-500/10 border-b border-yellow-500/20 text-yellow-600 dark:text-yellow-400 text-xs text-center"
        >
          Reconnecting...
        </div>
      )}

      {/* Stop button header (only when streaming) */}
      {streaming && (
        <div className="flex items-center justify-end px-4 py-2 border-b border-border">
          <StopButton onStop={() => {
            if (pendingStopMessageId !== null) {
              stopGeneration(pendingStopMessageId);
            } else {
              stopGeneration(0);
            }
          }} />
        </div>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 overflow-x-hidden">
      <div className="px-4 sm:px-6 py-4 space-y-0">
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onRegenerate={(id) => {
              setPendingStopMessageId(id);
              regenerate(id);
            }}
          />
        ))}

        {/* Streaming indicator */}
        {streaming && (
          <StreamingBubble content={streamingContent} statusText={statusText} />
        )}

        {/* Error bubble */}
        {wsError && !streaming && (
          <div data-testid="ws-error-bubble" className="flex justify-start mb-4">
            <div className="max-w-[75%] bg-destructive/10 text-destructive rounded-2xl rounded-tl-sm px-4 py-3">
              <p className="text-sm font-medium">Something went wrong</p>
              <p className="text-xs mt-1 opacity-80">{wsError}</p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>
      </ScrollArea>

      {/* Input area */}
      <div className="border-t border-border px-4 py-3">
        <div className="relative">
          {/* @mention / scope autocomplete */}
          {mentionMatch && (
            <MentionAutocomplete
              match={mentionMatch}
              onSelect={handleMentionSelect}
              onClose={() => setMentionMatch(null)}
              selectedScopes={contextScopes}
            />
          )}

          <div className="flex flex-wrap items-end gap-1.5 rounded-xl border border-border bg-background focus-within:ring-1 focus-within:ring-primary px-3 py-2">
            {/* Scope chips */}
            {contextScopes.map((scope) => (
              <ScopeChip
                key={scope}
                scope={scope}
                onRemove={() => handleRemoveScope(scope)}
              />
            ))}
            <textarea
              ref={inputRef}
              data-testid="chat-input"
              value={inputValue}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              disabled={tokenBudgetExceeded}
              placeholder={
                tokenBudgetExceeded
                  ? 'Monthly token budget reached. Upgrade to continue.'
                  : 'Ask anything about your feedback... (type @ for scopes)'
              }
              rows={1}
              className="flex-1 min-w-[150px] resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground max-h-32 overflow-y-auto leading-6 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ height: 'auto' }}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = 'auto';
                el.style.height = Math.min(el.scrollHeight, 128) + 'px';
              }}
            />
            <button
              onClick={handleSend}
              disabled={!inputValue.trim() || streaming}
              className="p-1.5 rounded-lg bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90 transition-opacity shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
