import { useEffect, useMemo, useState } from 'react';
import type { Prospect, AgentRunLog } from '../types';
import { ArrowDown, ArrowUp, Loader2, Mail, MailWarning } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { leadRowToneClass, recipientEmail } from '../lib/leadTone';
import { computeOutcomes, hasEmail } from '../lib/outcomes';
import { brandAssets } from '../lib/brandAssets';
import { FitScoreBadge } from './FitScoreBadge';
import { useConfirm } from './ConfirmDialog';
import PageAmbient from './brand/PageAmbient';
import TemplatesCta from './TemplatesCta';

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
  onPrepareOutreach?: (ids?: string[]) => void | Promise<void>;
  onSendAllReady?: () => void | Promise<void>;
  onSendSelected?: (ids: string[]) => Promise<void> | void;
  onRefreshContacts?: (id: string) => Promise<void> | void;
  gmailConnected?: boolean;
  onGoWorkspace?: () => void;
  templateCount?: number;
  onGoTemplates?: () => void;
  /** After a hunt finishes, focus Latest hunt + With email. */
  preferLatestHunt?: boolean;
  onPreferLatestHuntHandled?: () => void;
}

type SortKey = 'fit' | 'intent';
type SortDir = 'asc' | 'desc';
type HuntScope = 'latest' | 'all';
type EmailFilter = 'all' | 'has_email' | 'missing_email';

const INTENT_RANK: Record<string, number> = { high: 3, low: 2, none: 1 };

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
  templateCount = 0,
  onGoTemplates,
  preferLatestHunt = false,
  onPreferLatestHuntHandled,
}: Props) {
  const [filter, setFilter] = useState<string>('All');
  const [huntScope, setHuntScope] = useState<HuntScope>('all');
  const [emailFilter, setEmailFilter] = useState<EmailFilter>('all');
  const [clearing, setClearing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [sendingSelected, setSendingSelected] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [preparingKind, setPreparingKind] = useState<'selected' | 'best' | ''>('');
  const [sendingBest, setSendingBest] = useState(false);
  const [refreshingId, setRefreshingId] = useState('');
  const [sortKey, setSortKey] = useState<SortKey | null>('fit');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const confirm = useConfirm();
  const lastRun = agentLogs[0];
  const lastRunLabel = lastRun ? formatRelative(lastRun.timestamp) : null;

  const latestHuntId = useMemo(() => {
    let bestId = '';
    let bestAt = '';
    for (const p of prospects) {
      const jid = (p.discoveryJobId || '').trim();
      if (!jid) continue;
      const at = p.discoveredAt || '';
      if (!bestId || at > bestAt) {
        bestId = jid;
        bestAt = at;
      }
    }
    return bestId;
  }, [prospects]);

  const latestHuntProspects = useMemo(() => {
    if (!latestHuntId) return [];
    return prospects.filter(p => (p.discoveryJobId || '') === latestHuntId);
  }, [prospects, latestHuntId]);

  useEffect(() => {
    if (!preferLatestHunt || !latestHuntId) return;
    setHuntScope('latest');
    setEmailFilter('has_email');
    setFilter('All');
    onPreferLatestHuntHandled?.();
  }, [preferLatestHunt, latestHuntId, onPreferLatestHuntHandled]);

  const scopedProspects = huntScope === 'latest' && latestHuntId ? latestHuntProspects : prospects;
  const outcomes = useMemo(() => computeOutcomes(scopedProspects), [scopedProspects]);

  const handleClear = async () => {
    if (!onClearLeads || !prospects.length || clearing) return;
    const ok = await confirm({
      title: 'Clear all leads?',
      body:
        `Remove all ${prospects.length} leads for this company. This cannot be undone. ` +
        'Hunt memory (previously seen websites) is kept — use Find buyers → Start over if you want the next hunt to rediscover them from page 1.',
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

  const stageCounts = useMemo(() => {
    const map: Record<string, number> = { All: scopedProspects.length };
    for (const s of LEAD_STAGES) map[s] = 0;
    for (const p of scopedProspects) {
      const key = normalizeStage(p.stage);
      map[key] = (map[key] || 0) + 1;
    }
    return map;
  }, [scopedProspects]);

  const visible = useMemo(() => {
    const rows = scopedProspects.filter(p => {
      if (emailFilter === 'has_email' && !hasEmail(p)) return false;
      if (emailFilter === 'missing_email' && hasEmail(p)) return false;
      if (filter === 'All') return true;
      return normalizeStage(p.stage) === filter;
    });
    if (!sortKey) return rows;
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (sortKey === 'fit') {
        const diff = (Number(a.fitScore) || 0) - (Number(b.fitScore) || 0);
        if (diff !== 0) return diff * dir;
      } else {
        const ai = INTENT_RANK[prospectIntent(a)] ?? 0;
        const bi = INTENT_RANK[prospectIntent(b)] ?? 0;
        if (ai !== bi) return (ai - bi) * dir;
        const scoreDiff = (Number(a.fitScore) || 0) - (Number(b.fitScore) || 0);
        if (scoreDiff !== 0) return scoreDiff * -1;
      }
      return (a.companyName || '').localeCompare(b.companyName || '');
    });
  }, [scopedProspects, emailFilter, filter, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'desc' ? 'asc' : 'desc'));
      return;
    }
    setSortKey(key);
    setSortDir('desc');
  };

  const filtersActive = huntScope !== 'all' || emailFilter !== 'all' || filter !== 'All';

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
            title="Hunt only checks the homepage quickly. Find crawls contact pages on this site."
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
    <div className="page-shell max-w-6xl w-full">
      {prospects.length > 0 && <PageAmbient variant="leads" tone="whisper" />}
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

      {onGoTemplates && (
        <div className="templates-cta-row nr-enter nr-enter-delay-1">
          <TemplatesCta templateCount={templateCount} onClick={onGoTemplates} />
          {templateCount <= 0 && (
            <p className="templates-cta-row__hint">
              Write your emails once — Prepare will match by category.
            </p>
          )}
        </div>
      )}

      <div className="toolbar nr-enter nr-enter-delay-1">
        <button
          type="button"
          className={`btn btn-primary${emailFilter === 'has_email' ? '' : ' nr-soft-pulse'}`}
          aria-pressed={emailFilter === 'has_email'}
          onClick={() => {
            setEmailFilter('has_email');
            setFilter('All');
          }}
          title="Show only leads you can email"
        >
          With email ({outcomes.withEmail || 0})
        </button>
        <button
          type="button"
          className={emailFilter === 'missing_email' ? 'btn btn-secondary' : 'btn btn-ghost'}
          onClick={() => {
            setEmailFilter(emailFilter === 'missing_email' ? 'all' : 'missing_email');
            setFilter('All');
          }}
        >
          No email ({outcomes.missingEmail || 0})
        </button>
        {latestHuntId ? (
          <button
            type="button"
            className={huntScope === 'latest' ? 'btn btn-secondary' : 'btn btn-ghost'}
            onClick={() => setHuntScope(huntScope === 'latest' ? 'all' : 'latest')}
          >
            Latest hunt ({latestHuntProspects.length})
          </button>
        ) : null}
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => {
            void (async () => {
              try {
                const resp = await apiFetch('/api/prospects/export.csv');
                if (!resp.ok) throw new Error(await resp.text());
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'nexivoreach-leads.csv';
                a.click();
                URL.revokeObjectURL(url);
              } catch (err) {
                console.error(err);
              }
            })();
          }}
        >
          Export CSV
        </button>
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
        {onPrepareOutreach && selectedIds.length > 0 && (
          <button
            type="button"
            disabled={preparing}
            onClick={() => {
              void (async () => {
                setPreparing(true);
                setPreparingKind('selected');
                try {
                  await onPrepareOutreach(selectedIds);
                } finally {
                  setPreparing(false);
                  setPreparingKind('');
                }
              })();
            }}
            className="btn btn-primary nr-soft-pulse"
            title="Draft outreach only for the leads you’ve checked"
          >
            {preparingKind === 'selected' ? 'Preparing…' : `Prepare selected (${selectedIds.length})`}
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
                setPreparingKind('best');
                try {
                  await onPrepareOutreach();
                } finally {
                  setPreparing(false);
                  setPreparingKind('');
                }
              })();
            }}
            className={selectedIds.length > 0 ? 'btn btn-secondary' : 'btn btn-primary'}
            title="Draft outreach for all high-fit leads that don’t have a draft yet"
          >
            {preparingKind === 'best' ? 'Preparing…' : 'Prepare best-fit'}
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
          {filtersActive || huntScope !== 'all' ? ` of ${prospects.length}` : ''}
          {selectedIds.length > 0 ? ` · ${selectedIds.length} selected` : ''}
        </span>
      </div>

      <div className="seg mb-4 overflow-x-auto max-w-full nr-enter nr-enter-delay-2" role="group" aria-label="Lead stage">
        <button
          type="button"
          className={filter === 'All' && emailFilter === 'all' ? 'is-active' : undefined}
          onClick={() => {
            setEmailFilter('all');
            setFilter('All');
          }}
        >
          All {scopedProspects.length}
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
        {filtersActive && (
          <button
            type="button"
            className="btn btn-ghost ml-1"
            onClick={() => {
              setHuntScope('all');
              setEmailFilter('all');
              setFilter('All');
            }}
          >
            Clear
          </button>
        )}
      </div>
      <div className="leads-sort-bar nr-enter nr-enter-delay-2" aria-label="Sort leads">
        <span className="leads-sort-bar__label">Sort</span>
        <button
          type="button"
          className={`data-table__sort${sortKey === 'intent' ? ' is-active' : ''}`}
          onClick={() => toggleSort('intent')}
        >
          Intent
          {sortKey === 'intent' ? (
            sortDir === 'desc' ? <ArrowDown className="w-3 h-3" strokeWidth={2.25} /> : <ArrowUp className="w-3 h-3" strokeWidth={2.25} />
          ) : (
            <ArrowDown className="w-3 h-3 data-table__sort-hint" strokeWidth={2} />
          )}
        </button>
        <button
          type="button"
          className={`data-table__sort${sortKey === 'fit' ? ' is-active' : ''}`}
          onClick={() => toggleSort('fit')}
        >
          Fit
          {sortKey === 'fit' ? (
            sortDir === 'desc' ? <ArrowDown className="w-3 h-3" strokeWidth={2.25} /> : <ArrowUp className="w-3 h-3" strokeWidth={2.25} />
          ) : (
            <ArrowDown className="w-3 h-3 data-table__sort-hint" strokeWidth={2} />
          )}
        </button>
      </div>

      {visible.length === 0 ? (
        <div className="empty-state nr-enter nr-enter-delay-3">
          <img
            src={EMPTY_QUEUE_IMG}
            alt=""
            className="empty-state__art"
            loading="lazy"
            decoding="async"
          />
          <div className="empty-state__content">
            <p className="empty-state__title">No leads match these filters</p>
            <p className="empty-state__desc">
              {filtersActive
                ? 'Nothing in this view. Try With email, or Clear.'
                : 'Describe who to find in Hunt, then run Find buyers. Qualified accounts land here.'}
            </p>
            {!(filtersActive) && onGoWorkspace && (
              <button type="button" className="btn btn-primary" onClick={onGoWorkspace}>
                Find buyers
              </button>
            )}
          </div>
        </div>
      ) : (
        <>
          <div key={`m-${huntScope}-${emailFilter}-${filter}-${sortKey}-${sortDir}`} className="md:hidden space-y-2 nr-stagger">
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
                <button
                  type="button"
                  className={`data-table__sort${sortKey === 'intent' ? ' is-active' : ''}`}
                  onClick={() => toggleSort('intent')}
                  aria-label={`Sort by intent${sortKey === 'intent' ? `, currently ${sortDir}` : ''}`}
                  title="Sort by intent"
                >
                  Intent
                  {sortKey === 'intent' ? (
                    sortDir === 'desc' ? <ArrowDown className="w-3 h-3" strokeWidth={2.25} /> : <ArrowUp className="w-3 h-3" strokeWidth={2.25} />
                  ) : (
                    <ArrowDown className="w-3 h-3 data-table__sort-hint" strokeWidth={2} />
                  )}
                </button>
                <button
                  type="button"
                  className={`data-table__sort data-table__sort--end${sortKey === 'fit' ? ' is-active' : ''}`}
                  onClick={() => toggleSort('fit')}
                  aria-label={`Sort by fit${sortKey === 'fit' ? `, currently ${sortDir}` : ''}`}
                  title="Sort by fit score"
                >
                  Fit
                  {sortKey === 'fit' ? (
                    sortDir === 'desc' ? <ArrowDown className="w-3 h-3" strokeWidth={2.25} /> : <ArrowUp className="w-3 h-3" strokeWidth={2.25} />
                  ) : (
                    <ArrowDown className="w-3 h-3 data-table__sort-hint" strokeWidth={2} />
                  )}
                </button>
                <span className="text-right">Status</span>
              </div>
              <div key={`d-${huntScope}-${emailFilter}-${filter}-${sortKey}-${sortDir}`} className="nr-stagger">
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

function formatRelative(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp.replace(' ', 'T')).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
