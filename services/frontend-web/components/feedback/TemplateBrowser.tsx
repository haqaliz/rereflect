'use client';

import { useState, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ArrowLeft, Search, Loader2, FileText } from 'lucide-react';
import { responsesAPI, type ResponseTemplate } from '@/lib/api/responses';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TemplateBrowserProps {
  onSelect: (template: ResponseTemplate) => void;
  onBack: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function TemplateBrowser({ onSelect, onBack }: TemplateBrowserProps) {
  const [templates, setTemplates] = useState<ResponseTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    responsesAPI.listTemplates()
      .then(setTemplates)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return templates;
    const q = search.toLowerCase();
    return templates.filter(
      t =>
        t.name.toLowerCase().includes(q) ||
        t.category.toLowerCase().includes(q)
    );
  }, [templates, search]);

  const systemTemplates = filtered.filter(t => t.is_system);
  const customTemplates = filtered.filter(t => !t.is_system);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} className="flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" />
          Back
        </Button>
        <span className="font-semibold text-sm">Browse Templates</span>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          placeholder="Search templates..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Loading state */}
      {loading && (
        <div data-testid="template-browser-loading" className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty state */}
      {!loading && filtered.length === 0 && (
        <div className="text-center py-10 text-muted-foreground">
          <FileText className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p>No templates found</p>
        </div>
      )}

      {/* System Templates */}
      {systemTemplates.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            System Templates
          </h3>
          <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
            {systemTemplates.map(template => (
              <TemplateRow key={template.id} template={template} onSelect={onSelect} />
            ))}
          </div>
        </section>
      )}

      {/* Custom Templates */}
      {customTemplates.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Custom Templates
          </h3>
          <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
            {customTemplates.map(template => (
              <TemplateRow key={template.id} template={template} onSelect={onSelect} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ─── Template Row ──────────────────────────────────────────────────────────────

function TemplateRow({
  template,
  onSelect,
}: {
  template: ResponseTemplate;
  onSelect: (t: ResponseTemplate) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 p-3 bg-background hover:bg-secondary/20 transition-colors">
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm">{template.name}</p>
        <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
          {template.body}
        </p>
      </div>
      <Button
        size="sm"
        variant="outline"
        className="shrink-0"
        onClick={() => onSelect(template)}
      >
        Use
      </Button>
    </div>
  );
}
