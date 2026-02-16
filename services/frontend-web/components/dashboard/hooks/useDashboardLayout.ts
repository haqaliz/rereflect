'use client';

import { useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { LayoutItem, ResponsiveLayouts } from 'react-grid-layout';
import apiClient from '@/lib/api-client';
import { defaultLayout, responsiveLayouts } from '../constants/default-layouts';
import { widgetRegistryMap } from '../constants/widget-registry';

interface ServerWidgetItem {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface ServerLayoutData {
  layouts: {
    lg: ServerWidgetItem[];
    md: ServerWidgetItem[];
    sm: ServerWidgetItem[];
  };
  version: number;
}

function restoreMinConstraints(items: ServerWidgetItem[]): LayoutItem[] {
  return items.map((w) => {
    const def = widgetRegistryMap.get(w.id);
    return {
      i: w.id,
      x: w.x,
      y: w.y,
      w: w.w,
      h: w.h,
      minW: def?.minW ?? 2,
      minH: def?.minH ?? 2,
    };
  });
}

function serverToResponsiveLayouts(data: ServerLayoutData): ResponsiveLayouts {
  return {
    lg: restoreMinConstraints(data.layouts.lg),
    md: restoreMinConstraints(data.layouts.md),
    sm: restoreMinConstraints(data.layouts.sm),
  };
}

function layoutItemsToServer(items: readonly LayoutItem[]): ServerWidgetItem[] {
  return items.map((item) => ({
    id: item.i,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h,
  }));
}

function responsiveLayoutsToServer(layouts: ResponsiveLayouts): ServerLayoutData {
  return {
    layouts: {
      lg: layoutItemsToServer((layouts.lg || []) as readonly LayoutItem[]),
      md: layoutItemsToServer((layouts.md || []) as readonly LayoutItem[]),
      sm: layoutItemsToServer((layouts.sm || []) as readonly LayoutItem[]),
    },
    version: 2,
  };
}

async function fetchLayout(): Promise<ResponsiveLayouts> {
  try {
    const res = await apiClient.get('/api/v1/user/dashboard-layout/');
    // If server returns default layout, use frontend defaults instead
    if (res.data.is_default) {
      return responsiveLayouts;
    }
    const data = res.data.layout_json;
    // v2 format: { layouts: { lg, md, sm }, version: 2 }
    if (data.version === 2 && data.layouts) {
      return serverToResponsiveLayouts(data);
    }
    // v1 or unknown format — ignore and use frontend defaults
    return responsiveLayouts;
  } catch {
    return responsiveLayouts;
  }
}

async function saveLayoutToServer(layouts: ResponsiveLayouts) {
  const data = responsiveLayoutsToServer(layouts);
  await apiClient.put('/api/v1/user/dashboard-layout/', { layout_json: data });
}

export function useDashboardLayout() {
  const queryClient = useQueryClient();
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingLayouts = useRef<ResponsiveLayouts | null>(null);

  const { data: layouts, isLoading } = useQuery({
    queryKey: ['dashboard-layout'],
    queryFn: fetchLayout,
    staleTime: Infinity,
    gcTime: 60 * 60 * 1000,
    retry: false,
    placeholderData: responsiveLayouts,
  });

  const mutation = useMutation({
    mutationFn: saveLayoutToServer,
  });

  const currentLayouts = layouts ?? responsiveLayouts;

  // Flush any pending debounced save immediately
  const flushSave = useCallback(() => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
      debounceTimer.current = null;
    }
    if (pendingLayouts.current) {
      mutation.mutate(pendingLayouts.current);
      pendingLayouts.current = null;
    }
  }, [mutation]);

  const saveLayout = useCallback(
    (newLayouts: ResponsiveLayouts) => {
      queryClient.setQueryData(['dashboard-layout'], newLayouts);
      pendingLayouts.current = newLayouts;

      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
      debounceTimer.current = setTimeout(() => {
        if (pendingLayouts.current) {
          mutation.mutate(pendingLayouts.current);
          pendingLayouts.current = null;
        }
      }, 500);
    },
    [queryClient, mutation]
  );

  const resetLayout = useCallback(async () => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
      debounceTimer.current = null;
    }
    pendingLayouts.current = null;
    queryClient.setQueryData(['dashboard-layout'], responsiveLayouts);
    try {
      await apiClient.delete('/api/v1/user/dashboard-layout/');
    } catch {
      // Silently fail on error
    }
  }, [queryClient]);

  const addWidget = useCallback(
    (widgetId: string) => {
      const widget = widgetRegistryMap.get(widgetId);
      if (!widget) return;

      const lgLayout = [...((currentLayouts.lg as LayoutItem[]) || defaultLayout)];

      if (lgLayout.some((item) => item.i === widgetId)) return;

      const maxY = lgLayout.reduce(
        (max, item) => Math.max(max, item.y + item.h),
        0
      );

      const newItem: LayoutItem = {
        i: widgetId,
        x: 0,
        y: maxY,
        w: widget.defaultW,
        h: widget.defaultH,
        minW: widget.minW,
        minH: widget.minH,
      };

      const newLayouts: ResponsiveLayouts = {
        ...currentLayouts,
        lg: [...lgLayout, newItem],
        md: [
          ...((currentLayouts.md as LayoutItem[]) || []),
          { ...newItem, w: Math.min(newItem.w, 6), x: 0 },
        ],
        sm: [
          ...((currentLayouts.sm as LayoutItem[]) || []),
          { ...newItem, w: 1, x: 0 },
        ],
      };

      saveLayout(newLayouts);
    },
    [currentLayouts, saveLayout]
  );

  const removeWidget = useCallback(
    (widgetId: string) => {
      const filterLayout = (layout: readonly LayoutItem[] | undefined) =>
        ((layout as LayoutItem[]) || []).filter((item) => item.i !== widgetId);

      const newLayouts: ResponsiveLayouts = {
        lg: filterLayout(currentLayouts.lg),
        md: filterLayout(currentLayouts.md),
        sm: filterLayout(currentLayouts.sm),
      };
      saveLayout(newLayouts);
    },
    [currentLayouts, saveLayout]
  );

  return {
    layouts: currentLayouts,
    isLoading,
    saveLayout,
    flushSave,
    resetLayout,
    addWidget,
    removeWidget,
  };
}
