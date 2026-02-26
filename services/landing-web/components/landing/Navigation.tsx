'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Menu, X } from 'lucide-react';
import { Logo } from '@rereflect/ui';

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? (process.env.NODE_ENV === 'development' ? 'http://localhost:3000' : 'https://app.rereflect.ca');

interface NavigationProps {
  isSticky: boolean;
  onScrollToSection?: (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => void;
}

export function Navigation({ isSticky, onScrollToSection }: NavigationProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const stickyClasses = isSticky
    ? 'fixed top-0 left-0 right-0 w-full border-b border-border/50 shadow-sm transition-all duration-200'
    : 'relative transition-all duration-200';

  const handleMobileNavClick = (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => {
    setMobileMenuOpen(false);
    onScrollToSection?.(e, targetId);
  };

  return (
    <nav
      className={`z-50 px-6 py-5 ${stickyClasses}`}
      style={isSticky ? { backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)', backgroundColor: 'rgba(0, 0, 0, 0.5)' } : undefined}
    >
      <div className="max-w-7xl mx-auto flex justify-between items-center">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="relative">
            <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full scale-150 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <Logo size="lg" className="relative" />
          </div>
          <span className="text-xl font-bold tracking-tight">
            <span className="text-muted-foreground">Re</span>
            <span className="text-foreground">reflect</span>
          </span>
        </Link>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-8">
          <a
            href="#features"
            onClick={onScrollToSection ? (e) => onScrollToSection(e, 'features') : undefined}
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Features
          </a>
          <a
            href="#pricing"
            onClick={onScrollToSection ? (e) => onScrollToSection(e, 'pricing') : undefined}
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Pricing
          </a>
          <Link
            href="/integrations"
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Integrations
          </Link>
          <Link
            href="/blog"
            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Blog
          </Link>
        </div>

        <div className="flex items-center gap-3">
          {/* Sign In - hidden on mobile when menu is closed to save space */}
          <a href={`${APP_URL}/login`} className="hidden sm:block">
            <button className="px-4 py-2.5 text-sm font-medium text-foreground/80 hover:text-foreground transition-colors">
              Sign In
            </button>
          </a>
          <a href={`${APP_URL}/signup`} className="hidden sm:block">
            <button className="group relative px-5 py-2.5 text-sm font-semibold text-primary-foreground rounded-xl overflow-hidden transition-all duration-300 hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02]">
              <div className="absolute inset-0 bg-gradient-to-r from-primary via-chart-5 to-primary bg-[length:200%_100%] animate-[shimmer_3s_ease-in-out_infinite]" />
              <span className="relative flex items-center gap-1.5">
                Get Started
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </span>
            </button>
          </a>

          {/* Mobile menu toggle */}
          <button
            className="md:hidden p-2 min-h-[44px] min-w-[44px] flex items-center justify-center text-foreground"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileMenuOpen && (
        <div
          data-testid="mobile-menu"
          className="md:hidden mt-4 pb-4 border-t border-border/50 pt-4"
        >
          <div className="flex flex-col gap-1">
            <a
              href="#features"
              onClick={(e) => handleMobileNavClick(e, 'features')}
              className="px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-primary/5 rounded-lg transition-colors"
            >
              Features
            </a>
            <a
              href="#pricing"
              onClick={(e) => handleMobileNavClick(e, 'pricing')}
              className="px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-primary/5 rounded-lg transition-colors"
            >
              Pricing
            </a>
            <Link
              href="/integrations"
              className="px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-primary/5 rounded-lg transition-colors"
              onClick={() => setMobileMenuOpen(false)}
            >
              Integrations
            </Link>
            <Link
              href="/blog"
              className="px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-primary/5 rounded-lg transition-colors"
              onClick={() => setMobileMenuOpen(false)}
            >
              Blog
            </Link>
            <div className="mt-6 pt-4 border-t border-border/50 flex flex-col gap-2 px-4">
              <a href={`${APP_URL}/login`}>
                <button className="w-full py-3 text-sm font-medium text-foreground/80 hover:text-foreground transition-colors rounded-lg border border-border">
                  Sign In
                </button>
              </a>
              <a href={`${APP_URL}/signup`}>
                <button className="w-full py-3 text-sm font-semibold text-primary-foreground rounded-lg bg-gradient-to-r from-primary to-chart-5">
                  Get Started
                </button>
              </a>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
