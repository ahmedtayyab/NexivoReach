import { useEffect, useMemo, useState } from 'react';
import type { BusinessInfo, IdealCustomerProfile, Prospect, AgentRunLog, Product } from '../types';
import { Loader2 } from 'lucide-react';
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

const HUNT_ETA_SECONDS = 35;

function buildPhases(query: string, placeHint: string): string[] {
  const focus = (query || '').trim() || 'matching buyers';
  const short = focus.length > 48 ? `${focus.slice(0, 48)}…` : focus;
  const place = placeHint ? ` in ${placeHint}` : '';
  return [
    `Planning searches for “${short}”…`,
    `Scanning Google and maps${place}…`,
    'Opening company sites to score Fit…',
    'Filtering strong vs average leads…',
    'Ranking your shortlist — almost done…',
  ];
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
  const [productChip, setProductChip] = useState('');
  const [buyerChip, setBuyerChip] = useState('');
  const [placeChip, setPlaceChip] = useState('');

  const catalogCats = useMemo(() => categoriesFromProducts(products), [products]);
  const productOptions = useMemo(() => {
    const fromCatalog = catalogCats.length ? catalogCats : (businessInfo.primaryCategories || []);
    return fromCatalog.filter(Boolean).slice(0, 6);
  }, [catalogCats, businessInfo.primaryCategories]);
  const buyerOptions = useMemo(
    () => (icp.targetBuyerTypes || []).filter(Boolean).slice(0, 6),
    [icp.targetBuyerTypes],
  );
  const placeOptions = useMemo(() => {
    const fromIcp = (icp.targetCountries || []).filter(Boolean);
    const fromBiz = (businessInfo.targetMarkets || []).filter(Boolean);
    return [...fromIcp, ...fromBiz].filter((v, i, a) => a.indexOf(v) === i).slice(0, 6);
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
    () => suggestionsForField('discover', context, catalogCats),
    [context, catalogCats],
  );

  const hasBrief =
    Boolean(businessInfo.description?.trim()) ||
    (Boolean(businessInfo.name?.trim()) && !isPlaceholderCompanyName(businessInfo.name)) ||
    products.length > 0 ||
    (businessInfo.primaryCategories || []).length > 0 ||
    (icp.targetBuyerTypes || []).length > 0;

  const ready = Boolean(query.trim()) || hasBrief;
  const canHunt = ready && sheetsConnected;
  const phases = useMemo(
    () => buildPhases(query, placeChip || placeOptions[0] || ''),
    [query, placeChip, placeOptions],
  );

  const composeFromChips = (nextProduct: string, nextBuyer: string, nextPlace: string) => {
    const parts = [nextProduct, nextBuyer].filter(Boolean);
    let sentence = parts.join(' ');
    if (nextPlace) sentence = sentence ? `${sentence} in ${nextPlace}` : nextPlace;
    if (sentence) setQuery(sentence);
  };

  const toggleChip = (
    kind: 'product' | 'buyer' | 'place',
    value: string,
  ) => {
    const nextProduct = kind === 'product' ? (productChip === value ? '' : value) : productChip;
    const nextBuyer = kind === 'buyer' ? (buyerChip === value ? '' : value) : buyerChip;
    const nextPlace = kind === 'place' ? (placeChip === value ? '' : value) : placeChip;
    if (kind === 'product') setProductChip(nextProduct);
    if (kind === 'buyer') setBuyerChip(nextBuyer);
    if (kind === 'place') setPlaceChip(nextPlace);
    composeFromChips(nextProduct, nextBuyer, nextPlace);
  };

  useEffect(() => {
    if (!isRunning) return;
    setElapsedSec(0);
    setPhaseIndex(0);
    const tick = window.setInterval(() => setElapsedSec(s => s + 1), 1000);
    const phase = window.setInterval(
      () => setPhaseIndex(i => Math.min(i + 1, phases.length - 1)),
      7000,
    );
    return () => {
      window.clearInterval(tick);
      window.clearInterval(phase);
    };
  }, [isRunning, phases.length]);

  const etaLabel = useMemo(() => {
    if (!isRunning) return '';
    const remaining = Math.max(5, HUNT_ETA_SECONDS - elapsedSec);
    if (elapsedSec < HUNT_ETA_SECONDS) {
      return `About ${remaining}s left · usually under a minute`;
    }
    return 'Taking a bit longer than usual — still working…';
  }, [isRunning, elapsedSec]);

  const handleRun = async () => {
    if (!canHunt || isRunning) return;
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
      setStatusText(
        found.length
          ? `Added ${found.length} lead${found.length === 1 ? '' : 's'}${
              skipped ? ` (${skipped} already in your list)` : ''
            } — filter Strong vs Average on Leads. Synced to Sheets.`
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

  const showBuilder = productOptions.length + buyerOptions.length + placeOptions.length > 0;

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
                width: `${Math.min(92, Math.round((elapsedSec / HUNT_ETA_SECONDS) * 100))}%`,
              }}
            />
          </div>
          <p className="find-buyers__overlay-eta">{etaLabel}</p>
        </div>
      )}

      {!compact && (
        <div className="find-buyers__head">
          <h3 className="find-buyers__title">Find buyers</h3>
          <p className="find-buyers__desc">
            Be specific — product, buyer type, and place. Results go to Leads and Google Sheets.
          </p>
        </div>
      )}

      {!sheetsConnected && (
        <p className="ui-banner ui-banner--warn" role="status">
          Connect Google Sheets first so leads are saved and won&apos;t disappear on a re-run.{' '}
          {onGoConnect && (
            <button type="button" className="linkish" onClick={onGoConnect}>
              Connect Google
            </button>
          )}
        </p>
      )}

      {sheetsConnected && !ready && (
        <p className="ui-banner ui-banner--warn" role="status">
          Type who you want below, or add a short company brief first.
        </p>
      )}

      {showBuilder && (
        <div className="hunt-builder" aria-label="Build hunt from chips">
          {productOptions.map(opt => (
            <button
              key={`p-${opt}`}
              type="button"
              className={`hunt-chip ${productChip === opt ? 'is-on' : ''}`}
              onClick={() => toggleChip('product', opt)}
            >
              <span className="hunt-chip__key">Product</span>
              {opt}
            </button>
          ))}
          {buyerOptions.map(opt => (
            <button
              key={`b-${opt}`}
              type="button"
              className={`hunt-chip ${buyerChip === opt ? 'is-on' : ''}`}
              onClick={() => toggleChip('buyer', opt)}
            >
              <span className="hunt-chip__key">Buyer</span>
              {opt}
            </button>
          ))}
          {placeOptions.map(opt => (
            <button
              key={`l-${opt}`}
              type="button"
              className={`hunt-chip ${placeChip === opt ? 'is-on' : ''}`}
              onClick={() => toggleChip('place', opt)}
            >
              <span className="hunt-chip__key">Place</span>
              {opt}
            </button>
          ))}
          {!buyerOptions.length && (
            <button
              type="button"
              className="hunt-chip"
              onClick={() => {
                const v = 'importers';
                setBuyerChip(v);
                composeFromChips(productChip, v, placeChip);
              }}
            >
              <span className="hunt-chip__key">Buyer</span>
              importers
            </button>
          )}
        </div>
      )}

      <PredictiveField
        label="What are you looking for?"
        hint="Tap chips above or type freely — e.g. martial arts belt importers in Nevada."
        value={query}
        onChange={setQuery}
        suggestions={suggestions}
        placeholder="e.g. martial arts belt importers in Nevada"
        single
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
                  : 'Typical hunt: about 30–45 seconds for a ranked shortlist.')}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={isRunning || !canHunt}
          className="btn btn-primary find-buyers__cta"
        >
          {isRunning ? 'Searching…' : 'Find buyers'}
        </button>
      </div>
    </div>
  );
}
