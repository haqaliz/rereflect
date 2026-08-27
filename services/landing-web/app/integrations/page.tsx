'use client';

import { useRef } from 'react';
import { SlackIcon } from '@/components/icons/SlackIcon';
import { IntercomIcon } from '@/components/icons/IntercomIcon';
import { EmailIcon } from '@/components/icons/EmailIcon';
import { ZendeskIcon } from '@/components/icons/ZendeskIcon';
import { HubSpotIcon } from '@/components/icons/HubSpotIcon';
import { LinearIcon } from '@/components/icons/LinearIcon';
import { SalesforceIcon } from '@/components/icons/SalesforceIcon';
import { JiraIcon } from '@/components/icons/JiraIcon';
import { AsanaIcon } from '@/components/icons/AsanaIcon';
import { getAvailableIntegrations, getComingSoonIntegrations } from '@/lib/integrations';
import { gsap, useGSAP } from '@/lib/landing/gsap';
import Nav from '@/components/landing/Nav';
import Footer from '@/components/landing/Footer';
import PageHero from '@/components/landing/PageHero';
import IntegrationTile from '@/components/landing/IntegrationTile';
import SubpageCTA from '@/components/landing/SubpageCTA';

export default function IntegrationsPage() {
  const containerRef = useRef<HTMLDivElement>(null);

  const availableIntegrations = getAvailableIntegrations();
  const comingSoonIntegrations = getComingSoonIntegrations();

  const iconMap: Record<string, React.ReactNode> = {
    slack: <SlackIcon size={28} />,
    intercom: <IntercomIcon size={28} />,
    email: <EmailIcon size={28} />,
    linear: <LinearIcon size={28} />,
    zendesk: <ZendeskIcon size={28} />,
    hubspot: <HubSpotIcon size={28} />,
    salesforce: <SalesforceIcon size={28} />,
    jira: <JiraIcon size={28} />,
    asana: <AsanaIcon size={28} />,
  };

  useGSAP(
    () => {
      gsap.fromTo(
        '.lp-tile',
        { y: 40, autoAlpha: 0 },
        {
          y: 0,
          autoAlpha: 1,
          duration: 0.8,
          stagger: 0.08,
          ease: 'power3.out',
          immediateRender: false,
          scrollTrigger: { trigger: '.lp-tile-grid', start: 'top 88%', toggleActions: 'play none none reverse' },
        },
      );
    },
    { scope: containerRef },
  );

  return (
    <div ref={containerRef}>
      <Nav />
      <main>
        <div className="lp-page">
          <PageHero
            eyebrow="Integrations"
            title="Feedback from"
            gradient="every channel"
            sub="Connect Slack, Intercom, email, and more. Rereflect pulls in customer feedback from your existing tools and turns it into actionable insights."
          />

          <div className="lp-section-block">
            <div className="lp-section-head">
              <span className="lp-section-eyebrow">Available now</span>
              <h2 className="lp-section-title font-display">Ready to connect today.</h2>
            </div>
            <div className="lp-tile-grid">
              {availableIntegrations.map((integration) => (
                <IntegrationTile
                  key={integration.slug}
                  integration={integration}
                  icon={iconMap[integration.slug]}
                />
              ))}
            </div>
          </div>

          {comingSoonIntegrations.length > 0 && (
            <div className="lp-section-block">
              <div className="lp-section-head">
                <span className="lp-section-eyebrow">Coming soon</span>
                <h2 className="lp-section-title font-display">More integrations on the way.</h2>
              </div>
              <div className="lp-tile-grid">
                {comingSoonIntegrations.map((integration) => (
                  <IntegrationTile
                    key={integration.slug}
                    integration={integration}
                    icon={iconMap[integration.slug]}
                    comingSoon
                  />
                ))}
              </div>
            </div>
          )}

          <SubpageCTA />
        </div>
      </main>
      <Footer />
    </div>
  );
}