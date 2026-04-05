'use client';

import { useEffect, useState, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Sparkles } from 'lucide-react';
import { useSidebar } from '@/components/ui/sidebar';
import { ConversationList } from '@/components/copilot/ConversationList';
import { ChatArea } from '@/components/copilot/ChatArea';
import { conversationsAPI } from '@/lib/api/conversations';

// Static template starters for empty state (fallback before API response)
const STATIC_TEMPLATES = [
  "This week's feedback summary",
  'Top pain points this month',
  'Most requested features',
  'Urgent feedback that needs attention',
  'Top churn risks right now',
  'Healthiest customers',
  'Customers with declining health scores',
  'Sentiment trends over the last 30 days',
  // Report templates (M2.4)
  'Executive summary this month',
  'Customer health report',
  'Feature request priorities',
  'Churn risk analysis',
];

function ConversationsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setOpen } = useSidebar();

  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [initialQuery, setInitialQuery] = useState<string | undefined>(undefined);
  const [hasConversations, setHasConversations] = useState(true);
  const [templateStarters, setTemplateStarters] = useState<string[]>(STATIC_TEMPLATES);
  const [refetchToggle, setRefetchToggle] = useState(0);
  const creatingRef = useRef(false);

  // Auto-collapse the main sidebar when on /conversations, restore on unmount
  useEffect(() => {
    setOpen(false);
    return () => {
      setOpen(true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle ?id= param — select existing conversation on initial load
  useEffect(() => {
    const idParam = searchParams.get('id');
    if (idParam) {
      setActiveConversationId(idParam);
    }
  }, [searchParams]);

  // Handle ?new=true&q=... param — create new conversation from Cmd+K
  useEffect(() => {
    const isNew = searchParams.get('new') === 'true';
    const q = searchParams.get('q')?.trim();
    if (!isNew || !q) return;

    let cancelled = false;
    conversationsAPI
      .createConversation({ context_scope: 'all_data', title: q.slice(0, 50) })
      .then((conv) => {
        if (cancelled) return;
        setInitialQuery(q);
        setActiveConversationId(conv.public_id);
        setHasConversations(true);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [searchParams, router]);

  // Sync activeConversationId → URL so each conversation has a unique, shareable URL
  useEffect(() => {
    const currentId = searchParams.get('id');
    const isNewFlow = searchParams.get('new') === 'true';

    if (activeConversationId) {
      // Only update URL if it doesn't already match (avoid loops)
      if (currentId !== activeConversationId || isNewFlow) {
        router.replace(`/conversations?id=${activeConversationId}`, { scroll: false });
      }
    } else {
      // No active conversation — clean URL
      if (currentId || isNewFlow) {
        router.replace('/conversations', { scroll: false });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConversationId]);

  // Check whether any conversations exist (drives empty state)
  useEffect(() => {
    conversationsAPI
      .getConversations({ page: 1, page_size: 1 })
      .then((res) => setHasConversations(res.total > 0))
      .catch(() => {});
  }, [refetchToggle]);

  // Fetch dynamic template starters, fall back to static if unavailable
  useEffect(() => {
    conversationsAPI
      .getTemplateStarters()
      .then((res) => {
        if (res.templates.length > 0) setTemplateStarters(res.templates);
      })
      .catch(() => {});
  }, []);

  const handleNewConversation = () => {
    // Reset to welcome state — conversation will be created when user sends a message
    setInitialQuery(undefined);
    setActiveConversationId(null);
  };

  const handleTemplateClick = async (query: string) => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    try {
      const conv = await conversationsAPI.createConversation({
        context_scope: 'all_data',
        title: query.slice(0, 50),
      });
      setInitialQuery(query);
      setActiveConversationId(conv.public_id);
      setHasConversations(true);
      setRefetchToggle((n) => n + 1);
    } finally {
      creatingRef.current = false;
    }
  };

  return (
    <div
      data-testid="conversations-page"
      data-sidebar-collapsed="true"
      className="flex h-[calc(100vh-5.5rem)] overflow-hidden -mx-4 -mb-4"
    >
      {/* Conversation list panel — ~240px */}
      <div
        data-testid="conversation-list-panel"
        className="w-72 shrink-0 border-r border-border flex flex-col bg-background overflow-hidden"
      >
        <ConversationList
          activeConversationId={activeConversationId}
          onSelectConversation={(publicId) => { setInitialQuery(undefined); setActiveConversationId(publicId); }}
          onNewConversation={handleNewConversation}
          onDeleteConversation={(publicId) => {
            if (activeConversationId === publicId) setActiveConversationId(null);
          }}
          refetchKey={refetchToggle}
        />
      </div>

      {/* Chat area */}
      <div
        data-testid="chat-area"
        className="flex-1 flex flex-col bg-background overflow-hidden"
      >
        {activeConversationId ? (
          <ChatArea conversationId={activeConversationId} initialQuery={initialQuery} />
        ) : (
          // Empty / welcome state with template starters
          <div
            data-testid="conversations-empty-state"
            className="flex-1 flex flex-col items-center justify-center gap-6 px-8 max-w-2xl mx-auto w-full"
          >
            <div className="text-center space-y-3">
              <div className="inline-flex p-4 rounded-2xl bg-primary/10">
                <Sparkles className="w-10 h-10 text-primary" />
              </div>
              <h2 className="text-2xl font-bold text-foreground">AI Copilot</h2>
              <p className="text-muted-foreground">
                Ask anything about your feedback data in plain English
              </p>
            </div>

            {/* Template starters grid */}
            <div className="w-full grid grid-cols-2 gap-2">
              {templateStarters.map((template) => (
                <button
                  key={template}
                  onClick={() => handleTemplateClick(template)}
                  className="text-left text-sm px-4 py-3 rounded-xl border border-border hover:bg-muted transition-colors"
                >
                  {template}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ConversationsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[calc(100vh-4rem)] items-center justify-center">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      }
    >
      <ConversationsPageInner />
    </Suspense>
  );
}
