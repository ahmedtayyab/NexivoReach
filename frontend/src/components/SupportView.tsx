import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Loader2, LifeBuoy, Send } from 'lucide-react';
import { apiFetch } from '../lib/api';

type Ticket = {
  id: string;
  subject: string;
  body: string;
  status: string;
  priority: string;
  category: string;
  adminReply?: string;
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string | null;
};

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

export default function SupportView() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [category, setCategory] = useState('general');
  const [priority, setPriority] = useState('normal');

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

  const selected = tickets.find(t => t.id === selectedId) || null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !body.trim()) return;
    setBusy(true);
    setMsg('');
    setError('');
    try {
      const resp = await apiFetch('/api/support/tickets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject: subject.trim(),
          body: body.trim(),
          category,
          priority,
        }),
      });
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Could not submit ticket'));
      const ticket = (await resp.json()) as Ticket;
      setTickets(prev => [ticket, ...prev]);
      setSelectedId(ticket.id);
      setSubject('');
      setBody('');
      setMsg('Ticket submitted — we’ll reply in this panel.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit ticket');
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
        </p>
      </header>

      {error && (
        <p className="ui-banner ui-banner--warn mb-4" role="alert">
          {error}
        </p>
      )}
      {msg && (
        <p className="ui-banner ui-banner--ok mb-4" role="status">
          {msg}
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
                </select>
              </label>
              <label>
                Priority
                <select value={priority} onChange={e => setPriority(e.target.value)}>
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
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
            <button type="submit" className="btn btn-primary" disabled={busy || !subject.trim() || !body.trim()}>
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              {busy ? 'Sending…' : 'Submit ticket'}
            </button>
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
            <p className="text-[13px] text-ink-muted">No tickets yet.</p>
          ) : (
            <ul className="support-tickets">
              {tickets.map(t => (
                <li key={t.id}>
                  <button
                    type="button"
                    className={selectedId === t.id ? 'is-active' : ''}
                    onClick={() => setSelectedId(t.id)}
                  >
                    <span className="support-tickets__subject">{t.subject}</span>
                    <span className="support-tickets__meta">
                      <span className={`support-status is-${t.status}`}>{t.status.replace('_', ' ')}</span>
                      · {t.category} · {(t.updatedAt || t.createdAt || '').slice(0, 10)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {selected && (
            <div className="support-detail">
              <h3>{selected.subject}</h3>
              <p className="support-detail__meta">
                {selected.status.replace('_', ' ')} · {selected.priority} · {selected.category}
              </p>
              <p className="support-detail__body">{selected.body}</p>
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
