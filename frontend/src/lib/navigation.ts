export type AppRoute = 'queue' | 'discover' | 'catalog' | 'company' | 'icp' | 'activity' | 'integrations';

export type SettingsSection = 'company' | 'catalog' | 'icp' | 'integrations';

export const APP_ROUTES: AppRoute[] = [
  'queue',
  'discover',
  'catalog',
  'company',
  'icp',
  'integrations',
  'activity',
];

export const SETTINGS_SECTIONS: SettingsSection[] = ['company', 'catalog', 'icp', 'integrations'];

const ROUTE_ALIASES: Record<string, AppRoute> = {
  settings: 'company',
  setting: 'company',
  profile: 'company',
  'company-profile': 'company',
  catalogue: 'catalog',
  'product-catalog': 'catalog',
  signals: 'icp',
  'icp-signals': 'icp',
};

export function normalizeRoute(raw: string | undefined | null): AppRoute {
  if (!raw) return 'queue';
  const key = raw.replace(/^#/, '').trim().toLowerCase();
  if (!key) return 'queue';
  if (ROUTE_ALIASES[key]) return ROUTE_ALIASES[key];
  if (APP_ROUTES.includes(key as AppRoute)) return key as AppRoute;
  return 'queue';
}

export function parseRoute(hash: string): AppRoute {
  return normalizeRoute(hash);
}

export function resolveRouteFromLocation(state: unknown = window.history.state): AppRoute {
  const historyState = (state ?? null) as { route?: string; tab?: string } | null;
  if (historyState?.route) {
    const route = normalizeRoute(historyState.route);
    if (route !== 'queue' || historyState.route.toLowerCase() === 'queue') return route;
  }
  if (historyState?.tab) {
    const route = normalizeRoute(historyState.tab);
    if (route !== 'queue' || historyState.tab.toLowerCase() === 'queue') return route;
  }
  return parseRoute(window.location.hash);
}

export function isSettingsRoute(route: AppRoute): route is SettingsSection {
  return SETTINGS_SECTIONS.includes(route as SettingsSection);
}

export function sidebarTabForRoute(route: AppRoute): string {
  if (route === 'catalog') return 'catalog';
  if (route === 'company' || route === 'icp' || route === 'integrations') return 'settings';
  return route;
}

export function routeFromSidebarTab(tab: string): AppRoute {
  return normalizeRoute(tab);
}
