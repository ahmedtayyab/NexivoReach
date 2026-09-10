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
  onSendAllReady?: () => void;
  gmailConnected?: boolean;
  onGoWorkspace?: () => void;
}

type IntentFilter = 'all' | 'high' | 'low' | 'none';
type FitFilter = 'all' | 'high' | 'medium' | 'low' | 'score75' | 'score90';
type PriorityFilter = 'all' | 'priority' | 'nurture' | 'review' | 'low';

export default function QueueView({
  prospects,
  agentLogs,
  onReviewProspect,
  onUpdateStage,
  onClearLeads,
  onPrepareOutreach,
  onSendAllReady,
  gmailConnected = false,
  onGoWorkspace,
}: Props) {
  const [filter, setFilter] = useState<string>('To contact');
  const [intentFilter, setIntentFilter] = useState<IntentFilter>('all');
  const [fitFilter, setFitFilter] = useState<FitFilter>('all');
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>('all');
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

  const qualityFiltered = useMemo(() => {
    return prospects.filter(p => matchesQualityFilters(p, intentFilter, fitFilter, priorityFilter));
  }, [prospects, intentFilter, fitFilter, priorityFilter]);

  const stageCounts = useMemo(() => {
    const map: Record<string, number> = { All: qualityFiltered.length };
    for (const s of LEAD_STAGES) map[s] = 0;
    for (const p of qualityFiltered) {
      const key = normalizeStage(p.stage);
      map[key] = (map[key] || 0) + 1;
    }
    return map;
  }, [qualityFiltered]);

  const visible = qualityFiltered.filter(p => {
    if (filter === 'All') return true;
    return normalizeStage(p.stage) === filter;
  });

  const filtersActive = intentFilter !== 'all' || fitFilter !== 'all' || priorityFilter !== 'all';
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
          {onSendAllReady && gmailConnected && (
            <button
              type="button"
              onClick={() => onSendAllReady()}
              className="px-3 py-1.5 text-[12px] bg-accent hover:bg-accent-hover text-white rounded-md nr-btn-press"
            >
              Send emails
            </button>
          )}
          {onPrepareOutreach && prospects.some(p => !p.outreachDraft && (
            (p.fitScore || 0) >= 75
            || (p.fitBreakdown?.fitSummary || '').toLowerCase() === 'high'
            || ['priority', 'nurture'].includes((p.priority || p.fitBreakdown?.priority || '').toLowerCase())
          )) && (
            <button
              type="button"
              onClick={() => onPrepareOutreach()}
              className="px-3 py-1.5 text-[12px] border border-border text-ink-secondary hover:text-ink hover:border-ink-muted rounded-md nr-btn-press"
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

      <div className="flex flex-wrap items-center gap-2 mb-3 nr-enter nr-enter-delay-2">
        <label className="inline-flex items-center gap-1.5 text-[12px] text-ink-secondary">
          <span className="text-ink-muted shrink-0">Intent</span>
          <select
            value={intentFilter}
            onChange={e => setIntentFilter(e.target.value as IntentFilter)}
            className="text-[12px] border border-border rounded-md px-2 py-1 bg-panel text-ink"
          >
            <option value="all">All</option>
            <option value="high">High</option>
            <option value="low">Low</option>
            <option value="none">None</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1.5 text-[12px] text-ink-secondary">
          <span className="text-ink-muted shrink-0">Fit</span>
          <select
            value={fitFilter}
            onChange={e => setFitFilter(e.target.value as FitFilter)}
            className="text-[12px] border border-border rounded-md px-2 py-1 bg-panel text-ink"
          >
            <option value="all">All</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="score90">Score 90+</option>
            <option value="score75">Score 75+</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1.5 text-[12px] text-ink-secondary">
          <span className="text-ink-muted shrink-0">Priority</span>
          <select
            value={priorityFilter}
            onChange={e => setPriorityFilter(e.target.value as PriorityFilter)}
            className="text-[12px] border border-border rounded-md px-2 py-1 bg-panel text-ink"
          >
            <option value="all">All</option>
            <option value="priority">Priority</option>
            <option value="nurture">Nurture</option>
            <option value="review">Review</option>
            <option value="low">Low</option>
          </select>
        </label>
        {filtersActive && (
          <button
            type="button"
            onClick={() => {
              setIntentFilter('all');
              setFitFilter('all');
              setPriorityFilter('all');
            }}
            className="text-[12px] text-accent hover:underline"
          >
            Clear filters
          </button>
        )}
        <span className="text-[12px] text-ink-muted ml-auto tabular-nums">
          {visible.length} shown
          {filtersActive || filter !== 'All' ? ` of ${prospects.length}` : ''}
        </span>
      </div>

      <div className="flex flex-nowrap sm:flex-wrap gap-1.5 mb-4 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-none nr-enter nr-enter-delay-2">
        <FilterChip label="All" count={stageCounts.All || 0} active={filter === 'All'} onClick={() => setFilter('All')} />
        {LEAD_STAGES.map(s => (
          <FilterChip
            key={s}
            label={s}
            count={stageCounts[s] || 0}
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
        <div className="empty-state nr-enter nr-enter-delay-3">
          <img
            src={EMPTY_QUEUE_IMG}
            alt=""
            className="empty-state__art"
          />
          <p className="empty-state__title">No leads match these filters</p>
          <p className="empty-state__desc">
            {filtersActive || filter !== 'All'
              ? 'Try clearing Intent / Fit / Priority or switch status to All.'
              : 'Brief the agent in Workspace, then run Find buyers. Qualified accounts land here.'}
          </p>
          {!(filtersActive || filter !== 'All') && onGoWorkspace && (
            <button type="button" className="btn btn-primary mt-4" onClick={onGoWorkspace}>
              Open Workspace
            </button>
          )}
        </div>
      ) : (
        <>
          <div key={`m-${filter}-${intentFilter}-${fitFilter}-${priorityFilter}`} className="md:hidden space-y-2 nr-stagger">
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
            <div key={`d-${filter}-${intentFilter}-${fitFilter}-${priorityFilter}`} className="divide-y divide-border-subtle nr-stagger">
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

function prospectIntent(p: Prospect): string {
  return (p.intent || p.fitBreakdown?.intent || 'none').toLowerCase();
}

function prospectFitSummary(p: Prospect): string {
  return (p.fitBreakdown?.fitSummary || p.icpFit || '').toLowerCase();
}

function prospectPriority(p: Prospect): string {
  return (p.priority || p.fitBreakdown?.priority || '').toLowerCase();
}

function matchesQualityFilters(
  p: Prospect,
  intentFilter: IntentFilter,
  fitFilter: FitFilter,
  priorityFilter: PriorityFilter,
): boolean {
  if (intentFilter !== 'all' && prospectIntent(p) !== intentFilter) return false;

  if (fitFilter === 'score90' && (p.fitScore || 0) < 90) return false;
  if (fitFilter === 'score75' && (p.fitScore || 0) < 75) return false;
  if (fitFilter === 'high' || fitFilter === 'medium' || fitFilter === 'low') {
    const summary = prospectFitSummary(p);
    if (summary) {
      if (summary !== fitFilter) return false;
    } else {
      // Fall back to score bands when summary is missing
      const score = p.fitScore || 0;
      if (fitFilter === 'high' && score < 75) return false;
      if (fitFilter === 'medium' && (score < 55 || score >= 75)) return false;
      if (fitFilter === 'low' && score >= 55) return false;
    }
  }

  if (priorityFilter !== 'all' && prospectPriority(p) !== priorityFilter) return false;
  return true;
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
