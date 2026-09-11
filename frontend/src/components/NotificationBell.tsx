import { useCallback, useEffect, useRef, useState } from 'react';
import { Bell, CheckCheck, Loader2 } from 'lucide-react';
import { apiFetch } from '../lib/api';
import type { AuthUser } from '../types';

export type AppNotification = {
  id: string;
  kind: string;
  title: string;
  body: string;
  href?: string | null;
  readAt?: string | null;
  createdAt: string;
  meta?: Record<string, unknown>;
};

type Props = {
  user: AuthUser | null;
  onNavigate?: (hash: string) => void;
  pollMs?: number;
};

function pct(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

function UsageMeters({ user }: { user: AuthUser }) {
  const u = user.usage;
  if (!u) return null;
  const kinds: Array<{ key: keyof typeof u.used; label: string }> = [
    { key: 'hunt', label: 'Hunt' },
    { key: 'extract', label: 'Extract' },
    { key: 'prepare', label: 'Prepare' },
    { key: 'send', label: 'Send' },
  ];
  const unlimited = Boolean(u.bypassed);
  return (
    <div className="notif-usage">
      <p className="notif-usage__label">Today · {u.day} UTC</p>
      <div className="notif-usage__grid">
        {kinds.map(({ key, label }) => {
          const used = u.used[key];
          const limit = u.limits[key];
          const p = unlimited ? 0 : pct(used, limit);
          const hot = !unlimited && p >= 80;
          return (
            <div key={key} className="notif-usage__row">
              <div className="notif-usage__meta">
                <span>{label}</span>
                <span className="tabular-nums">
                  {unlimited ? `${used} · ∞` : `${used}/${limit} · ${p}%`}
                </span>
              </div>
              <div className="notif-usage__track">
                <div
                  className={`notif-usage__fill ${hot ? 'is-hot' : ''}`}
                  style={{ width: unlimited ? '100%' : `${p}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function NotificationBell({ user, onNavigate, pollMs = 45000 }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const resp = await apiFetch('/api/notifications?limit=20');
      if (!resp.ok) return;
      const data = await resp.json();
      setItems(Array.isArray(data.notifications) ? data.notifications : []);
      setUnread(Number(data.unreadCount) || 0);
    } catch {
      // ignore poll errors
    }
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!user) return;
    const id = window.setInterval(() => void load(), pollMs);
    return () => window.clearInterval(id);
  }, [user, load, pollMs]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const markAll = async () => {
    setLoading(true);
    try {
      await apiFetch('/api/notifications/read-all', { method: 'POST' });
      setItems(prev => prev.map(n => ({ ...n, readAt: n.readAt || new Date().toISOString() })));
      setUnread(0);
    } finally {
      setLoading(false);
    }
  };

  const openItem = async (n: AppNotification) => {
    if (!n.readAt) {
      try {
        const resp = await apiFetch(`/api/notifications/${n.id}/read`, { method: 'POST' });
        if (resp.ok) {
          const data = await resp.json();
          setUnread(Number(data.unreadCount) || 0);
          setItems(prev =>
            prev.map(x => (x.id === n.id ? { ...x, readAt: data.notification?.readAt || new Date().toISOString() } : x)),
          );
        }
      } catch {
        // ignore
      }
    }
    if (n.href) {
      setOpen(false);
      const route = n.href.replace(/^#/, '').split(/[?/]/)[0] || 'support';
      onNavigate?.(route);
    }
  };

  if (!user) return null;

  return (
    <div className="notif-bell" ref={wrapRef}>
      <button
        type="button"
        className={`nr-nav-link notif-bell__btn ${open ? 'is-active' : ''}`}
        onClick={() => {
          setOpen(v => !v);
          if (!open) void load();
        }}
        aria-label={unread ? `${unread} unread notifications` : 'Notifications'}
      >
        <span className="nr-nav-link__left">
          <span className="relative inline-flex">
            <Bell className="w-4 h-4 shrink-0" strokeWidth={open ? 2 : 1.75} />
            {unread > 0 && (
              <span className="notif-bell__badge tabular-nums">{unread > 9 ? '9+' : unread}</span>
            )}
          </span>
          Notifications
        </span>
      </button>

      {open && (
        <div className="notif-panel" role="dialog" aria-label="Notifications">
          <div className="notif-panel__head">
            <strong>Notifications</strong>
            <button
              type="button"
              className="notif-panel__mark"
              onClick={() => void markAll()}
              disabled={loading || unread === 0}
            >
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCheck className="w-3.5 h-3.5" />}
              Mark all read
            </button>
          </div>

          {user.usage && <UsageMeters user={user} />}

          <ul className="notif-list">
            {items.length === 0 ? (
              <li className="notif-empty">No notifications yet.</li>
            ) : (
              items.map(n => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={`notif-item ${n.readAt ? '' : 'is-unread'}`}
                    onClick={() => void openItem(n)}
                  >
                    <span className={`notif-item__kind is-${n.kind}`}>{n.kind}</span>
                    <span className="notif-item__title">{n.title}</span>
                    {n.body && <span className="notif-item__body">{n.body}</span>}
                    <span className="notif-item__time">{(n.createdAt || '').replace('T', ' ').replace('Z', ' UTC')}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
