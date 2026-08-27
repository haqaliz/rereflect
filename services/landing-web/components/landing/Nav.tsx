'use client';

import Link from 'next/link';
import { Github } from 'lucide-react';
import { Logo } from '@rereflect/ui';
import { lenisStore } from '@/lib/landing/lenis';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';

export default function Nav() {
  const scrollTo = (id: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    if (lenisStore.lenis) {
      lenisStore.lenis.scrollTo(id, { offset: -80 });
    } else {
      document.querySelector(id)?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-white/5 bg-[#070607]/60 backdrop-blur-xl">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="lp-logo">
          <Logo size="md" />
          <span>
            <span className="text-[var(--lp-coral)]">Re</span>reflect
          </span>
        </Link>

        <div className="hidden items-center gap-8 text-[0.9rem] font-medium text-white/70 md:flex">
          <a
            href="#features"
            onClick={scrollTo('#features')}
            className="transition-colors hover:text-white"
          >
            Features
          </a>
          <Link href="/integrations" className="transition-colors hover:text-white">
            Integrations
          </Link>
          <Link href="/blog" className="transition-colors hover:text-white">
            Blog
          </Link>
        </div>

        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="lp-btn lp-btn-ghost !px-4 !py-2 text-[0.85rem]"
        >
          <Github className="h-4 w-4" />
          GitHub
        </a>
      </nav>
    </header>
  );
}