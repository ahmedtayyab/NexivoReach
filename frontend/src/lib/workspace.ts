import type { BusinessInfo, IdealCustomerProfile } from '../types';
import { emptyBusinessInfo, emptyICP } from '../data/defaults';

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
