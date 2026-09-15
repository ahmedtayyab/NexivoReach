import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { CheckCircle2, Loader2, LifeBuoy, Paperclip, Send, X, XCircle } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { brandAssets } from '../lib/brandAssets';
import type { ToastKind } from './ToastHost';

type TicketAttachment = {
  id: string;
  name: string;
  mime: string;
  size: number;
  url: string;
};

type Ticket = {
  id: string;
  subject: string;
  body: string;
  status: string;
  priority: string;
  category: string;
  adminReply?: string;
  attachments?: TicketAttachment[];
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string | null;
};

type Props = {
  onToast?: (kind: ToastKind, title: string, body?: string) => void;
};

const MAX_ATTACHMENTS = 4;
const MAX_ATTACHMENT_BYTES = 2_500_000;
const SUPPORT_SEEN_KEY = 'nr-support-ticket-seen';

async function apiErrorMessage(resp: Response, fallback: string): Promise<string> {
  const text = await resp.text();
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail.trim();
  } catch {
    // plain
  }
  return text.trim() || fallback;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function ticketAttentionKey(t: Ticket): string {
  return `${t.id}:${t.updatedAt || t.createdAt || ''}:${(t.adminReply || '').length}`;
}

function loadSeenKeys(): Set<string> {
  try {
    const raw = localStorage.getItem(SUPPORT_SEEN_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? new Set(parsed.filter(x => typeof x === 'string')) : new Set();
  } catch {
    return new Set();
  }
}

function persistSeenKeys(ids: Set<string>) {
  try {
    localStorage.setItem(SUPPORT_SEEN_KEY, JSON.stringify([...ids].slice(-200)));
  } catch {
    // ignore
  }
}

export default function SupportView({ onToast }: Props) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [sendFeedback, setSendFeedback] = useState<'idle' | 'ok' | 'err'>('idle');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [category, setCategory] = useState('general');
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [seenKeys, setSeenKeys] = useState<Set<string>>(() => loadSeenKeys());

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const resp = await apiFetch('/api/support/tickets');
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Failed to load tickets'));
      const data = await resp.json();
      const list = Array.isArray(data.tickets) ? (data.tickets as Ticket[]) : [];
      setTickets(list);
      if (selectedId && !list.some(t => t.id === selectedId)) setSelectedId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tickets');
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial load only
  }, []);

  useEffect(() => {
    const urls = files.map(f => URL.createObjectURL(f));
    setPreviews(urls);
    return () => {
      urls.forEach(u => URL.revokeObjectURL(u));
    };
  }, [files]);

  const selected = tickets.find(t => t.id === selectedId) || null;

  const markSeen = useCallback((t: Ticket) => {
    const key = ticketAttentionKey(t);
    setSeenKeys(prev => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      persistSeenKeys(next);
      return next;
    });
  }, []);

  const addFiles = (list: FileList | null) => {
    if (!list?.length) return;
    setError('');
    const next = [...files];
    for (const file of Array.from(list)) {
      if (!file.type.startsWith('image/')) {
        setError('Only image files are allowed (PNG, JPEG, WebP, GIF).');
        continue;
      }
      if (file.size > MAX_ATTACHMENT_BYTES) {
        setError(`Each image must be under ${formatBytes(MAX_ATTACHMENT_BYTES)}.`);
        continue;
      }
      if (next.length >= MAX_ATTACHMENTS) {
        setError(`You can attach up to ${MAX_ATTACHMENTS} images.`);
        break;
      }
      next.push(file);
    }
    setFiles(next);
  };

  const removeFile = (idx: number) => {
    setFiles(prev => prev.filter((_, i) => i !== idx));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !body.trim()) return;
    setBusy(true);
    setError('');
    setSendFeedback('idle');
    try {
      const form = new FormData();
      form.append('subject', subject.trim());
      form.append('body', body.trim());
      form.append('category', category);
      for (const file of files) {
        form.append('files', file);
      }
      const resp = await apiFetch('/api/support/tickets', {
        method: 'POST',
        body: form,
      });
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Could not submit ticket'));
      const ticket = (await resp.json()) as Ticket;
      setTickets(prev => [ticket, ...prev]);
      setSelectedId(ticket.id);
      markSeen(ticket);
      setSubject('');
      setBody('');
      setFiles([]);
      setSendFeedback('ok');
      onToast?.('sent', 'Ticket submitted', 'We’ll reply in this panel.');
      window.setTimeout(() => setSendFeedback(cur => (cur === 'ok' ? 'idle' : cur)), 2800);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not submit ticket';
      setError(message);
      setSendFeedback('err');
      onToast?.('error', 'Could not submit ticket', message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="support-desk">
      <header className="support-desk__hero">
        <p className="support-desk__eyebrow">
          <LifeBuoy className="w-3.5 h-3.5" /> Help
        </p>
        <h1 className="support-desk__title">Support</h1>
        <p className="support-desk__lede">
          Raise a ticket for limits, billing questions, or bugs. Replies show up here and in Notifications.
          {' '}
          <a href="/privacy.html" className="linkish">
            Privacy policy
          </a>
        </p>
      </header>

      {error && (
        <p className="ui-banner ui-banner--warn mb-4" role="alert">
          {error}
        </p>
      )}

      <div className="support-grid">
        <section className="support-panel">
          <h2>New ticket</h2>
          <form className="support-form" onSubmit={e => void submit(e)}>
            <label>
              Subject
              <input
                value={subject}
                onChange={e => setSubject(e.target.value)}
                placeholder="e.g. Need higher hunt limit"
                maxLength={200}
                required
              />
            </label>
            <div className="support-form__row">
              <label>
                Category
                <select value={category} onChange={e => setCategory(e.target.value)}>
                  <option value="general">General</option>
                  <option value="limits">Limits / usage</option>
                  <option value="billing">Billing / plan</option>
                  <option value="bug">Bug</option>
                  <option value="appeal">Appeal / suspension</option>
                </select>
              </label>
            </div>
            <label>
              Details
              <textarea
                value={body}
                onChange={e => setBody(e.target.value)}
                rows={5}
                placeholder="What happened, and what do you need?"
                maxLength={5000}
                required
              />
            </label>

            <div className="support-attach">
              <div className="support-attach__head">
                <span>
                  <Paperclip className="w-3.5 h-3.5 inline-block mr-1" />
                  Screenshots / images
                </span>
                <span className="support-attach__hint">
                  Up to {MAX_ATTACHMENTS} · {formatBytes(MAX_ATTACHMENT_BYTES)} each
                </span>
              </div>
              <label className="support-attach__pick">
                <input
                  type="file"
                  accept="image/*,image/jpeg,image/png,image/webp,image/gif"
                  multiple
                  onChange={e => {
                    addFiles(e.target.files);
                    e.target.value = '';
                  }}
                />
                Add images
              </label>
              {files.length > 0 && (
                <ul className="support-attach__list">
                  {files.map((file, idx) => (
                    <li key={`${file.name}-${idx}`}>
                      <img src={previews[idx]} alt="" />
                      <div>
                        <span className="support-attach__name">{file.name}</span>
                        <span className="support-attach__size">{formatBytes(file.size)}</span>
                      </div>
                      <button type="button" aria-label="Remove image" onClick={() => removeFile(idx)}>
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <button
              type="submit"
              className={`btn btn-primary${sendFeedback === 'ok' ? ' is-send-ok' : ''}${
                sendFeedback === 'err' ? ' is-send-err' : ''
              }`}
              disabled={busy || !subject.trim() || !body.trim()}
            >
              {busy ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : sendFeedback === 'ok' ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : sendFeedback === 'err' ? (
                <XCircle className="w-3.5 h-3.5" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
              {busy ? 'Sending…' : sendFeedback === 'ok' ? 'Submitted' : sendFeedback === 'err' ? 'Failed — retry' : 'Submit ticket'}
            </button>
            {sendFeedback === 'ok' && (
              <p className="admin-send-flash is-ok" role="status">
                Ticket submitted — we’ll reply here.
              </p>
            )}
          </form>
        </section>

        <section className="support-panel support-panel--list">
          <div className="support-panel__head">
            <h2>Your tickets</h2>
            <button type="button" className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
              Refresh
            </button>
          </div>
          {loading && tickets.length === 0 ? (
            <p className="text-[13px] text-ink-muted flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
            </p>
          ) : tickets.length === 0 ? (
            <div className="empty-state empty-state--compact nr-enter">
              <div className="empty-state__art-wrap">
                <img src={brandAssets.emptySupport} alt="" className="empty-state__art" loading="lazy" decoding="async" />
              </div>
              <p className="empty-state__title">No tickets yet</p>
              <p className="empty-state__desc">Send a message above when you need help.</p>
            </div>
          ) : (
            <ul className="support-tickets">
              {tickets.map(t => {
                const key = ticketAttentionKey(t);
                const hasReply = Boolean((t.adminReply || '').trim());
                const isUnread = hasReply && !seenKeys.has(key);
                return (
                  <li key={t.id}>
                    <button
                      type="button"
                      className={`${selectedId === t.id ? 'is-active' : ''}${isUnread ? ' is-unread' : ''}`}
                      onClick={() => {
                        setSelectedId(t.id);
                        markSeen(t);
                      }}
                    >
                      <span className="support-tickets__subject">
                        {isUnread ? 'New reply · ' : ''}
                        {t.subject}
                      </span>
                      <span className="support-tickets__meta">
                        <span className={`support-status is-${t.status}`}>{t.status.replace('_', ' ')}</span>
                        · {t.category}
                        {(t.attachments?.length || 0) > 0
                          ? ` · ${t.attachments!.length} image${t.attachments!.length === 1 ? '' : 's'}`
                          : ''}
                        · {(t.updatedAt || t.createdAt || '').slice(0, 10)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {selected && (
            <div className="support-detail">
              <h3>{selected.subject}</h3>
              <p className="support-detail__meta">
                {selected.status.replace('_', ' ')} · {selected.category}
              </p>
              <p className="support-detail__body">{selected.body}</p>
              {(selected.attachments?.length || 0) > 0 && (
                <div className="support-detail__atts">
                  {selected.attachments!.map(a => (
                    <a key={a.id} href={a.url} target="_blank" rel="noreferrer" className="support-detail__att">
                      <img src={a.url} alt={a.name} loading="lazy" />
                      <span>{a.name}</span>
                    </a>
                  ))}
                </div>
              )}
              {selected.adminReply ? (
                <div className="support-detail__reply">
                  <strong>Support reply</strong>
                  <p>{selected.adminReply}</p>
                </div>
              ) : (
                <p className="text-[12.5px] text-ink-muted mt-3">No reply yet — we’ll notify you when there is one.</p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
