import { useEffect, useMemo, useState } from 'react';
import type { BusinessInfo, IdealCustomerProfile, Prospect, AgentRunLog, Product } from '../types';
import { Check, FileSpreadsheet, Loader2, X } from 'lucide-react';
import { apiFetch } from '../lib/api';
import PredictiveField from './PredictiveField';
import { categoriesFromProducts, suggestionsForField } from '../data/taxonomy';
import { isPlaceholderCompanyName } from '../lib/workspace';

interface Props {
  businessInfo: BusinessInfo;
  icp: IdealCustomerProfile;
  products?: Product[];
  onAddProspects: (prospects: Prospect[]) => void;
  onAddLog: (log: AgentRunLog) => void;
  onComplete?: (foundCount: number) => void;
  compact?: boolean;
  sheetsConnected?: boolean;
  onGoConnect?: () => void;
}

const HUNT_PHASE_SECONDS = [0, 12, 28, 45, 70];
const SKIP_SHEETS_PROMPT_KEY = 'nr-hunt-skip-sheets-prompt';

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
 * Primary product action: describe who to find, then hunt.
 */
export default function FindBuyersPanel({
  businessInfo,
  icp,
  products = [],
  onAddProspects,
  onAddLog,
  onComplete,
  compact = false,
  sheetsConnected = false,
  onGoConnect,
}: Props) {
  const [query, setQuery] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [lastFound, setLastFound] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [showSheetsPrompt, setShowSheetsPrompt] = useState(false);
  const [skipSheetsPrompt, setSkipSheetsPrompt] = useState(() => loadSkipSheetsPrompt());

  const catalogCats = useMemo(() => categoriesFromProducts(products), [products]);
  const placeHint = useMemo(() => {
    const fromIcp = (icp.targetCountries || []).filter(Boolean);
    const fromBiz = (businessInfo.targetMarkets || []).filter(Boolean);
    return [...fromIcp, ...fromBiz][0] || '';
  }, [icp.targetCountries, businessInfo.targetMarkets]);

  const context = useMemo(
    () =>
      [
        query,
        businessInfo.description,
        ...(businessInfo.primaryCategories ?? []),
        ...(icp.targetBuyerTypes ?? []),
        ...(icp.targetCountries ?? []),
        ...catalogCats,
      ].join(' '),
    [query, businessInfo, icp, catalogCats],
  );
  const suggestions = useMemo(
    () => suggestionsForField('discover', context, catalogCats).slice(0, 3),
    [context, catalogCats],
  );

  const hasBrief =
    Boolean(businessInfo.description?.trim()) ||
    (Boolean(businessInfo.name?.trim()) && !isPlaceholderCompanyName(businessInfo.name)) ||
    products.length > 0 ||
    (businessInfo.primaryCategories || []).length > 0 ||
    (icp.targetBuyerTypes || []).length > 0;

  const ready = Boolean(query.trim()) || hasBrief;
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

  // Indeterminate-feeling bar: climbs quickly early, then slows (never claims a fake deadline)
  const progressPct = useMemo(() => {
    if (!isRunning) return 0;
    const t = elapsedSec;
    if (t <= 20) return Math.round(12 + t * 2.2);
    if (t <= 50) return Math.round(56 + (t - 20) * 0.7);
    if (t <= 90) return Math.round(77 + (t - 50) * 0.3);
    return Math.min(94, 89 + Math.floor((t - 90) / 15));
  }, [isRunning, elapsedSec]);

  const runHunt = async () => {
    if (!canHunt || isRunning) return;
    setShowSheetsPrompt(false);
    setIsRunning(true);
    setStatusText(phases[0]);
    setLastFound(null);
    try {
      const resp = await apiFetch('/api/discovery/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_prompt: query,
          products,
          icp,
          business: businessInfo,
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `Discovery failed (${resp.status})`);
      }
      const data = await resp.json();
      const found: Prospect[] = Array.isArray(data.prospects)
        ? data.prospects
        : data.prospect
          ? [data.prospect]
          : [];
      if (found.length) onAddProspects(found);
      if (data.agent_log) onAddLog(data.agent_log as AgentRunLog);
      setLastFound(found.length);
      const skipped = Number(data.skippedExisting || 0);
      const sheetsNote = sheetsConnected ? ' Synced to Sheets.' : '';
      setStatusText(
        found.length
          ? `Added ${found.length} lead${found.length === 1 ? '' : 's'}${
              skipped ? ` (${skipped} already in your list)` : ''
            } — filter Strong vs Average on Leads.${sheetsNote}`
          : skipped
            ? `All matches were already in your list (${skipped}). Try a different hunt.`
            : 'No accounts this round — try a clearer product, buyer type, or place.',
      );
      onComplete?.(found.length);
    } catch (err: unknown) {
      console.error('Discovery failed', err);
      setStatusText(err instanceof Error ? err.message : 'Discovery failed');
    } finally {
      setIsRunning(false);
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

  const continueWithoutSheets = () => {
    setSkipSheetsPrompt(true);
    try {
      sessionStorage.setItem(SKIP_SHEETS_PROMPT_KEY, '1');
    } catch {
      // ignore
    }
    void runHunt();
  };

  return (
    <div className={`find-buyers find-buyers--primary ${compact ? 'find-buyers--compact' : ''}`}>
      {isRunning && (
        <div className="find-buyers__overlay" role="status" aria-live="polite">
          <p className="find-buyers__overlay-title">Finding buyers</p>
          <p className="find-buyers__overlay-phase inline-flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin shrink-0 text-[var(--cta)]" strokeWidth={1.75} />
            {phases[phaseIndex]}
          </p>
          <div className="find-buyers__overlay-track" aria-hidden="true">
            <div
              className="find-buyers__overlay-fill"
              style={{
                width: `${progressPct}%`,
              }}
            />
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
              You can hunt now — leads always save in NexivoReach. Sheets makes the experience better:
            </p>
            <ul className="sheets-prompt__perks">
              <li>
                <Check className="w-3.5 h-3.5" strokeWidth={2.25} aria-hidden />
                <span>
                  <strong>Spreadsheet backup</strong> you can open in Google Sheets anytime
                </span>
              </li>
              <li>
                <Check className="w-3.5 h-3.5" strokeWidth={2.25} aria-hidden />
                <span>
                  <strong>Share leads</strong> with teammates who live in spreadsheets
                </span>
              </li>
              <li>
                <Check className="w-3.5 h-3.5" strokeWidth={2.25} aria-hidden />
                <span>
                  <strong>Auto-sync</strong> after each hunt and when stages change
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
          <h3 className="find-buyers__title">Find buyers</h3>
          <p className="find-buyers__desc">
            Product, buyer type, and place. Results go to Leads.
          </p>
        </div>
      )}

      <div className="hunt-howto" aria-label="Hunt writing tips">
        <p className="hunt-howto__lede">
          One hunt at a time. Run again for another market.
        </p>
        <p className="hunt-howto__examples">
          e.g. <em>belt importers in Nevada</em>
          {' · '}
          <em>hoodie wholesalers in Texas</em>
        </p>
      </div>

      {!sheetsConnected && (
        <div className="sheets-recommend" role="status">
          <div className="sheets-recommend__head">
            <FileSpreadsheet className="w-4 h-4 shrink-0" strokeWidth={1.75} aria-hidden />
            <p className="sheets-recommend__title">Sheets recommended</p>
          </div>
          <p className="sheets-recommend__body">
            Leads save in the app either way. Connect Google Sheets for a spreadsheet backup and
            easier sharing.
          </p>
          {onGoConnect && (
            <button type="button" className="linkish sheets-recommend__link" onClick={onGoConnect}>
              Connect Google Sheets
            </button>
          )}
        </div>
      )}

      {!ready && (
        <p className="ui-banner ui-banner--warn" role="status">
          Type a hunt below, or add a company brief first.
        </p>
      )}

      <PredictiveField
        label="What are you looking for?"
        hint="One product · one buyer · one place"
        value={query}
        onChange={setQuery}
        suggestions={suggestions}
        placeholder="e.g. belt importers in Nevada"
        single
        hideSuggestionsWhenFilled
        aiContext={{
          field: 'discover',
          description: businessInfo.description,
          catalogCategories: catalogCats.length ? catalogCats : businessInfo.primaryCategories,
        }}
      />

      <div className="find-buyers__actions">
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
        <button
          type="button"
          onClick={handleRunClick}
          disabled={isRunning || !canHunt}
          className="btn btn-primary find-buyers__cta"
        >
          {isRunning ? 'Searching…' : 'Find buyers'}
        </button>
      </div>
    </div>
  );
}
