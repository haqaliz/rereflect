'use client';

import { usePathname, useRouter } from 'next/navigation';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Settings, CreditCard, Users, Slack } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

interface SettingsTab {
  value: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  requiredRole?: 'owner' | 'admin' | 'member'; // minimum role required (owner > admin > member)
}

const SETTINGS_TABS: SettingsTab[] = [
  {
    value: 'preferences',
    label: 'Preferences',
    href: '/settings/preferences',
    icon: Settings,
  },
  {
    value: 'billing',
    label: 'Billing',
    href: '/settings/billing',
    icon: CreditCard,
    requiredRole: 'owner', // Only owner can access billing
  },
  {
    value: 'team',
    label: 'Team',
    href: '/settings/team',
    icon: Users,
  },
  {
    value: 'integrations',
    label: 'Integrations',
    href: '/settings/integrations',
    icon: Slack,
    requiredRole: 'admin', // Admin or owner can access integrations
  },
];

// Check if user has required role
const hasRole = (userRole: string | undefined, requiredRole: 'owner' | 'admin' | 'member' | undefined): boolean => {
  if (!requiredRole) return true; // No role required
  if (!userRole) return false;

  const roleHierarchy = { owner: 3, admin: 2, member: 1 };
  return (roleHierarchy[userRole as keyof typeof roleHierarchy] || 0) >= roleHierarchy[requiredRole];
};

export function SettingsTabs() {
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useAuth();

  // Filter tabs based on user role
  const visibleTabs = SETTINGS_TABS.filter(tab => hasRole(user?.role, tab.requiredRole));

  // Determine active tab from pathname
  const getActiveTab = () => {
    const tab = visibleTabs.find((t) => pathname.startsWith(t.href));
    return tab?.value || 'preferences';
  };

  const handleTabChange = (value: string) => {
    const tab = visibleTabs.find((t) => t.value === value);
    if (tab) {
      router.push(tab.href);
    }
  };

  // Dynamic grid columns based on visible tabs
  const gridColsClass = visibleTabs.length === 2 ? 'grid-cols-2' :
                        visibleTabs.length === 3 ? 'grid-cols-3' : 'grid-cols-4';

  return (
    <Tabs value={getActiveTab()} onValueChange={handleTabChange} className="w-full">
      <TabsList className={`grid w-full ${gridColsClass} h-11`}>
        {visibleTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="flex items-center gap-2 data-[state=active]:bg-background"
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </TabsTrigger>
          );
        })}
      </TabsList>
    </Tabs>
  );
}
