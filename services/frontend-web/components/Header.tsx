'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, MessageSquare, Settings as SettingsIcon, LogOut } from 'lucide-react';
import { authAPI } from '@/lib/api/auth';
import { Logo } from './Logo';

export function Header() {
  const pathname = usePathname();

  const handleLogout = () => {
    authAPI.logout();
  };

  const isActive = (path: string) => pathname === path;

  return (
    <header className="glass sticky top-0 z-40 border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex justify-between items-center">
          <Link href="/dashboard" className="flex items-center space-x-3 group">
            <Logo size="xl" />
            <div>
              <h1 className="text-xl font-bold text-text-primary">Rereflect</h1>
              <p className="text-xs text-text-tertiary font-mono">Analytics Platform</p>
            </div>
          </Link>

          <nav className="flex items-center space-x-2">
            <Link
              href="/dashboard"
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-all ${
                isActive('/dashboard')
                  ? 'bg-accent-amber-50 text-accent-amber-700 hover:bg-accent-amber-100'
                  : 'text-text-secondary hover:bg-surface-raised'
              }`}
            >
              <LayoutDashboard className="w-4 h-4" />
              <span>Dashboard</span>
            </Link>
            <Link
              href="/feedbacks"
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-all ${
                isActive('/feedbacks')
                  ? 'bg-accent-amber-50 text-accent-amber-700 hover:bg-accent-amber-100'
                  : 'text-text-secondary hover:bg-surface-raised'
              }`}
            >
              <MessageSquare className="w-4 h-4" />
              <span>Feedbacks</span>
            </Link>
            <Link
              href="/settings"
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-all ${
                isActive('/settings')
                  ? 'bg-accent-amber-50 text-accent-amber-700 hover:bg-accent-amber-100'
                  : 'text-text-secondary hover:bg-surface-raised'
              }`}
            >
              <SettingsIcon className="w-4 h-4" />
              <span>Settings</span>
            </Link>

            <button
              onClick={handleLogout}
              className="p-2.5 text-text-secondary hover:text-error-text hover:bg-error-bg rounded-lg transition-all"
              title="Logout"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </nav>
        </div>
      </div>
    </header>
  );
}
