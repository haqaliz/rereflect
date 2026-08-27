import type { Metadata } from 'next';
import IntegrationPage from '@/components/landing/IntegrationPage';

export const metadata: Metadata = {
  title: 'Intercom Integration | Rereflect',
  description:
    'Connect Intercom to Rereflect and turn customer feedback from Intercom into sentiment, pain points, and feature requests automatically.',
};

export default function IntercomIntegrationPage() {
  return <IntegrationPage slug="intercom" />;
}
