import type { Metadata } from 'next';
import IntegrationPage from '@/components/landing/IntegrationPage';

export const metadata: Metadata = {
  title: 'Salesforce Integration | Rereflect',
  description:
    'Connect Salesforce to Rereflect and turn customer feedback from Salesforce into sentiment, pain points, and feature requests automatically.',
};

export default function SalesforceIntegrationPage() {
  return <IntegrationPage slug="salesforce" />;
}
