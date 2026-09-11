import { useEffect, useMemo, useRef, useState } from 'react';
import type { Prospect } from '../types';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import { leadRowToneClass, recipientEmail } from '../lib/leadTone';
import { brandAssets } from '../lib/brandAssets';

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
  onSendAllReady?: () => void;
  onPrepareAndSend?: () => void;
  onBackfillRecipients?: () => Promise<void>;
  onRemoveProspect?: (id: string) => void;
  onClearAll?: () => void;
  onSendSelected?: (ids: string[]) => Promise<void> | void;
  gmailConnected?: boolean;
  onGoWorkspace?: () => void;
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
  onSendAllReady,
  onPrepareAndSend,
  onBackfillRecipients,
  onRemoveProspect,
  onClearAll,
  onSendSelected,
  gmailConnected = false,
  onGoWorkspace,
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

  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    setIndex(0);
  }, [filter, withDrafts.length]);

  useEffect(() => {
    setSelectedIds([]);
  }, [filter]);

  const backfillAttempted = useRef(false);
  useEffect(() => {
    if (!onBackfillRecipients || backfillAttempted.current) return;
    const missing = withDrafts.some(p => {
      const st = p.outreachDraft?.status;
      if (st === 'Sent' || st === 'Replied') return false;
      return !recipientEmail(p);
    });
    if (!missing) return;
    backfillAttempted.current = true;
    void onBackfillRecipients();
  }, [onBackfillRecipients, withDrafts]);

  useEffect(() => {
    if (index >= filtered.length && filtered.length > 0) {
      setIndex(filtered.length - 1);
    }
  }, [filtered.length, index]);

  const toggleSelected = (id: string) => {
    setSelectedIds(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]));
  };

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
    setToEmail(recipientEmail(current));
  }, [current?.id, draft?.subject, draft?.body, draft?.toEmail, current?.email, current?.contacts]);

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

  const sendableCount = withDrafts.filter(p => {
    const st = p.outreachDraft?.status;
    const to = recipientEmail(p);
    return (st === 'Draft' || st === 'Approved') && to.includes('@') && isBestFit(p);
  }).length;

  const bestFitCount = withDrafts.filter(
    p => (p.outreachDraft?.status === 'Draft' || p.outreachDraft?.status === 'Approved') && isBestFit(p),
  ).length;

  const persistDraftFields = () => {
    if (!current || !draft) return;
    if (
      subject !== draft.subject ||
      body !== draft.body ||
      toEmail !== recipientEmail(current)
    ) {
      onSaveDraft(current.id, subject, body, toEmail);
    }
  };

  if (!withDrafts.length) {
    return (
      <div className="max-w-2xl w-full">
        <div className="page-header nr-enter">
          <h1 className="page-header__title">Outreach</h1>
          <p className="page-header__desc">
            Best-fit queue with drafts. Send to any address once Gmail is connected.
          </p>
        </div>
        <div className="empty-state nr-enter nr-enter-delay-2">
          <img src={brandAssets.emptyOutreach} alt="" className="empty-state__art" />
          <p className="empty-state__title">No drafts yet</p>
          <p className="empty-state__desc">
            Find buyers in Workspace, then use Leads → Prepare outreach. Send ready emails here.
          </p>
          <div className="flex flex-wrap justify-center gap-2 mt-4">
            {onGoWorkspace && (
              <button type="button" className="btn btn-secondary" onClick={onGoWorkspace}>
                Open Workspace
              </button>
            )}
            {gmailConnected && onPrepareAndSend && (
              <button type="button" className="btn btn-primary" onClick={() => onPrepareAndSend()}>
                Prepare & send best-fit
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl w-full">
      <div className="page-header nr-enter">
        <h1 className="page-header__title">Outreach</h1>
        <p className="page-header__desc">
          {bestFitCount} best-fit ready · Sorted by Fit + Intent ·{' '}
          {gmailConnected
            ? 'Send to any To: address via Gmail'
            : 'Connect Gmail to send in-app (any recipient)'}
          {' · '}J/K · Enter send
        </p>
      </div>

      <div className="toolbar nr-enter nr-enter-delay-1">
        {gmailConnected && onSendAllReady && sendableCount > 0 && (
          <button type="button" onClick={() => onSendAllReady()} className="btn btn-primary">
            Send all ready ({sendableCount})
          </button>
        )}
        {gmailConnected && onPrepareAndSend && (
          <button type="button" onClick={() => onPrepareAndSend()} className="btn btn-secondary">
            Prepare & send
          </button>
        )}
        {gmailConnected && onSendSelected && selectedIds.length > 0 && (
          <button
            type="button"
            onClick={() => {
              const count = selectedIds.length;
              if (!window.confirm(`Send ${count} selected outreach email(s) via Gmail?`)) return;
              void Promise.resolve(onSendSelected(selectedIds)).then(() => setSelectedIds([])).catch(err => {
                console.error(err);
              });
            }}
            className="btn btn-primary"
          >
            Send selected ({selectedIds.length})
          </button>
        )}
        {selectedIds.length > 0 && (
          <button type="button" onClick={() => setSelectedIds([])} className="btn btn-ghost">
            Clear selection
          </button>
        )}
        {onSyncReplies && (
          <button type="button" onClick={() => onSyncReplies()} className="btn btn-ghost">
            Sync replies
          </button>
        )}
        {onClearAll && (
          <button type="button" onClick={() => onClearAll()} className="btn btn-ghost">
            Clear all
          </button>
        )}
        <span className="toolbar-spacer" />
        <div className="seg" role="group" aria-label="Outreach filter">
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
              className={filter === id ? 'is-active' : undefined}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="outreach-layout nr-enter nr-enter-delay-2">
        <div className="outreach-list">
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
                  <div
                    key={p.id}
                    className={`border-b border-border-subtle transition-colors lead-row-tone ${leadRowToneClass(p)}`}
                  >
                    <div className="flex items-start gap-2">
                      {onSendSelected && (
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(p.id)}
                          onChange={() => toggleSelected(p.id)}
                          className="mt-3 ml-2 h-4 w-4 accent-accent"
                          aria-label={`Select ${p.companyName}`}
                        />
                      )}
                      <button
                        type="button"
                        onClick={() => setIndex(i)}
                        className={`item flex-1 min-w-0 ${active ? 'is-active' : ''}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-[13px] font-medium text-ink truncate">{p.companyName}</p>
                          <span className="text-[11px] tabular-nums text-ink font-semibold shrink-0">{p.fitScore}</span>
                        </div>
                        <p className="text-[11px] text-ink-muted truncate mt-0.5">
                          Intent {intent} · {st}
                        </p>
                        <p className="text-[11px] text-ink-muted truncate">
                          {recipientEmail(p) || 'Will resolve from site contacts'}
                        </p>
                      </button>
                      {onRemoveProspect && (
                        <button
                          type="button"
                          aria-label={`Remove ${p.companyName}`}
                          title="Remove lead"
                          onClick={() => onRemoveProspect(p.id)}
                          className="mt-2 mr-2 p-1.5 text-ink-muted hover:text-ink hover:bg-muted"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {current && draft ? (
          <div key={current.id} className="outreach-editor nr-pop">
            <div className="flex items-start justify-between gap-3">
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
                  className="p-1.5 border border-border disabled:opacity-30"
                >
                  <ChevronUp className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  aria-label="Next"
                  disabled={index >= filtered.length - 1}
                  onClick={() => setIndex(i => Math.min(filtered.length - 1, i + 1))}
                  className="p-1.5 border border-border disabled:opacity-30"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div>
              <label className="field-label">Buyer email (To)</label>
              <div className="flex gap-2">
                <input
                  type="email"
                  value={toEmail}
                  onChange={e => setToEmail(e.target.value)}
                  onBlur={persistDraftFields}
                  placeholder="Will fill from contact page…"
                  className="flex-1 border border-border px-3 py-2 text-[13px] bg-panel"
                />
                {!toEmail.includes('@') && onBackfillRecipients && (
                  <button
                    type="button"
                    onClick={() => void onBackfillRecipients()}
                    className="btn btn-secondary shrink-0"
                  >
                    Find on site
                  </button>
                )}
              </div>
            </div>
            <div>
              <label className="field-label">Subject</label>
              <input
                value={subject}
                onChange={e => setSubject(e.target.value)}
                onBlur={persistDraftFields}
                className="w-full border border-border px-3 py-2 text-[13px] bg-panel"
              />
            </div>
            <div className="flex flex-col flex-1 min-h-0">
              <label className="field-label">Body</label>
              <textarea
                value={body}
                onChange={e => setBody(e.target.value)}
                onBlur={persistDraftFields}
                rows={14}
                className="min-h-[16rem]"
              />
            </div>
            {draft.outreachRationale && (
              <div className="border border-border-subtle bg-muted px-3 py-2.5 space-y-1.5">
                <p className="field-label mb-0">Outreach rationale</p>
                {draft.outreachRationale.primary_signal && (
                  <p className="text-[12px] text-ink-secondary">
                    <span className="text-ink-muted">Signal:</span> {draft.outreachRationale.primary_signal}
                  </p>
                )}
                {draft.outreachRationale.pain_hypothesis && (
                  <p className="text-[12px] text-ink-secondary">
                    <span className="text-ink-muted">Pain hypothesis:</span> {draft.outreachRationale.pain_hypothesis}
                  </p>
                )}
                {draft.outreachRationale.matched_product && (
                  <p className="text-[12px] text-ink-secondary">
                    <span className="text-ink-muted">Matched product:</span> {draft.outreachRationale.matched_product}
                  </p>
                )}
                <p className="text-[12px] text-ink-secondary">
                  {draft.outreachRationale.angle ? (
                    <><span className="text-ink-muted">Approach:</span> {draft.outreachRationale.angle}</>
                  ) : null}
                  {draft.outreachRationale.signal_confidence ? (
                    <>
                      {draft.outreachRationale.angle ? ' · ' : null}
                      <span className="text-ink-muted">Confidence:</span> {draft.outreachRationale.signal_confidence}
                    </>
                  ) : null}
                </p>
              </div>
            )}
            {!draft.outreachRationale && draft.personalizedReason && (
              <p className="text-[12px] text-ink-muted">{draft.personalizedReason}</p>
            )}

            <div className="flex flex-wrap items-center gap-2 border-t border-border-subtle pt-3 mt-auto">
              {(draft.status === 'Draft' || draft.status === 'Approved') && (
                <button
                  type="button"
                  onClick={() => {
                    persistDraftFields();
                    onSendViaEmail(current.id, { subject, body, toEmail });
                    setIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
                  }}
                  className="btn btn-primary"
                >
                  {gmailConnected ? 'Approve & send via Gmail' : 'Approve & open email'}
                </button>
              )}
              {onPrepareFollowUp && (draft.status === 'Sent' || draft.status === 'Replied' || current.stage === 'Re-contact') && (
                <button
                  type="button"
                  onClick={() => onPrepareFollowUp(current.id)}
                  className="btn btn-secondary"
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
                  className="btn btn-ghost"
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
          <div className="outreach-editor items-center justify-center text-center text-[13px] text-ink-muted">
            Select a draft from the list.
          </div>
        )}
      </div>
    </div>
  );
}
