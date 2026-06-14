'use client';

import Link from 'next/link';
import { Logo } from '@rereflect/ui';

interface FooterProps {
  onScrollToSection?: (e: React.MouseEvent<HTMLAnchorElement>, targetId: string) => void;
}

export function Footer({ onScrollToSection }: FooterProps) {
  return (
    <footer className="relative z-10 border-t border-border bg-card/50 py-16">
      <div className="max-w-7xl mx-auto px-6">
        {/* Brand section - full width above columns */}
        <div className="mb-12">
          <Link href="/" className="flex items-center gap-3 mb-4 w-fit">
            <Logo size="lg" />
            <span className="text-xl font-bold">
              <span className="text-muted-foreground">Re</span>
              <span className="text-foreground">reflect</span>
            </span>
          </Link>
          <p className="text-muted-foreground max-w-sm mb-6">
            Transform overwhelming customer feedback into clear, actionable insights with AI-powered analysis.
          </p>
        </div>

        {/* 4-column grid */}
        <div className="grid md:grid-cols-4 gap-12 mb-12">
          {/* Product column */}
          <div>
            <h4 className="font-semibold text-foreground mb-4">Product</h4>
            <ul className="space-y-3 text-muted-foreground">
              <li>
                <a
                  href="#features"
                  onClick={onScrollToSection ? (e) => onScrollToSection(e, 'features') : undefined}
                  className="hover:text-foreground transition-colors cursor-pointer"
                >
                  Features
                </a>
              </li>
              <li>
                <a
                  href="#pricing"
                  onClick={onScrollToSection ? (e) => onScrollToSection(e, 'pricing') : undefined}
                  className="hover:text-foreground transition-colors cursor-pointer"
                >
                  Pricing
                </a>
              </li>
              <li>
                <Link href="/integrations" className="hover:text-foreground transition-colors">
                  Integrations
                </Link>
              </li>
              <li>
                <Link href="/customers" className="hover:text-foreground transition-colors">
                  Customers
                </Link>
              </li>
            </ul>
          </div>

          {/* Resources column */}
          <div>
            <h4 className="font-semibold text-foreground mb-4">Resources</h4>
            <ul className="space-y-3 text-muted-foreground">
              <li>
                <Link href="/blog" className="hover:text-foreground transition-colors">
                  Blog
                </Link>
              </li>
            </ul>
          </div>

          {/* Company column */}
          <div>
            <h4 className="font-semibold text-foreground mb-4">Company</h4>
            <ul className="space-y-3 text-muted-foreground">
              <li>
                <Link href="/privacy" className="hover:text-foreground transition-colors">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="hover:text-foreground transition-colors">
                  Terms of Service
                </Link>
              </li>
            </ul>
          </div>

          {/* Connect column */}
          <div>
            <h4 className="font-semibold text-foreground mb-4">Connect</h4>
            <ul className="space-y-3 text-muted-foreground">
              <li>
                <a
                  href="https://twitter.com/rereflectapp"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 hover:text-foreground transition-colors"
                >
                  <span>Follow us on X</span>
                  <svg width="20" height="20" viewBox="0 0 20 20" className='fill-foreground' xmlns="http://www.w3.org/2000/svg">
                      <path d="m15.08,2.1h2.68l-5.89,6.71,6.88,9.1h-5.4l-4.23-5.53-4.84,5.53H1.59l6.24-7.18L1.24,2.1h5.54l3.82,5.05,4.48-5.05Zm-.94,14.23h1.48L6,3.61h-1.6l9.73,12.71h0Z" />
                  </svg>
                </a>
              </li>
              <li>
                <a
                  href="https://www.producthunt.com/products/rereflect?embed=true&utm_source=badge-featured&utm_medium=badge&utm_campaign=badge-rereflect"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    alt="Rereflect - AI-powered customer feedback analysis for SaaS teams | Product Hunt"
                    width="200"
                    height="43"
                    src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1073104&theme=dark&t=1770240628252"
                  />
                </a>
              </li>
              <li>
                <a
                  href="mailto:support@rereflect.com"
                  className="hover:text-foreground transition-colors"
                >
                  support@rereflect.com
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Footer Bottom */}
        <div className="pt-8 border-t border-border flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-muted-foreground">
          <p>© 2026 Rereflect. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
