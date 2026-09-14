import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { initTheme, resolveTheme, readStoredTheme, setTheme, type Theme } from '../lib/theme';

interface Props {
  className?: string;
  /** Compact icon-only control for the mobile header */
  compact?: boolean;
}

export default function ThemeToggle({ className = '', compact = false }: Props) {
  const [theme, setThemeState] = useState<Theme>(() => resolveTheme(readStoredTheme()));

  useEffect(() => {
    setThemeState(initTheme());
  }, []);

  const isDark = theme === 'dark';

  const flip = () => {
    const next: Theme = isDark ? 'light' : 'dark';
    setTheme(next);
    setThemeState(next);
  };

  if (compact) {
    return (
      <button
        type="button"
        onClick={flip}
        className={`theme-toggle theme-toggle--icon ${className}`}
        aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        title={isDark ? 'Light mode' : 'Dark mode'}
      >
        {isDark ? <Sun className="w-4 h-4" strokeWidth={1.75} /> : <Moon className="w-4 h-4" strokeWidth={1.75} />}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={flip}
      className={`theme-toggle ${className}`}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-pressed={isDark}
    >
      <span className={`theme-toggle__option ${!isDark ? 'is-active' : ''}`}>
        <Sun className="w-3.5 h-3.5" strokeWidth={1.75} />
        Light
      </span>
      <span className={`theme-toggle__option ${isDark ? 'is-active' : ''}`}>
        <Moon className="w-3.5 h-3.5" strokeWidth={1.75} />
        Dark
      </span>
      <span className={`theme-toggle__thumb ${isDark ? 'is-dark' : ''}`} aria-hidden />
    </button>
  );
}
