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

/** Visual wash for outreached / replied / follow-up rows. */
export function leadRowToneClass(prospect: Prospect): string {
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
  return 'lead-row-tone-idle';
}
