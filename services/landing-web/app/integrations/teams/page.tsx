import type { Metadata } from 'next';
import IntegrationPage from '@/components/landing/IntegrationPage';

export const metadata: Metadata = {
  title: 'Microsoft Teams Integration | Rereflect',
  description:
    'Connect Microsoft Teams to Rereflect and get urgent feedback, health-drop and automation alerts delivered as message cards to the channel your team watches.',
};

export default function TeamsIntegrationPage() {
  return <IntegrationPage slug="teams" />;
}