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
];

export const CATEGORY_SUGGESTIONS = [
  'Fitness & Bodybuilding',
  'Sportswear',
  'Gloves',
  'Sports Goods',
  'Gym Equipment',
  'Private Label Apparel',
  'Protective Gear',
  'Teamwear',
];

export const BUYER_SUGGESTIONS = [
  'Gyms & fitness clubs',
  'Sports retailers',
  'Fitness brands',
  'E-commerce sellers',
  'Distributors',
  'Wholesalers',
  'Team outfitters',
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
