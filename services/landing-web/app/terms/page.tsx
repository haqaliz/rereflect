'use client';

import Link from 'next/link';
import { Logo } from '@rereflect/ui';
import { ArrowLeft } from 'lucide-react';

export default function TermsOfServicePage() {
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
        <h1 className="text-4xl font-bold text-foreground mb-4">Terms of Service</h1>
        <p className="text-muted-foreground mb-12">Last updated: June 14, 2026</p>

        <div className="prose prose-neutral dark:prose-invert max-w-none space-y-8">
          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">1. Acceptance of Terms</h2>
            <p className="text-muted-foreground leading-relaxed">
              By accessing or using Rereflect&apos;s software and associated documentation (&quot;the Software&quot;), you agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use the Software.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">2. Description of Software</h2>
            <p className="text-muted-foreground leading-relaxed">
              Rereflect is an open-source, self-hosted AI-powered customer feedback analysis platform. The Software is provided free of charge under the MIT License. It helps teams analyze sentiment, detect pain points, extract feature requests, and identify churn risk from customer communications, running on infrastructure you control.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">3. MIT License</h2>
            <p className="text-muted-foreground leading-relaxed">
              Rereflect is distributed under the MIT License. You are free to use, copy, modify, merge, publish, distribute, sublicense, and sell copies of the Software, subject to the conditions of the MIT License included in the repository. The MIT License governs your rights to the Software; these Terms of Service supplement it for the purpose of this website and related materials.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">4. Self-Hosted Deployment</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">
              Rereflect is designed to run on infrastructure you own and control. As a self-hosted deployment:
            </p>
            <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
              <li>You are responsible for securing and maintaining your deployment</li>
              <li>You are responsible for protecting your users&apos; data</li>
              <li>You are responsible for complying with applicable data protection laws</li>
              <li>No data is transmitted to Rereflect project maintainers from your deployment</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">5. Acceptable Use</h2>
            <p className="text-muted-foreground leading-relaxed mb-4">You agree not to use the Software to:</p>
            <ul className="list-disc list-inside text-muted-foreground space-y-2 ml-4">
              <li>Violate any applicable laws or regulations</li>
              <li>Infringe on intellectual property rights of others</li>
              <li>Process illegal or harmful content</li>
              <li>Misrepresent the origin or authorship of the Software</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">6. Data Ownership</h2>
            <p className="text-muted-foreground leading-relaxed">
              Because Rereflect is self-hosted, all data you process remains entirely within your infrastructure. The Rereflect project maintainers have no access to your data and make no claims over it. You retain full ownership and responsibility for all data you process using the Software.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">7. No Fees or Subscriptions</h2>
            <p className="text-muted-foreground leading-relaxed">
              Rereflect is provided free of charge. There are no subscription tiers, no seat limits, no usage caps, and no payment terms. Third-party costs (such as LLM API usage from providers like OpenAI or Anthropic) are subject to those providers&apos; own terms and pricing and are your responsibility.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">8. Intellectual Property</h2>
            <p className="text-muted-foreground leading-relaxed">
              The Rereflect source code is MIT licensed. The Rereflect name and branding remain the property of the project maintainers. The MIT License grants you broad rights to modify and distribute the code, but does not grant rights to use the Rereflect name or branding in ways that imply official affiliation without permission.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">9. Disclaimer of Warranties</h2>
            <p className="text-muted-foreground leading-relaxed">
              The Software is provided &quot;as is&quot;, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. The project maintainers make no guarantee of accuracy, completeness, or fitness for any particular use case.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">10. Limitation of Liability</h2>
            <p className="text-muted-foreground leading-relaxed">
              To the maximum extent permitted by law, the Rereflect project maintainers shall not be liable for any indirect, incidental, special, consequential, or punitive damages, including loss of profits, data, or business opportunities arising from use of the Software.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">11. Changes to Terms</h2>
            <p className="text-muted-foreground leading-relaxed">
              We reserve the right to modify these terms at any time. Material changes will be noted in the repository changelog. Continued use of this website after changes constitutes acceptance of the updated terms.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">12. Governing Law</h2>
            <p className="text-muted-foreground leading-relaxed">
              These terms shall be governed by and construed in accordance with applicable laws. Any disputes shall be resolved in a competent court of jurisdiction.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">13. Contact</h2>
            <p className="text-muted-foreground leading-relaxed">
              For questions about these Terms of Service, please open an issue on the{' '}
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
