import type { Metadata } from 'next';
import IntegrationPage from '@/components/landing/IntegrationPage';

export const metadata: Metadata = {
  title: 'HubSpot Integration | Rereflect',
  description:
    'Connect HubSpot to Rereflect and turn customer feedback from HubSpot into sentiment, pain points, and feature requests automatically.',
};

export default function HubSpotIntegrationPage() {
  return <IntegrationPage slug="hubspot" />;
}
