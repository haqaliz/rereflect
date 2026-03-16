'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  MessageSquare,
  Settings as SettingsIcon,
  LogOut,
  CircleAlert,
  Lightbulb,
  AlertTriangle,
  UserX,
  ChevronUp,
  ChevronRight,
  FileText,
  Bell,
  CreditCard,
  Users,
  Plug,
  Brain,
  TrendingUp,
  Share2,
  KanbanSquare,
  GitBranchPlus,
  Tag,
  Building2,
  Sparkles,
  MessageSquarePlus,
  Webhook,
} from 'lucide-react';
import { authAPI, UserResponse } from '@/lib/api/auth';
import { Logo } from './Logo';

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const workspaceNavItems = [
  {
    title: 'Dashboard',
    href: '/dashboard',
    icon: LayoutDashboard,
  },
  {
    title: 'Feedbacks',
    href: '/feedbacks',
    icon: MessageSquare,
  },
  {
    title: 'AI Copilot',
    href: '/conversations',
    icon: Sparkles,
  },
  {
    title: 'Customers',
    href: '/customers',
    icon: Users,
    proBadge: true,
  },
  {
    title: 'Workflow',
    href: '/workflow',
    icon: KanbanSquare,
  },
  {
    title: 'Shared Links',
    href: '/shared-links',
    icon: Share2,
  },
];

const analysisNavItems = [
  {
    title: 'Analytics',
    href: '/analytics',
    icon: TrendingUp,
  },
  {
    title: 'Pain Points',
    href: '/pain-points',
    icon: AlertTriangle,
  },
  {
    title: 'Feature Requests',
    href: '/feature-requests',
    icon: Lightbulb,
  },
  {
    title: 'Urgent Feedbacks',
    href: '/urgent-feedbacks',
    icon: CircleAlert,
  },
  {
    title: 'Churn Risks',
    href: '/churn-risks',
    icon: UserX,
  },
];

const settingsNavItems = [
  { title: 'Preferences', href: '/settings/preferences', icon: SettingsIcon },
  { title: 'Notifications', href: '/settings/notifications', icon: Bell },
  { title: 'Team', href: '/settings/team', icon: Users },
  { title: 'Integrations', href: '/settings/integrations', icon: Plug, requiredRole: 'admin' as const },
  { title: 'AI', href: '/settings/ai', icon: Brain, requiredRole: 'admin' as const },
  { title: 'Response Templates', href: '/settings/response-templates', icon: MessageSquarePlus, requiredRole: 'admin' as const },
  { title: 'Webhooks', href: '/settings/webhooks', icon: Webhook },
  { title: 'Workflow', href: '/settings/workflow', icon: GitBranchPlus },
  { title: 'Billing', href: '/settings/billing', icon: CreditCard, requiredRole: 'owner' as const },
];

const systemNavItems = [
  { title: 'Changelog', href: '/system/changelog', icon: FileText },
  { title: 'Users', href: '/system/users', icon: Users },
  { title: 'Organizations', href: '/system/organizations', icon: Building2 },
  { title: 'Promo Codes', href: '/system/promo-codes', icon: Tag },
  { title: 'AI Models', href: '/system/ai-models', icon: Brain },
];

const hasRole = (userRole: string | undefined, requiredRole?: 'owner' | 'admin' | 'member'): boolean => {
  if (!requiredRole) return true;
  if (!userRole) return false;
  const hierarchy: Record<string, number> = { owner: 3, admin: 2, member: 1 };
  return (hierarchy[userRole] || 0) >= (hierarchy[requiredRole] || 0);
};

export function AppSidebar() {
  const pathname = usePathname();
  const [user, setUser] = useState<UserResponse | null>(null);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const userData = await authAPI.getMe();
        setUser(userData);
      } catch (err) {
        console.error('Failed to fetch user:', err);
      }
    };
    fetchUser();
  }, []);

  const handleLogout = () => {
    authAPI.logout();
  };

  const isActive = (href: string) => {
    if (href === '/feedbacks') {
      return pathname === href || pathname.startsWith('/feedbacks/') || pathname.startsWith('/feedback-sources');
    }
    if (href === '/customers') {
      return pathname === href || pathname.startsWith('/customers/');
    }
    if (href === '/workflow') {
      return pathname === href;
    }
    if (href === '/categories') {
      return pathname.startsWith('/categories/');
    }
    if (href.startsWith('/settings/')) {
      return pathname.startsWith(href);
    }
    return pathname === href;
  };

  // Auto-expand: section is open if any child route is active
  const isWorkspaceActive = workspaceNavItems.some(item => isActive(item.href)) || isActive('/dashboard');
  const isAnalysisActive = analysisNavItems.some(item => isActive(item.href));
  const isSettingsActive = settingsNavItems.some(item => isActive(item.href));
  const isSystemActive = systemNavItems.some(item => isActive(item.href));

  return (
    <Sidebar>
      <SidebarHeader className="p-4">
        <Link href="/dashboard" className="flex items-center gap-3 group">
          <div className="p-2 bg-primary/10 rounded-xl group-hover:bg-primary/20 transition-colors">
            <Logo size="md" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-sidebar-foreground">Rereflect</h1>
          </div>
        </Link>
      </SidebarHeader>

      <SidebarContent>
        {/* Workspace Section — Collapsible */}
        <Collapsible defaultOpen={isWorkspaceActive}>
          <SidebarGroup className="pb-0">
            <CollapsibleTrigger className="w-full">
              <SidebarGroupLabel className="flex items-center justify-between cursor-pointer hover:text-sidebar-foreground transition-colors">
                <span>Workspace</span>
                <ChevronRight className="w-3.5 h-3.5 transition-transform duration-200 [[data-state=open]>&]:rotate-90" />
              </SidebarGroupLabel>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <SidebarGroupContent>
                <SidebarMenu>
                  {workspaceNavItems.map((item) => (
                    <SidebarMenuItem key={item.title}>
                      <SidebarMenuButton
                        asChild
                        isActive={isActive(item.href)}
                        tooltip={item.title}
                      >
                        <Link href={item.href}>
                          <item.icon className="w-4 h-4" />
                          <span>{item.title}</span>
                          {item.proBadge && user?.plan === 'free' && (
                            <span className="ml-auto text-[10px] font-semibold px-1.5 py-0.5 rounded bg-primary/10 text-primary leading-none">
                              Pro
                            </span>
                          )}
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </CollapsibleContent>
          </SidebarGroup>
        </Collapsible>

        
        {/* Analysis Section — Collapsible */}
        <Collapsible defaultOpen={isAnalysisActive}>
          <SidebarGroup className="py-0">
            <CollapsibleTrigger className="w-full">
              <SidebarGroupLabel className="flex items-center justify-between cursor-pointer hover:text-sidebar-foreground transition-colors">
                <span>Analysis</span>
                <ChevronRight className="w-3.5 h-3.5 transition-transform duration-200 [[data-state=open]>&]:rotate-90" />
              </SidebarGroupLabel>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <SidebarGroupContent>
                <SidebarMenu>
                  {analysisNavItems.map((item) => (
                    <SidebarMenuItem key={item.title}>
                      <SidebarMenuButton
                        asChild
                        isActive={isActive(item.href)}
                        tooltip={item.title}
                      >
                        <Link href={item.href}>
                          <item.icon className="w-4 h-4" />
                          <span>{item.title}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </CollapsibleContent>
          </SidebarGroup>
        </Collapsible>

        
        {/* Settings Section — Collapsible */}
        <Collapsible defaultOpen={isSettingsActive}>
          <SidebarGroup className="py-0">
            <CollapsibleTrigger className="w-full">
              <SidebarGroupLabel className="flex items-center justify-between cursor-pointer hover:text-sidebar-foreground transition-colors">
                <span>Settings</span>
                <ChevronRight className="w-3.5 h-3.5 transition-transform duration-200 [[data-state=open]>&]:rotate-90" />
              </SidebarGroupLabel>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <SidebarGroupContent>
                <SidebarMenu>
                  {settingsNavItems
                    .filter(item => hasRole(user?.role, item.requiredRole))
                    .map((item) => (
                      <SidebarMenuItem key={item.title}>
                        <SidebarMenuButton
                          asChild
                          isActive={isActive(item.href)}
                          tooltip={item.title}
                        >
                          <Link href={item.href}>
                            <item.icon className="w-4 h-4" />
                            <span>{item.title}</span>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </CollapsibleContent>
          </SidebarGroup>
        </Collapsible>

        {/* System Section — Collapsible (System Admins only) */}
        {user?.is_system_admin && (
          <>
                        <Collapsible defaultOpen={isSystemActive}>
              <SidebarGroup className="py-0">
                <CollapsibleTrigger className="w-full">
                  <SidebarGroupLabel className="flex items-center justify-between cursor-pointer hover:text-sidebar-foreground transition-colors">
                    <span>System</span>
                    <ChevronRight className="w-3.5 h-3.5 transition-transform duration-200 [[data-state=open]>&]:rotate-90" />
                  </SidebarGroupLabel>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <SidebarGroupContent>
                    <SidebarMenu>
                      {systemNavItems.map((item) => (
                        <SidebarMenuItem key={item.title}>
                          <SidebarMenuButton
                            asChild
                            isActive={isActive(item.href)}
                            tooltip={item.title}
                          >
                            <Link href={item.href}>
                              <item.icon className="w-4 h-4" />
                              <span>{item.title}</span>
                            </Link>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      ))}
                    </SidebarMenu>
                  </SidebarGroupContent>
                </CollapsibleContent>
              </SidebarGroup>
            </Collapsible>
          </>
        )}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground group/user"
                >
                  <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary text-primary-foreground font-semibold text-sm">
                    {user?.email?.charAt(0).toUpperCase() || 'U'}
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold capitalize">{user?.role || 'User'}</span>
                    <span className="truncate text-xs text-sidebar-foreground/70 group-hover/user:text-sidebar-foreground/90">{user?.email || 'Loading...'}</span>
                  </div>
                  <ChevronUp className="ml-auto" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                side="top"
                align="end"
                sideOffset={4}
              >
                <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
                  <LogOut className="w-4 h-4 mr-2" />
                  <span>Log out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
