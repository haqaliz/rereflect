'use client';

import { useEffect, useState } from 'react';
import { getSamlStatus } from '@/lib/api/saml';

// Renders nothing until the runtime probe confirms SSO is enabled — the
// enabled-state can only be known at runtime (it's admin-configured).
// Mirrors OidcSignInButton exactly except for the status endpoint and the
// sign-in nav target (`/auth/saml/login` — the SP-initiated AuthnRequest
// start route — vs OIDC's `/auth/oidc/start`).
export function SamlSignInButton() {
  const [enabled, setEnabled] = useState(false);
  const [buttonLabel, setButtonLabel] = useState('Sign in with SSO');

  useEffect(() => {
    let cancelled = false;

    getSamlStatus()
      .then((status) => {
        if (cancelled) return;
        setEnabled(status.enabled);
        if (status.button_label) {
          setButtonLabel(status.button_label);
        }
      })
      .catch(() => {
        // Older/absent backend, or the probe failed — fail open to hidden.
        if (!cancelled) setEnabled(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!enabled) {
    return null;
  }

  const handleClick = () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    // Full-page navigation — this is a redirect flow, not an axios fetch.
    window.location.href = `${apiUrl}/api/v1/auth/saml/login`;
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`
        w-full h-12 px-4 rounded-lg
        flex items-center justify-center gap-3
        bg-white dark:bg-zinc-800
        border border-zinc-300 dark:border-zinc-600
        text-zinc-700 dark:text-zinc-200
        font-medium text-sm
        transition-all duration-200
        hover:bg-zinc-50 dark:hover:bg-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-500 cursor-pointer
      `}
    >
      {buttonLabel}
    </button>
  );
}
