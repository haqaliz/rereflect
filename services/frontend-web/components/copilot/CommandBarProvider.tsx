'use client';

import { useEffect, useState } from 'react';
import { CommandBar } from './CommandBar';
import { CommandBarContext } from './CommandBarContext';

export function CommandBarProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().includes('MAC');
      const modifier = isMac ? e.metaKey : e.ctrlKey;
      if (modifier && e.key === 'k') {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <CommandBarContext.Provider value={{ open, setOpen }}>
      {children}
      <CommandBar open={open} onClose={() => setOpen(false)} />
    </CommandBarContext.Provider>
  );
}
