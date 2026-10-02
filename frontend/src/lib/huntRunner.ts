/**
 * Module-level Find buyers runner.
 * Survives Workspace → Leads tab switches (panel unmount) so polls keep going.
 */
import { apiFetch } from './api';
import type { AgentRunLog, Prospect } from '../types';

const STORAGE_KEY = 'nr-active-hunt-v1';

export type HuntTelemetry = {
  searchIntents?: number;
  completedIntents?: number;
  googlePages?: number;
  uniqueDomains?: number;
  websitesInspected?: number;
  emailsFound?: number;
  leadsSaved?: number;
  leadsPerRun?: number;
  perIntentCap?: number;
  alreadyKnown?: number;
  currentQuery?: string;
};

export type HuntProgress = {
  jobId: string;
  status: string;
  phase: string;
  progress: number;
  telemetryHint: string;
  startedAt: number;
  userPrompt: string;
};

export type HuntResult = {
  jobId: string;
  foundCount: number;
  skippedExisting: number;
  prospects: Prospect[];
  agentLog?: AgentRunLog | null;
  error?: string | null;
  userPrompt: string;
};

type HuntListener = {
  onProgress?: (p: HuntProgress) => void;
  onComplete?: (r: HuntResult) => void;
  onError?: (message: string, meta: { jobId?: string; userPrompt: string }) => void;
};

type ActiveHunt = {
  jobId: string;
  userPrompt: string;
  startedAt: number;
  abort: boolean;
};

let active: ActiveHunt | null = null;
let pollPromise: Promise<void> | null = null;
const listeners = new Set<HuntListener>();

function emitProgress(p: HuntProgress) {
  listeners.forEach(l => l.onProgress?.(p));
}

function emitComplete(r: HuntResult) {
  listeners.forEach(l => l.onComplete?.(r));
}

function emitError(message: string, meta: { jobId?: string; userPrompt: string }) {
  listeners.forEach(l => l.onError?.(message, meta));
}

function persist(job: ActiveHunt | null) {
  try {
    if (!job) sessionStorage.removeItem(STORAGE_KEY);
    else
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          jobId: job.jobId,
          userPrompt: job.userPrompt,
          startedAt: job.startedAt,
        }),
      );
  } catch {
    /* ignore */
  }
}

function readPersisted(): Omit<ActiveHunt, 'abort'> | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as { jobId?: string; userPrompt?: string; startedAt?: number };
    if (!data.jobId) return null;
    return {
      jobId: data.jobId,
      userPrompt: data.userPrompt || '',
      startedAt: Number(data.startedAt) || Date.now(),
    };
  } catch {
    return null;
  }
}

function telemetryToHint(t: HuntTelemetry | undefined): string {
  if (!t || typeof t !== 'object') return '';
  const bits = [
    t.leadsSaved != null && t.leadsPerRun != null
      ? `Leads ${t.leadsSaved}/${t.leadsPerRun}`
      : t.leadsSaved != null
        ? `Saved ${t.leadsSaved}`
        : null,
    t.perIntentCap != null ? `~${t.perIntentCap}/line` : null,
    t.searchIntents != null ? `Intents ${t.completedIntents ?? 0}/${t.searchIntents}` : null,
    t.googlePages != null ? `Pages ${t.googlePages}` : null,
    t.emailsFound != null ? `Emails ${t.emailsFound}` : null,
    t.alreadyKnown ? `Known ${t.alreadyKnown}` : null,
  ].filter(Boolean);
  return bits.join(' · ');
}

export function subscribeHunt(listener: HuntListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getActiveHunt(): { jobId: string; userPrompt: string; startedAt: number } | null {
  if (active) {
    return { jobId: active.jobId, userPrompt: active.userPrompt, startedAt: active.startedAt };
  }
  return readPersisted();
}

export function isHuntRunning(): boolean {
  return Boolean(active && pollPromise);
}

type StartPayload = {
  userPrompt: string;
  products: unknown[];
  icp: Record<string, unknown>;
  business: Record<string, unknown>;
};

async function pollUntilDone(job: ActiveHunt): Promise<void> {
  active = job;
  persist(job);
  emitProgress({
    jobId: job.jobId,
    status: 'running',
    phase: 'Hunting buyers…',
    progress: 4,
    telemetryHint: '',
    startedAt: job.startedAt,
    userPrompt: job.userPrompt,
  });

  try {
    let data: {
      status?: string;
      phase?: string;
      progress?: number;
      prospects?: Prospect[];
      foundCount?: number;
      skippedExisting?: number;
      agent_log?: AgentRunLog;
      error?: string;
      telemetry?: HuntTelemetry;
    } = { status: 'running' };

    while (data.status !== 'completed' && data.status !== 'failed') {
      if (job.abort) return;
      await new Promise(r => window.setTimeout(r, 1200));
      if (job.abort) return;
      const poll = await apiFetch(`/api/discovery/jobs/${job.jobId}`);
      if (!poll.ok) {
        const text = await poll.text();
        throw new Error(text || `Could not poll hunt (${poll.status})`);
      }
      data = await poll.json();
      emitProgress({
        jobId: job.jobId,
        status: data.status || 'running',
        phase: data.phase || 'Hunting buyers…',
        progress: typeof data.progress === 'number' ? data.progress : 4,
        telemetryHint: telemetryToHint(data.telemetry),
        startedAt: job.startedAt,
        userPrompt: job.userPrompt,
      });
    }

    if (data.status === 'failed') {
      throw new Error(data.error || 'Discovery failed');
    }

    const prospects = Array.isArray(data.prospects) ? data.prospects : [];
    const foundCount = Number(data.foundCount ?? prospects.length);
    emitComplete({
      jobId: job.jobId,
      foundCount,
      skippedExisting: Number(data.skippedExisting || 0),
      prospects,
      agentLog: data.agent_log || null,
      error: null,
      userPrompt: job.userPrompt,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Discovery failed';
    emitError(message, { jobId: job.jobId, userPrompt: job.userPrompt });
  } finally {
    if (active?.jobId === job.jobId) {
      active = null;
      persist(null);
    }
    pollPromise = null;
  }
}

export async function startHunt(payload: StartPayload): Promise<string> {
  if (isHuntRunning()) {
    throw new Error('A hunt is already running');
  }
  const resp = await apiFetch('/api/discovery/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_prompt: payload.userPrompt,
      products: payload.products,
      icp: payload.icp,
      business: payload.business,
      async_mode: true,
    }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Discovery failed (${resp.status})`);
  }
  const started = await resp.json();
  const jobId = started.jobId as string | undefined;
  if (!jobId) throw new Error('Hunt started but no job id returned');

  const job: ActiveHunt = {
    jobId,
    userPrompt: payload.userPrompt,
    startedAt: Date.now(),
    abort: false,
  };
  pollPromise = pollUntilDone(job);
  return jobId;
}

/** Resume polling a job still marked active in sessionStorage (e.g. after refresh). */
export function resumePersistedHunt(): boolean {
  if (isHuntRunning()) return true;
  const saved = readPersisted();
  if (!saved) return false;
  const job: ActiveHunt = { ...saved, abort: false };
  pollPromise = pollUntilDone(job);
  return true;
}
