import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { Integration } from '@/lib/integrations';

const GITHUB_URL = 'https://github.com/haqaliz/rereflect';

interface IntegrationTileProps {
  integration: Integration;
  icon: React.ReactNode;
  comingSoon?: boolean;
}

export default function IntegrationTile({
  integration,
  icon,
  comingSoon = false,
}: IntegrationTileProps) {
  const inner = (
    <>
      <div className="lp-tile-icon">{icon}</div>
      <h3 className="lp-tile-name">{integration.name}</h3>
      <p className="lp-tile-tagline">{integration.tagline}</p>
      <span className="lp-tile-link">
        {comingSoon ? 'Request on GitHub' : 'Learn more'}
        <ArrowRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-1" />
      </span>
    </>
  );

  if (comingSoon) {
    return (
      <a
        href={GITHUB_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="lp-tile group"
      >
        {inner}
      </a>
    );
  }

  return (
    <Link href={`/integrations/${integration.slug}`} className="lp-tile group">
      {inner}
    </Link>
  );
}