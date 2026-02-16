'use client';

import { Component, type ReactNode } from 'react';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { GripVertical, X, Lock } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

// Error boundary for individual widgets
interface ErrorBoundaryProps {
  widgetId: string;
  children: ReactNode;
}
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class WidgetErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-4 text-center">
          <p className="text-sm font-medium text-destructive mb-1">Widget Error</p>
          <p className="text-xs text-muted-foreground">
            {this.state.error?.message || 'Something went wrong'}
          </p>
          <Button
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Retry
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}

interface WidgetWrapperProps {
  widgetId: string;
  title: string;
  subtitle?: string;
  icon?: LucideIcon;
  isEditMode: boolean;
  onRemove?: () => void;
  children: ReactNode;
  isLoading?: boolean;
  error?: string | null;
  planGated?: boolean;
  hideHeader?: boolean;
}

export function WidgetWrapper({
  widgetId,
  title,
  subtitle,
  icon: Icon,
  isEditMode,
  onRemove,
  children,
  isLoading,
  error,
  planGated,
  hideHeader,
}: WidgetWrapperProps) {
  // Headerless mode: stat cards and similar self-contained widgets
  if (hideHeader) {
    return (
      <div className="h-full relative group/widget">
        {/* Edit mode overlay controls */}
        {isEditMode && (
          <div className="absolute top-1 left-1 right-1 z-20 flex items-center justify-between pointer-events-none">
            <div className="drag-handle cursor-grab active:cursor-grabbing p-1 rounded bg-background/80 backdrop-blur-sm pointer-events-auto">
              <GripVertical className="w-4 h-4 text-muted-foreground" />
            </div>
            {onRemove && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 bg-background/80 backdrop-blur-sm pointer-events-auto opacity-0 group-hover/widget:opacity-100 transition-opacity"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove();
                }}
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            )}
          </div>
        )}
        <WidgetErrorBoundary widgetId={widgetId}>
          {children}
        </WidgetErrorBoundary>
      </div>
    );
  }

  return (
    <Card className="h-full flex flex-col overflow-hidden relative group/widget">
      {/* Header */}
      <CardHeader className="border-b border-border p-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            {isEditMode && (
              <div className="drag-handle cursor-grab active:cursor-grabbing p-1 -ml-1 rounded hover:bg-muted transition-colors">
                <GripVertical className="w-4 h-4 text-muted-foreground" />
              </div>
            )}
            {Icon && (
              <div className="p-1.5 bg-secondary rounded-lg flex-shrink-0">
                <Icon className="w-4 h-4 text-primary" />
              </div>
            )}
            <div className="min-w-0">
              <CardTitle className="text-sm font-semibold truncate">{title}</CardTitle>
              {subtitle && (
                <p className="text-[11px] text-muted-foreground truncate mt-0.5">{subtitle}</p>
              )}
            </div>
          </div>
          {isEditMode && onRemove && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 flex-shrink-0 opacity-0 group-hover/widget:opacity-100 transition-opacity"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
            >
              <X className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      </CardHeader>

      {/* Content */}
      <CardContent className="flex-1 p-3 overflow-y-auto scrollbar-auto-hide relative">
        {planGated ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/80 backdrop-blur-sm z-10">
            <Lock className="w-8 h-8 text-muted-foreground mb-2" />
            <p className="text-sm font-medium text-foreground">Upgrade Required</p>
            <p className="text-xs text-muted-foreground mt-1">Upgrade to Pro to unlock this widget</p>
          </div>
        ) : isLoading ? (
          <div className="space-y-3 p-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full p-4 text-center">
            <p className="text-sm text-destructive mb-1">Failed to load</p>
            <p className="text-xs text-muted-foreground">{error}</p>
          </div>
        ) : (
          <WidgetErrorBoundary widgetId={widgetId}>
            {children}
          </WidgetErrorBoundary>
        )}
      </CardContent>

    </Card>
  );
}
