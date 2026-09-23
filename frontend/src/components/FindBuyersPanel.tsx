import { useEffect, useMemo, useState } from 'react';
import type { BusinessInfo, IdealCustomerProfile, Prospect, AgentRunLog, Product } from '../types';
import { Check, FileSpreadsheet, Loader2, RotateCcw, Search, X } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { categoriesFromProducts, suggestionsForField } from '../data/taxonomy';
import {
  HUNT_BUSINESS_CATEGORIES,
  HUNT_LOCATION_OPTIONS,
} from '../data/huntTaxonomy';
import { isPlaceholderCompanyName } from '../lib/workspace';
import PageAmbient from './brand/PageAmbient';
import HuntCombobox from './FindBuyers/HuntCombobox';
import PredictiveField from './PredictiveField';

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

const HUNT_PHASE_SECONDS = [0, 12, 28, 45, 70];
const SKIP_SHEETS_PROMPT_KEY = 'nr-hunt-skip-sheets-prompt';

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

export function composeHuntPrompt(category: string, location: string, details = ''): string {
  const cat = (category || '').trim();
  const loc = (location || '').trim();
  const detail = (details || '').trim();
  const headerParts: string[] = [];
  if (cat && loc) {
    if (/\b(?:in|near|around|within)\s+/i.test(cat)) headerParts.push(cat);
    else headerParts.push(`${cat} in ${loc}`);
  } else if (cat) {
    headerParts.push(cat);
  } else if (loc) {
    headerParts.push(`buyers in ${loc}`);
  }
  const header = headerParts.join(' ').trim();
  if (!detail) return header;
  if (!header) return detail;
  // Details are first-class hunt input — product×buyer lines the agent must cover.
  return [
    header,
    '',
    'Priority hunt lines (find authentic leads in this region for each):',
    detail,
  ].join('\n');
}

function buildPhases(query: string, placeHint: string): string[] {
  const focus = (query || '').trim() || 'matching buyers';
  const short = focus.length > 48 ? `${focus.slice(0, 48)}…` : focus;
  const place = placeHint ? ` in ${placeHint}` : '';
  return [
    `Planning searches for “${short}”…`,
    `Searching the web${place}…`,
    'Opening company sites…',
    'Scoring Fit on live pages…',
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
 * Primary product action: category + location bar → hunt.
 */
export default function FindBuyersPanel({
  businessInfo,
  icp,
  products = [],
  onAddProspects,
  onAddLog,
  onComplete,
  onSaveICP,
  compact = false,
  sheetsConnected = false,
  onGoConnect,
}: Props) {
  const [category, setCategory] = useState('');
  const [location, setLocation] = useState('');
  const [details, setDetails] = useState('');
  const [buyerTypes, setBuyerTypes] = useState((icp.targetBuyerTypes ?? []).join(', '));
  const [openField, setOpenField] = useState<'location' | 'category' | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [lastFound, setLastFound] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [showSheetsPrompt, setShowSheetsPrompt] = useState(false);
  const [skipSheetsPrompt, setSkipSheetsPrompt] = useState(() => loadSkipSheetsPrompt());
  const [serverPhase, setServerPhase] = useState('');
  const [serverProgress, setServerProgress] = useState(0);
  const [recentHunts, setRecentHunts] = useState<RecentHunt[]>([]);

  const query = useMemo(
    () => composeHuntPrompt(category, location, details),
    [category, location, details],
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

  useEffect(() => {
    void loadRecentHunts();
  }, []);

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

  const categoryOptions = useMemo(() => {
    const fromCatalog = categoriesFromProducts(products);
    return Array.from(new Set([...HUNT_BUSINESS_CATEGORIES, ...fromCatalog]));
  }, [products]);

  const catalogCats = useMemo(() => categoriesFromProducts(products), [products]);
  const buyerContext = useMemo(
    () =>
      [
        businessInfo.description,
        ...(businessInfo.primaryCategories ?? []),
        category,
        details,
        buyerTypes,
        ...catalogCats,
      ].join(' '),
    [businessInfo, category, details, buyerTypes, catalogCats],
  );
  const buyerSuggestions = useMemo(
    () => suggestionsForField('buyers', buyerContext, catalogCats),
    [buyerContext, catalogCats],
  );

  // Persist optional buyer types into ICP as the user types.
  useEffect(() => {
    if (!onSaveICP) return;
    const timer = window.setTimeout(() => {
      const nextTypes = buyerTypes.split(',').map(s => s.trim()).filter(Boolean);
      const prev = (icp.targetBuyerTypes ?? []).join(', ');
      if (nextTypes.join(', ') === prev) return;
      onSaveICP({
        ...icp,
        targetBuyerTypes: nextTypes,
      });
    }, 450);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- draft buyer types only
  }, [buyerTypes]);

  const hasBrief =
    Boolean(businessInfo.description?.trim()) ||
    (Boolean(businessInfo.name?.trim()) && !isPlaceholderCompanyName(businessInfo.name)) ||
    products.length > 0 ||
    (businessInfo.primaryCategories || []).length > 0 ||
    (icp.targetBuyerTypes || []).length > 0;

  const ready =
    Boolean(category.trim()) ||
    Boolean(location.trim()) ||
    Boolean(details.trim()) ||
    hasBrief;
  const canHunt = ready;
  const phases = useMemo(() => buildPhases(query, placeHint), [query, placeHint]);

  useEffect(() => {
    if (!isRunning) return;
    setElapsedSec(0);
    setPhaseIndex(0);
    const tick = window.setInterval(() => setElapsedSec(s => s + 1), 1000);
    return () => window.clearInterval(tick);
  }, [isRunning]);

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
    if (elapsedSec < 45) return `Working · ${elapsedSec}s elapsed`;
    if (elapsedSec < 90) return `Still hunting · ${elapsedSec}s — often finishes around a minute`;
    return `Still working · ${elapsedSec}s — large markets take longer`;
  }, [isRunning, elapsedSec]);

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
      const parts = splitHuntPrompt(header);
      setCategory(parts.category);
      if (parts.location) setLocation(parts.location);
      setDetails(afterColon);
      return;
    }
    const parts = splitHuntPrompt(raw);
    setCategory(parts.category);
    if (parts.location) setLocation(parts.location);
    // Multi-line pastes without our marker → treat as details
    if (raw.includes('\n')) {
      setDetails(raw);
      if (!parts.location && !parts.category) {
        setCategory('');
      }
    }
  };

  const runHunt = async (promptOverride?: string) => {
    const huntQuery = (promptOverride ?? query).trim();
    if (promptOverride !== undefined) applyPrompt(promptOverride);
    if ((!huntQuery && !hasBrief) || isRunning) return;
    setShowSheetsPrompt(false);
    setIsRunning(true);
    setStatusText(phases[0]);
    setServerPhase(phases[0]);
    setServerProgress(4);
    setLastFound(null);
    try {
      const resp = await apiFetch('/api/discovery/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_prompt: huntQuery || query,
          products,
          icp: {
            ...icp,
            targetBuyerTypes: buyerTypes.split(',').map(s => s.trim()).filter(Boolean),
            targetCountries: location.trim()
              ? [location.trim()]
              : (icp.targetCountries?.length
                  ? icp.targetCountries
                  : businessInfo.targetMarkets || []),
          },
          business: businessInfo,
          async_mode: true,
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `Discovery failed (${resp.status})`);
      }
      const started = await resp.json();
      const jobId = started.jobId as string | undefined;
      if (!jobId) {
        throw new Error('Hunt started but no job id returned');
      }

      let data: {
        status?: string;
        phase?: string;
        progress?: number;
        prospects?: Prospect[];
        foundCount?: number;
        skippedExisting?: number;
        agent_log?: AgentRunLog;
        error?: string;
      } = started;

      while (data.status !== 'completed' && data.status !== 'failed') {
        await new Promise(r => window.setTimeout(r, 1200));
        const poll = await apiFetch(`/api/discovery/jobs/${jobId}`);
        if (!poll.ok) {
          const text = await poll.text();
          throw new Error(text || `Could not poll hunt (${poll.status})`);
        }
        data = await poll.json();
        if (data.phase) {
          setServerPhase(data.phase);
          setStatusText(data.phase);
        }
        if (typeof data.progress === 'number') setServerProgress(data.progress);
      }

      if (data.status === 'failed') {
        throw new Error(data.error || 'Discovery failed');
      }

      const found: Prospect[] = Array.isArray(data.prospects) ? data.prospects : [];
      if (found.length) onAddProspects(found);
      if (data.agent_log) onAddLog(data.agent_log as AgentRunLog);
      const foundCount = Number(data.foundCount ?? found.length);
      setLastFound(foundCount);
      const skipped = Number(data.skippedExisting || 0);
      const sheetsNote = sheetsConnected ? ' Synced to Sheets.' : '';
      setStatusText(
        foundCount
          ? `Added ${foundCount} lead${foundCount === 1 ? '' : 's'}${
              skipped ? ` (${skipped} already in your list)` : ''
            } — filter Strong vs Average on Leads.${sheetsNote}`
          : skipped
            ? `All matches were already in your list (${skipped}). Try a different hunt.`
            : 'No accounts this round — try a clearer category or location.',
      );
      onComplete?.(foundCount);
      void loadRecentHunts();
    } catch (err: unknown) {
      console.error('Discovery failed', err);
      setStatusText(err instanceof Error ? err.message : 'Discovery failed');
    } finally {
      setIsRunning(false);
      setServerProgress(0);
      setServerPhase('');
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

  return (
    <div className={`find-buyers${compact ? ' find-buyers--compact' : ' find-buyers--primary'}`}>
      {!compact && <PageAmbient variant="leads" tone="whisper" />}
      {isRunning && (
        <div className="find-buyers__overlay" role="status" aria-live="polite">
          <Loader2 className="w-5 h-5 animate-spin text-[var(--cta)]" />
          <p className="find-buyers__overlay-title">Hunting buyers</p>
          <p className="find-buyers__overlay-phase">{serverPhase || phases[phaseIndex]}</p>
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
          <h3 className="find-buyers__title">Find buyers in your market</h3>
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
          <HuntCombobox
            className="hunt-search-bar__combo hunt-search-bar__combo--category"
            label="Business category"
            value={category}
            onChange={setCategory}
            options={categoryOptions}
            placeholder="Business category…"
            disabled={isRunning}
            allowCustom
            open={openField === 'category'}
            onOpenChange={open => setOpenField(open ? 'category' : null)}
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
        <textarea
          className="hunt-details__input"
          value={details}
          onChange={e => setDetails(e.target.value)}
          onFocus={() => setOpenField(null)}
          disabled={isRunning}
          rows={8}
          placeholder={
            'Fitness / Bodybuilding\n' +
            'weightlifting straps distributors\n' +
            'weightlifting straps wholesalers\n' +
            'weightlifting belts importers\n' +
            'wrist wraps distributors'
          }
        />
      </label>

      <div className="hunt-buyer-types">
        <PredictiveField
          label="Buyer types (optional)"
          value={buyerTypes}
          onChange={setBuyerTypes}
          suggestions={buyerSuggestions}
          placeholder="Buyer type"
          aiContext={{
            field: 'buyers',
            description: businessInfo.description,
            catalogCategories: catalogCats.length ? catalogCats : businessInfo.primaryCategories,
          }}
        />
      </div>

      {!ready && (
        <p className="ui-banner ui-banner--warn hunt-ready-hint" role="status">
          Add a location, category, or hunt description — or set up a company brief first.
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
                    <span className="saved-hunts__prompt">{prompt}</span>
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
                    aria-label={`Run again: ${prompt}`}
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
                  : 'Usually under a minute for ~20–40 leads.')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
