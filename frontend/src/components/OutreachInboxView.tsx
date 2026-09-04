import { useEffect, useMemo, useState } from 'react';
import type { Prospect } from '../types';
import { ChevronDown, ChevronUp, Mail } from 'lucide-react';

interface Props {
  prospects: Prospect[];
  onSendViaEmail: (id: string) => void;
  onSaveDraft: (id: string, subject: string, body: string) => void;
  onSkip?: (id: string) => void;
}

type Filter = 'needs_review' | 'sent' | 'all';

export default function OutreachInboxView({
  prospects,
  onSendViaEmail,
  onSaveDraft,
  onSkip,
}: Props) {
  const withDrafts = useMemo(
    () => prospects.filter(p => p.outreachDraft),
    [prospects],
  );
  const [filter, setFilter] = useState<Filter>('needs_review');
  const filtered = useMemo(() => {
    const rows = withDrafts.filter(p => {
      const st = p.outreachDraft?.status;
      if (filter === 'needs_review') return st === 'Draft' || st === 'Approved';
      if (filter === 'sent') return st === 'Sent' || st === 'Replied';
      return true;
    });
    return [...rows].sort((a, b) => {
      const order = { Draft: 0, Approved: 1, Sent: 2, Replied: 3 };
      const ao = order[a.outreachDraft?.status || 'Draft'] ?? 9;
      const bo = order[b.outreachDraft?.status || 'Draft'] ?? 9;
      if (ao !== bo) return ao - bo;
      return (b.fitScore || 0) - (a.fitScore || 0);
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
        onSendViaEmail(current.id);
        setIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [filtered.length, current, draft?.status, onSendViaEmail]);

  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  useEffect(() => {
    if (!draft) {
      setSubject('');
      setBody('');
      return;
    }
    setSubject(draft.subject);
    setBody(draft.body);
  }, [current?.id, draft?.subject, draft?.body]);

  const needsReview = withDrafts.filter(
    p => p.outreachDraft?.status === 'Draft' || p.outreachDraft?.status === 'Approved',
  ).length;

  if (!withDrafts.length) {
    return (
      <div className="max-w-2xl w-full">
        <h1 className="text-[15px] font-semibold text-ink tracking-tight">Outreach</h1>
        <p className="text-[13px] text-ink-secondary mt-1 mb-6">
          Review personalized drafts, then open your mail client to send. No auto-send.
        </p>
        <div className="bg-panel border border-border rounded-lg px-5 py-10 text-center">
          <Mail className="w-8 h-8 text-ink-muted mx-auto mb-3" strokeWidth={1.5} />
          <p className="text-[13.5px] font-medium text-ink-secondary">No drafts yet</p>
          <p className="text-[13px] text-ink-muted mt-1">
            Run Discover — high-fit leads get contacts and a draft automatically.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl w-full">
      <div className="mb-5 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-[15px] font-semibold text-ink tracking-tight">Outreach</h1>
          <p className="text-[13px] text-ink-secondary mt-1">
            {needsReview} to review · Read the draft, then send. Keys: J/K move · Enter send
          </p>
        </div>
        <div className="flex gap-1.5">
          {(
            [
              ['needs_review', 'Needs review'],
              ['sent', 'Sent'],
              ['all', 'All'],
            ] as [Filter, string][]
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={`px-2.5 py-1 rounded-full text-[12px] border ${
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

      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-4">
        <div className="bg-panel border border-border rounded-lg overflow-hidden max-h-[70vh] overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="p-4 text-[13px] text-ink-muted">Nothing in this filter.</p>
          ) : (
            filtered.map((p, i) => {
              const active = i === index;
              const st = p.outreachDraft?.status || 'Draft';
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setIndex(i)}
                  className={`w-full text-left px-3 py-2.5 border-b border-border-subtle ${
                    active ? 'bg-muted' : 'hover:bg-canvas/60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink truncate">{p.companyName}</p>
                    <span className="text-[11px] tabular-nums text-ink-muted shrink-0">{p.fitScore}</span>
                  </div>
                  <p className="text-[11px] text-ink-muted truncate mt-0.5">
                    {p.outreachDraft?.toEmail || p.email || 'No email'} · {st}
                  </p>
                </button>
              );
            })
          )}
        </div>

        {current && draft ? (
          <div className="bg-panel border border-border rounded-lg p-4 sm:p-5 flex flex-col min-h-[420px]">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div className="min-w-0">
                <h2 className="text-[15px] font-semibold text-ink truncate">{current.companyName}</h2>
                <p className="text-[12px] text-ink-muted mt-0.5 truncate">
                  To: {draft.toEmail || current.email || '— (paste recipient in your mail app)'}
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

            <label className="text-[11px] font-medium text-ink-muted uppercase tracking-wide">Subject</label>
            <input
              value={subject}
              onChange={e => setSubject(e.target.value)}
              onBlur={() => {
                if (subject !== draft.subject || body !== draft.body) {
                  onSaveDraft(current.id, subject, body);
                }
              }}
              className="mt-1 mb-3 w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel-elevated"
            />
            <label className="text-[11px] font-medium text-ink-muted uppercase tracking-wide">Body</label>
            <textarea
              value={body}
              onChange={e => setBody(e.target.value)}
              onBlur={() => {
                if (subject !== draft.subject || body !== draft.body) {
                  onSaveDraft(current.id, subject, body);
                }
              }}
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
                    if (subject !== draft.subject || body !== draft.body) {
                      onSaveDraft(current.id, subject, body);
                    }
                    onSendViaEmail(current.id);
                    setIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
                  }}
                  className="px-4 py-2 bg-accent hover:bg-accent-hover text-white text-[13px] font-medium rounded-md"
                >
                  Approve &amp; open email
                </button>
              )}
              {onSkip && (draft.status === 'Draft' || draft.status === 'Approved') && (
                <button
                  type="button"
                  onClick={() => {
                    onSkip(current.id);
                    setIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
                  }}
                  className="px-3 py-2 text-[13px] border border-border rounded-md text-ink-secondary hover:border-ink-muted"
                >
                  Skip for now
                </button>
              )}
              {(draft.status === 'Sent' || draft.status === 'Replied') && (
                <span className="text-[13px] text-green-700 font-medium">{draft.status}</span>
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
