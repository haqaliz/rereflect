'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { authAPI } from '@/lib/api/auth';
import { identifyUser, analytics } from '@/lib/analytics';

interface User {
  id: number;
  email: string;
  organization_id: number;
  role: string;
  plan: string;
  is_system_admin: boolean;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Public routes that don't require authentication
const publicRoutes = ['/', '/login', '/login/callback', '/signup', '/privacy', '/terms', '/changelog'];

// Public route prefixes (routes that start with these paths)
const publicRoutePrefixes = ['/invite', '/shared'];

// Auth routes that should redirect to dashboard if already logged in
const authRoutes = ['/login', '/signup'];

// Check if a path is public
const isPublicRoute = (path: string): boolean => {
  if (publicRoutes.includes(path)) return true;
  return publicRoutePrefixes.some(prefix => path.startsWith(prefix));
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const isAuthenticated = !!user;

  // Check authentication status on mount and route changes
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('access_token');

      if (!token) {
        setUser(null);
        setIsLoading(false);

        // Redirect to login if on a protected route
        if (!isPublicRoute(pathname)) {
          router.push('/login');
        }
        return;
      }

      try {
        // Verify token by fetching user data
        const userData = await authAPI.getMe();
        setUser(userData);

        // Identify user in Mixpanel
        identifyUser(String(userData.id), {
          email: userData.email,
          role: userData.role,
          organization_id: userData.organization_id,
        });

        // Redirect to dashboard if on auth routes and already logged in
        if (authRoutes.includes(pathname)) {
          router.push('/dashboard');
        }
      } catch {
        // Token is invalid, clear it
        localStorage.removeItem('access_token');
        setUser(null);

        // Redirect to login if on a protected route
        if (!isPublicRoute(pathname)) {
          router.push('/login');
        }
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, [pathname, router]);

  const login = (token: string) => {
    localStorage.setItem('access_token', token);
    // The useEffect will pick up the token and fetch user data
  };

  const logout = () => {
    analytics.logout(); // Track and reset Mixpanel
    localStorage.removeItem('access_token');
    setUser(null);
    router.push('/login');
  };

  // Show loading screen while checking auth on protected routes
  if (isLoading && !isPublicRoute(pathname)) {
    return (
      <AuthContext.Provider value={{ user, isLoading, isAuthenticated, login, logout }}>
        <div className="min-h-screen bg-background flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
            <p className="text-muted-foreground">Loading...</p>
          </div>
        </div>
      </AuthContext.Provider>
    );
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
