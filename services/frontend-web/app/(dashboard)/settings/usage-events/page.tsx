'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import Link from 'next/link';
import { ExternalLink, Terminal, CheckCircle } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Normalized event schema example (inline constant avoids template literal escaping)
const CURL_EXAMPLE = `curl -X POST ${API_BASE}/api/v1/webhooks/usage \\
  -H "X-API-Key: rrf_YOUR_INGEST_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
  "events": [
    {
      "type": "track",
      "email": "alice@acme.com",
      "event": "feature_used",
      "name": "export_csv",
      "timestamp": "2026-06-28T10:00:00Z",
      "messageId": "evt_unique_id_001",
      "properties": { "plan": "team" }
    },
    {
      "type": "identify",
      "email": "alice@acme.com",
      "timestamp": "2026-06-28T10:01:00Z",
      "messageId": "evt_unique_id_002",
      "traits": { "name": "Alice" }
    }
  ]
}'`;

const SCHEMA_EXAMPLE = `{
  "events": [
    {
      "type": "track" | "identify",  // required
      "email": "user@example.com",   // required; events without email are skipped
      "event": "page_view",          // recommended for track events
      "name": "dashboard",           // human-readable event/feature name
      "timestamp": "ISO 8601",       // when the event occurred
      "messageId": "evt_abc123",     // dedup key — idempotent on replay
      "properties": { ... },         // arbitrary JSON (max 16 KB)
      "traits": { ... }              // for identify events
    }
  ]
}`;

export default function UsageEventsPage() {
  const router = useRouter();
  const { user } = useAuth();

  // Admin/owner gate — same pattern as integrations page
  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  useEffect(() => {
    if (user && user.role !== 'owner' && user.role !== 'admin') {
      router.replace('/settings/preferences');
    }
  }, [user, router]);

  if (!isAdminOrOwner) {
    return null;
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-foreground">Send Product-Usage Events</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Feed per-customer product activity into Rereflect to enrich health scores and the
          Customer 360 profile. This uses an inbound{' '}
          <code className="text-xs bg-muted px-1 py-0.5 rounded">POST</code> endpoint — distinct
          from the outbound webhooks in{' '}
          <Link href="/settings/webhooks" className="underline underline-offset-2">
            Settings → Webhooks
          </Link>
          .
        </p>
      </div>

      {/* Step 1 — Create ingest key */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
              1
            </span>
            Create an ingest-scoped API key
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Go to{' '}
            <Link href="/settings/api-keys" className="underline underline-offset-2">
              Settings → API Keys
            </Link>{' '}
            and create a key with the <strong className="text-foreground">ingest</strong> scope.
            The key starts with <code className="bg-muted px-1 py-0.5 rounded">rrf_</code>.
          </p>
          <p>
            Keep the key secret. It is org-scoped — events can only attach to customers in your
            organization.
          </p>
        </CardContent>
      </Card>

      {/* Step 2 — Endpoint + schema */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
              2
            </span>
            Endpoint &amp; normalized schema
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div>
            <p className="text-muted-foreground mb-1">Endpoint</p>
            <code className="block bg-muted rounded px-3 py-2 text-xs font-mono">
              POST {API_BASE}/api/v1/webhooks/usage
            </code>
            <p className="text-xs text-muted-foreground mt-1">
              Auth header: <code className="bg-muted px-1 py-0.5 rounded">X-API-Key: rrf_…</code>
            </p>
          </div>

          <div>
            <p className="text-muted-foreground mb-1">Schema (Segment-compatible subset)</p>
            <pre className="bg-muted rounded px-3 py-2 text-xs font-mono overflow-x-auto whitespace-pre-wrap">
              {SCHEMA_EXAMPLE}
            </pre>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="rounded border border-border p-3">
              <p className="font-semibold text-foreground mb-1">Accepted event types</p>
              <ul className="space-y-0.5 text-muted-foreground">
                <li><code>track</code> — a user performed an action (login, feature use, page view)</li>
                <li><code>identify</code> — update user traits</li>
              </ul>
            </div>
            <div className="rounded border border-border p-3">
              <p className="font-semibold text-foreground mb-1">Matching &amp; dedup</p>
              <ul className="space-y-0.5 text-muted-foreground">
                <li>Customer matched by <code>email</code> field (required)</li>
                <li>Events without a resolvable email are skipped</li>
                <li><code>messageId</code> deduplicates replays</li>
                <li>Batch: max 1 000 events per request</li>
              </ul>
            </div>
          </div>

          <div>
            <p className="text-muted-foreground mb-1">Response</p>
            <code className="block bg-muted rounded px-3 py-2 text-xs font-mono">
              202 &#123;&quot;accepted&quot;: 2, &quot;skipped&quot;: 0, &quot;skipped_reasons&quot;: &#123;&#125;&#125;
            </code>
          </div>
        </CardContent>
      </Card>

      {/* Step 3 — curl example */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Terminal className="w-4 h-4" />
            curl example
          </CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="bg-muted rounded px-3 py-2 text-xs font-mono overflow-x-auto whitespace-pre-wrap">
            {CURL_EXAMPLE}
          </pre>
        </CardContent>
      </Card>

      {/* Verify it's working */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />
            Verify it&apos;s working
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <ol className="list-decimal list-inside space-y-1">
            <li>
              POST one or two events for a customer email that already exists in Rereflect
              (e.g. a customer you can see in the Customers list).
            </li>
            <li>
              The endpoint returns{' '}
              <code className="bg-muted px-1 py-0.5 rounded">202</code> with an{' '}
              <code className="bg-muted px-1 py-0.5 rounded">accepted</code> count greater than 0.
            </li>
            <li>
              Open that customer&apos;s profile page. Within one Celery cycle (typically
              &lt;30 s), the <strong className="text-foreground">Usage Activity</strong> card
              should show the{' '}
              <strong className="text-foreground">Last Active</strong> timestamp and event count.
            </li>
            <li>
              To factor usage into the health score, go to{' '}
              <Link href="/settings/ai" className="underline underline-offset-2">
                Settings → AI → Health Score Weights
              </Link>{' '}
              and raise the{' '}
              <strong className="text-foreground">Usage Activity</strong> weight above 0 (all
              six weights must sum to 100).
            </li>
          </ol>
          <p className="text-xs pt-2">
            For more details, see the{' '}
            <a
              href="https://github.com/haqaliz/rereflect/blob/master/docs/SELF_HOSTING.md"
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 inline-flex items-center gap-1"
            >
              SELF_HOSTING guide
              <ExternalLink className="w-3 h-3" />
            </a>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
