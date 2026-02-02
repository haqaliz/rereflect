'use client';

import { SidebarProvider, SidebarInset, SidebarTrigger } from '@/components/ui/sidebar';
import { AppSidebar } from '@/components/AppSidebar';
import { Separator } from '@/components/ui/separator';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { usePathname } from 'next/navigation';
import { TrialBanner } from '@/components/TrialBanner';
import { UsageWarning } from '@/components/UsageWarning';
import { Toaster } from 'sonner';

const pageTitles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/feedbacks': 'Feedbacks',
  '/feedback-sources': 'Feedback Sources',
  '/feedback-sources/new': 'New Feedback Source',
  '/feedback-sources/pending': 'Pending Feedback',
  '/pain-points': 'Pain Points',
  '/feature-requests': 'Feature Requests',
  '/urgent-feedbacks': 'Urgent Feedbacks',
  '/settings': 'Settings',
  '/settings/billing': 'Billing',
  '/settings/integrations': 'Integrations',
  '/settings/team': 'Team',
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  // Get page title from pathname
  const getPageTitle = () => {
    // Check for exact match first
    if (pageTitles[pathname]) {
      return pageTitles[pathname];
    }
    // Check for feedbacks detail page
    if (pathname.startsWith('/feedbacks/')) {
      return 'Feedback Details';
    }
    // Check for feedback source detail page
    if (pathname.match(/^\/feedback-sources\/\d+$/)) {
      return 'Source Details';
    }
    // Check for category page
    if (pathname.startsWith('/categories/')) {
      const category = pathname.split('/').pop() || '';
      return category.charAt(0).toUpperCase() + category.slice(1).replace(/-/g, ' ');
    }
    return 'Page';
  };

  return (
    <SidebarProvider>
      <Toaster position="top-right" richColors />
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 border-b border-border px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4" />
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem className="hidden md:block">
                <BreadcrumbLink href="/dashboard">
                  Rereflect
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator className="hidden md:block" />
              <BreadcrumbItem>
                <BreadcrumbPage>{getPageTitle()}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </header>
        <div className="flex-1 overflow-auto">
          {/* Billing banners */}
          <div className="px-4 pt-4 space-y-2">
            <TrialBanner />
            <UsageWarning />
          </div>
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
