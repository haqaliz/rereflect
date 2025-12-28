'use client';

import { useTheme } from '@/contexts/ThemeContext';
import { Moon, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Prevent hydration mismatch
  if (!mounted) {
    return (
      <div className="w-[72px] h-10 rounded-xl bg-surface-raised border border-border" />
    );
  }

  const isDark = theme === 'dark';

  return (
    <button
      onClick={toggleTheme}
      className="group relative h-10 w-[72px] rounded-xl overflow-hidden surface-raised border-2 border-border hover:border-accent-amber-500 transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-accent-amber-500 focus:ring-offset-2 focus:ring-offset-background"
      aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
      title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
    >
      {/* Background gradient that slides */}
      <div
        className="absolute inset-0 bg-gradient-to-r from-accent-amber-400 to-accent-amber-600 transition-transform duration-500 ease-out"
        style={{
          transform: isDark ? 'translateX(0%)' : 'translateX(100%)',
        }}
      />

      {/* Toggle slider */}
      <div
        className="absolute top-1 bottom-1 w-8 rounded-lg surface shadow-lg transition-all duration-500 ease-out flex items-center justify-center"
        style={{
          left: isDark ? '4px' : 'calc(100% - 36px)',
        }}
      >
        {/* Icons with crossfade */}
        <div className="relative w-5 h-5">
          <Moon
            className="absolute inset-0 w-5 h-5 text-accent-amber-600 transition-all duration-300"
            style={{
              opacity: isDark ? 1 : 0,
              transform: isDark ? 'rotate(0deg) scale(1)' : 'rotate(-90deg) scale(0.5)',
            }}
            strokeWidth={2.5}
          />
          <Sun
            className="absolute inset-0 w-5 h-5 text-accent-amber-600 transition-all duration-300"
            style={{
              opacity: isDark ? 0 : 1,
              transform: isDark ? 'rotate(90deg) scale(0.5)' : 'rotate(0deg) scale(1)',
            }}
            strokeWidth={2.5}
          />
        </div>
      </div>

      {/* Static background icons for context */}
      <div className="absolute inset-0 flex items-center justify-between px-2 pointer-events-none">
        <Moon
          className="w-4 h-4 transition-colors duration-300"
          style={{
            color: isDark ? 'var(--text-inverse)' : 'var(--text-tertiary)',
          }}
          strokeWidth={2}
        />
        <Sun
          className="w-4 h-4 transition-colors duration-300"
          style={{
            color: isDark ? 'var(--text-tertiary)' : 'var(--text-inverse)',
          }}
          strokeWidth={2}
        />
      </div>

      {/* Glow effect on hover */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
        style={{
          background: 'radial-gradient(circle at center, rgba(245, 158, 11, 0.15) 0%, transparent 70%)',
        }}
      />
    </button>
  );
}
