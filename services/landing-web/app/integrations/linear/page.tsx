import type { Metadata } from 'next';
import IntegrationPage from '@/components/landing/IntegrationPage';

export const metadata: Metadata = {
  title: 'Linear Integration | Rereflect',
  description:
    'Connect Linear to Rereflect and turn customer feedback from Linear into sentiment, pain points, and feature requests automatically.',
};

export default function LinearIntegrationPage() {
  return <IntegrationPage slug="linear" />;
}
