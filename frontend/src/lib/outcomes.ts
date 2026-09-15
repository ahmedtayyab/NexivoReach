import type { AuthUser, Prospect } from '../types';
import { recipientEmail } from './leadTone';

const FOLLOW_UP_DAYS = 3;

function normalizeStage(stage: string): string {
  const map: Record<string, string> = {
    New: 'To contact',
    Qualified: 'To contact',
    Researched: 'To contact',
  };
  return map[stage] || stage || 'To contact';
}

function daysSince(iso?: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / (1000 * 60 * 60 * 24);
}

/** Lead needs a follow-up: Re-contact, or sent/contacted with no reply for a few days. */
export function isDueFollowUp(p: Prospect): boolean {
  const stage = normalizeStage(p.stage);
  if (stage === 'Denied' || stage === 'Avoid' || stage === 'Won' || stage === 'Meeting') {
    return false;
  }
  if (stage === 'Re-contact') return true;
  if (p.replySummary || stage === 'Replied' || p.outreachDraft?.status === 'Replied') {
    return p.contactAgain === true;
  }
  const sent = p.outreachDraft?.status === 'Sent' || stage === 'Contacted';
  if (!sent) return false;
  const age = daysSince(p.outreachDraft?.sentAt || p.discoveredAt);
  return age !== null && age >= FOLLOW_UP_DAYS;
}

export function hasEmail(p: Prospect): boolean {
  return recipientEmail(p).includes('@');
}

export type PipelineOutcomes = {
  total: number;
  withEmail: number;
  missingEmail: number;
  toContact: number;
  contacted: number;
  replied: number;
  dueFollowUp: number;
  meeting: number;
  won: number;
  draftsReady: number;
};

export function computeOutcomes(prospects: Prospect[]): PipelineOutcomes {
  const out: PipelineOutcomes = {
    total: prospects.length,
    withEmail: 0,
    missingEmail: 0,
    toContact: 0,
    contacted: 0,
    replied: 0,
    dueFollowUp: 0,
    meeting: 0,
    won: 0,
    draftsReady: 0,
  };
  for (const p of prospects) {
    if (hasEmail(p)) out.withEmail += 1;
    else out.missingEmail += 1;
    const stage = normalizeStage(p.stage);
    if (stage === 'To contact') out.toContact += 1;
    if (stage === 'Contacted' || p.outreachDraft?.status === 'Sent') out.contacted += 1;
    if (stage === 'Replied' || p.outreachDraft?.status === 'Replied' || p.replySummary) {
      out.replied += 1;
    }
    if (isDueFollowUp(p)) out.dueFollowUp += 1;
    if (stage === 'Meeting') out.meeting += 1;
    if (stage === 'Won') out.won += 1;
    const st = p.outreachDraft?.status;
    if ((st === 'Draft' || st === 'Approved') && hasEmail(p)) out.draftsReady += 1;
  }
  return out;
}

export function planLabel(plan?: string | null): string {
  const p = (plan || 'pilot').toLowerCase();
  return p.charAt(0).toUpperCase() + p.slice(1);
}

export type UsageKind = 'hunt' | 'extract' | 'prepare' | 'send';

export function usageKinds(): { id: UsageKind; label: string }[] {
  return [
    { id: 'hunt', label: 'Hunts' },
    { id: 'extract', label: 'Extracts' },
    { id: 'prepare', label: 'Prepares' },
    { id: 'send', label: 'Sends' },
  ];
}

export function usageRemaining(user: AuthUser | null | undefined, kind: UsageKind): number | null {
  if (!user?.usage) return null;
  if (user.usage.bypassed) return null;
  return user.usage.remaining?.[kind] ?? null;
}
