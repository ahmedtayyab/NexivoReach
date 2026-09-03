/**
 * Industry taxonomy for predictive suggestions.
 * Typing a keyword (e.g. "gym") activates matching packs and surfaces
 * related categories, buyers, and discover queries.
 */

export type IndustryPack = {
  id: string;
  name: string;
  /** Words that activate this pack when the user types them */
  triggers: string[];
  categories: string[];
  buyers: string[];
  markets: string[];
  discoverQueries: string[];
};

export const MARKET_SUGGESTIONS = [
  'United States',
  'United Kingdom',
  'United Arab Emirates',
  'Saudi Arabia',
  'Germany',
  'France',
  'Netherlands',
  'Canada',
  'Australia',
  'India',
  'Pakistan',
  'Qatar',
  'Singapore',
  'Malaysia',
  'Turkey',
  'South Africa',
];

export const INDUSTRY_PACKS: IndustryPack[] = [
  {
    id: 'sportswear',
    name: 'Sportswear & Fitness',
    triggers: ['gym', 'fitness', 'sportswear', 'sport', 'glove', 'hoodie', 'apparel', 'athleisure', 'bodybuilding', 'teamwear'],
    categories: ['Sportswear', 'Fitness & Bodybuilding', 'Gloves', 'Gym Equipment', 'Teamwear', 'Protective Gear', 'Private Label Apparel'],
    buyers: ['Gyms & fitness clubs', 'Sports retailers', 'Fitness brands', 'Team outfitters', 'E-commerce sellers', 'Distributors'],
    markets: ['United Arab Emirates', 'Saudi Arabia', 'United States', 'United Kingdom', 'Germany'],
    discoverQueries: [
      'Find sportswear distributors expanding in the GCC',
      'Find commercial gyms opening new locations that buy branded apparel',
      'Find fitness brands looking for private-label manufacturing partners',
    ],
  },
  {
    id: 'industrial',
    name: 'Industrial & Manufacturing',
    triggers: ['industrial', 'manufacturing', 'valve', 'machinery', 'factory', 'oem', 'parts', 'equipment', 'steel', 'metal'],
    categories: ['Industrial Equipment', 'Machinery Parts', 'OEM Components', 'Safety Equipment', 'Tools', 'Raw Materials'],
    buyers: ['Manufacturers', 'Engineering firms', 'Distributors', 'Procurement teams', 'Plant operators', 'OEMs'],
    markets: ['Germany', 'United States', 'United Kingdom', 'Netherlands', 'India', 'United Arab Emirates'],
    discoverQueries: [
      'Find industrial distributors stocking OEM components in Europe',
      'Find manufacturers expanding production capacity that need machinery parts',
      'Find plant operators seeking safety equipment suppliers',
    ],
  },
  {
    id: 'food',
    name: 'Food & Beverage',
    triggers: ['food', 'beverage', 'restaurant', 'ingredient', 'snack', 'packaging', 'fmcg', 'grocery', 'cafe'],
    categories: ['Food Ingredients', 'Packaged Foods', 'Beverages', 'Food Packaging', 'Private Label Food'],
    buyers: ['Restaurants & cafes', 'Grocery chains', 'Food distributors', 'Hotels', 'Caterers', 'Importers'],
    markets: ['United Arab Emirates', 'Saudi Arabia', 'United Kingdom', 'Singapore', 'Malaysia'],
    discoverQueries: [
      'Find food importers expanding grocery assortments in the GCC',
      'Find restaurant groups opening new locations seeking ingredient suppliers',
      'Find hotel procurement teams looking for beverage partners',
    ],
  },
  {
    id: 'saas',
    name: 'Software & SaaS',
    triggers: ['saas', 'software', 'software', 'b2b', 'platform', 'cloud', 'crm', 'erp', 'api', 'tech'],
    categories: ['SaaS', 'B2B Software', 'Developer Tools', 'Analytics', 'Automation', 'Security Software'],
    buyers: ['Mid-market companies', 'Enterprises', 'Startups', 'IT teams', 'Agencies', 'MSPs'],
    markets: ['United States', 'United Kingdom', 'Germany', 'Canada', 'Australia', 'Singapore'],
    discoverQueries: [
      'Find mid-market companies hiring for ops roles that need workflow automation',
      'Find agencies looking for white-label SaaS tools',
      'Find IT teams evaluating CRM or analytics platforms',
    ],
  },
  {
    id: 'healthcare',
    name: 'Healthcare & Medical',
    triggers: ['health', 'medical', 'hospital', 'clinic', 'pharma', 'dental', 'device', 'lab'],
    categories: ['Medical Devices', 'Consumables', 'Lab Equipment', 'Healthcare Supplies', 'Diagnostics'],
    buyers: ['Hospitals', 'Clinics', 'Labs', 'Distributors', 'Dental practices', 'Pharmacies'],
    markets: ['United Arab Emirates', 'Saudi Arabia', 'Germany', 'United Kingdom', 'United States'],
    discoverQueries: [
      'Find hospital groups expanding facilities that need medical supplies',
      'Find clinic chains looking for diagnostic equipment partners',
      'Find medical distributors stocking consumables in the GCC',
    ],
  },
  {
    id: 'beauty',
    name: 'Beauty & Personal Care',
    triggers: ['beauty', 'cosmetic', 'skincare', 'salon', 'spa', 'personal care', 'fragrance'],
    categories: ['Skincare', 'Cosmetics', 'Personal Care', 'Salon Products', 'Private Label Beauty'],
    buyers: ['Salons & spas', 'Retailers', 'E-commerce brands', 'Distributors', 'Hotels'],
    markets: ['United Arab Emirates', 'United Kingdom', 'United States', 'France', 'Saudi Arabia'],
    discoverQueries: [
      'Find salon chains opening new locations seeking product suppliers',
      'Find beauty retailers expanding private-label lines',
      'Find spa hotels looking for premium skincare partners',
    ],
  },
  {
    id: 'logistics',
    name: 'Logistics & Supply Chain',
    triggers: ['logistics', 'shipping', 'freight', 'warehouse', 'supply chain', '3pl', 'courier'],
    categories: ['Freight', 'Warehousing', '3PL', 'Last-Mile Delivery', 'Supply Chain Software'],
    buyers: ['Importers & exporters', 'E-commerce brands', 'Manufacturers', 'Retailers', 'Distributors'],
    markets: ['United Arab Emirates', 'Singapore', 'Netherlands', 'United States', 'Germany'],
    discoverQueries: [
      'Find e-commerce brands expanding into the GCC needing 3PL partners',
      'Find importers looking for freight and warehousing providers',
      'Find manufacturers outsourcing logistics in Europe',
    ],
  },
  {
    id: 'construction',
    name: 'Construction & Building',
    triggers: ['construction', 'building', 'contractor', 'architect', 'cement', 'tiling', 'hvac', 'interior'],
    categories: ['Building Materials', 'Construction Tools', 'HVAC', 'Interior Finishes', 'Safety Gear'],
    buyers: ['Contractors', 'Developers', 'Architects', 'Distributors', 'Facility managers'],
    markets: ['United Arab Emirates', 'Saudi Arabia', 'Qatar', 'India', 'United Kingdom'],
    discoverQueries: [
      'Find contractors on new commercial projects needing building materials',
      'Find developers fitting out properties seeking interior finish suppliers',
      'Find facility managers looking for HVAC partners',
    ],
  },
];

const GENERIC_CATEGORIES = [
  'Consumer Goods',
  'Private Label',
  'Wholesale',
  'Export Goods',
  'Custom Manufacturing',
];

const GENERIC_BUYERS = [
  'Distributors',
  'Wholesalers',
  'Retailers',
  'E-commerce sellers',
  'Importers',
  'Corporate buyers',
];

export function toggleCsvValue(current: string, value: string): string {
  const items = current.split(',').map(item => item.trim()).filter(Boolean);
  const exists = items.some(item => item.toLowerCase() === value.toLowerCase());
  const next = exists
    ? items.filter(item => item.toLowerCase() !== value.toLowerCase())
    : [...items, value];
  return next.join(', ');
}

export function csvIncludes(current: string, value: string): boolean {
  return current
    .split(',')
    .map(item => item.trim().toLowerCase())
    .includes(value.toLowerCase());
}

/** Last incomplete token the user is currently typing (after the last comma). */
export function activeToken(value: string): string {
  const parts = value.split(',');
  return (parts[parts.length - 1] || '').trim();
}

function packScore(pack: IndustryPack, haystack: string): number {
  const text = haystack.toLowerCase();
  let score = 0;
  for (const trigger of pack.triggers) {
    if (text.includes(trigger.toLowerCase())) score += trigger.length > 4 ? 3 : 2;
  }
  for (const cat of pack.categories) {
    if (text.includes(cat.toLowerCase())) score += 2;
  }
  return score;
}

export function matchIndustryPacks(context: string, catalogCategories: string[] = []): IndustryPack[] {
  const haystack = `${context} ${catalogCategories.join(' ')}`.toLowerCase();
  if (!haystack.trim()) return [];
  return INDUSTRY_PACKS
    .map(pack => ({ pack, score: packScore(pack, haystack) }))
    .filter(row => row.score > 0)
    .sort((a, b) => b.score - a.score)
    .map(row => row.pack);
}

function uniquePreserve(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

export function suggestionsForField(
  field: 'categories' | 'buyers' | 'markets' | 'discover',
  context: string,
  catalogCategories: string[] = [],
): string[] {
  const packs = matchIndustryPacks(context, catalogCategories);
  if (field === 'markets') {
    const fromPacks = packs.flatMap(p => p.markets);
    return uniquePreserve([...fromPacks, ...MARKET_SUGGESTIONS]).slice(0, 16);
  }
  if (field === 'categories') {
    const fromPacks = packs.flatMap(p => p.categories);
    const fromCatalog = catalogCategories.filter(Boolean);
    return uniquePreserve([...fromCatalog, ...fromPacks, ...GENERIC_CATEGORIES]).slice(0, 16);
  }
  if (field === 'buyers') {
    const fromPacks = packs.flatMap(p => p.buyers);
    return uniquePreserve([...fromPacks, ...GENERIC_BUYERS]).slice(0, 16);
  }
  // discover
  const fromPacks = packs.flatMap(p => p.discoverQueries);
  const fallback = [
    'Find distributors expanding in my target markets',
    'Find companies that recently raised funding and match my ICP',
    'Find retailers launching private-label lines in my category',
  ];
  return uniquePreserve([...fromPacks, ...fallback]).slice(0, 8);
}

export function filterMatches(pool: string[], query: string, limit = 8): string[] {
  const q = query.trim().toLowerCase();
  if (!q) return pool.slice(0, limit);
  return pool
    .filter(item => item.toLowerCase().includes(q))
    .slice(0, limit);
}

/** Derive category labels from scraped/saved products for catalog-aware suggestions. */
export function categoriesFromProducts(products: { category?: string; name?: string }[]): string[] {
  const counts = new Map<string, number>();
  for (const p of products) {
    const cat = (p.category || '').trim();
    if (!cat || cat.toLowerCase() === 'uncategorized') continue;
    counts.set(cat, (counts.get(cat) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([cat]) => cat)
    .slice(0, 12);
}
