import type { Metadata } from 'next';
import IntegrationPage from '@/components/landing/IntegrationPage';

export const metadata: Metadata = {
  title: 'Slack Integration | Rereflect',
  description:
    'Connect Slack to Rereflect and turn customer feedback from Slack into sentiment, pain points, and feature requests automatically.',
};

export default function SlackIntegrationPage() {
  return <IntegrationPage slug="slack" />;
}
