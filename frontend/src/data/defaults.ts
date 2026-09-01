import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog } from '../types';

export const emptyBusinessInfo: BusinessInfo = {
  name: '',
  website: '',
  description: '',
  targetMarkets: [],
  primaryCategories: [],
};

export const emptyProducts: Product[] = [];

export const emptyICP: IdealCustomerProfile = {
  targetBuyerTypes: [],
  targetCountries: [],
  companySize: 'Any',
  buyingSignals: [
    { id: 'sig-1', name: 'Expansion', description: 'New site, plant, branch, or capacity coming online.', weight: 20 },
    { id: 'sig-2', name: 'Upgrade / replacement', description: 'Replacing equipment, remodeling, or issuing a new spec.', weight: 20 },
    { id: 'sig-3', name: 'Hiring', description: 'Hiring operators, managers, or technical staff that implies growth.', weight: 15 },
    { id: 'sig-4', name: 'Procurement / RFP', description: 'Public tender, supplier change, or active procurement language.', weight: 15 },
  ],
};

export const emptyProspects: Prospect[] = [];
export const emptyAgentLogs: AgentRunLog[] = [];
