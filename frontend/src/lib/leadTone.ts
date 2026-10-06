import type { Prospect } from '../types';

function normalizeStage(stage: string): string {
  const map: Record<string, string> = {
    New: 'To contact',
    Qualified: 'To contact',
    Researched: 'To contact',
  };
  return map[stage] || stage || 'To contact';
}

function pushEmail(out: string[], seen: Set<string>, raw?: string) {
  for (const part of (raw || '').split(/[,;\n]+/)) {
    let value = part.trim();
    if (value.toLowerCase().startsWith('mailto:')) {
      value = value.split(':')[1]?.split('?')[0]?.trim() || '';
    }
    if (!value.includes('@')) continue;
    const key = value.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(value);
  }
}

/** Every address for this company: draft To:, lead.email, then contacts[]. */
export function recipientEmails(p: Prospect | null | undefined): string[] {
  if (!p) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  pushEmail(out, seen, p.outreachDraft?.toEmail);
  pushEmail(out, seen, p.email);
  for (const contact of p.contacts || []) {
    const type = (contact.type || '').toLowerCase();
    if (type && type !== 'email' && type !== 'mail' && type !== 'e-mail') continue;
    pushEmail(out, seen, contact.value);
  }
  return out;
}

/** Resolve outreach To: from draft, lead.email, or contacts[]. */
export function recipientEmail(p: Prospect | null | undefined): string {
  return recipientEmails(p).join(', ');
}

/** Visual wash for outreached / replied / follow-up rows. */
export function leadRowToneClass(prospect: Prospect): string {
  const stage = normalizeStage(prospect.stage);
  const draftStatus = prospect.outreachDraft?.status;

  if (stage === 'Manual') return 'lead-row-tone-manual';
  if (stage === 'Won') return 'lead-row-tone-won';
  if (stage === 'Meeting') return 'lead-row-tone-meeting';
  if (stage === 'Denied' || stage === 'Avoid') return 'lead-row-tone-denied';
  if (stage === 'Replied' || draftStatus === 'Replied' || Boolean(prospect.replySummary)) {
    return 'lead-row-tone-replied';
  }
  if (stage === 'Re-contact') return 'lead-row-tone-recontact';
  if (stage === 'Contacted' || draftStatus === 'Sent') return 'lead-row-tone-sent';
  if (draftStatus === 'Draft' || draftStatus === 'Approved') return 'lead-row-tone-draft';
  return 'lead-row-tone-idle';
}
