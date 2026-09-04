export interface BusinessInfo {
  id?: string;
  name: string;
  website: string;
  description: string;
  targetMarkets: string[];
  primaryCategories: string[];
  extractedByAi?: boolean;
}

export interface Product {
  id: string;
  name: string;
  category: string;
  description: string;
  price?: string;
  moq?: string;
  productUrl?: string;
  imageUrl?: string;
  sourceUrl?: string;
  inStock?: boolean | null;
}

export interface BuyingSignalConfig {
  id: string;
  name: string;
  description: string;
  weight: number;
  isCustom?: boolean;
}

export interface IdealCustomerProfile {
  targetBuyerTypes: string[];
  targetCountries: string[];
  companySize: 'Any' | 'Small' | 'Medium' | 'Enterprise';
  minDealSize?: string;
  shippingMarkets?: string[];
  salesConstraints?: string[];
  buyingSignals: BuyingSignalConfig[];
}

export interface BuyingSignalDetected {
  signal: string;
  whyItMatters: string;
  sourceUrl?: string;
  sourceExcerpt?: string;
}

export interface ProductFitMatch {
  productName: string;
  fitLevel: 'High' | 'Medium' | 'Low';
  reasoning: string;
}

export interface ProspectEvidence {
  claim: 'icp' | 'offer' | 'motion' | 'intent' | string;
  statement: string;
  quote?: string;
  url?: string;
  sourceType?: string;
  sourceQuality?: string;
  confidence?: number;
}

export interface Prospect {
  id: string;
  companyName: string;
  website: string;
  location: string;
  industry: string;
  companySize: string;
  fitScore: number;
  fitBreakdown: {
    industryFit: number; // max 25
    locationFit: number; // max 20
    productMatch: number; // max 20
    buyingSignals: number; // max 20
    companyFit: number; // max 15
    icpFit?: string;
    offerFit?: string;
    motionFit?: string;
    fitSummary?: string;
    intent?: string;
    confidence?: number;
    priority?: string;
    entityType?: string;
    discoveryPool?: string;
    whyNow?: string;
    evidence?: ProspectEvidence[];
  };
  whyThisProspect: string;
  whyNow?: string;
  icpFit?: string;
  offerFit?: string;
  motionFit?: string;
  intent?: string;
  confidence?: number;
  priority?: string;
  entityType?: string;
  discoveryPool?: string;
  evidence?: ProspectEvidence[];
  buyingSignals: BuyingSignalDetected[];
  productFit: ProductFitMatch[];
  recommendedApproach: string;
  source?: string;
  phone?: string;
  email?: string;
  contacts?: {
    type: 'email' | 'phone' | 'url' | string;
    value: string;
    label?: string;
    source?: string;
    role?: string;
  }[];
  contactAgain?: boolean;
  lastReplyAt?: string;
  replySummary?: string;
  outreachDraft?: {
    id: string;
    subject: string;
    body: string;
    personalizedReason: string;
    status: 'Draft' | 'Approved' | 'Sent' | 'Replied';
    createdAt: string;
    toEmail?: string;
    kind?: string;
    gmailMessageId?: string;
    gmailThreadId?: string;
    sentVia?: string;
    sentAt?: string;
  };
  stage:
    | 'To contact'
    | 'Contacted'
    | 'Replied'
    | 'Re-contact'
    | 'Denied'
    | 'Avoid'
    | 'Meeting'
    | 'Won'
    | 'New'
    | 'Researched'
    | 'Qualified';
  discoveredAt: string;
  agentTimeline: {
    time: string;
    action: string;
    details?: string;
  }[];
}

export interface AgentRunLog {
  id: string;
  timestamp: string;
  task: string;
  durationMs: number;
  toolsUsed: string[];
  sourcesCount: number;
  status: 'Completed' | 'In Progress' | 'Failed' | 'CompletedWithNoCandidates';
  decisions: {
    step: number;
    observation: string;
    decision: string;
    toolCalled?: string;
    toolResultSnippet?: string;
  }[];
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  picture?: string;
  gmail?: {
    connected: boolean;
    email?: string;
    connectedAt?: string;
  };
}
