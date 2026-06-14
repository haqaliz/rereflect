'use client';

import Link from 'next/link';
import { Logo } from '@rereflect/ui';
import { ArrowLeft } from 'lucide-react';

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="relative z-50 px-6 py-5 border-b border-border">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <Link href="/" className="flex items-center gap-3 group">
            <Logo size="lg" className="relative" />
            <span className="text-xl font-bold tracking-tight">
              <span className="text-muted-foreground">Re</span>
              <span className="text-foreground">reflect</span>
            </span>
          </Link>
          <Link href="/" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="w-4 h-4" />
            Back to Home
          </Link>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-6 py-16">
        <h1 className="text-4xl font-bold text-foreground mb-4">Privacy Policy</h1>
        <p className="text-muted-foreground mb-12">Last updated: June 14, 2026</p>

        <div className="prose prose-neutral dark:prose-invert max-w-none space-y-8">
          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">1. Introduction</h2>
            <p className="text-muted-foreground leading-relaxed">
              Rereflect is an open-source, self-hosted software project. This Privacy Policy explains what information this marketing website (rereflect.ca) collects, and how we handle it. It does not govern your self-hosted Rereflect deployment — your deployment runs on your infrastructure and you control all data within it.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">2. What This Website Collects</h2>
            <h3 className="text-lg font-medium text-foreground mb-2">Website Analytics</h3>
            <p className="text-muted-foreground leading-relaxed mb-4">
              This marketing website may collect basic analytics data (page views, referrers, browser type) to understand how visitors discover Rereflect. We do not sell this data.
            </p>

            <h3 className="text-lg font-medium text-foreground mb-2 mt-6">No User Accounts Here</h3>
            <p className="text-muted-foreground leading-relaxed">
              This website does not have user accounts, does not collect payment information, and does not store personal data beyond what is submitted via any contact forms.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">3. Your Self-Hosted Deployment</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              When you self-host Rereflect, all data — including customer feedback, user accounts, and analysis results — resides entirely on your infrastructure. The Rereflect project maintainers have no access to this data. You are the data controller for your deployment and are responsible for:
            </p>
            <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
              <li>Complying with applicable data protection laws (GDPR, CCPA, etc.)</li>
              <li>Securing your server and database</li>
              <li>Handling user data export and deletion requests from your users</li>
              <li>Any third-party API keys you configure (e.g., LLM providers)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">4. Data Security (This Website)</h2>
            <p className="text-muted-foreground leading-relaxed">
              This marketing website uses HTTPS to encrypt data in transit. Because no personal data or accounts are stored here, the attack surface is minimal. For your self-hosted deployment, security is governed by how you configure and maintain your own server.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">5. Third-Party Services</h2>
            <p className="text-muted-foreground leading-relaxed">
              This website may use third-party services for analytics or hosting (e.g., Vercel). These services have their own privacy policies. Your self-hosted Rereflect instance may optionally integrate with third parties (LLM providers, Slack, etc.) — those are entirely under your control and governed by those providers&apos; policies.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">6. Cookies</h2>
            <p className="text-muted-foreground leading-relaxed">
              This website may use cookies for basic session or analytics purposes. You can control cookie preferences through your browser settings.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">7. Changes to This Policy</h2>
            <p className="text-muted-foreground leading-relaxed">
              We may update this Privacy Policy from time to time. Changes will be noted in the repository. Continued use of this website after changes constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">8. Contact</h2>
            <p className="text-muted-foreground leading-relaxed">
              For privacy questions related to this website, please open an issue on the{' '}
              <a href="https://github.com/haqaliz/rereflect" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                GitHub repository
              </a>.
            </p>
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-8 mt-16">
        <div className="max-w-4xl mx-auto px-6 text-center text-sm text-muted-foreground">
          <p>2026 Rereflect. MIT licensed — free to use, fork, and self-host.</p>
        </div>
      </footer>
    </div>
  );
}
