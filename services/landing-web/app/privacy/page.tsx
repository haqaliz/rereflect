import type { Metadata } from 'next';
import LegalPage from '@/components/landing/LegalPage';

export const metadata: Metadata = {
  title: 'Privacy Policy | Rereflect',
  description:
    'Privacy policy for the Rereflect marketing website. Rereflect is self-hosted — your deployment data lives entirely on your infrastructure.',
};

const sections = [
  {
    h2: '1. Introduction',
    paragraphs: [
      'Rereflect is an open-source, self-hosted software project. This Privacy Policy explains what information this marketing website (rereflect.ca) collects, and how we handle it. It does not govern your self-hosted Rereflect deployment — your deployment runs on your infrastructure and you control all data within it.',
    ],
  },
  {
    h2: '2. What This Website Collects',
    paragraphs: [
      'This marketing website may collect basic analytics data (page views, referrers, browser type) to understand how visitors discover Rereflect. We do not sell this data.',
      'This website does not have user accounts, does not collect payment information, and does not store personal data beyond what is submitted via any contact forms.',
    ],
  },
  {
    h2: '3. Your Self-Hosted Deployment',
    paragraphs: [
      'When you self-host Rereflect, all data — including customer feedback, user accounts, and analysis results — resides entirely on your infrastructure. The Rereflect project maintainers have no access to this data. You are the data controller for your deployment and are responsible for:',
    ],
    listItems: [
      'Complying with applicable data protection laws (GDPR, CCPA, etc.)',
      'Securing your server and database',
      'Handling user data export and deletion requests from your users',
      'Any third-party API keys you configure (e.g., LLM providers)',
    ],
  },
  {
    h2: '4. Data Security (This Website)',
    paragraphs: [
      'This marketing website uses HTTPS to encrypt data in transit. Because no personal data or accounts are stored here, the attack surface is minimal. For your self-hosted deployment, security is governed by how you configure and maintain your own server.',
    ],
  },
  {
    h2: '5. Third-Party Services',
    paragraphs: [
      'This website may use third-party services for analytics or hosting (e.g., Vercel). These services have their own privacy policies. Your self-hosted Rereflect instance may optionally integrate with third parties (LLM providers, Slack, etc.) — those are entirely under your control and governed by those providers\u2019 policies.',
    ],
  },
  {
    h2: '6. Cookies',
    paragraphs: [
      'This website may use cookies for basic session or analytics purposes. You can control cookie preferences through your browser settings.',
    ],
  },
  {
    h2: '7. Changes to This Policy',
    paragraphs: [
      'We may update this Privacy Policy from time to time. Changes will be noted in the repository. Continued use of this website after changes constitutes acceptance of the updated policy.',
    ],
  },
  {
    h2: '8. Contact',
    paragraphs: [
      'For privacy questions related to this website, please open an issue on the GitHub repository.',
    ],
  },
];

export default function PrivacyPolicyPage() {
  return <LegalPage title="Privacy Policy" updated="June 14, 2026" sections={sections} />;
}