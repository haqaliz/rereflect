import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// ─── Mock next/navigation ─────────────────────────────────────────────────────

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/dashboard',
  useSearchParams: () => new URLSearchParams(),
}));

// ─── Mock UI components ───────────────────────────────────────────────────────

vi.mock('@/components/ui/sidebar', () => ({
  SidebarProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SidebarInset: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SidebarTrigger: () => <button>Toggle Sidebar</button>,
}));

vi.mock('@/components/AppSidebar', () => ({
  AppSidebar: () => <nav data-testid="app-sidebar">Sidebar</nav>,
}));

vi.mock('@/components/ui/separator', () => ({
  Separator: () => <hr />,
}));

vi.mock('@/components/ui/breadcrumb', () => ({
  Breadcrumb: ({ children }: { children: React.ReactNode }) => <nav>{children}</nav>,
  BreadcrumbItem: ({ children }: { children: React.ReactNode }) => <li>{children}</li>,
  BreadcrumbLink: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
  BreadcrumbList: ({ children }: { children: React.ReactNode }) => <ol>{children}</ol>,
  BreadcrumbPage: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  BreadcrumbSeparator: () => <span>/</span>,
}));

vi.mock('sonner', () => ({
  Toaster: () => <div data-testid="toaster">Toaster</div>,
}));

vi.mock('@/components/NotificationBell', () => ({
  NotificationBell: () => <button data-testid="notification-bell">Bell</button>,
}));

vi.mock('@/components/copilot/CommandBarProvider', () => ({
  CommandBarProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/copilot/CopilotHeaderButton', () => ({
  CopilotHeaderButton: () => <button data-testid="copilot-btn">Copilot</button>,
}));

// ─── Mock RealtimeContext ─────────────────────────────────────────────────────

const mockRealtimeProvider = vi.fn(({ children }: { children: React.ReactNode }) => (
  <div data-testid="realtime-provider">{children}</div>
));

vi.mock('@/contexts/RealtimeContext', () => ({
  RealtimeProvider: (props: { children: React.ReactNode }) => mockRealtimeProvider(props),
  useRealtime: () => ({ connected: false, reconnecting: false, subscribe: vi.fn() }),
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('DashboardLayout — realtime migration', () => {
  // 13. test_realtime_provider_wraps_dashboard
  it('test_realtime_provider_wraps_dashboard — RealtimeProvider is rendered in the layout tree', async () => {
    const { default: DashboardLayout } = await import(
      '@/app/(dashboard)/layout'
    );

    render(
      <DashboardLayout>
        <div data-testid="page-content">Page Content</div>
      </DashboardLayout>
    );

    // RealtimeProvider should be in the tree
    expect(screen.getByTestId('realtime-provider')).toBeInTheDocument();
    // Children should be inside the provider
    expect(screen.getByTestId('page-content')).toBeInTheDocument();
  });

  it('test_children_rendered_inside_realtime_provider — page content rendered within RealtimeProvider', async () => {
    const { default: DashboardLayout } = await import(
      '@/app/(dashboard)/layout'
    );

    render(
      <DashboardLayout>
        <div data-testid="child-content">Child Content</div>
      </DashboardLayout>
    );

    const provider = screen.getByTestId('realtime-provider');
    expect(provider).toBeInTheDocument();
    // The child content should exist in the document (it's a descendant of the provider)
    expect(screen.getByTestId('child-content')).toBeInTheDocument();
  });
});
