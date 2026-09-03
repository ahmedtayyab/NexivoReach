import { useMemo, useState } from 'react';
import type { Prospect, AgentRunLog } from '../types';

export const LEAD_STAGES = [
  'To contact',
  'Contacted',
  'Replied',
  'Re-contact',
  'Denied',
  'Avoid',
  'Meeting',
  'Won',
] as const;

interface Props {
  prospects: Prospect[];
  agentLogs: AgentRunLog[];
  onReviewProspect: (id: string) => void;
  onUpdateStage: (id: string, stage: Prospect['stage']) => void;
  onClearLeads?: () => Promise<void> | void;
}

export default function QueueView({
  prospects,
  agentLogs,
  onReviewProspect,
  onUpdateStage,
  onClearLeads,
}: Props) {
  const [filter, setFilter] = useState<string>('To contact');
  const [clearing, setClearing] = useState(false);
  const lastRun = agentLogs[0];
  const lastRunLabel = lastRun ? formatRelative(lastRun.timestamp) : null;

  const handleClear = async () => {
    if (!onClearLeads || !prospects.length || clearing) return;
    const ok = window.confirm(
      `Clear all ${prospects.length} leads for this company? This cannot be undone.`,
    );
    if (!ok) return;
    setClearing(true);
    try {
      await onClearLeads();
    } finally {
      setClearing(false);
    }
  };

  const counts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of LEAD_STAGES) map[s] = 0;
    for (const p of prospects) {
      const key = normalizeStage(p.stage);
      map[key] = (map[key] || 0) + 1;
    }
    return map;
  }, [prospects]);

  const visible = prospects.filter(p => {
    if (filter === 'All') return true;
    return normalizeStage(p.stage) === filter;
  });

  return (
    <div className="max-w-3xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[15px] font-semibold text-ink tracking-tight">Leads</h1>
          <p className="text-[13px] text-ink-secondary mt-0.5">
            {prospects.length} saved
            {lastRunLabel && <span className="text-ink-muted"> · Last scan {lastRunLabel}</span>}
          </p>
        </div>
        {onClearLeads && prospects.length > 0 && (
          <button
            type="button"
            onClick={handleClear}
            disabled={clearing}
            className="shrink-0 px-3 py-1.5 text-[12px] border border-border rounded-md text-ink-secondary hover:text-ink hover:border-ink-muted disabled:opacity-40 transition-colors"
          >
            {clearing ? 'Clearing…' : 'Clear all leads'}
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5 mb-4">
        <FilterChip label="All" count={prospects.length} active={filter === 'All'} onClick={() => setFilter('All')} />
        {LEAD_STAGES.map(s => (
          <FilterChip
            key={s}
            label={s}
            count={counts[s] || 0}
            active={filter === s}
            onClick={() => setFilter(s)}
          />
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="bg-panel border border-border rounded-lg px-5 py-10 text-center">
          <p className="text-[13.5px] font-medium text-ink-secondary">No leads in this bucket</p>
          <p className="text-[13px] text-ink-muted mt-1">
            Run Discover to hunt buyers from your catalog, then update their status here.
          </p>
        </div>
      ) : (
        <div className="bg-panel border border-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-[1fr_90px_72px_56px_140px] items-center px-4 py-2 border-b border-border-subtle bg-muted">
            <span className="section-label">Lead</span>
            <span className="section-label">Source</span>
            <span className="section-label">Intent</span>
            <span className="section-label text-right">Fit</span>
            <span className="section-label text-right">Status</span>
          </div>
          <div className="divide-y divide-border-subtle">
            {visible.map(prospect => (
              <div
                key={prospect.id}
                className="grid grid-cols-[1fr_90px_72px_56px_140px] items-center px-4 py-3 gap-2 hover:bg-canvas/60"
              >
                <button type="button" className="text-left min-w-0" onClick={() => onReviewProspect(prospect.id)}>
                  <p className="text-[13.5px] font-medium text-ink truncate">{prospect.companyName}</p>
                  <p className="text-[12px] text-ink-muted truncate mt-px">
                    {prospect.location || prospect.website || '—'}
                  </p>
                </button>
                <span className="text-[12px] text-ink-muted capitalize">{prospect.source || 'web'}</span>
                <span className="text-[12px] text-ink-muted capitalize">{prospect.intent || prospect.fitBreakdown?.intent || '—'}</span>
                <span className="text-[13px] font-semibold text-right tabular-nums">{prospect.fitScore}</span>
                <select
                  value={normalizeStage(prospect.stage)}
                  onChange={e => onUpdateStage(prospect.id, e.target.value as Prospect['stage'])}
                  className="text-[12px] border border-border rounded-md px-1.5 py-1 bg-panel text-ink-secondary"
                >
                  {LEAD_STAGES.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FilterChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2.5 py-1 rounded-full text-[12px] border transition-colors ${
        active ? 'bg-ink text-panel-elevated border-ink' : 'bg-panel border-border text-ink-secondary hover:border-ink-muted'
      }`}
    >
      {label} {count}
    </button>
  );
}

function normalizeStage(stage: string): string {
  const map: Record<string, string> = {
    New: 'To contact',
    Qualified: 'To contact',
    Researched: 'To contact',
  };
  return map[stage] || stage || 'To contact';
}

function formatRelative(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp.replace(' ', 'T')).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
