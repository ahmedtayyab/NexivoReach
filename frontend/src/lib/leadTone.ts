import type { Prospect } from '../types';

function normalizeStage(stage: string): string {
  const map: Record<string, string> = {
    New: 'To contact',
    Qualified: 'To contact',
    Researched: 'To contact',
  };
  return map[stage] || stage || 'To contact';
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
