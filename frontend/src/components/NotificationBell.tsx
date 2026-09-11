import { useCallback, useEffect, useState } from 'react';
import { Bell, CheckCheck, Loader2, X } from 'lucide-react';
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
  onNavigate?: (route: string) => void;
  pollMs?: number;
  /** Controlled mobile sheet */
  mobileOpen?: boolean;
  onMobileOpenChange?: (open: boolean) => void;
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

function NotificationList({
  items,
  onOpen,
}: {
  items: AppNotification[];
  onOpen: (n: AppNotification) => void;
}) {
  if (items.length === 0) {
    return <p className="notif-empty">No notifications yet. Account changes and usage alerts show up here.</p>;
  }
  return (
    <ul className="notif-list">
      {items.map(n => (
        <li key={n.id}>
          <button
            type="button"
            className={`notif-item ${n.readAt ? '' : 'is-unread'}`}
            onClick={() => void onOpen(n)}
          >
            <span className={`notif-item__kind is-${n.kind}`}>{n.kind}</span>
            <span className="notif-item__title">{n.title}</span>
            {n.body && <span className="notif-item__body">{n.body}</span>}
            <span className="notif-item__time">
              {(n.createdAt || '').replace('T', ' ').replace('Z', ' UTC')}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function NotificationHeaderButton({
  unread,
  onClick,
}: {
  unread: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="notif-header-btn"
      onClick={onClick}
      aria-label={unread ? `${unread} unread notifications` : 'Notifications'}
    >
      <span className="relative inline-flex">
        <Bell className="w-5 h-5" strokeWidth={1.75} />
        {unread > 0 && (
          <span className="notif-bell__badge tabular-nums">{unread > 9 ? '9+' : unread}</span>
        )}
      </span>
    </button>
  );
}

export default function NotificationsRail({
  user,
  onNavigate,
  pollMs = 45000,
  mobileOpen = false,
  onMobileOpenChange,
}: Props) {
  const [items, setItems] = useState<AppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const resp = await apiFetch('/api/notifications?limit=30');
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
    if (mobileOpen) void load();
  }, [mobileOpen, load]);

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
            prev.map(x =>
              x.id === n.id ? { ...x, readAt: data.notification?.readAt || new Date().toISOString() } : x,
            ),
          );
        }
      } catch {
        // ignore
      }
    }
    if (n.href) {
      onMobileOpenChange?.(false);
      const route = n.href.replace(/^#/, '').split(/[?/]/)[0] || 'support';
      onNavigate?.(route === 'notifications' ? 'support' : route);
    }
  };

  if (!user) return null;

  const panel = (
    <div className="notif-rail__inner">
      <div className="notif-panel__head">
        <div className="notif-rail__title">
          <Bell className="w-4 h-4" strokeWidth={1.75} />
          <strong>Notifications</strong>
          {unread > 0 && <span className="notif-rail__count tabular-nums">{unread}</span>}
        </div>
        <div className="notif-rail__actions">
          <button
            type="button"
            className="notif-panel__mark"
            onClick={() => void markAll()}
            disabled={loading || unread === 0}
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCheck className="w-3.5 h-3.5" />}
            Mark all
          </button>
          {onMobileOpenChange && (
            <button
              type="button"
              className="notif-rail__close lg:hidden"
              onClick={() => onMobileOpenChange(false)}
              aria-label="Close notifications"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {user.usage && <UsageMeters user={user} />}

      <div className="notif-rail__scroll">
        <NotificationList items={items} onOpen={openItem} />
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: persistent right column */}
      <aside className="notif-rail" aria-label="Notifications">
        {panel}
      </aside>

      {/* Mobile: sheet over content */}
      {mobileOpen && (
        <div className="notif-sheet lg:hidden" role="dialog" aria-modal="true" aria-label="Notifications">
          <button
            type="button"
            className="notif-sheet__backdrop"
            aria-label="Close"
            onClick={() => onMobileOpenChange?.(false)}
          />
          <div className="notif-sheet__panel">{panel}</div>
        </div>
      )}
    </>
  );
}

/** Expose unread count for mobile header via a tiny hook-like poller wrapper in App. */
export function useNotificationUnread(user: AuthUser | null, pollMs = 45000) {
  const [unread, setUnread] = useState(0);
  const load = useCallback(async () => {
    if (!user) {
      setUnread(0);
      return;
    }
    try {
      const resp = await apiFetch('/api/notifications?limit=1');
      if (!resp.ok) return;
      const data = await resp.json();
      setUnread(Number(data.unreadCount) || 0);
    } catch {
      // ignore
    }
  }, [user]);

  useEffect(() => {
    void load();
    if (!user) return;
    const id = window.setInterval(() => void load(), pollMs);
    return () => window.clearInterval(id);
  }, [user, load, pollMs]);

  return unread;
}
