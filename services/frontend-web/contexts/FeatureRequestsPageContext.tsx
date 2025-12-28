'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface FeatureRequestsPageState {
  searchQuery: string;
  currentPage: number;
}

interface FeatureRequestsPageContextType extends FeatureRequestsPageState {
  setSearchQuery: (query: string) => void;
  setCurrentPage: (page: number) => void;
  resetFilters: () => void;
}

const defaultState: FeatureRequestsPageState = {
  searchQuery: '',
  currentPage: 1,
};

const FeatureRequestsPageContext = createContext<FeatureRequestsPageContextType | undefined>(undefined);

const STORAGE_KEY = 'feature_requests_page_state';

export function FeatureRequestsPageProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FeatureRequestsPageState>(defaultState);
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
        console.error('Failed to parse stored feature requests page state:', err);
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
    <FeatureRequestsPageContext.Provider
      value={{
        ...state,
        setSearchQuery,
        setCurrentPage,
        resetFilters,
      }}
    >
      {children}
    </FeatureRequestsPageContext.Provider>
  );
}

export function useFeatureRequestsPage() {
  const context = useContext(FeatureRequestsPageContext);
  if (context === undefined) {
    throw new Error('useFeatureRequestsPage must be used within a FeatureRequestsPageProvider');
  }
  return context;
}
