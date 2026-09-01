import { useState } from 'react';
import type { BusinessInfo, IdealCustomerProfile, Prospect, AgentRunLog } from '../types';
import { Loader2 } from 'lucide-react';

interface Props {
  businessInfo: BusinessInfo;
  icp: IdealCustomerProfile;
  onAddProspect: (prospect: Prospect) => void;
  onAddLog: (log: AgentRunLog) => void;
}

export default function DiscoverView({ onAddProspect, onAddLog }: Props) {
  const [query, setQuery] = useState(
    'Find commercial gyms expanding in the GCC region needing heavy-duty strength equipment.'
  );
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [runHistory, setRunHistory] = useState<
    Array<{ id: string; startedAt: Date; foundCount: number; durationSec: number }>
  >([
    { id: 'run-1', startedAt: new Date(Date.now() - 7200000), foundCount: 3, durationSec: 118 },
    { id: 'run-2', startedAt: new Date(Date.now() - 86400000 * 1.4), foundCount: 1, durationSec: 74 },
  ]);

  const handleRun = async () => {
    if (!query.trim() || isRunning) return;
    setIsRunning(true);
    setStatusText('Starting discovery...');

    const runId = `run-${Date.now()}`;
    const startedAt = new Date();

    try {
      setStatusText('Sending query to discovery agent...');
      const resp = await fetch('/api/discovery/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_prompt: query, products: [], icp: {} }),
      });

      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`Discovery API error: ${resp.status} ${text}`);
      }

      setStatusText('Processing agent results...');
      const data = await resp.json();

      // Expecting { prospect, agent_log }
      if (data.prospect) {
        onAddProspect(data.prospect as Prospect);
      }
      if (data.agent_log) {
        onAddLog(data.agent_log as AgentRunLog);
      }

      const durationSec = Math.max(1, Math.round((Date.now() - startedAt.getTime()) / 1000));
      setRunHistory(prev => [{ id: runId, startedAt, foundCount: data.prospect ? 1 : 0, durationSec }, ...prev]);
      setStatusText('Completed');
    } catch (err: any) {
      console.error('Discovery failed', err);
      setStatusText(err?.message || 'Discovery failed');
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
          Describe the type of buyer you are looking for. Results appear in your Queue.
        </p>
      </div>

      {/* Prompt area */}
      <div className="bg-panel border border-border rounded-md p-4 space-y-3">
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          disabled={isRunning}
          rows={3}
          placeholder="Find commercial fitness centers expanding in the GCC region..."
          className="w-full text-sm text-ink-secondary placeholder-ink-muted resize-none focus:outline-none border-none p-0 bg-transparent"
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

      {/* Run history */}
      {runHistory.length > 0 && (
        <div className="mt-8">
          <p className="text-xs font-medium text-ink-muted uppercase tracking-widest mb-3">Recent Runs</p>
          <div className="divide-y divide-border-subtle">
            {runHistory.map(run => (
              <div key={run.id} className="py-2.5 flex items-center justify-between text-sm">
                <div>
                  <span className="text-ink-secondary">
                    {run.startedAt.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}
                    {' '}
                    {run.startedAt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span className="text-ink-muted ml-2">
                    · Found {run.foundCount} prospect{run.foundCount !== 1 ? 's' : ''}
                  </span>
                </div>
                <span className="text-slate-400 text-xs tabular-nums">
                  {run.durationSec < 60 ? `${run.durationSec}s` : `${Math.round(run.durationSec / 60)}m`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatRelative(date: Date): string {
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
