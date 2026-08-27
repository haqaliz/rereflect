'use client';

import dynamic from 'next/dynamic';

const GalaxyScene = dynamic(() => import('./GalaxyScene'), {
  ssr: false,
  loading: () => null,
});

export default function Galaxy() {
  return (
    <div className="absolute inset-0" aria-hidden="true">
      <GalaxyScene />
    </div>
  );
}