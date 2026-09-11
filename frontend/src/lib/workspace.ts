import type { BusinessInfo, IdealCustomerProfile, Product } from '../types';
import { emptyBusinessInfo, emptyICP } from '../data/defaults';
import type { SettingsSection } from './navigation';

const PLACEHOLDER_NAMES = new Set([
  '',
  'company',
  'my company',
  'new company',
  'untitled',
  'untitled company',
  'business',
]);

export function isPlaceholderCompanyName(name: string | null | undefined): boolean {
  return PLACEHOLDER_NAMES.has((name || '').trim().toLowerCase());
}

export function parseProfileResponse(data: unknown): BusinessInfo {
  if (!data || typeof data !== 'object') return emptyBusinessInfo;
  const payload = data as Record<string, unknown>;
  const profile = (payload.profile ?? payload) as Record<string, unknown>;
  if (!profile || typeof profile !== 'object') return emptyBusinessInfo;
  return {
    ...emptyBusinessInfo,
    id: typeof profile.id === 'string' ? profile.id : undefined,
    name: typeof profile.name === 'string' ? profile.name : '',
    website: typeof profile.website === 'string' ? profile.website : '',
    description: typeof profile.description === 'string' ? profile.description : '',
    targetMarkets: Array.isArray(profile.targetMarkets) ? profile.targetMarkets as string[] : [],
    primaryCategories: Array.isArray(profile.primaryCategories) ? profile.primaryCategories as string[] : [],
    extractedByAi: Boolean(profile.extractedByAi),
  };
}

export function parseIcpResponse(data: unknown): IdealCustomerProfile {
  if (!data || typeof data !== 'object') return emptyICP;
  const payload = data as Record<string, unknown>;
  const icp = (payload.icp ?? payload) as Record<string, unknown>;
  if (!icp || typeof icp !== 'object') return emptyICP;
  const companySize = icp.companySize;
  const validSize =
    companySize === 'Any' || companySize === 'Small' || companySize === 'Medium' || companySize === 'Enterprise'
      ? companySize
      : emptyICP.companySize;
  return {
    ...emptyICP,
    targetBuyerTypes: Array.isArray(icp.targetBuyerTypes) ? icp.targetBuyerTypes as string[] : [],
    targetCountries: Array.isArray(icp.targetCountries) ? icp.targetCountries as string[] : [],
    companySize: validSize,
    minDealSize: typeof icp.minDealSize === 'string' ? icp.minDealSize : undefined,
    shippingMarkets: Array.isArray(icp.shippingMarkets) ? icp.shippingMarkets as string[] : [],
    salesConstraints: Array.isArray(icp.salesConstraints) ? icp.salesConstraints as string[] : [],
    buyingSignals: Array.isArray(icp.buyingSignals) ? icp.buyingSignals as IdealCustomerProfile['buyingSignals'] : emptyICP.buyingSignals,
  };
}

/** Enough company brief for Find buyers (real name or a usable description). */
export function isCompanySetupComplete(business: BusinessInfo): boolean {
  const name = (business.name || '').trim();
  const description = (business.description || '').trim();
  if (name && !isPlaceholderCompanyName(name)) return true;
  return description.length >= 24;
}

/** Catalog tab: at least one product, or categories already set on the company. */
export function isCatalogSetupComplete(products: Product[], business: BusinessInfo): boolean {
  if ((products || []).length > 0) return true;
  return (business.primaryCategories || []).some(c => (c || '').trim());
}

/** Buyers tab: at least one buyer type. */
export function isBuyersSetupComplete(icp: IdealCustomerProfile): boolean {
  return (icp.targetBuyerTypes || []).some(t => (t || '').trim());
}

export type WorkspaceStepStatus = {
  id: SettingsSection;
  label: string;
  complete: boolean;
  optional?: boolean;
};

export function workspaceSetupSteps(
  business: BusinessInfo,
  products: Product[],
  icp: IdealCustomerProfile,
  connectReady = false,
): WorkspaceStepStatus[] {
  return [
    { id: 'company', label: 'Company', complete: isCompanySetupComplete(business) },
    { id: 'integrations', label: 'Connect', complete: connectReady },
    { id: 'catalog', label: 'Catalog', complete: isCatalogSetupComplete(products, business) },
    { id: 'icp', label: 'Buyers', complete: isBuyersSetupComplete(icp) },
  ];
}

export function workspaceSetupProgress(steps: WorkspaceStepStatus[]): {
  done: number;
  total: number;
  percent: number;
  requiredDone: number;
  requiredTotal: number;
} {
  const required = steps.filter(s => !s.optional);
  const done = steps.filter(s => s.complete).length;
  const requiredDone = required.filter(s => s.complete).length;
  const total = steps.length;
  const requiredTotal = required.length || 1;
  return {
    done,
    total,
    percent: Math.round((done / total) * 100),
    requiredDone,
    requiredTotal,
  };
}

/** Next tab after a successful save — stay on Buyers so Find buyers remains visible. */
export function nextWorkspaceSection(from: SettingsSection): SettingsSection | null {
  if (from === 'company') return 'integrations';
  if (from === 'integrations') return 'catalog';
  if (from === 'catalog') return 'icp';
  return null;
}
