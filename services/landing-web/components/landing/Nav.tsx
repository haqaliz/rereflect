'use client';

import Link from 'next/link';
import { Github } from 'lucide-react';
import { Logo } from '@rereflect/ui';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';

export default function Nav() {
  const scrollTo = (id: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    document.querySelector(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <header className="lp-nav">
      <nav className="lp-nav-inner">
        <Link href="/" className="lp-logo">
          <Logo size="md" />
          <span>
            <span className="text-accent">Re</span>reflect
          </span>
        </Link>

        <div className="lp-nav-links">
          <a href="#features" onClick={scrollTo('#features')} className="lp-nav-link">
            Features
          </a>
          <Link href="/integrations" className="lp-nav-link">
            Integrations
          </Link>
          <Link href="/blog" className="lp-nav-link">
            Blog
          </Link>
        </div>

        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="lp-btn lp-btn-ghost"
        >
          <Github className="h-3.5 w-3.5" />
          GitHub
        </a>
      </nav>
    </header>
  );
}
