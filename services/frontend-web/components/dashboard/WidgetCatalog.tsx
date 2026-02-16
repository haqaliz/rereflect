'use client';

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Plus, Check } from 'lucide-react';
import {
  widgetRegistry,
  widgetCategories,
  type WidgetCategory,
} from './constants/widget-registry';

interface WidgetCatalogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeWidgetIds: string[];
  onAddWidget: (widgetId: string) => void;
}

export function WidgetCatalog({
  open,
  onOpenChange,
  activeWidgetIds,
  onAddWidget,
}: WidgetCatalogProps) {
  const widgetsByCategory = widgetCategories.reduce(
    (acc, category) => {
      acc[category] = widgetRegistry.filter((w) => w.category === category);
      return acc;
    },
    {} as Record<WidgetCategory, typeof widgetRegistry>
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[420px] sm:max-w-[420px] p-0">
        <SheetHeader className="p-6 pb-4 border-b border-border">
          <SheetTitle>Widget Catalog</SheetTitle>
          <SheetDescription>Add widgets to your dashboard</SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-120px)]">
          <div className="p-4 space-y-6">
            {widgetCategories.map((category) => {
              const widgets = widgetsByCategory[category];
              if (!widgets || widgets.length === 0) return null;

              return (
                <div key={category}>
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 px-1">
                    {category}
                  </h3>
                  <div className="space-y-2">
                    {widgets.map((widget) => {
                      const isAdded = activeWidgetIds.includes(widget.id);
                      const Icon = widget.icon;

                      return (
                        <div
                          key={widget.id}
                          className={`flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 ${
                            isAdded
                              ? 'opacity-60 bg-muted/30 border-border'
                              : 'bg-card border-border hover:border-primary/50 hover:shadow-sm'
                          }`}
                        >
                          <div className="p-2 bg-secondary rounded-lg flex-shrink-0">
                            <Icon className="w-4 h-4 text-primary" />
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <p className="text-sm font-medium text-foreground truncate">
                                {widget.name}
                              </p>
                              {widget.planGate && (
                                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                                  Pro
                                </Badge>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                              {widget.description}
                            </p>
                            <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                              {widget.defaultW}x{widget.defaultH}
                            </p>
                          </div>

                          {isAdded ? (
                            <div className="flex items-center gap-1 text-xs text-muted-foreground flex-shrink-0">
                              <Check className="w-3.5 h-3.5" />
                              <span>Added</span>
                            </div>
                          ) : (
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-7 px-2 text-xs flex-shrink-0"
                              onClick={() => onAddWidget(widget.id)}
                            >
                              <Plus className="w-3.5 h-3.5 mr-1" />
                              Add
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
