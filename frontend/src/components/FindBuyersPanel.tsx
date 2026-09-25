import { useEffect, useMemo, useState } from 'react';
import type { BusinessInfo, IdealCustomerProfile, Prospect, AgentRunLog, Product } from '../types';
import { Check, FileSpreadsheet, Loader2, RotateCcw, Search, X } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { useConfirm } from './ConfirmDialog';
import {
  startHunt,
  subscribeHunt,
  resumePersistedHunt,
  getActiveHunt,
  isHuntRunning,
} from '../lib/huntRunner';
import {
  HUNT_LOCATION_OPTIONS,
} from '../data/huntTaxonomy';
import { isPlaceholderCompanyName } from '../lib/workspace';
import PageAmbient from './brand/PageAmbient';
import HuntCombobox from './FindBuyers/HuntCombobox';

interface Props {
  businessInfo: BusinessInfo;
  icp: IdealCustomerProfile;
  products?: Product[];
  onAddProspects: (prospects: Prospect[]) => void;
  onAddLog: (log: AgentRunLog) => void;
  onComplete?: (foundCount: number) => void;
  onSaveICP?: (icp: IdealCustomerProfile) => void;
  compact?: boolean;
  sheetsConnected?: boolean;
  onGoConnect?: () => void;
}

type RecentHunt = {
  jobId: string;
  status: string;
  userPrompt?: string;
  foundCount?: number;
  createdAt?: string;
  requestPayload?: { user_prompt?: string };
};

const HUNT_PHASE_SECONDS = [0, 8, 18, 35];
const SKIP_SHEETS_PROMPT_KEY = 'nr-hunt-skip-sheets-prompt';
const DEFAULT_DOC_TITLE = 'NexivoReach';

/** Realistic wall-clock ETA from hunt line count and per-run lead cap. */
export function estimateHuntSeconds(
  lineCount: number,
  leadsPerRun = 100,
): { low: number; high: number } {
  const lines = Math.max(1, Math.min(40, Math.floor(lineCount || 1)));
  const leads = Math.max(20, Math.min(200, Math.floor(leadsPerRun || 100)));
  // Scale with both search lines and lead quota (inspect/enrich dominates).
  const low = Math.max(60, Math.round(25 + lines * 4 + leads * 0.9));
  const high = Math.max(low + 45, Math.round(50 + lines * 8 + leads * 1.6));
  return { low, high };
}

export function formatDuration(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m <= 0) return `${r}s`;
  return `${m}:${String(r).padStart(2, '0')}`;
}

export function formatEtaRange(low: number, high: number): string {
  const loM = Math.max(1, Math.round(low / 60));
  const hiM = Math.max(loM, Math.round(high / 60));
  if (loM === hiM) return `~${loM} min`;
  return `~${loM}–${hiM} min`;
}

function notifyHuntFinishedInTab(foundCount: number, failed = false) {
  if (typeof document === 'undefined') return;
  const title = failed
    ? `Hunt failed · ${DEFAULT_DOC_TITLE}`
    : foundCount > 0
      ? `(${foundCount}) Hunt done · ${DEFAULT_DOC_TITLE}`
      : `Hunt finished · ${DEFAULT_DOC_TITLE}`;
  // Always flash the tab title briefly so background tabs light up in the browser bar
  document.title = title;
  const restore = () => {
    if (!document.hidden) {
      document.title = DEFAULT_DOC_TITLE;
      document.removeEventListener('visibilitychange', restore);
      window.removeEventListener('focus', restore);
    }
  };
  document.addEventListener('visibilitychange', restore);
  window.addEventListener('focus', restore);
  // If already focused, clear after a short beat so the flash is noticeable
  if (!document.hidden) {
    window.setTimeout(() => {
      if (!document.hidden) document.title = DEFAULT_DOC_TITLE;
    }, 4000);
  }
}

/** Split a past freeform hunt into category + location when possible. */
export function splitHuntPrompt(prompt: string): { category: string; location: string } {
  const raw = (prompt || '').trim();
  if (!raw) return { category: '', location: '' };
  const m = raw.match(/\s+\b(?:in|near|around|within)\s+(.+)$/i);
  if (m) {
    return {
      category: raw.slice(0, m.index).trim(),
      location: (m[1] || '').trim(),
    };
  }
  return { category: raw, location: '' };
}

export function composeHuntPrompt(
  category: string,
  location: string,
  details = '',
): string {
  const cat = (category || '').trim();
  const loc = (location || '').trim();
  const detail = (details || '').trim();
  // The description is the search. Product + buyer type pairs are parsed from it.
  if (detail) {
    const headerParts: string[] = [];
    if (loc) headerParts.push(`Target location: ${loc}`);
    if (cat) headerParts.push(`Context: ${cat}`);
    const header = headerParts.join('\n').trim();
    if (!header) return detail;
    return [header, '', 'Priority hunt lines:', detail].join('\n');
  }
  const headerParts: string[] = [];
  if (cat && loc) {
    if (/\b(?:in|near|around|within)\s+/i.test(cat)) headerParts.push(cat);
    else headerParts.push(`${cat} in ${loc}`);
  } else if (cat) {
    headerParts.push(cat);
  } else if (loc) {
    headerParts.push(`buyers in ${loc}`);
  }
  return headerParts.join(' ').trim();
}

/** Short labels for recent-hunt list — avoid dumping the full multi-line prompt. */
export function summarizeHuntPrompt(prompt: string): { title: string; detail: string } {
  const raw = (prompt || '').trim();
  if (!raw || raw === '(brief-only hunt)') {
    return { title: 'Brief-only hunt', detail: '' };
  }
  const locMatch = raw.match(/Target location:\s*(.+)/i);
  const loc = (locMatch?.[1] || '').split(/\r?\n/)[0]?.trim() || '';
  const marker = 'Priority hunt lines';
  const markerIdx = raw.indexOf(marker);
  let lines: string[] = [];
  if (markerIdx >= 0) {
    lines = raw
      .slice(markerIdx + marker.length)
      .split(/\r?\n/)
      .map(s => s.replace(/^[:\s]+/, '').trim())
      .filter(Boolean);
  } else {
    lines = raw.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  }
  if (loc && lines.length) {
    const preview =
      lines.length <= 2
        ? lines.join(' · ')
        : `${lines.slice(0, 2).join(' · ')} · +${lines.length - 2} more`;
    return { title: loc, detail: `${lines.length} lines · ${preview}` };
  }
  if (loc) return { title: loc, detail: '' };
  if (lines.length === 1) return { title: lines[0], detail: '' };
  if (lines.length > 1) {
    return {
      title: lines[0],
      detail: `${lines.length} lines · ${lines.slice(1, 3).join(' · ')}${
        lines.length > 3 ? ` · +${lines.length - 3} more` : ''
      }`,
    };
  }
  const flat = raw.replace(/\s+/g, ' ').trim();
  return {
    title: flat.length > 72 ? `${flat.slice(0, 69)}…` : flat,
    detail: '',
  };
}

function buildPhases(query: string, placeHint: string): string[] {
  const focus = (query || '').trim() || 'matching buyers';
  const short = focus.length > 48 ? `${focus.slice(0, 48)}…` : focus;
  const place = placeHint ? ` in ${placeHint}` : '';
  return [
    `Planning searches for “${short}”…`,
    `Searching Google${place}…`,
    'Filtering & combining results…',
    'Building your shortlist…',
  ];
}

function loadSkipSheetsPrompt(): boolean {
  try {
    return sessionStorage.getItem(SKIP_SHEETS_PROMPT_KEY) === '1';
  } catch {
    return false;
  }
}

/**
 * Primary hunt: location + multi-line description (product × buyer).
 */
export default function FindBuyersPanel({
  businessInfo,
  icp,
  products = [],
  onAddProspects: _onAddProspects,
  onAddLog: _onAddLog,
  onComplete: _onComplete,
  compact = false,
  sheetsConnected = false,
  onGoConnect,
}: Props) {
  const [location, setLocation] = useState('');
  const [details, setDetails] = useState('');
  const [openField, setOpenField] = useState<'location' | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [lastFound, setLastFound] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [showSheetsPrompt, setShowSheetsPrompt] = useState(false);
  const [skipSheetsPrompt, setSkipSheetsPrompt] = useState(() => loadSkipSheetsPrompt());
  const [serverPhase, setServerPhase] = useState('');
  const [serverProgress, setServerProgress] = useState(0);
  const [telemetryHint, setTelemetryHint] = useState('');
  const [recentHunts, setRecentHunts] = useState<RecentHunt[]>([]);
  const [leadsPerRun, setLeadsPerRun] = useState(100);
  const [resettingMemory, setResettingMemory] = useState(false);
  const confirm = useConfirm();

  const query = useMemo(
    () => composeHuntPrompt('', location, details),
    [location, details],
  );

  const lineCount = useMemo(
    () =>
      details
        .split(/\r?\n/)
        .map(l => l.trim())
        .filter(Boolean).length,
    [details],
  );

  const loadRecentHunts = async () => {
    try {
      const resp = await apiFetch('/api/discovery/jobs?limit=8');
      if (!resp.ok) return;
      const rows = (await resp.json()) as RecentHunt[];
      setRecentHunts(Array.isArray(rows) ? rows : []);
    } catch {
      /* ignore */
    }
  };

  const loadHuntLimits = async () => {
    try {
      const resp = await apiFetch('/api/discovery/limits');
      if (!resp.ok) return;
      const data = await resp.json();
      const n = Number(data?.leadsPerRun);
      if (Number.isFinite(n) && n >= 5) setLeadsPerRun(n);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    void loadRecentHunts();
    void loadHuntLimits();
    resumePersistedHunt();
  }, []);

  useEffect(() => {
    const unsub = subscribeHunt({
      onProgress: p => {
        setIsRunning(true);
        setServerPhase(p.phase);
        setStatusText(p.phase);
        setServerProgress(p.progress);
        if (p.telemetryHint) setTelemetryHint(p.telemetryHint);
        const started = p.startedAt || Date.now();
        setElapsedSec(Math.max(0, Math.floor((Date.now() - started) / 1000)));
      },
      onComplete: r => {
        setIsRunning(false);
        setServerProgress(0);
        setServerPhase('');
        setTelemetryHint('');
        setLastFound(r.foundCount);
        const sheetsNote = sheetsConnected ? ' Synced to Sheets.' : '';
        setStatusText(
          r.foundCount
            ? `Added ${r.foundCount} lead${r.foundCount === 1 ? '' : 's'}${
                r.skippedExisting ? ` (${r.skippedExisting} already researched)` : ''
              } — open Latest hunt on Leads to review new accounts.${sheetsNote}`
            : r.skippedExisting
              ? `All matches were already researched (${r.skippedExisting}). Use Start over to rediscover them, or try a different hunt.`
              : 'No accounts this round — try more specific hunt lines or another location.',
        );
        notifyHuntFinishedInTab(r.foundCount);
        void loadRecentHunts();
        // Prospects / navigation are handled by the App-level huntRunner subscriber
        // so switching tabs mid-hunt still saves leads.
      },
      onError: message => {
        setIsRunning(false);
        setServerProgress(0);
        setServerPhase('');
        setTelemetryHint('');
        setStatusText(message);
        notifyHuntFinishedInTab(0, true);
      },
    });
    // Sync UI if a hunt is already in flight (navigated back mid-run)
    const current = getActiveHunt();
    if (current || isHuntRunning()) {
      setIsRunning(true);
      if (current) {
        setElapsedSec(Math.max(0, Math.floor((Date.now() - current.startedAt) / 1000)));
        if (current.userPrompt) applyPrompt(current.userPrompt);
      }
    }
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheetsConnected]);

  useEffect(() => {
    if (!isRunning) return;
    const active = getActiveHunt();
    const startedAt = active?.startedAt;
    setElapsedSec(
      startedAt ? Math.max(0, Math.floor((Date.now() - startedAt) / 1000)) : 0,
    );
    setPhaseIndex(0);
    const tick = window.setInterval(() => {
      const cur = getActiveHunt();
      if (cur?.startedAt) {
        setElapsedSec(Math.max(0, Math.floor((Date.now() - cur.startedAt) / 1000)));
      } else {
        setElapsedSec(s => s + 1);
      }
    }, 1000);
    return () => window.clearInterval(tick);
  }, [isRunning]);

  // Prefill location from ICP / markets when empty
  useEffect(() => {
    if (location.trim()) return;
    const fromIcp = (icp.targetCountries || []).filter(Boolean)[0];
    const fromBiz = (businessInfo.targetMarkets || []).filter(Boolean)[0];
    const hint = fromIcp || fromBiz || '';
    if (hint) setLocation(hint);
    // only on mount / company change — intentional
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessInfo.id]);

  const placeHint = location.trim() || (icp.targetCountries || [])[0] || '';

  const hasBrief =
    Boolean(businessInfo.description?.trim()) ||
    (Boolean(businessInfo.name?.trim()) && !isPlaceholderCompanyName(businessInfo.name)) ||
    products.length > 0 ||
    (icp.targetBuyerTypes || []).length > 0;

  // Hunt description is required for accurate product×buyer searches.
  const ready = Boolean(details.trim()) || (Boolean(location.trim()) && hasBrief);
  const canHunt = Boolean(details.trim()) || (Boolean(location.trim()) && hasBrief);
  const phases = useMemo(() => buildPhases(query, placeHint), [query, placeHint]);
  const huntEta = useMemo(
    () => estimateHuntSeconds(lineCount || 8, leadsPerRun),
    [lineCount, leadsPerRun],
  );

  useEffect(() => {
    if (isRunning) {
      document.title = `Hunting… ${formatDuration(elapsedSec)} · ${DEFAULT_DOC_TITLE}`;
      return;
    }
  }, [isRunning, elapsedSec]);

  useEffect(() => {
    if (!isRunning) return;
    let idx = 0;
    for (let i = HUNT_PHASE_SECONDS.length - 1; i >= 0; i -= 1) {
      if (elapsedSec >= HUNT_PHASE_SECONDS[i]) {
        idx = i;
        break;
      }
    }
    setPhaseIndex(Math.min(idx, phases.length - 1));
  }, [isRunning, elapsedSec, phases.length]);

  const progressLabel = useMemo(() => {
    if (!isRunning) return '';
    const etaLabel = formatEtaRange(huntEta.low, huntEta.high);
    const remaining = Math.max(0, huntEta.high - elapsedSec);
    const timeBit = `${formatDuration(elapsedSec)} elapsed · est. ${etaLabel}`;
    const leftBit =
      elapsedSec < huntEta.low
        ? ` · ~${formatDuration(Math.max(15, huntEta.low - elapsedSec))}–${formatDuration(remaining)} left`
        : remaining > 20
          ? ` · ~${formatDuration(remaining)} left`
          : ' · wrapping up';
    if (telemetryHint) return `${telemetryHint} · ${timeBit}`;
    if (elapsedSec < 60) return `Paging Google · ${timeBit}${leftBit}`;
    if (elapsedSec < 180) return `Inspecting sites · ${timeBit}${leftBit}`;
    return `Deep research · ${timeBit}${leftBit}`;
  }, [isRunning, elapsedSec, telemetryHint, huntEta]);

  const progressPct = useMemo(() => {
    if (!isRunning) return 0;
    if (serverProgress > 0) return Math.min(99, serverProgress);
    const t = elapsedSec;
    if (t <= 20) return Math.round(12 + t * 2.2);
    if (t <= 50) return Math.round(56 + (t - 20) * 0.7);
    if (t <= 90) return Math.round(77 + (t - 50) * 0.3);
    return Math.min(94, 89 + Math.floor((t - 90) / 15));
  }, [isRunning, elapsedSec, serverProgress]);

  const applyPrompt = (prompt: string) => {
    const raw = (prompt || '').trim();
    const marker = 'Priority hunt lines';
    const markerIdx = raw.indexOf(marker);
    if (markerIdx >= 0) {
      const header = raw.slice(0, markerIdx).trim();
      const rest = raw.slice(markerIdx);
      const afterColon = rest.includes('\n') ? rest.slice(rest.indexOf('\n') + 1).trim() : '';
      const locMatch = header.match(/Target location:\s*(.+)/i);
      if (locMatch?.[1]) setLocation(locMatch[1].trim());
      else {
        const parts = splitHuntPrompt(header);
        if (parts.location) setLocation(parts.location);
      }
      const buyerMatch = header.match(/Buyer types:\s*(.+)/i);
      const roles = (buyerMatch?.[1] || '')
        .split(/[,;/|]+/)
        .map(s => s.trim())
        .filter(Boolean);
      const lines = afterColon.split('\n').map(s => s.trim()).filter(Boolean);
      const hasRole = (line: string) =>
        /\b(distributors?|wholesalers?|importers?|retailers?|dealers?|wholesale)\b/i.test(line);
      if (roles.length && lines.some(line => !hasRole(line))) {
        const expanded = lines.flatMap(line =>
          hasRole(line) ? [line] : roles.map(role => `${line} ${role}`),
        );
        setDetails(expanded.join('\n'));
      } else {
        setDetails(afterColon);
      }
      return;
    }
    const parts = splitHuntPrompt(raw);
    if (parts.location) setLocation(parts.location);
    // Multi-line pastes → hunt description (primary)
    if (raw.includes('\n')) {
      setDetails(raw);
    } else if (!parts.location) {
      setDetails(raw);
    }
  };

  const runHunt = async (promptOverride?: string) => {
    const huntQuery = (promptOverride ?? query).trim();
    if (promptOverride !== undefined) applyPrompt(promptOverride);
    if ((!huntQuery && !hasBrief) || isRunning || isHuntRunning()) return;
    setShowSheetsPrompt(false);
    setIsRunning(true);
    setStatusText(phases[0]);
    setServerPhase(phases[0]);
    setServerProgress(4);
    setTelemetryHint('');
    setLastFound(null);
    try {
      await startHunt({
        userPrompt: huntQuery || query,
        products,
        icp: {
          ...icp,
          targetBuyerTypes: [],
          targetCountries: location.trim()
            ? [location.trim()]
            : (icp.targetCountries?.length
                ? icp.targetCountries
                : businessInfo.targetMarkets || []),
        },
        business: businessInfo as unknown as Record<string, unknown>,
      });
      // Progress / completion handled by huntRunner subscribers (survives tab changes).
    } catch (err: unknown) {
      console.error('Discovery failed', err);
      setIsRunning(false);
      setServerProgress(0);
      setServerPhase('');
      setTelemetryHint('');
      setStatusText(err instanceof Error ? err.message : 'Discovery failed');
      notifyHuntFinishedInTab(0, true);
    }
  };

  const handleRunClick = () => {
    if (!canHunt || isRunning) return;
    if (!sheetsConnected && !skipSheetsPrompt) {
      setShowSheetsPrompt(true);
      return;
    }
    void runHunt();
  };

  const rerunHunt = (hunt: RecentHunt) => {
    if (isRunning) return;
    const prompt = (hunt.requestPayload?.user_prompt || hunt.userPrompt || '').trim();
    if (!prompt && !hasBrief) return;
    applyPrompt(prompt);
    if (!sheetsConnected && !skipSheetsPrompt) {
      setShowSheetsPrompt(true);
      return;
    }
    void runHunt(prompt);
  };

  const continueWithoutSheets = () => {
    setSkipSheetsPrompt(true);
    try {
      sessionStorage.setItem(SKIP_SHEETS_PROMPT_KEY, '1');
    } catch {
      /* ignore */
    }
    setShowSheetsPrompt(false);
    void runHunt();
  };

  const handleResetHuntMemory = async () => {
    if (isRunning || resettingMemory) return;
    const ok = await confirm({
      title: 'Start hunt from the beginning?',
      body:
        'This forgets previously seen websites and resets Google search pages to page 1 for this company. ' +
        'Your next hunt can rediscover the same domains. Saved leads are kept. Sheets is not changed.',
      confirmLabel: 'Start over',
      cancelLabel: 'Cancel',
      tone: 'danger',
    });
    if (!ok) return;
    setResettingMemory(true);
    try {
      const resp = await apiFetch('/api/discovery/reset-memory', { method: 'POST' });
      if (!resp.ok) {
        const err = await resp.text();
        setStatusText(err.slice(0, 160) || 'Could not reset hunt memory');
        return;
      }
      const data = (await resp.json()) as { deletedCompanies?: number; deletedCursors?: number };
      const n = Number(data.deletedCompanies || 0);
      const c = Number(data.deletedCursors || 0);
      setStatusText(
        n || c
          ? `Ready to start over (${n} domains forgotten, ${c} page cursors reset).`
          : 'Ready to start over — hunt memory was already empty.',
      );
    } catch (err: unknown) {
      setStatusText(err instanceof Error ? err.message : 'Could not reset hunt memory');
    } finally {
      setResettingMemory(false);
    }
  };

  return (
    <div className={`find-buyers${compact ? ' find-buyers--compact' : ' find-buyers--primary'}`}>
      {!compact && <PageAmbient variant="leads" tone="whisper" />}
      {isRunning && (
        <div className="find-buyers__overlay" role="status" aria-live="polite">
          <Loader2 className="w-5 h-5 animate-spin text-[var(--cta)]" />
          <p className="find-buyers__overlay-title">Hunting buyers</p>
          <p className="find-buyers__overlay-phase">{serverPhase || phases[phaseIndex]}</p>
          <p className="find-buyers__overlay-timer">
            {formatDuration(elapsedSec)} elapsed · est. {formatEtaRange(huntEta.low, huntEta.high)}
            {lineCount > 0 ? ` · ${lineCount} search lines` : ''}
          </p>
          <div className="find-buyers__overlay-track" aria-hidden="true">
            <div className="find-buyers__overlay-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <p className="find-buyers__overlay-eta">{progressLabel}</p>
        </div>
      )}

      {showSheetsPrompt && !sheetsConnected && (
        <div
          className="sheets-prompt-backdrop"
          role="presentation"
          onClick={() => setShowSheetsPrompt(false)}
        >
          <div
            className="sheets-prompt"
            role="dialog"
            aria-modal="true"
            aria-labelledby="sheets-prompt-title"
            onClick={e => e.stopPropagation()}
          >
            <button
              type="button"
              className="sheets-prompt__close"
              aria-label="Close"
              onClick={() => setShowSheetsPrompt(false)}
            >
              <X className="w-4 h-4" strokeWidth={2} />
            </button>
            <div className="sheets-prompt__icon" aria-hidden>
              <FileSpreadsheet className="w-5 h-5" strokeWidth={1.75} />
            </div>
            <h2 id="sheets-prompt-title" className="sheets-prompt__title">
              Recommended: connect Google Sheets
            </h2>
            <p className="sheets-prompt__lede">
              You can hunt now — leads always save in NexivoReach. Sheets makes the experience better.
            </p>
            <ul className="sheets-prompt__perks">
              <li>
                <Check className="w-3.5 h-3.5" strokeWidth={2.25} aria-hidden />
                <span>
                  <strong>Spreadsheet backup</strong> you can open anytime
                </span>
              </li>
              <li>
                <Check className="w-3.5 h-3.5" strokeWidth={2.25} aria-hidden />
                <span>
                  <strong>Share leads</strong> with teammates
                </span>
              </li>
              <li>
                <Check className="w-3.5 h-3.5" strokeWidth={2.25} aria-hidden />
                <span>
                  <strong>Auto-sync</strong> after each hunt
                </span>
              </li>
            </ul>
            <div className="sheets-prompt__actions">
              {onGoConnect && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => {
                    setShowSheetsPrompt(false);
                    onGoConnect();
                  }}
                >
                  Connect Sheets
                </button>
              )}
              <button type="button" className="btn btn-secondary" onClick={continueWithoutSheets}>
                Continue without Sheets
              </button>
            </div>
          </div>
        </div>
      )}

      {!compact && (
        <div className="find-buyers__head">
          <div className="find-buyers__head-row">
            <h3 className="find-buyers__title">Find buyers in your market</h3>
            <button
              type="button"
              className="btn btn-danger find-buyers__reset"
              disabled={isRunning || resettingMemory}
              onClick={() => void handleResetHuntMemory()}
              title="Forget seen websites and restart Google search from page 1"
            >
              {resettingMemory ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Starting over…
                </>
              ) : (
                <>
                  <RotateCcw className="w-3.5 h-3.5" />
                  Start over
                </>
              )}
            </button>
          </div>
          <p className="find-buyers__cap" role="status">
            Up to <strong>{leadsPerRun}</strong> leads per run
            {lineCount > 0
              ? ` · ~${Math.max(1, Math.ceil(leadsPerRun / lineCount))} per search line`
              : ''}
            {' · '}
            est. {formatEtaRange(huntEta.low, huntEta.high)}
          </p>
        </div>
      )}

      {!sheetsConnected && (
        <div className="sheets-recommend" role="status">
          <div className="sheets-recommend__head">
            <FileSpreadsheet className="w-4 h-4 shrink-0" strokeWidth={1.75} aria-hidden />
            <p className="sheets-recommend__title">Sheets recommended</p>
          </div>
          <p className="sheets-recommend__body">
            Leads save in the app either way. Connect Google Sheets for a spreadsheet backup.
          </p>
          {onGoConnect && (
            <button type="button" className="linkish sheets-recommend__link" onClick={onGoConnect}>
              Connect Google Sheets
            </button>
          )}
        </div>
      )}

      <div className="hunt-search-bar" role="search">
        <div className="hunt-search-bar__row">
          <HuntCombobox
            className="hunt-search-bar__combo hunt-search-bar__combo--location"
            label="Location"
            value={location}
            onChange={setLocation}
            options={HUNT_LOCATION_OPTIONS}
            placeholder="Country or city…"
            disabled={isRunning}
            icon="pin"
            allowCustom
            open={openField === 'location'}
            onOpenChange={open => setOpenField(open ? 'location' : null)}
          />
          <button
            type="button"
            className="btn btn-primary hunt-search-bar__cta"
            onClick={handleRunClick}
            disabled={isRunning || !canHunt}
          >
            {isRunning ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" strokeWidth={2.25} />
            )}
            {isRunning ? 'Searching…' : 'Find buyers'}
          </button>
        </div>
      </div>

      <label className="hunt-details">
        <span className="hunt-details__label">Hunt description</span>
        <p className="hunt-details__hint text-[12px] text-ink-muted m-0 mb-1.5">
          One search per line: <strong>product + buyer type</strong>. Location is added
          automatically. Press Enter after each line — do not write a paragraph.
        </p>
        <textarea
          className="hunt-details__input"
          value={details}
          onChange={e => setDetails(e.target.value)}
          onFocus={() => setOpenField(null)}
          disabled={isRunning}
          rows={10}
          spellCheck={false}
          placeholder={
            'weightlifting straps distributors\n' +
            'weightlifting straps wholesalers\n' +
            'weightlifting straps importers\n' +
            'weightlifting belts distributors\n' +
            'weightlifting belts wholesalers\n' +
            'martial arts belts distributors'
          }
        />
        {lineCount > 0 && (
          <p className="hunt-details__meta text-[11px] text-ink-muted m-0 mt-1.5" aria-live="polite">
            {lineCount} search line{lineCount === 1 ? '' : 's'}
            {location.trim() ? ` · each adds “${location.trim()}”` : ''}
          </p>
        )}
      </label>

      {!ready && (
        <p className="ui-banner ui-banner--warn hunt-ready-hint" role="status">
          Add location, then list each product + buyer on its own line.
        </p>
      )}

      {recentHunts.length > 0 && !isRunning && (
        <div className="saved-hunts">
          <p className="saved-hunts__label">Recent hunts</p>
          <ul className="saved-hunts__list">
            {recentHunts.slice(0, 5).map(hunt => {
              const prompt =
                (hunt.requestPayload?.user_prompt || hunt.userPrompt || '').trim() ||
                '(brief-only hunt)';
              const summary = summarizeHuntPrompt(prompt);
              const when = (hunt.createdAt || '').slice(0, 10);
              const count = typeof hunt.foundCount === 'number' ? hunt.foundCount : null;
              return (
                <li key={hunt.jobId}>
                  <button
                    type="button"
                    className="saved-hunts__item"
                    disabled={isRunning}
                    onClick={() => applyPrompt(prompt === '(brief-only hunt)' ? '' : prompt)}
                    title="Load into search"
                  >
                    <span className="saved-hunts__prompt">{summary.title}</span>
                    {summary.detail ? (
                      <span className="saved-hunts__lines">{summary.detail}</span>
                    ) : null}
                    <span className="saved-hunts__meta">
                      {when}
                      {count !== null ? ` · ${count} leads` : ''}
                      {hunt.status && hunt.status !== 'completed' ? ` · ${hunt.status}` : ''}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="saved-hunts__rerun"
                    disabled={isRunning}
                    aria-label={`Run again: ${summary.title}`}
                    title="Run again"
                    onClick={() => rerunHunt(hunt)}
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="find-buyers__actions find-buyers__actions--status-only">
        <div className="find-buyers__status-block" aria-live="polite">
          {!isRunning && (
            <p className="find-buyers__status">
              {statusText ||
                (lastFound !== null
                  ? `Last run added ${lastFound} lead${lastFound === 1 ? '' : 's'}.`
                  : `Up to ${leadsPerRun} leads per run · usually ${formatEtaRange(
                      huntEta.low,
                      huntEta.high,
                    )}${lineCount > 0 ? ` (${lineCount} search lines)` : ''}.`)}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
