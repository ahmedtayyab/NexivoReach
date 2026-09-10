import { useMemo, useState } from 'react';
import type { BusinessInfo, IdealCustomerProfile, Prospect, AgentRunLog, Product } from '../types';
import { Loader2 } from 'lucide-react';
import { apiFetch } from '../lib/api';
import PredictiveField from './PredictiveField';
import { categoriesFromProducts, suggestionsForField } from '../data/taxonomy';

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
 * Core agent action: find buyers from company + catalog + ICP.
 * Lives in Workspace (not a separate Discover tab).
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

  const ready =
    Boolean(query.trim()) ||
    products.length > 0 ||
    (businessInfo.primaryCategories || []).length > 0;

  const missing: string[] = [];
  if (!businessInfo.name?.trim() && !businessInfo.description?.trim()) missing.push('company');
  if (!products.length && !(businessInfo.primaryCategories || []).length) missing.push('catalog or categories');
  if (!(icp.targetBuyerTypes || []).length) missing.push('buyer types');

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
          ? `Added ${found.length} qualified lead${found.length === 1 ? '' : 's'}.`
          : 'No qualified accounts this round — try a clearer buyer type or market.',
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
    <div className={`find-buyers ${compact ? 'find-buyers--compact' : ''}`}>
      <div className="find-buyers__head">
        <h3 className="find-buyers__title">Find buyers</h3>
        <p className="find-buyers__desc">
          The agent searches from your company, catalog, and buyer profile — then scores Fit and Intent separately.
        </p>
      </div>

      {!ready && missing.length > 0 && (
        <p className="ui-banner ui-banner--warn" role="status">
          Add {missing.join(', ')} above so the agent has enough to work with.
        </p>
      )}

      <PredictiveField
        label="Optional focus"
        hint="Leave blank to use your catalog and buyers. Or type a specific hunt."
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
              : 'Uses saved company + catalog + buyers when the box is empty.')
          )}
        </p>
        <button
          type="button"
          onClick={handleRun}
          disabled={isRunning || !ready}
          className="btn btn-primary"
        >
          {isRunning ? 'Searching…' : 'Find buyers'}
        </button>
      </div>
    </div>
  );
}
