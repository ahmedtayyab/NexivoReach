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
  onAddProspect: (prospect: Prospect) => void;
  onAddLog: (log: AgentRunLog) => void;
}

export default function DiscoverView({
  businessInfo,
  icp,
  products = [],
  onAddProspect,
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

  const handleRun = async () => {
    if (!query.trim() || isRunning) return;
    setIsRunning(true);
    setStatusText('Starting discovery...');

    const runId = `run-${Date.now()}`;
    const startedAt = new Date();

    try {
      setStatusText('Sending query to discovery agent...');
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

      setStatusText('Processing agent results...');
      const data = await resp.json();

      if (data.prospect) {
        onAddProspect(data.prospect as Prospect);
      }
      if (data.agent_log) {
        onAddLog(data.agent_log as AgentRunLog);
      }

      const durationSec = Math.max(1, Math.round((Date.now() - startedAt.getTime()) / 1000));
      setRunHistory(prev => [
        { id: runId, startedAt, foundCount: data.prospect ? 1 : 0, durationSec },
        ...prev,
      ]);
      setStatusText('Completed');
    } catch (err: unknown) {
      console.error('Discovery failed', err);
      setStatusText(err instanceof Error ? err.message : 'Discovery failed');
    } finally {
      setIsRunning(false);
      setTimeout(() => setStatusText(''), 2000);
    }
  };

  const lastRun = runHistory[0];

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-ink">Discover</h1>
        <p className="text-sm text-ink-secondary mt-0.5">
          Describe the buyers you want. Suggestions adapt to your catalog and ICP — click one or type your own.
        </p>
      </div>

      <div className="bg-panel border border-border rounded-md p-4 space-y-3">
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
        <div className="flex items-center justify-between pt-2 border-t border-border-subtle">
          {isRunning ? (
            <span className="flex items-center space-x-2 text-sm text-ink-secondary">
              <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.75} />
              <span>{statusText}</span>
            </span>
          ) : (
            <span className="text-xs text-ink-muted">
              {lastRun
                ? `Last run ${formatRelative(lastRun.startedAt)}`
                : 'No runs yet'}
            </span>
          )}
          <button
            onClick={handleRun}
            disabled={isRunning || !query.trim()}
            className="px-4 py-1.5 bg-accent hover:bg-accent-hover disabled:opacity-40 text-white text-sm font-medium rounded-md transition-colors"
          >
            {isRunning ? 'Running...' : 'Run Scan'}
          </button>
        </div>
      </div>

      {runHistory.length > 0 && (
        <div className="mt-8">
          <p className="text-xs font-medium text-ink-muted uppercase tracking-widest mb-3">Recent Runs</p>
          <div className="divide-y divide-border-subtle">
            {runHistory.map(run => (
              <div key={run.id} className="py-2.5 flex items-center justify-between text-sm">
                <div>
                  <p className="text-ink-secondary">{run.foundCount} prospect{run.foundCount === 1 ? '' : 's'} found</p>
                  <p className="text-xs text-ink-muted">{formatRelative(run.startedAt)}</p>
                </div>
                <span className="text-xs text-ink-muted font-mono">{run.durationSec}s</span>
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
