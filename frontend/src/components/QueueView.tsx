import { useMemo, useState } from 'react';
import type { Prospect, AgentRunLog } from '../types';
import LeadPipeline from './brand/LeadPipeline';
import { leadRowToneClass } from '../lib/leadTone';

const EMPTY_QUEUE_IMG = '/brand/empty-queue.jpg';

const LEAD_STAGES = [
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
  onPrepareOutreach?: () => void;
}

export default function QueueView({
  prospects,
  agentLogs,
  onReviewProspect,
  onUpdateStage,
  onClearLeads,
  onPrepareOutreach,
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
  const pipelineLive = (counts['To contact'] || 0) + (counts['Re-contact'] || 0) > 0;

  return (
    <div className="max-w-3xl w-full">
      <div className="mb-6 flex items-start justify-between gap-3 nr-enter">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold text-ink tracking-tight">Leads</h1>
          <p className="text-[13px] text-ink-secondary mt-0.5">
            {prospects.length} saved
            {lastRunLabel && <span className="text-ink-muted"> · Last scan {lastRunLabel}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {onPrepareOutreach && prospects.some(p => !p.outreachDraft && (
            (p.fitScore || 0) >= 75
            || (p.fitBreakdown?.fitSummary || '').toLowerCase() === 'high'
            || ['priority', 'nurture'].includes((p.priority || p.fitBreakdown?.priority || '').toLowerCase())
          )) && (
            <button
              type="button"
              onClick={() => onPrepareOutreach()}
              className="px-3 py-1.5 text-[12px] bg-accent hover:bg-accent-hover text-white rounded-md nr-btn-press"
            >
              Prepare outreach
            </button>
          )}
          {onClearLeads && prospects.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              disabled={clearing}
              className="px-3 py-1.5 text-[12px] border border-border rounded-md text-ink-secondary hover:text-ink hover:border-ink-muted disabled:opacity-40 nr-btn-press"
            >
              {clearing ? 'Clearing…' : 'Clear all'}
            </button>
          )}
        </div>
      </div>

      <div className="mb-5 nr-enter nr-enter-delay-1">
        <LeadPipeline active={pipelineLive} />
      </div>

      <div className="flex flex-nowrap sm:flex-wrap gap-1.5 mb-4 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-none nr-enter nr-enter-delay-2">
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

      {visible.length > 0 && (
        <div className="lead-tone-legend nr-enter nr-enter-delay-2" aria-hidden>
          <span><i className="lead-tone-swatch lead-tone-swatch-draft" /> Draft ready</span>
          <span><i className="lead-tone-swatch lead-tone-swatch-sent" /> Outreached / contacted</span>
          <span><i className="lead-tone-swatch lead-tone-swatch-replied" /> They replied</span>
          <span><i className="lead-tone-swatch lead-tone-swatch-recontact" /> Re-contact</span>
          <span><i className="lead-tone-swatch lead-tone-swatch-denied" /> Denied / avoid</span>
        </div>
      )}

      {visible.length === 0 ? (
        <div className="bg-panel border border-border rounded-lg px-5 py-8 sm:py-10 text-center nr-panel nr-enter nr-enter-delay-3">
          <img
            src={EMPTY_QUEUE_IMG}
            alt="Empty leads queue"
            className="mx-auto mb-5 w-full max-w-[280px] sm:max-w-[360px] rounded-lg border border-border-subtle shadow-sm object-cover nr-empty-art"
          />
          <p className="text-[13.5px] font-medium text-ink-secondary">No leads in this bucket</p>
          <p className="text-[13px] text-ink-muted mt-1 max-w-sm mx-auto">
            Run Discover to hunt buyers from your catalog, then update their status here.
          </p>
        </div>
      ) : (
        <>
          <div key={`m-${filter}`} className="md:hidden space-y-2 nr-stagger">
            {visible.map(prospect => (
              <div
                key={prospect.id}
                className={`bg-panel border border-border rounded-lg p-3.5 nr-panel lead-row-tone ${leadRowToneClass(prospect)}`}
              >
                <button type="button" className="text-left w-full min-w-0" onClick={() => onReviewProspect(prospect.id)}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13.5px] font-medium text-ink truncate">{prospect.companyName}</p>
                      <p className="text-[12px] text-ink-muted truncate mt-0.5">
                        {prospect.location || prospect.website || '—'}
                      </p>
                    </div>
                    <span className="text-[14px] font-semibold tabular-nums shrink-0">{prospect.fitScore}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-[12px] text-ink-muted">
                    <span className="capitalize">{prospect.source || 'web'}</span>
                    <span className="capitalize">Intent {prospect.intent || prospect.fitBreakdown?.intent || '—'}</span>
                  </div>
                </button>
                <select
                  value={normalizeStage(prospect.stage)}
                  onChange={e => onUpdateStage(prospect.id, e.target.value as Prospect['stage'])}
                  className="mt-3 w-full text-[12px] border border-border rounded-md px-2 py-1.5 bg-panel text-ink-secondary"
                >
                  {LEAD_STAGES.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          <div className="hidden md:block bg-panel border border-border rounded-lg overflow-hidden nr-panel nr-enter nr-enter-delay-3">
            <div className="grid grid-cols-[1fr_90px_72px_56px_140px] items-center px-4 py-2 border-b border-border-subtle bg-muted">
              <span className="section-label">Lead</span>
              <span className="section-label">Source</span>
              <span className="section-label">Intent</span>
              <span className="section-label text-right">Fit</span>
              <span className="section-label text-right">Status</span>
            </div>
            <div key={`d-${filter}`} className="divide-y divide-border-subtle nr-stagger">
              {visible.map(prospect => (
                <div
                  key={prospect.id}
                  className={`grid grid-cols-[1fr_90px_72px_56px_140px] items-center px-4 py-3 gap-2 nr-row lead-row-tone ${leadRowToneClass(prospect)}`}
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
        </>
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
      className={`nr-chip shrink-0 px-2.5 py-1 rounded-full text-[12px] border ${
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
