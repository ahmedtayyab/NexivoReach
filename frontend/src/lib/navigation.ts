export type AppRoute = 'queue' | 'discover' | 'catalog' | 'company' | 'icp' | 'activity';

export type SettingsSection = 'company' | 'catalog' | 'icp';

export const APP_ROUTES: AppRoute[] = [
  'queue',
  'discover',
  'catalog',
  'company',
  'icp',
  'activity',
];

export const SETTINGS_SECTIONS: SettingsSection[] = ['company', 'catalog', 'icp'];

export function parseRoute(hash: string): AppRoute {
  const route = hash.replace(/^#/, '').trim() as AppRoute;
  return APP_ROUTES.includes(route) ? route : 'queue';
}

export function isSettingsRoute(route: AppRoute): route is SettingsSection {
  return SETTINGS_SECTIONS.includes(route as SettingsSection);
}

export function sidebarTabForRoute(route: AppRoute): string {
  if (route === 'catalog') return 'catalog';
  if (route === 'company' || route === 'icp') return 'settings';
  return route;
}

export function routeFromSidebarTab(tab: string): AppRoute {
  if (tab === 'settings') return 'company';
  if (tab === 'catalog') return 'catalog';
  return tab as AppRoute;
}
