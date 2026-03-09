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
  SidebarSeparator,
} from '@/components/ui/sidebar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const mainNavItems = [
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
  { title: 'Workflow', href: '/settings/workflow', icon: GitBranchPlus },
  { title: 'Billing', href: '/settings/billing', icon: CreditCard, requiredRole: 'owner' as const },
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
        {/* Main Navigation */}
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNavItems.map((item) => (
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
        </SidebarGroup>

        <SidebarSeparator />

        {/* Analysis Section */}
        <SidebarGroup>
          <SidebarGroupLabel>Analysis</SidebarGroupLabel>
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
        </SidebarGroup>

        <SidebarSeparator />

        {/* Settings Section */}
        <SidebarGroup>
          <SidebarGroupLabel>Settings</SidebarGroupLabel>
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
        </SidebarGroup>

        {/* System Section (System Admins only) */}
        {user?.is_system_admin && (
          <>
            <SidebarSeparator />
            <SidebarGroup>
              <SidebarGroupLabel>System</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive('/system/changelog')}
                      tooltip="Changelog"
                    >
                      <Link href="/system/changelog">
                        <FileText className="w-4 h-4" />
                        <span>Changelog</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive('/system/users')}
                      tooltip="Users"
                    >
                      <Link href="/system/users">
                        <Users className="w-4 h-4" />
                        <span>Users</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive('/system/organizations')}
                      tooltip="Organizations"
                    >
                      <Link href="/system/organizations">
                        <Building2 className="w-4 h-4" />
                        <span>Organizations</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive('/system/promo-codes')}
                      tooltip="Promo Codes"
                    >
                      <Link href="/system/promo-codes">
                        <Tag className="w-4 h-4" />
                        <span>Promo Codes</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive('/system/ai-models')}
                      tooltip="AI Models"
                    >
                      <Link href="/system/ai-models">
                        <Brain className="w-4 h-4" />
                        <span>AI Models</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
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
