'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface FeedbackPageState {
  searchQuery: string;
  sentimentFilter: string;
  urgentFilter: string;
  currentPage: number;
}

interface FeedbackPageContextType extends FeedbackPageState {
  setSearchQuery: (query: string) => void;
  setSentimentFilter: (filter: string) => void;
  setUrgentFilter: (filter: string) => void;
  setCurrentPage: (page: number) => void;
  resetFilters: () => void;
}

const defaultState: FeedbackPageState = {
  searchQuery: '',
  sentimentFilter: '',
  urgentFilter: '',
  currentPage: 1,
};

const FeedbackPageContext = createContext<FeedbackPageContextType | undefined>(undefined);

const STORAGE_KEY = 'feedback_page_state';

export function FeedbackPageProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FeedbackPageState>(defaultState);
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
        console.error('Failed to parse stored feedback page state:', err);
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

  const setUrgentFilter = (filter: string) => {
    setState(prev => ({ ...prev, urgentFilter: filter, currentPage: 1 }));
  };

  const setCurrentPage = (page: number) => {
    setState(prev => ({ ...prev, currentPage: page }));
  };

  const resetFilters = () => {
    setState(defaultState);
  };

  return (
    <FeedbackPageContext.Provider
      value={{
        ...state,
        setSearchQuery,
        setSentimentFilter,
        setUrgentFilter,
        setCurrentPage,
        resetFilters,
      }}
    >
      {children}
    </FeedbackPageContext.Provider>
  );
}

export function useFeedbackPage() {
  const context = useContext(FeedbackPageContext);
  if (context === undefined) {
    throw new Error('useFeedbackPage must be used within a FeedbackPageProvider');
  }
  return context;
}
