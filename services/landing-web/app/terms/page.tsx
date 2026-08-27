import type { Metadata } from 'next';
import LegalPage from '@/components/landing/LegalPage';

export const metadata: Metadata = {
  title: 'Terms of Service | Rereflect',
  description:
    'Terms of service for Rereflect — MIT-licensed, self-hosted, free forever. No tiers, no seats, no usage caps.',
};

const sections = [
  {
    h2: '1. Acceptance of Terms',
    paragraphs: [
      'By accessing or using Rereflect\u2019s software and associated documentation ("the Software"), you agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use the Software.',
    ],
  },
  {
    h2: '2. Description of Software',
    paragraphs: [
      'Rereflect is an open-source, self-hosted AI-powered customer feedback analysis platform. The Software is provided free of charge under the MIT License. It helps teams analyze sentiment, detect pain points, extract feature requests, and identify churn risk from customer communications, running on infrastructure you control.',
    ],
  },
  {
    h2: '3. MIT License',
    paragraphs: [
      'Rereflect is distributed under the MIT License. You are free to use, copy, modify, merge, publish, distribute, sublicense, and sell copies of the Software, subject to the conditions of the MIT License included in the repository. The MIT License governs your rights to the Software; these Terms of Service supplement it for the purpose of this website and related materials.',
    ],
  },
  {
    h2: '4. Self-Hosted Deployment',
    paragraphs: ['Rereflect is designed to run on infrastructure you own and control. As a self-hosted deployment:'],
    listItems: [
      'You are responsible for securing and maintaining your deployment',
      'You are responsible for protecting your users\u2019 data',
      'You are responsible for complying with applicable data protection laws',
      'No data is transmitted to Rereflect project maintainers from your deployment',
    ],
  },
  {
    h2: '5. Acceptable Use',
    paragraphs: ['You agree not to use the Software to:'],
    listItems: [
      'Violate any applicable laws or regulations',
      'Infringe on intellectual property rights of others',
      'Process illegal or harmful content',
      'Misrepresent the origin or authorship of the Software',
    ],
  },
  {
    h2: '6. Data Ownership',
    paragraphs: [
      'Because Rereflect is self-hosted, all data you process remains entirely within your infrastructure. The Rereflect project maintainers have no access to your data and make no claims over it. You retain full ownership and responsibility for all data you process using the Software.',
    ],
  },
  {
    h2: '7. No Fees or Subscriptions',
    paragraphs: [
      'Rereflect is provided free of charge. There are no subscription tiers, no seat limits, no usage caps, and no payment terms. Third-party costs (such as LLM API usage from providers like OpenAI or Anthropic) are subject to those providers\u2019 own terms and pricing and are your responsibility.',
    ],
  },
  {
    h2: '8. Intellectual Property',
    paragraphs: [
      'The Rereflect source code is MIT licensed. The Rereflect name and branding remain the property of the project maintainers. The MIT License grants you broad rights to modify and distribute the code, but does not grant rights to use the Rereflect name or branding in ways that imply official affiliation without permission.',
    ],
  },
  {
    h2: '9. Disclaimer of Warranties',
    paragraphs: [
      'The Software is provided "as is", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement. The project maintainers make no guarantee of accuracy, completeness, or fitness for any particular use case.',
    ],
  },
  {
    h2: '10. Limitation of Liability',
    paragraphs: [
      'To the maximum extent permitted by law, the Rereflect project maintainers shall not be liable for any indirect, incidental, special, consequential, or punitive damages, including loss of profits, data, or business opportunities arising from use of the Software.',
    ],
  },
  {
    h2: '11. Changes to Terms',
    paragraphs: [
      'We reserve the right to modify these terms at any time. Material changes will be noted in the repository changelog. Continued use of this website after changes constitutes acceptance of the updated terms.',
    ],
  },
  {
    h2: '12. Governing Law',
    paragraphs: [
      'These terms shall be governed by and construed in accordance with applicable laws. Any disputes shall be resolved in a competent court of jurisdiction.',
    ],
  },
  {
    h2: '13. Contact',
    paragraphs: [
      'For questions about these Terms of Service, please open an issue on the GitHub repository.',
    ],
  },
];

export default function TermsOfServicePage() {
  return <LegalPage title="Terms of Service" updated="June 14, 2026" sections={sections} />;
}