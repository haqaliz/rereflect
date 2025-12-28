'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface UrgentFeedbackPageState {
  searchQuery: string;
  sentimentFilter: string;
  currentPage: number;
}

interface UrgentFeedbackPageContextType extends UrgentFeedbackPageState {
  setSearchQuery: (query: string) => void;
  setSentimentFilter: (filter: string) => void;
  setCurrentPage: (page: number) => void;
  resetFilters: () => void;
}

const defaultState: UrgentFeedbackPageState = {
  searchQuery: '',
  sentimentFilter: '',
  currentPage: 1,
};

const UrgentFeedbackPageContext = createContext<UrgentFeedbackPageContextType | undefined>(undefined);

const STORAGE_KEY = 'urgent_feedback_page_state';

export function UrgentFeedbackPageProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<UrgentFeedbackPageState>(defaultState);
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
        console.error('Failed to parse stored urgent feedback page state:', err);
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

  const setSentimentFilter = (filter: string) => {
    setState(prev => ({ ...prev, sentimentFilter: filter, currentPage: 1 }));
  };

  const setCurrentPage = (page: number) => {
    setState(prev => ({ ...prev, currentPage: page }));
  };

  const resetFilters = () => {
    setState(defaultState);
  };

  return (
    <UrgentFeedbackPageContext.Provider
      value={{
        ...state,
        setSearchQuery,
        setSentimentFilter,
        setCurrentPage,
        resetFilters,
      }}
    >
      {children}
    </UrgentFeedbackPageContext.Provider>
  );
}

export function useUrgentFeedbackPage() {
  const context = useContext(UrgentFeedbackPageContext);
  if (context === undefined) {
    throw new Error('useUrgentFeedbackPage must be used within a UrgentFeedbackPageProvider');
  }
  return context;
}
