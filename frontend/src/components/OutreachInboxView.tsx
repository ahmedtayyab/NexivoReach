import { useEffect, useMemo, useState } from 'react';
import type { Prospect } from '../types';
import { ChevronDown, ChevronUp, Mail } from 'lucide-react';
import MailFlow from './brand/MailFlow';

interface Props {
  prospects: Prospect[];
  onSendViaEmail: (
    id: string,
    overrides?: { subject?: string; body?: string; toEmail?: string },
  ) => void;
  onSaveDraft: (id: string, subject: string, body: string, toEmail?: string) => void;
  onSkip?: (id: string) => void;
  onSyncReplies?: () => void;
  onPrepareFollowUp?: (id: string) => void;
  gmailConnected?: boolean;
}

type Filter = 'best_fit' | 'needs_review' | 'sent' | 'all';

function isBestFit(p: Prospect): boolean {
  const summary = (p.fitBreakdown?.fitSummary || '').toLowerCase();
  const priority = (p.priority || p.fitBreakdown?.priority || '').toLowerCase();
  const intent = (p.intent || p.fitBreakdown?.intent || 'none').toLowerCase();
  if (summary === 'high') return true;
  if (priority === 'priority' || priority === 'nurture') return true;
  if ((p.fitScore || 0) >= 75) return true;
  if ((p.fitScore || 0) >= 65 && (intent === 'high' || intent === 'low')) return true;
  return false;
}

function rankProspect(p: Prospect): number {
  const intent = { high: 3, low: 2, none: 0 }[(p.intent || p.fitBreakdown?.intent || 'none').toLowerCase()] ?? 0;
  const pri = { priority: 3, nurture: 2, review: 1 }[(p.priority || p.fitBreakdown?.priority || '').toLowerCase()] ?? 0;
  return pri * 1000 + intent * 100 + (p.fitScore || 0);
}

export default function OutreachInboxView({
  prospects,
  onSendViaEmail,
  onSaveDraft,
  onSkip,
  onSyncReplies,
  onPrepareFollowUp,
  gmailConnected = false,
}: Props) {
  const withDrafts = useMemo(
    () => prospects.filter(p => p.outreachDraft),
    [prospects],
  );
  const [filter, setFilter] = useState<Filter>('best_fit');
  const filtered = useMemo(() => {
    const rows = withDrafts.filter(p => {
      const st = p.outreachDraft?.status;
      if (filter === 'best_fit') {
        return (st === 'Draft' || st === 'Approved') && isBestFit(p);
      }
      if (filter === 'needs_review') return st === 'Draft' || st === 'Approved';
      if (filter === 'sent') return st === 'Sent' || st === 'Replied';
      return true;
    });
    return [...rows].sort((a, b) => {
      const order = { Draft: 0, Approved: 1, Sent: 2, Replied: 3 };
      const ao = order[a.outreachDraft?.status || 'Draft'] ?? 9;
      const bo = order[b.outreachDraft?.status || 'Draft'] ?? 9;
      if (ao !== bo) return ao - bo;
      return rankProspect(b) - rankProspect(a);
    });
  }, [withDrafts, filter]);

  const [index, setIndex] = useState(0);
  const current = filtered[index] || null;
  const draft = current?.outreachDraft;

  useEffect(() => {
    setIndex(0);
  }, [filter, withDrafts.length]);

  useEffect(() => {
    if (index >= filtered.length && filtered.length > 0) {
      setIndex(filtered.length - 1);
    }
  }, [filtered.length, index]);

  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [toEmail, setToEmail] = useState('');

  useEffect(() => {
    if (!draft) {
      setSubject('');
      setBody('');
      setToEmail('');
      return;
    }
    setSubject(draft.subject);
    setBody(draft.body);
    setToEmail(draft.toEmail || current?.email || '');
  }, [current?.id, draft?.subject, draft?.body, draft?.toEmail, current?.email]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setIndex(i => Math.max(i - 1, 0));
      } else if (e.key === 'Enter' && current && (draft?.status === 'Draft' || draft?.status === 'Approved')) {
        e.preventDefault();
        onSendViaEmail(current.id, { subject, body, toEmail });
        setIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [filtered.length, current, draft?.status, onSendViaEmail, subject, body, toEmail]);

  const bestFitCount = withDrafts.filter(
    p => (p.outreachDraft?.status === 'Draft' || p.outreachDraft?.status === 'Approved') && isBestFit(p),
  ).length;

  const persistDraftFields = () => {
    if (!current || !draft) return;
    if (
      subject !== draft.subject ||
      body !== draft.body ||
      toEmail !== (draft.toEmail || current.email || '')
    ) {
      onSaveDraft(current.id, subject, body, toEmail);
    }
  };

  if (!withDrafts.length) {
    return (
      <div className="max-w-2xl w-full">
        <div className="nr-enter">
          <h1 className="text-[15px] font-semibold text-ink tracking-tight">Outreach</h1>
          <p className="text-[13px] text-ink-secondary mt-1 mb-5">
            Best-fit queue: high Fit / Intent leads with drafts. You can send to any email address once Gmail is connected.
          </p>
        </div>
        <div className="mb-5 nr-enter nr-enter-delay-1">
          <MailFlow active={false} />
        </div>
        <div className="bg-panel border border-border rounded-lg px-5 py-10 text-center nr-panel nr-enter nr-enter-delay-2">
          <Mail className="w-8 h-8 text-ink-muted mx-auto mb-3 nr-pop" strokeWidth={1.5} />
          <p className="text-[13.5px] font-medium text-ink-secondary">No drafts yet</p>
          <p className="text-[13px] text-ink-muted mt-1">
            Run Discover or use Leads → Prepare outreach for high-fit accounts.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl w-full">
      <div className="mb-5 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 nr-enter">
        <div>
          <h1 className="text-[15px] font-semibold text-ink tracking-tight">Outreach</h1>
          <p className="text-[13px] text-ink-secondary mt-1">
            {bestFitCount} best-fit ready · Sorted by Fit + Intent ·{' '}
            {gmailConnected
              ? 'Send to any To: address via Gmail'
              : 'Connect Gmail to send in-app (any recipient)'}
            {' · '}J/K · Enter send
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {onSyncReplies && (
            <button
              type="button"
              onClick={() => onSyncReplies()}
              className="nr-chip px-2.5 py-1 rounded-full text-[12px] border border-border bg-panel text-ink-secondary"
            >
              Sync replies
            </button>
          )}
          {(
            [
              ['best_fit', 'Best fit'],
              ['needs_review', 'All drafts'],
              ['sent', 'Sent'],
              ['all', 'All'],
            ] as [Filter, string][]
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={`nr-chip px-2.5 py-1 rounded-full text-[12px] border ${
                filter === id
                  ? 'bg-ink text-panel-elevated border-ink'
                  : 'bg-panel border-border text-ink-secondary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-5 nr-enter nr-enter-delay-1">
        <MailFlow active={bestFitCount > 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4 nr-enter nr-enter-delay-2">
        <div className="bg-panel border border-border rounded-lg overflow-hidden max-h-[70vh] overflow-y-auto nr-panel">
          {filtered.length === 0 ? (
            <p className="p-4 text-[13px] text-ink-muted">
              {filter === 'best_fit'
                ? 'No best-fit drafts yet. Prepare outreach on high-fit Leads, or switch to All drafts.'
                : 'Nothing in this filter.'}
            </p>
          ) : (
            <div key={filter} className="nr-stagger">
              {filtered.map((p, i) => {
                const active = i === index;
                const st = p.outreachDraft?.status || 'Draft';
                const intent = p.intent || p.fitBreakdown?.intent || 'none';
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setIndex(i)}
                    className={`w-full text-left px-3 py-2.5 border-b border-border-subtle transition-colors ${
                      active ? 'bg-muted' : 'hover:bg-canvas/60'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[13px] font-medium text-ink truncate">{p.companyName}</p>
                      <span className="text-[11px] tabular-nums text-ink font-semibold shrink-0">{p.fitScore}</span>
                    </div>
                    <p className="text-[11px] text-ink-muted truncate mt-0.5">
                      Intent {intent} · {st}
                    </p>
                    <p className="text-[11px] text-ink-muted truncate">
                      {p.outreachDraft?.toEmail || p.email || 'Set recipient below'}
                    </p>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {current && draft ? (
          <div key={current.id} className="bg-panel border border-border rounded-lg p-4 sm:p-5 flex flex-col min-h-[420px] nr-panel nr-pop">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div className="min-w-0">
                <h2 className="text-[15px] font-semibold text-ink truncate">{current.companyName}</h2>
                <p className="text-[12px] text-ink-muted mt-0.5">
                  Fit {current.fitScore}
                  {current.intent || current.fitBreakdown?.intent
                    ? ` · Intent ${current.intent || current.fitBreakdown?.intent}`
                    : ''}
                  {isBestFit(current) ? ' · Best fit' : ''}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  aria-label="Previous"
                  disabled={index <= 0}
                  onClick={() => setIndex(i => Math.max(0, i - 1))}
                  className="p-1.5 rounded-md border border-border disabled:opacity-30"
                >
                  <ChevronUp className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  aria-label="Next"
                  disabled={index >= filtered.length - 1}
                  onClick={() => setIndex(i => Math.min(filtered.length - 1, i + 1))}
                  className="p-1.5 rounded-md border border-border disabled:opacity-30"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>
            </div>

            <label className="text-[11px] font-medium text-ink-muted uppercase tracking-wide">To (any email)</label>
            <input
              type="email"
              value={toEmail}
              onChange={e => setToEmail(e.target.value)}
              onBlur={persistDraftFields}
              placeholder="buyer@company.com"
              className="mt-1 mb-3 w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel-elevated"
            />
            <label className="text-[11px] font-medium text-ink-muted uppercase tracking-wide">Subject</label>
            <input
              value={subject}
              onChange={e => setSubject(e.target.value)}
              onBlur={persistDraftFields}
              className="mt-1 mb-3 w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel-elevated"
            />
            <label className="text-[11px] font-medium text-ink-muted uppercase tracking-wide">Body</label>
            <textarea
              value={body}
              onChange={e => setBody(e.target.value)}
              onBlur={persistDraftFields}
              rows={12}
              className="mt-1 flex-1 w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel-elevated resize-y min-h-[220px]"
            />
            {draft.personalizedReason && (
              <p className="text-[12px] text-ink-muted mt-2">{draft.personalizedReason}</p>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border-subtle pt-4">
              {(draft.status === 'Draft' || draft.status === 'Approved') && (
                <button
                  type="button"
                  onClick={() => {
                    persistDraftFields();
                    onSendViaEmail(current.id, { subject, body, toEmail });
                    setIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
                  }}
                  className="px-4 py-2 bg-accent hover:bg-accent-hover text-white text-[13px] font-medium rounded-md nr-btn-press"
                >
                  {gmailConnected ? 'Approve & send via Gmail' : 'Approve & open email'}
                </button>
              )}
              {onPrepareFollowUp && (draft.status === 'Sent' || draft.status === 'Replied' || current.stage === 'Re-contact') && (
                <button
                  type="button"
                  onClick={() => onPrepareFollowUp(current.id)}
                  className="px-3 py-2 text-[13px] border border-border rounded-md text-ink-secondary hover:border-ink-muted nr-btn-press"
                >
                  Draft follow-up
                </button>
              )}
              {onSkip && (draft.status === 'Draft' || draft.status === 'Approved') && (
                <button
                  type="button"
                  onClick={() => {
                    onSkip(current.id);
                    setIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
                  }}
                  className="px-3 py-2 text-[13px] border border-border rounded-md text-ink-secondary hover:border-ink-muted nr-btn-press"
                >
                  Skip for now
                </button>
              )}
              {(draft.status === 'Sent' || draft.status === 'Replied') && (
                <span className="text-[13px] text-green-700 font-medium">
                  {draft.status}
                  {draft.sentVia ? ` · ${draft.sentVia}` : ''}
                </span>
              )}
              <span className="text-[12px] text-ink-muted ml-auto">
                {index + 1} / {filtered.length}
              </span>
            </div>
          </div>
        ) : (
          <div className="bg-panel border border-border rounded-lg p-8 text-center text-[13px] text-ink-muted">
            Select a draft from the list.
          </div>
        )}
      </div>
    </div>
  );
}
