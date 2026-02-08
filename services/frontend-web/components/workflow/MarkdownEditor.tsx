'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { MarkdownContent } from './MarkdownContent';

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
}

export function MarkdownEditor({
  value,
  onChange,
  placeholder = 'Write markdown...',
  rows = 3,
}: MarkdownEditorProps) {
  const [activeTab, setActiveTab] = useState<string>('write');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  useEffect(() => {
    if (activeTab === 'write') {
      requestAnimationFrame(autoResize);
    }
  }, [value, activeTab, autoResize]);

  return (
    <Tabs value={activeTab} onValueChange={setActiveTab}>
      <div className="flex items-center justify-between">
        <TabsList className="h-7">
          <TabsTrigger value="write" className="text-xs px-2 h-5">Write</TabsTrigger>
          <TabsTrigger value="preview" className="text-xs px-2 h-5">Preview</TabsTrigger>
        </TabsList>
        <span className="text-[10px] text-muted-foreground">Markdown supported</span>
      </div>
      <TabsContent value="write" className="mt-2">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            autoResize();
          }}
          placeholder={placeholder}
          rows={rows}
          className="resize-none overflow-hidden"
        />
      </TabsContent>
      <TabsContent value="preview" className="mt-2">
        <div className="min-h-[80px] p-3 border border-border rounded-md bg-background">
          {value.trim() ? (
            <MarkdownContent content={value} />
          ) : (
            <p className="text-sm text-muted-foreground italic">Nothing to preview</p>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}
