import type { Prospect } from '../types';

function normalizeStage(stage: string): string {
  const map: Record<string, string> = {
    New: 'To contact',
    Qualified: 'To contact',
    Researched: 'To contact',
  };
  return map[stage] || stage || 'To contact';
}

/** Resolve outreach To: from draft, lead.email, or contacts[]. */
export function recipientEmail(p: Prospect | null | undefined): string {
  if (!p) return '';
  const fromDraft = (p.outreachDraft?.toEmail || '').trim();
  if (fromDraft.includes('@')) return fromDraft;
  const fromLead = (p.email || '').trim();
  if (fromLead.includes('@')) return fromLead;
  for (const c of p.contacts || []) {
    const type = (c.type || '').toLowerCase();
    let val = (c.value || '').trim();
    if (val.toLowerCase().startsWith('mailto:')) {
      val = val.split(':')[1]?.split('?')[0]?.trim() || '';
    }
    if (type && type !== 'email' && type !== 'mail' && type !== 'e-mail') continue;
    if (val.includes('@')) return val;
  }
  return '';
}

function prospectDomain(p: Prospect): string {
  try {
    const raw = (p.website || '').trim();
    if (!raw) return '';
    const host = new URL(raw.startsWith('http') ? raw : `https://${raw}`).hostname.toLowerCase();
    return host.startsWith('www.') ? host.slice(4) : host;
  } catch {
    return (p.website || '').trim().toLowerCase();
  }
}

/** Domains that appear on more than one lead in the given list. */
export function duplicateDomainSet(prospects: Prospect[]): Set<string> {
  const counts = new Map<string, number>();
  for (const p of prospects) {
    const d = prospectDomain(p);
    if (!d) continue;
    counts.set(d, (counts.get(d) || 0) + 1);
  }
  const dupes = new Set<string>();
  for (const [d, n] of counts) {
    if (n > 1) dupes.add(d);
  }
  return dupes;
}

export function isDuplicateLead(
  prospect: Prospect,
  duplicateDomains?: Set<string>,
  latestHuntId?: string,
): boolean {
  if (duplicateDomains?.has(prospectDomain(prospect))) return true;
  if (prospect.fitBreakdown?.rediscovered) {
    const job = (prospect.fitBreakdown.rediscoveredInJobId || '').trim();
    if (!latestHuntId || !job || job === latestHuntId) return true;
  }
  return false;
}

/** Visual wash for outreached / replied / follow-up rows. */
export function leadRowToneClass(
  prospect: Prospect,
  opts?: { duplicateDomains?: Set<string>; latestHuntId?: string },
): string {
  const stage = normalizeStage(prospect.stage);
  const draftStatus = prospect.outreachDraft?.status;

  if (stage === 'Won') return 'lead-row-tone-won';
  if (stage === 'Meeting') return 'lead-row-tone-meeting';
  if (stage === 'Denied' || stage === 'Avoid') return 'lead-row-tone-denied';
  if (stage === 'Replied' || draftStatus === 'Replied' || Boolean(prospect.replySummary)) {
    return 'lead-row-tone-replied';
  }
  if (stage === 'Re-contact') return 'lead-row-tone-recontact';
  if (stage === 'Contacted' || draftStatus === 'Sent') return 'lead-row-tone-sent';
  if (draftStatus === 'Draft' || draftStatus === 'Approved') return 'lead-row-tone-draft';
  if (isDuplicateLead(prospect, opts?.duplicateDomains, opts?.latestHuntId)) {
    return 'lead-row-tone-duplicate';
  }
  return 'lead-row-tone-idle';
}
