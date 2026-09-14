import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Loader2, LogOut, Paperclip, ShieldAlert, X } from 'lucide-react';
import BrandLockup from './brand/BrandLockup';
import { apiFetch } from '../lib/api';
import { brandAssets } from '../lib/brandAssets';
import type { AuthUser } from '../types';

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
  category: string;
  adminReply?: string;
  attachments?: TicketAttachment[];
  createdAt: string;
  updatedAt: string;
  alreadyOpen?: boolean;
};

type Props = {
  user: AuthUser;
  onLogout: () => void;
};

const MAX_ATTACHMENTS = 4;
const MAX_ATTACHMENT_BYTES = 2_500_000;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function SuspendedView({ user, onLogout }: Props) {
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      const resp = await apiFetch('/api/support/tickets');
      if (!resp.ok) return;
      const data = await resp.json();
      const list = Array.isArray(data.tickets) ? (data.tickets as Ticket[]) : [];
      setTickets(list.filter(t => t.category === 'appeal' || t.subject.toLowerCase().includes('suspension')));
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const urls = files.map(f => URL.createObjectURL(f));
    setPreviews(urls);
    return () => {
      urls.forEach(u => URL.revokeObjectURL(u));
    };
  }, [files]);

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
    if (!body.trim()) return;
    setBusy(true);
    setError('');
    setMsg('');
    try {
      const form = new FormData();
      form.append('subject', 'Account suspension appeal');
      form.append('body', body.trim());
      for (const file of files) {
        form.append('files', file);
      }
      const resp = await apiFetch('/api/support/appeal', {
        method: 'POST',
        body: form,
      });
      if (!resp.ok) {
        const text = await resp.text();
        let detail = 'Could not submit appeal';
        try {
          const parsed = JSON.parse(text) as { detail?: string };
          if (typeof parsed.detail === 'string') detail = parsed.detail;
        } catch {
          // plain
        }
        throw new Error(detail);
      }
      const ticket = (await resp.json()) as Ticket;
      setBody('');
      setFiles([]);
      setMsg(
        ticket.alreadyOpen
          ? 'You already have an open appeal — an admin will review it.'
          : 'Appeal submitted. We’ll review it and restore access if this was a mistake.',
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit appeal');
    } finally {
      setBusy(false);
    }
  };

  const latest = tickets[0];

  return (
    <div className="min-h-dvh flex items-center justify-center px-4 sm:px-6 relative overflow-hidden">
      <img
        src={brandAssets.suspendedAtmosphere}
        alt=""
        className="absolute inset-0 w-full h-full object-cover nr-kenburns"
        decoding="async"
      />
      <div className="absolute inset-0 bg-canvas/70" aria-hidden />

      <div className="relative w-full max-w-lg nr-enter">
        <div className="mb-8 flex justify-center nr-pop">
          <BrandLockup size="lg" className="scale-110 origin-center" />
        </div>

        <div className="bg-panel border border-border p-5 sm:p-6 nr-enter nr-enter-delay-1 rounded-xl shadow-[0_20px_50px_rgba(23,32,51,0.08)]">
          <p className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-ink-muted mb-2">
            <ShieldAlert className="w-3.5 h-3.5" /> Account paused
          </p>
          <h1 className="font-display text-[1.55rem] font-bold text-ink leading-tight tracking-tight">
            Access suspended
          </h1>
          <p className="text-[13.5px] text-ink-secondary mt-2 leading-relaxed">
            Signed in as <span className="font-medium text-ink">{user.email}</span>. Your workspace is
            locked — sometimes this is intentional, sometimes it’s a mistake or a bug. Tell us what
            happened and we’ll review.
          </p>

          {error && (
            <p className="ui-banner ui-banner--warn mt-4" role="alert">
              {error}
            </p>
          )}
          {msg && (
            <p className="ui-banner ui-banner--ok mt-4" role="status">
              {msg}
            </p>
          )}

          <form className="mt-5 space-y-3" onSubmit={e => void submit(e)}>
            <label className="block text-[12px] text-ink-muted">
              What happened?
              <textarea
                value={body}
                onChange={e => setBody(e.target.value)}
                rows={5}
                required
                maxLength={5000}
                placeholder="e.g. I hit a usage limit and everything locked, or I think this was suspended by mistake…"
                className="mt-1.5 w-full border border-border bg-panel-elevated px-3 py-2 text-[13px] text-ink"
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
              className="btn btn-primary w-full justify-center"
              disabled={busy || !body.trim()}
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
              {busy ? 'Sending…' : 'Submit appeal'}
            </button>
          </form>

          {latest && (
            <div className="mt-5 pt-4 border-t border-border-subtle">
              <p className="text-[12px] text-ink-muted uppercase tracking-[0.08em] mb-1">Your appeal</p>
              <p className="text-[13px] font-medium text-ink">{latest.subject}</p>
              <p className="text-[12px] text-ink-muted mt-0.5 capitalize">
                {latest.status.replace('_', ' ')} · {(latest.updatedAt || latest.createdAt || '').slice(0, 10)}
              </p>
              {(latest.attachments?.length || 0) > 0 && (
                <div className="support-detail__atts mt-3">
                  {latest.attachments!.map(a => (
                    <a key={a.id} href={a.url} target="_blank" rel="noreferrer" className="support-detail__att">
                      <img src={a.url} alt={a.name} loading="lazy" />
                      <span>{a.name}</span>
                    </a>
                  ))}
                </div>
              )}
              {latest.adminReply ? (
                <div className="mt-3 p-3 border border-border-subtle bg-canvas">
                  <strong className="block text-[11px] uppercase tracking-[0.08em] text-ink-muted mb-1">
                    Admin reply
                  </strong>
                  <p className="text-[13px] text-ink-secondary whitespace-pre-wrap m-0">{latest.adminReply}</p>
                </div>
              ) : (
                <p className="text-[12.5px] text-ink-muted mt-2">No reply yet.</p>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={onLogout}
            className="mt-5 inline-flex items-center gap-1.5 text-[12.5px] text-ink-muted hover:text-ink"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
