import Link from 'next/link';
import { Logo } from '@rereflect/ui';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';

export default function Footer() {
  return (
    <footer className="lp-footer">
      <div className="lp-footer-grid">
        <div>
          <Link href="/" className="lp-logo">
            <Logo size="md" />
            <span>
              <span className="text-accent">Re</span>reflect
            </span>
          </Link>
          <p className="lp-footer-tag">
            Customer feedback, analyzed. Open source, self-hosted, and yours.
          </p>
          <div className="mt-6">
            <a
              href="https://www.producthunt.com/products/rereflect?embed=true&utm_source=badge-featured&utm_medium=badge&utm_campaign=badge-rereflect"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Rereflect on Product Hunt"
            >
              <img
                alt="Rereflect - AI-powered customer feedback analysis for SaaS teams | Product Hunt"
                width="200"
                height="43"
                src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1073104&theme=dark&t=1770240628252"
              />
            </a>
          </div>
        </div>

        <div className="lp-footer-col">
          <h4>Product</h4>
          <Link href="/#features">Features</Link>
          <Link href="/integrations">Integrations</Link>
          <Link href="/blog">Blog</Link>
        </div>

        <div className="lp-footer-col">
          <h4>Open source</h4>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
          <a href={`${GITHUB_URL}#self-hosting`} target="_blank" rel="noopener noreferrer">
            Self-host guide
          </a>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
        </div>

        <div className="lp-footer-col">
          <h4>Stack</h4>
          <span className="text-[0.8125rem] text-[var(--content-tertiary)]">FastAPI · Celery</span>
          <span className="text-[0.8125rem] text-[var(--content-tertiary)]">PostgreSQL · Redis</span>
          <span className="text-[0.8125rem] text-[var(--content-tertiary)]">Next.js · Tailwind</span>
        </div>
      </div>

      <div className="lp-footer-bottom">
        <span>© {new Date().getFullYear()} Rereflect</span>
        <span>MIT licensed · self-hosted</span>
      </div>
    </footer>
  );
}
