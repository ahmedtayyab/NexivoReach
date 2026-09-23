import type { Prospect } from '../../types';

type Chip = { label: string; value: string; tone?: 'good' | 'warn' | 'muted' | 'accent' };

function toneForFit(level?: string): Chip['tone'] {
  const v = (level || '').toLowerCase();
  if (v === 'high' || v === 'strong') return 'good';
  if (v === 'medium' || v === 'moderate') return 'accent';
  if (v === 'low' || v === 'weak' || v === 'none') return 'muted';
  return 'muted';
}

function toneForIntent(level?: string): Chip['tone'] {
  const v = (level || '').toLowerCase();
  if (v === 'high' || v === 'active' || v === 'strong') return 'good';
  if (v === 'medium' || v === 'moderate') return 'accent';
  if (v === 'low' || v === 'none' || !v) return 'muted';
  return 'warn';
}

/** Compact “why this buyer” chips from Fit / Intent / priority / catalog match. */
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
  const icp = prospect.icpFit || bd.icpFit;
  const offer = prospect.offerFit || bd.offerFit;
  const motion = prospect.motionFit || bd.motionFit;
  const intent = prospect.intent || bd.intent;
  const priority = prospect.priority || bd.priority;
  const topProduct = (prospect.productFit || []).find(p => p.fitLevel === 'High')
    || (prospect.productFit || [])[0];
  const enrich = prospect.fitBreakdown?.contactEnrich;

  const chips: Chip[] = [];
  if (icp) chips.push({ label: 'ICP', value: icp, tone: toneForFit(icp) });
  if (offer) chips.push({ label: 'Offer', value: offer, tone: toneForFit(offer) });
  if (motion) chips.push({ label: 'Motion', value: motion, tone: toneForFit(motion) });
  if (intent) chips.push({ label: 'Intent', value: intent, tone: toneForIntent(intent) });
  if (priority) chips.push({ label: 'Priority', value: priority, tone: 'accent' });
  if (topProduct) {
    chips.push({
      label: 'Catalog',
      value: topProduct.productName,
      tone: topProduct.fitLevel === 'High' ? 'good' : 'muted',
    });
  }
  if (enrich?.status) {
    chips.push({
      label: 'Contacts',
      value: enrich.status === 'found' ? (enrich.sources || []).join('+') || 'found' : enrich.status,
      tone: enrich.status === 'found' ? 'good' : enrich.status === 'none' ? 'warn' : 'muted',
    });
  }

  if (!chips.length) return null;

  const shown = compact ? chips.slice(0, 4) : chips;

  return (
    <div className={`lead-rationale-chips ${className}`.trim()} aria-label="Lead rationale">
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
