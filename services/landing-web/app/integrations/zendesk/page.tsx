import type { Metadata } from 'next';
import IntegrationPage from '@/components/landing/IntegrationPage';

export const metadata: Metadata = {
  title: 'Zendesk Integration | Rereflect',
  description:
    'Connect Zendesk to Rereflect and turn customer feedback from Zendesk into sentiment, pain points, and feature requests automatically.',
};

export default function ZendeskIntegrationPage() {
  return <IntegrationPage slug="zendesk" />;
}
