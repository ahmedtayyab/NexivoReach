import type { Prospect } from '../../types';

type Chip = { label: string; value: string; tone?: 'good' | 'warn' | 'muted' | 'accent' };

const ROLE_RE =
  /\b(distributors?|wholesalers?|importers?|retailers?|buyers?|dealers?|gyms?|clinics?|brands?)\b/i;

/** Pull product / buyer / place from a discovery SERP query when stored. */
function parseDiscoveryQuery(query: string): { product: string; buyer: string; place: string } {
  let raw = (query || '').trim().replace(/\s+/g, ' ');
  if (!raw) return { product: '', buyer: '', place: '' };
  raw = raw.replace(/\s+-\S+/g, '').trim();
  let place = '';
  const placeMatch = raw.match(/\bin\s+(.+)$/i);
  if (placeMatch) {
    place = placeMatch[1].trim().replace(/[.,]+$/, '');
    raw = raw.slice(0, placeMatch.index).trim();
  }
  const quoted = raw.match(/^"([^"]+)"\s*(.*)$/);
  if (quoted) {
    return { product: quoted[1].trim(), buyer: (quoted[2] || '').trim(), place };
  }
  // Match trailing place after buyer role (e.g. "straps distributors New York, United States")
  const rolePlace = raw.match(
    /^(.+?)\s+(distributors?|wholesalers?|importers?|retailers?|buyers?|dealers?|gyms?|clinics?|brands?)(?:\s+(?:in\s+)?(.+))?$/i,
  );
  if (rolePlace) {
    if (rolePlace[3] && !place) place = rolePlace[3].trim().replace(/[.,]+$/, '');
    return {
      product: rolePlace[1].trim(),
      buyer: rolePlace[2].trim(),
      place,
    };
  }
  return { product: raw, buyer: '', place };
}

function titleCaseRole(role: string): string {
  const r = (role || '').trim();
  if (!r) return '';
  return r.replace(/\b\w/g, c => c.toUpperCase());
}

/** Drop junk labels like "structure" from wave-2 / catalog fallbacks. */
function looksLikeHuntProduct(value: string): boolean {
  const v = (value || '').trim();
  if (!v) return false;
  const words = v.split(/\s+/).filter(Boolean);
  if (words.length < 2) return false;
  if (ROLE_RE.test(v)) return false;
  const junk = new Set([
    'structure', 'company', 'business', 'website', 'homepage', 'about',
    'priority hunt', 'target location', 'buyer types', 'general',
  ]);
  if (junk.has(v.toLowerCase())) return false;
  if (words.every(w => junk.has(w.toLowerCase()))) return false;
  return true;
}

/** Compact hunt context chips: Product · Buyer type · Location. */
export default function LeadRationaleChips({
  prospect,
  compact = false,
  className = '',
}: {
  prospect: Prospect;
  compact?: boolean;
  className?: string;
}) {
  const bd = prospect.fitBreakdown || ({} as Prospect['fitBreakdown']);
  const parsed = parseDiscoveryQuery(bd.discoveryQuery || '');

  // Prefer hunt fields / discovery query only — never seller catalog productFit names
  // (those caused chips like Product: Structure from the workspace catalog).
  const candidates = [bd.huntProduct, parsed.product, prospect.industry];
  const product = (candidates.find(v => looksLikeHuntProduct(String(v || ''))) || '').trim();

  const buyer = titleCaseRole(
    (bd.huntBuyerType || parsed.buyer || '').trim(),
  );

  const companyLocation = (
    (bd as { businessLocation?: string }).businessLocation ||
    prospect.location ||
    ''
  ).trim();
  const huntPlace = (
    (bd as { requestedLocation?: string }).requestedLocation ||
    parsed.place ||
    ''
  ).trim();

  const chips: Chip[] = [];
  if (product) chips.push({ label: 'Product', value: product, tone: 'accent' });
  if (buyer) chips.push({ label: 'Buyer type', value: buyer, tone: 'good' });
  if (companyLocation) {
    chips.push({ label: 'Location', value: companyLocation, tone: 'muted' });
  } else if (huntPlace) {
    chips.push({ label: 'Hunt target', value: huntPlace, tone: 'muted' });
  } else {
    chips.push({ label: 'Location', value: 'Not confirmed on site', tone: 'muted' });
  }
  // Same company found by other product + buyer searches — keep them on the one lead.
  const seenMatch = new Set([`${product.toLowerCase()}|${buyer.toLowerCase()}`]);
  for (const m of bd.huntMatches || []) {
    const p = (m.product || '').trim();
    const b = titleCaseRole(m.buyer || '');
    if (!looksLikeHuntProduct(p)) continue;
    const key = `${p.toLowerCase()}|${b.toLowerCase()}`;
    if (seenMatch.has(key)) continue;
    seenMatch.add(key);
    chips.push({ label: 'Also matched', value: b ? `${p} · ${b}` : p, tone: 'accent' });
  }

  const shown = compact ? chips.slice(0, 3) : chips;

  return (
    <div className={`lead-rationale-chips ${className}`.trim()} aria-label="Hunt match">
      {shown.map(c => (
        <span
          key={`${c.label}-${c.value}`}
          className={`lead-rationale-chip lead-rationale-chip--${c.tone || 'muted'}`}
          title={`${c.label}: ${c.value}`}
        >
          <span className="lead-rationale-chip__k">{c.label}</span>
          <span className="lead-rationale-chip__v">{c.value}</span>
        </span>
      ))}
    </div>
  );
}
