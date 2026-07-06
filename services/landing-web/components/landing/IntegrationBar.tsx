import { SlackIcon } from '@/components/icons/SlackIcon';
import { IntercomIcon } from '@/components/icons/IntercomIcon';
import { EmailIcon } from '@/components/icons/EmailIcon';
import { ZendeskIcon } from '@/components/icons/ZendeskIcon';
import { HubSpotIcon } from '@/components/icons/HubSpotIcon';
import { LinearIcon } from '@/components/icons/LinearIcon';
import { SalesforceIcon } from '@/components/icons/SalesforceIcon';
import { JiraIcon } from '@/components/icons/JiraIcon';
import { AsanaIcon } from '@/components/icons/AsanaIcon';

export function IntegrationBar() {
  return (
    <section className="relative z-10 py-16 border-y border-border bg-card/50">
      <div className="max-w-7xl mx-auto px-6 text-center">
        <h2 className="text-lg font-semibold text-foreground mb-8">
          Connect Your Feedback Sources
        </h2>
        <div className="flex items-center justify-center gap-12 flex-wrap mb-6">
          <span
            aria-label="Slack"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <SlackIcon size={40} />
          </span>
          <span
            aria-label="Intercom"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <IntercomIcon size={40} />
          </span>
          <span
            aria-label="Email"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <EmailIcon size={40} />
          </span>
          <span
            aria-label="Linear"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <LinearIcon size={40} />
          </span>
          <span
            aria-label="Zendesk"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <ZendeskIcon size={40} />
          </span>
          <span
            aria-label="HubSpot"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <HubSpotIcon size={40} />
          </span>
          <span
            aria-label="Salesforce"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <SalesforceIcon size={40} />
          </span>
          <span
            aria-label="Jira"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <JiraIcon size={40} />
          </span>
          <span
            aria-label="Asana"
            className="[&>svg]:grayscale hover:[&>svg]:grayscale-0 transition-all duration-300 cursor-default"
          >
            <AsanaIcon size={40} />
          </span>
        </div>
        <p className="text-muted-foreground text-sm">
          Works with the tools you already use. Connect in under 2 minutes.
        </p>
      </div>
    </section>
  );
}
