'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode, useState } from 'react';

export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Data stays fresh for 5 minutes before refetch
            staleTime: 5 * 60 * 1000,
            // Cache garbage collection after 30 minutes
            gcTime: 30 * 60 * 1000,
            // Only retry once on failure
            retry: 1,
            // Refetch on window focus
            refetchOnWindowFocus: true,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
