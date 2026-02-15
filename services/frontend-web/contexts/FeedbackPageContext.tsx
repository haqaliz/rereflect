'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';

interface FeedbackPageState {
  searchQuery: string;
  sentimentFilter: string;
  urgentFilter: string;
  churnRiskFilter: string;
  currentPage: number;
}

interface FeedbackPageContextType extends FeedbackPageState {
  setSearchQuery: (query: string) => void;
  setSentimentFilter: (filter: string) => void;
  setUrgentFilter: (filter: string) => void;
  setChurnRiskFilter: (filter: string) => void;
  setCurrentPage: (page: number) => void;
  resetFilters: () => void;
}

const defaultState: FeedbackPageState = {
  searchQuery: '',
  sentimentFilter: '',
  urgentFilter: '',
  churnRiskFilter: '',
  currentPage: 1,
};

const FeedbackPageContext = createContext<FeedbackPageContextType | undefined>(undefined);

const STORAGE_KEY = 'feedback_page_state';

export function FeedbackPageProvider({ children }: { children: ReactNode }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<FeedbackPageState>(defaultState);
  const [mounted, setMounted] = useState(false);
  const [initialLoadDone, setInitialLoadDone] = useState(false);

  // Update URL with current filters
  const updateURL = useCallback((sentimentFilter: string, urgentFilter: string, churnRiskFilter: string) => {
    const params = new URLSearchParams();
    if (sentimentFilter) params.set('sentiment', sentimentFilter);
    if (urgentFilter) params.set('urgent', urgentFilter);
    if (churnRiskFilter) params.set('churn_risk', churnRiskFilter);

    const queryString = params.toString();
    const newUrl = queryString ? `${pathname}?${queryString}` : pathname;

    router.replace(newUrl, { scroll: false });
  }, [pathname, router]);

  // Load state from URL params first, then localStorage on mount
  useEffect(() => {
    if (mounted) return; // Only run once on initial mount

    setMounted(true);

    // Check URL params first (they take priority)
    const sentimentParam = searchParams.get('sentiment');
    const urgentParam = searchParams.get('urgent');
    const churnRiskParam = searchParams.get('churn_risk');

    if (sentimentParam || urgentParam || churnRiskParam) {
      // URL params present - use them and ignore localStorage
      setState({
        ...defaultState,
        sentimentFilter: sentimentParam || '',
        urgentFilter: urgentParam || '',
        churnRiskFilter: churnRiskParam || '',
      });
    } else {
      // No URL params - fall back to localStorage
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          setState(parsed);
          // Sync localStorage state to URL
          if (parsed.sentimentFilter || parsed.urgentFilter || parsed.churnRiskFilter) {
            updateURL(parsed.sentimentFilter || '', parsed.urgentFilter || '', parsed.churnRiskFilter || '');
          }
        } catch (err) {
          console.error('Failed to parse stored feedback page state:', err);
        }
      }
    }
    setInitialLoadDone(true);
  }, [searchParams, mounted, updateURL]);

  // Save state to localStorage whenever it changes
  useEffect(() => {
    if (mounted) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    }
  }, [state, mounted]);

  // Sync filter changes to URL (after initial load)
  useEffect(() => {
    if (initialLoadDone) {
      updateURL(state.sentimentFilter, state.urgentFilter, state.churnRiskFilter);
    }
  }, [state.sentimentFilter, state.urgentFilter, state.churnRiskFilter, initialLoadDone, updateURL]);

  const setSearchQuery = (query: string) => {
    setState(prev => ({ ...prev, searchQuery: query, currentPage: 1 }));
  };

  const setSentimentFilter = (filter: string) => {
    setState(prev => ({ ...prev, sentimentFilter: filter, currentPage: 1 }));
  };

  const setUrgentFilter = (filter: string) => {
    setState(prev => ({ ...prev, urgentFilter: filter, currentPage: 1 }));
  };

  const setChurnRiskFilter = (filter: string) => {
    setState(prev => ({ ...prev, churnRiskFilter: filter, currentPage: 1 }));
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
        setChurnRiskFilter,
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
