'use client';

import { usePathname, useRouter } from 'next/navigation';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Settings, CreditCard, Users, Slack } from 'lucide-react';

interface SettingsTab {
  value: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
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
  },
];

export function SettingsTabs() {
  const pathname = usePathname();
  const router = useRouter();

  // Determine active tab from pathname
  const getActiveTab = () => {
    const tab = SETTINGS_TABS.find((t) => pathname.startsWith(t.href));
    return tab?.value || 'preferences';
  };

  const handleTabChange = (value: string) => {
    const tab = SETTINGS_TABS.find((t) => t.value === value);
    if (tab) {
      router.push(tab.href);
    }
  };

  return (
    <Tabs value={getActiveTab()} onValueChange={handleTabChange} className="w-full">
      <TabsList className="grid w-full grid-cols-4 h-11">
        {SETTINGS_TABS.map((tab) => {
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
