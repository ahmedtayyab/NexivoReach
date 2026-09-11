export type AppRoute =
  | 'queue'
  | 'discover'
  | 'outreach'
  | 'catalog'
  | 'company'
  | 'icp'
  | 'activity'
  | 'integrations'
  | 'admin'
  | 'support'
  | 'notifications';

export type SettingsSection = 'company' | 'catalog' | 'icp' | 'integrations';

export const APP_ROUTES: AppRoute[] = [
  'queue',
  'discover',
  'outreach',
  'catalog',
  'company',
  'icp',
  'integrations',
  'activity',
  'admin',
  'support',
  'notifications',
];

export const SETTINGS_SECTIONS: SettingsSection[] = ['company', 'integrations', 'catalog', 'icp'];

const ROUTE_ALIASES: Record<string, AppRoute> = {
  settings: 'company',
  setting: 'company',
  profile: 'company',
  workspace: 'company',
  setup: 'company',
  'company-profile': 'company',
  'settings/integrations': 'integrations',
  'settings/connect': 'integrations',
  connect: 'integrations',
  catalogue: 'catalog',
  'product-catalog': 'catalog',
  signals: 'icp',
  'icp-signals': 'icp',
  // Discover folded into Workspace — deep links land on setup
  discover: 'company',
  hunt: 'company',
  find: 'company',
  help: 'support',
  ticket: 'support',
  tickets: 'support',
  alerts: 'notifications',
};

export function normalizeRoute(raw: string | undefined | null): AppRoute {
  if (!raw) return 'company';
  const key = raw.replace(/^#/, '').trim().toLowerCase();
  if (!key) return 'company';
  // Support nested hashes like settings/integrations
  if (ROUTE_ALIASES[key]) return ROUTE_ALIASES[key];
  const leaf = key.includes('/') ? key.split('/').filter(Boolean).pop() || key : key;
  if (ROUTE_ALIASES[leaf]) return ROUTE_ALIASES[leaf];
  if (APP_ROUTES.includes(key as AppRoute)) return key as AppRoute;
  if (APP_ROUTES.includes(leaf as AppRoute)) return leaf as AppRoute;
  return 'company';
}

export function parseRoute(hash: string): AppRoute {
  return normalizeRoute(hash);
}

export function resolveRouteFromLocation(state: unknown = window.history.state): AppRoute {
  const historyState = (state ?? null) as { route?: string; tab?: string } | null;
  if (historyState?.route) {
    const route = normalizeRoute(historyState.route);
    if (route !== 'company' || historyState.route.toLowerCase() === 'company' || historyState.route.toLowerCase() === 'discover') {
      return route;
    }
  }
  if (historyState?.tab) {
    return normalizeRoute(historyState.tab);
  }
  return parseRoute(window.location.hash);
}

export function isSettingsRoute(route: AppRoute): route is SettingsSection {
  return SETTINGS_SECTIONS.includes(route as SettingsSection);
}

export function sidebarTabForRoute(route: AppRoute): string {
  if (route === 'company' || route === 'catalog' || route === 'icp' || route === 'integrations') {
    return 'settings';
  }
  return route;
}

export function routeFromSidebarTab(tab: string): AppRoute {
  return normalizeRoute(tab);
}
