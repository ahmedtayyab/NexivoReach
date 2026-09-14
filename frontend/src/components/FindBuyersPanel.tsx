import { useMemo, useState } from 'react';
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
}: Props) {
  const [query, setQuery] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [lastFound, setLastFound] = useState<number | null>(null);

  const catalogCats = useMemo(() => categoriesFromProducts(products), [products]);
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

  const handleRun = async () => {
    if (!ready || isRunning) return;
    setIsRunning(true);
    setStatusText('Planning searches, then qualifying Fit vs Intent…');
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
      setStatusText(
        found.length
          ? `Added ${found.length} lead${found.length === 1 ? '' : 's'} — filter Priority vs Review on Leads.`
          : 'No accounts this round — try a clearer product, buyer type, or place in the hunt.',
      );
      onComplete?.(found.length);
    } catch (err: unknown) {
      console.error('Discovery failed', err);
      setStatusText(err instanceof Error ? err.message : 'Discovery failed');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className={`find-buyers find-buyers--primary ${compact ? 'find-buyers--compact' : ''}`}>
      {!compact && (
        <div className="find-buyers__head">
          <h3 className="find-buyers__title">Find buyers</h3>
          <p className="find-buyers__desc">
            Be specific — product, buyer type, and place. Results go to Leads.
          </p>
        </div>
      )}

      {!ready && (
        <p className="ui-banner ui-banner--warn" role="status">
          Type who you want below, or add a short company brief first.
        </p>
      )}

      <PredictiveField
        label="What are you looking for?"
        hint="Example: martial arts belt importers in Nevada. Leave blank to use your company brief."
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
        <p className="find-buyers__status" aria-live="polite">
          {isRunning ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.75} />
              {statusText}
            </span>
          ) : (
            statusText ||
            (lastFound !== null
              ? `Last run added ${lastFound} lead${lastFound === 1 ? '' : 's'}.`
              : '')
          )}
        </p>
        <button
          type="button"
          onClick={handleRun}
          disabled={isRunning || !ready}
          className="btn btn-primary find-buyers__cta"
        >
          {isRunning ? 'Searching…' : 'Find buyers'}
        </button>
      </div>
    </div>
  );
}
