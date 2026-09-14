export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'nr-theme';

export function resolveTheme(stored?: string | null): Theme {
  if (stored === 'light' || stored === 'dark') return stored;
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
}

export function readStoredTheme(): Theme | null {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === 'light' || raw === 'dark') return raw;
  } catch {
    // ignore
  }
  return null;
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.setAttribute('data-theme', theme);
  root.style.colorScheme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute('content', theme === 'dark' ? '#1E1E20' : '#F7F7F5');
  }
}

export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // ignore
  }
  applyTheme(theme);
}

export function toggleTheme(): Theme {
  const next: Theme = resolveTheme(readStoredTheme()) === 'dark' ? 'light' : 'dark';
  setTheme(next);
  return next;
}

/** Apply saved or system theme before React paints (also used from index.html). */
export function initTheme(): Theme {
  const theme = resolveTheme(readStoredTheme());
  applyTheme(theme);
  return theme;
}
