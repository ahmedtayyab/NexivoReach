import { useMemo, useState } from 'react';
import type { Prospect, AgentRunLog } from '../types';
import { Loader2, Mail, MailWarning } from 'lucide-react';
import { leadRowToneClass, recipientEmail } from '../lib/leadTone';
import { computeOutcomes, hasEmail, isDueFollowUp } from '../lib/outcomes';
import { brandAssets } from '../lib/brandAssets';
import { FitScoreBadge } from './FitScoreBadge';
import { useConfirm } from './ConfirmDialog';
import OutcomesStrip from './OutcomesStrip';

const EMPTY_QUEUE_IMG = brandAssets.emptyQueue;

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
  onPrepareOutreach?: () => void | Promise<void>;
  onSendAllReady?: () => void | Promise<void>;
  onSendSelected?: (ids: string[]) => Promise<void> | void;
  onRefreshContacts?: (id: string) => Promise<void> | void;
  gmailConnected?: boolean;
  onGoWorkspace?: () => void;
}

type IntentFilter = 'all' | 'high' | 'low' | 'none';
type FitFilter = 'all' | 'high' | 'medium' | 'low' | 'score75' | 'score90';
type PriorityFilter = 'all' | 'priority' | 'nurture' | 'review' | 'low';
type CadenceFilter = 'all' | 'due' | 'missing_email';

export default function QueueView({
  prospects,
  agentLogs,
  onReviewProspect,
  onUpdateStage,
  onClearLeads,
  onPrepareOutreach,
  onSendAllReady,
  onSendSelected,
  onRefreshContacts,
  gmailConnected = false,
  onGoWorkspace,
}: Props) {
  const [filter, setFilter] = useState<string>('To contact');
  const [intentFilter, setIntentFilter] = useState<IntentFilter>('all');
  const [fitFilter, setFitFilter] = useState<FitFilter>('all');
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>('all');
  const [cadenceFilter, setCadenceFilter] = useState<CadenceFilter>('all');
  const [clearing, setClearing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [sendingSelected, setSendingSelected] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [sendingBest, setSendingBest] = useState(false);
  const [refreshingId, setRefreshingId] = useState('');
  const confirm = useConfirm();
  const lastRun = agentLogs[0];
  const lastRunLabel = lastRun ? formatRelative(lastRun.timestamp) : null;
  const outcomes = useMemo(() => computeOutcomes(prospects), [prospects]);

  const handleClear = async () => {
    if (!onClearLeads || !prospects.length || clearing) return;
    const ok = await confirm({
      title: 'Clear all leads?',
      body: `Remove all ${prospects.length} leads for this company. This cannot be undone.`,
      confirmLabel: 'Clear leads',
      tone: 'danger',
    });
    if (!ok) return;
    setClearing(true);
    try {
      await onClearLeads();
      setSelectedIds([]);
    } finally {
      setClearing(false);
    }
  };

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
    if (cadenceFilter === 'due' && !isDueFollowUp(p)) return false;
    if (cadenceFilter === 'missing_email' && hasEmail(p)) return false;
    if (filter === 'All') return true;
    return normalizeStage(p.stage) === filter;
  });

  const filtersActive =
    intentFilter !== 'all' ||
    fitFilter !== 'all' ||
    priorityFilter !== 'all' ||
    cadenceFilter !== 'all';

  const handleRefreshEmail = async (id: string) => {
    if (!onRefreshContacts || refreshingId) return;
    setRefreshingId(id);
    try {
      await onRefreshContacts(id);
    } finally {
      setRefreshingId('');
    }
  };

  const emailCell = (prospect: Prospect) => {
    const email = recipientEmail(prospect);
    if (email) {
      return (
        <span className="lead-email is-ok" title={email}>
          <Mail className="w-3 h-3 shrink-0" strokeWidth={1.75} />
          <span className="truncate">{email}</span>
        </span>
      );
    }
    return (
      <span className="lead-email is-missing">
        <MailWarning className="w-3 h-3 shrink-0" strokeWidth={1.75} />
        <span>No email</span>
        {onRefreshContacts && (
          <button
            type="button"
            className="linkish lead-email__find"
            disabled={refreshingId === prospect.id}
            onClick={e => {
              e.stopPropagation();
              void handleRefreshEmail(prospect.id);
            }}
          >
            {refreshingId === prospect.id ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Find'}
          </button>
        )}
      </span>
    );
  };
  const visibleIds = visible.map(p => p.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every(id => selectedIds.includes(id));

  const toggleSelected = (id: string) => {
    setSelectedIds(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]));
  };

  const toggleSelectAllVisible = () => {
    if (allVisibleSelected) {
      setSelectedIds(prev => prev.filter(id => !visibleIds.includes(id)));
      return;
    }
    setSelectedIds(prev => Array.from(new Set([...prev, ...visibleIds])));
  };

  const handleSendSelected = async () => {
    if (!onSendSelected || selectedIds.length === 0) return;
    const count = selectedIds.length;
    const ok = await confirm({
      title: count === 1 ? 'Send this lead?' : `Send ${count} selected leads?`,
      body: `Prepare and send outreach for ${count} selected lead${count === 1 ? '' : 's'} via Gmail.`,
      confirmLabel: count === 1 ? 'Send email' : 'Send emails',
      tone: 'send',
    });
    if (!ok) return;
    setSendingSelected(true);
    try {
      await onSendSelected(selectedIds);
      setSelectedIds([]);
    } finally {
      setSendingSelected(false);
    }
  };

  return (
    <div className="max-w-6xl w-full">
      <div className="page-header nr-enter">
        <h1 className="page-header__title">Leads</h1>
        <p className="page-header__desc">
          {prospects.length} saved
          {lastRunLabel && <span className="text-ink-muted"> · Last scan {lastRunLabel}</span>}
          {outcomes.dueFollowUp > 0 && (
            <span className="text-ink-muted"> · {outcomes.dueFollowUp} due for follow-up</span>
          )}
        </p>
      </div>

      <OutcomesStrip outcomes={outcomes} className="mb-4 nr-enter nr-enter-delay-1" />

      <div className="toolbar nr-enter nr-enter-delay-1">
        {onSendSelected && gmailConnected && selectedIds.length > 0 && (
          <button
            type="button"
            onClick={() => void handleSendSelected()}
            disabled={sendingSelected}
            className="btn btn-primary"
          >
            {sendingSelected ? 'Sending…' : `Send selected (${selectedIds.length})`}
          </button>
        )}
        {onSendAllReady && gmailConnected && (
          <button
            type="button"
            disabled={sendingBest}
            onClick={() => {
              void (async () => {
                setSendingBest(true);
                try {
                  await onSendAllReady();
                } finally {
                  setSendingBest(false);
                }
              })();
            }}
            className="btn btn-primary"
          >
            {sendingBest ? 'Sending…' : 'Send best-fit'}
          </button>
        )}
        {onPrepareOutreach && prospects.some(p => !p.outreachDraft && (
          (p.fitScore || 0) >= 75
          || (p.fitBreakdown?.fitSummary || '').toLowerCase() === 'high'
          || ['priority', 'nurture'].includes((p.priority || p.fitBreakdown?.priority || '').toLowerCase())
        )) && (
          <button
            type="button"
            disabled={preparing}
            onClick={() => {
              void (async () => {
                setPreparing(true);
                try {
                  await onPrepareOutreach();
                } finally {
                  setPreparing(false);
                }
              })();
            }}
            className="btn btn-secondary"
          >
            {preparing ? 'Preparing…' : 'Prepare outreach'}
          </button>
        )}
        {selectedIds.length > 0 && (
          <button type="button" onClick={() => setSelectedIds([])} className="btn btn-ghost">
            Clear selection
          </button>
        )}
        {onClearLeads && prospects.length > 0 && (
          <button
            type="button"
            onClick={handleClear}
            disabled={clearing}
            className="btn btn-ghost"
          >
            {clearing ? 'Clearing…' : 'Clear all'}
          </button>
        )}
        <span className="toolbar-spacer" />
        <span className="text-[12px] text-ink-muted tabular-nums">
          {visible.length} shown
          {filtersActive || filter !== 'All' ? ` of ${prospects.length}` : ''}
          {selectedIds.length > 0 ? ` · ${selectedIds.length} selected` : ''}
        </span>
      </div>

      <div className="filter-bar nr-enter nr-enter-delay-2">
        <label className="inline-flex items-center gap-1.5 text-[12px] text-ink-secondary">
          <span className="text-ink-muted shrink-0">Cadence</span>
          <select
            value={cadenceFilter}
            onChange={e => setCadenceFilter(e.target.value as CadenceFilter)}
          >
            <option value="all">All</option>
            <option value="due">Due follow-up ({outcomes.dueFollowUp})</option>
            <option value="missing_email">Missing email ({outcomes.missingEmail})</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1.5 text-[12px] text-ink-secondary">
          <span className="text-ink-muted shrink-0">Intent</span>
          <select
            value={intentFilter}
            onChange={e => setIntentFilter(e.target.value as IntentFilter)}
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
          >
            <option value="all">All</option>
            <option value="priority">Strong (Priority)</option>
            <option value="nurture">Strong (Nurture)</option>
            <option value="review">Average (Review)</option>
            <option value="low">Average (Low)</option>
          </select>
        </label>
        {filtersActive && (
          <button
            type="button"
            onClick={() => {
              setIntentFilter('all');
              setFitFilter('all');
              setPriorityFilter('all');
              setCadenceFilter('all');
            }}
            className="btn btn-ghost"
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="seg mb-4 overflow-x-auto max-w-full nr-enter nr-enter-delay-2" role="group" aria-label="Lead stage">
        <button
          type="button"
          className={filter === 'All' ? 'is-active' : undefined}
          onClick={() => setFilter('All')}
        >
          All {stageCounts.All || 0}
        </button>
        {LEAD_STAGES.map(s => (
          <button
            key={s}
            type="button"
            className={filter === s ? 'is-active' : undefined}
            onClick={() => setFilter(s)}
          >
            {s} {stageCounts[s] || 0}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="empty-state nr-enter nr-enter-delay-3">
          <div className="empty-state__art-wrap">
            <img
              src={EMPTY_QUEUE_IMG}
              alt=""
              className="empty-state__art"
              loading="lazy"
              decoding="async"
            />
          </div>
          <p className="empty-state__title">No leads match these filters</p>
          <p className="empty-state__desc">
            {filtersActive || filter !== 'All'
              ? 'Try clearing Intent / Fit / Priority or switch status to All.'
              : 'Describe who to find in Hunt, then run Find buyers. Qualified accounts land here.'}
          </p>
          {!(filtersActive || filter !== 'All') && onGoWorkspace && (
            <button type="button" className="btn btn-primary mt-4" onClick={onGoWorkspace}>
              Find buyers
            </button>
          )}
        </div>
      ) : (
        <>
          <div key={`m-${filter}-${intentFilter}-${fitFilter}-${priorityFilter}-${cadenceFilter}`} className="md:hidden space-y-2 nr-stagger">
            {visible.map(prospect => (
              <div
                key={prospect.id}
                className={`bg-panel border border-border p-3 lead-row-tone ${leadRowToneClass(prospect)}`}
              >
                <div className="flex items-start gap-2">
                  {onSendSelected && (
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(prospect.id)}
                      onChange={() => toggleSelected(prospect.id)}
                      className="mt-1 h-4 w-4 accent-[var(--accent)] shrink-0"
                      aria-label={`Select ${prospect.companyName}`}
                    />
                  )}
                  <button type="button" className="text-left w-full min-w-0" onClick={() => onReviewProspect(prospect.id)}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[13.5px] font-medium text-ink truncate">{prospect.companyName}</p>
                        <p className="text-[13px] text-ink-muted truncate mt-0.5">
                          {prospect.location || prospect.website || '—'}
                        </p>
                      </div>
                      <FitScoreBadge score={prospect.fitScore} />
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-[12.5px] text-ink-muted">
                      <span className="capitalize">{prospect.source || 'web'}</span>
                      <span className="capitalize">Intent {prospect.intent || prospect.fitBreakdown?.intent || '—'}</span>
                    </div>
                  </button>
                </div>
                <div className="mt-2">{emailCell(prospect)}</div>
                <select
                  value={normalizeStage(prospect.stage)}
                  onChange={e => onUpdateStage(prospect.id, e.target.value as Prospect['stage'])}
                  className="mt-3 w-full text-[12px] border border-border px-2 py-1.5 bg-panel text-ink-secondary"
                >
                  {LEAD_STAGES.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          <div className="hidden md:block nr-enter nr-enter-delay-3">
            <div className="data-table">
              <div className="data-table__head">
                <span>
                  {onSendSelected ? (
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAllVisible}
                      className="h-3.5 w-3.5 accent-[var(--accent)]"
                      aria-label="Select all visible leads"
                    />
                  ) : null}
                </span>
                <span>Lead</span>
                <span>Email</span>
                <span>Intent</span>
                <span className="text-right">Fit</span>
                <span className="text-right">Status</span>
              </div>
              <div key={`d-${filter}-${intentFilter}-${fitFilter}-${priorityFilter}-${cadenceFilter}`} className="nr-stagger">
                {visible.map(prospect => (
                  <div
                    key={prospect.id}
                    className={`data-table__row lead-row-tone ${leadRowToneClass(prospect)}`}
                  >
                    <span>
                      {onSendSelected && (
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(prospect.id)}
                          onChange={() => toggleSelected(prospect.id)}
                          className="h-3.5 w-3.5 accent-[var(--accent)]"
                          aria-label={`Select ${prospect.companyName}`}
                        />
                      )}
                    </span>
                    <button type="button" className="text-left min-w-0" onClick={() => onReviewProspect(prospect.id)}>
                      <p className="text-[13.5px] font-medium text-ink truncate">{prospect.companyName}</p>
                      <p className="text-[13px] text-ink-muted truncate mt-px">
                        {prospect.location || prospect.website || '—'}
                      </p>
                    </button>
                    <span className="min-w-0">{emailCell(prospect)}</span>
                    <span className="text-[13px] text-ink-muted capitalize">{prospect.intent || prospect.fitBreakdown?.intent || '—'}</span>
                    <span className="text-right justify-self-end">
                      <FitScoreBadge score={prospect.fitScore} />
                    </span>
                    <select
                      value={normalizeStage(prospect.stage)}
                      onChange={e => onUpdateStage(prospect.id, e.target.value as Prospect['stage'])}
                      className="text-[12px] border border-border px-1.5 py-1 bg-panel text-ink-secondary w-full"
                    >
                      {LEAD_STAGES.map(s => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
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
