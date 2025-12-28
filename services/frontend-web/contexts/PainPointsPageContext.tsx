'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface PainPointsPageState {
  searchQuery: string;
  currentPage: number;
}

interface PainPointsPageContextType extends PainPointsPageState {
  setSearchQuery: (query: string) => void;
  setCurrentPage: (page: number) => void;
  resetFilters: () => void;
}

const defaultState: PainPointsPageState = {
  searchQuery: '',
  currentPage: 1,
};

const PainPointsPageContext = createContext<PainPointsPageContextType | undefined>(undefined);

const STORAGE_KEY = 'pain_points_page_state';

export function PainPointsPageProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PainPointsPageState>(defaultState);
  const [mounted, setMounted] = useState(false);

  // Load state from localStorage on mount
  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setState(parsed);
      } catch (err) {
        console.error('Failed to parse stored pain points page state:', err);
      }
    }
  }, []);

  // Save state to localStorage whenever it changes
  useEffect(() => {
    if (mounted) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    }
  }, [state, mounted]);

  const setSearchQuery = (query: string) => {
    setState(prev => ({ ...prev, searchQuery: query, currentPage: 1 }));
  };

  const setCurrentPage = (page: number) => {
    setState(prev => ({ ...prev, currentPage: page }));
  };

  const resetFilters = () => {
    setState(defaultState);
  };

  return (
    <PainPointsPageContext.Provider
      value={{
        ...state,
        setSearchQuery,
        setCurrentPage,
        resetFilters,
      }}
    >
      {children}
    </PainPointsPageContext.Provider>
  );
}

export function usePainPointsPage() {
  const context = useContext(PainPointsPageContext);
  if (context === undefined) {
    throw new Error('usePainPointsPage must be used within a PainPointsPageProvider');
  }
  return context;
}
