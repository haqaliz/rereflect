import type { Metadata } from 'next';
import IntegrationPage from '@/components/landing/IntegrationPage';

export const metadata: Metadata = {
  title: 'Email Integration | Rereflect',
  description:
    'Connect Email to Rereflect and turn customer feedback from Email into sentiment, pain points, and feature requests automatically.',
};

export default function EmailIntegrationPage() {
  return <IntegrationPage slug="email" />;
}
