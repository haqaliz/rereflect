'use client';

import { createContext, useContext, useState } from 'react';

interface CommandBarContextType {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const CommandBarContext = createContext<CommandBarContextType | null>(null);

export function useCommandBar() {
  const ctx = useContext(CommandBarContext);
  if (!ctx) throw new Error('useCommandBar must be used within CommandBarProvider');
  return ctx;
}

export { CommandBarContext };
