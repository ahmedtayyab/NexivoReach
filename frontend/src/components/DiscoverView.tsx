import { useMemo, useState } from 'react';
import type { BusinessInfo, IdealCustomerProfile, Prospect, AgentRunLog, Product } from '../types';
import { Loader2 } from 'lucide-react';
import { apiFetch } from '../lib/api';
import PredictiveField from './PredictiveField';
import { categoriesFromProducts, suggestionsForField } from '../data/taxonomy';
import RadarSweep from './brand/RadarSweep';

interface Props {
  businessInfo: BusinessInfo;
  icp: IdealCustomerProfile;
  products?: Product[];
  onAddProspects: (prospects: Prospect[]) => void;
  onAddLog: (log: AgentRunLog) => void;
}

export default function DiscoverView({
  businessInfo,
  icp,
  products = [],
  onAddProspects,
  onAddLog,
}: Props) {
  const [query, setQuery] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [runHistory, setRunHistory] = useState<
    Array<{ id: string; startedAt: Date; foundCount: number; durationSec: number }>
  >([]);

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
  const discoverSuggestions = useMemo(
    () => suggestionsForField('discover', context, catalogCats),
    [context, catalogCats],
  );

  const canRun =
    Boolean(query.trim()) ||
    products.length > 0 ||
    (businessInfo.primaryCategories || []).length > 0;

  const handleRun = async () => {
    if (!canRun || isRunning) return;
    setIsRunning(true);
    setStatusText('Planning searches, then qualifying Fit vs Intent…');

    const runId = `run-${Date.now()}`;
    const startedAt = new Date();

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
        throw new Error(`Discovery API error: ${resp.status} ${text}`);
      }

      const data = await resp.json();
      const found: Prospect[] = Array.isArray(data.prospects)
        ? data.prospects
        : data.prospect
          ? [data.prospect]
          : [];
      if (found.length) onAddProspects(found);
      if (data.agent_log) onAddLog(data.agent_log as AgentRunLog);

      const durationSec = Math.max(1, Math.round((Date.now() - startedAt.getTime()) / 1000));
      setRunHistory(prev => [
        { id: runId, startedAt, foundCount: found.length, durationSec },
        ...prev,
      ]);
      setStatusText(
        found.length
          ? `Added ${found.length} qualified lead${found.length === 1 ? '' : 's'} (junk and low-fit accounts skipped).`
          : 'No qualified accounts this round — directories, factories, or weak matches were filtered out.',
      );
    } catch (err: unknown) {
      console.error('Discovery failed', err);
      setStatusText(err instanceof Error ? err.message : 'Discovery failed');
    } finally {
      setIsRunning(false);
    }
  };

  const lastRun = runHistory[0];

  return (
    <div className="max-w-2xl w-full">
      <div className="mb-6 nr-enter">
        <h1 className="text-lg font-semibold text-ink">Discover</h1>
        <p className="text-sm text-ink-secondary mt-0.5">
          The agent plans searches from your sales motion, filters junk, inspects promising sites, then saves accounts with Fit and Intent scored separately. Keyword overlap is not treated as buying intent.
        </p>
      </div>

      <div className="mb-5 nr-enter nr-enter-delay-1">
        <RadarSweep active={isRunning} />
      </div>

      <div className="bg-panel border border-border rounded-md p-3.5 sm:p-4 space-y-3 nr-enter nr-enter-delay-2">
        <PredictiveField
          label="Who should we find?"
          hint="Example: type “distributor” or “hospital” — related scan ideas appear."
          value={query}
          onChange={setQuery}
          suggestions={discoverSuggestions}
          placeholder="Find distributors expanding in my target markets…"
          single
          aiContext={{
            field: 'discover',
            description: businessInfo.description,
            catalogCategories: catalogCats.length
              ? catalogCats
              : businessInfo.primaryCategories,
          }}
        />
        <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 pt-2 border-t border-border-subtle">
          {isRunning ? (
            <span className="flex items-center space-x-2 text-sm text-ink-secondary">
              <Loader2 className="w-4 h-4 animate-spin shrink-0" strokeWidth={1.75} />
              <span>{statusText}</span>
            </span>
          ) : (
            <span className="text-xs text-ink-muted sm:max-w-[70%]">
              {statusText || (lastRun ? `Last run ${formatRelative(lastRun.startedAt)}` : 'Uses catalog + ICP if you leave the box empty')}
            </span>
          )}
          <button
            onClick={handleRun}
            disabled={isRunning || !canRun}
            className={`w-full sm:w-auto px-4 py-2 sm:py-1.5 bg-accent hover:bg-accent-hover disabled:opacity-40 text-white text-sm font-medium rounded-md nr-btn-press`}
          >
            {isRunning ? 'Searching…' : 'Find leads'}
          </button>
        </div>
      </div>

      {runHistory.length > 0 && (
        <div className="mt-8 nr-enter nr-enter-delay-3">
          <p className="text-xs font-medium text-ink-muted uppercase tracking-widest mb-3">Recent Runs</p>
          <div className="divide-y divide-border-subtle">
            {runHistory.map(run => (
              <div key={run.id} className="py-2.5 flex items-center justify-between text-sm gap-3">
                <div className="min-w-0">
                  <p className="text-ink-secondary">{run.foundCount} new lead{run.foundCount === 1 ? '' : 's'}</p>
                  <p className="text-xs text-ink-muted">{formatRelative(run.startedAt)}</p>
                </div>
                <span className="text-xs text-ink-muted font-mono shrink-0">{run.durationSec}s</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatRelative(date: Date): string {
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
