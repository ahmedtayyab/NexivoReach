import { useCallback, useEffect, useMemo, useState } from 'react';
import { Archive, Bell, CheckCheck, Loader2, Trash2, X } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { brandAssets } from '../lib/brandAssets';
import type { AuthUser } from '../types';
import { useConfirm } from './ConfirmDialog';

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

type NotifTab = 'new' | 'viewed';

type Props = {
  user: AuthUser | null;
  onNavigate?: (route: string) => void;
  pollMs?: number;
  /** Controlled mobile sheet */
  mobileOpen?: boolean;
  onMobileOpenChange?: (open: boolean) => void;
  /** Desktop rail open (persistent column) */
  desktopOpen?: boolean;
  onDesktopOpenChange?: (open: boolean) => void;
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
  emptyCopy,
  onOpen,
  onDismiss,
}: {
  items: AppNotification[];
  emptyCopy: string;
  onOpen: (n: AppNotification) => void;
  onDismiss: (n: AppNotification) => void;
}) {
  if (items.length === 0) {
    return (
      <div className="notif-empty-state nr-enter">
        <img
          src={brandAssets.emptyNotifications}
          alt=""
          className="empty-state__art"
          loading="lazy"
          decoding="async"
        />
        <p className="notif-empty">{emptyCopy}</p>
      </div>
    );
  }
  return (
    <ul className="notif-list">
      {items.map(n => (
        <li key={n.id} className="notif-row">
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
          <button
            type="button"
            className="notif-item__dismiss"
            aria-label="Remove notification"
            title="Remove"
            onClick={e => {
              e.stopPropagation();
              void onDismiss(n);
            }}
          >
            <X className="w-3.5 h-3.5" strokeWidth={2} />
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
  desktopOpen = true,
  onDesktopOpenChange,
}: Props) {
  const confirm = useConfirm();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<NotifTab>('new');

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const resp = await apiFetch('/api/notifications?limit=50');
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

  const newItems = useMemo(() => items.filter(n => !n.readAt), [items]);
  const viewedItems = useMemo(() => items.filter(n => Boolean(n.readAt)), [items]);
  const visible = tab === 'new' ? newItems : viewedItems;

  const markAll = async () => {
    setLoading(true);
    try {
      await apiFetch('/api/notifications/read-all', { method: 'POST' });
      setItems(prev => prev.map(n => ({ ...n, readAt: n.readAt || new Date().toISOString() })));
      setUnread(0);
      setTab('viewed');
    } finally {
      setLoading(false);
    }
  };

  const dismissOne = async (n: AppNotification) => {
    setItems(prev => prev.filter(x => x.id !== n.id));
    if (!n.readAt) setUnread(u => Math.max(0, u - 1));
    try {
      const resp = await apiFetch(`/api/notifications/${n.id}`, { method: 'DELETE' });
      if (resp.ok) {
        const data = await resp.json();
        setUnread(Number(data.unreadCount) || 0);
      } else {
        void load();
      }
    } catch {
      void load();
    }
  };

  const clearViewed = async () => {
    if (viewedItems.length === 0) return;
    const ok = await confirm({
      title: 'Clear viewed notifications?',
      body: 'Removes everything you’ve already opened. New alerts stay.',
      confirmLabel: 'Clear viewed',
      tone: 'danger',
    });
    if (!ok) return;
    setLoading(true);
    try {
      const resp = await apiFetch('/api/notifications/read', { method: 'DELETE' });
      if (resp.ok) {
        const data = await resp.json();
        setItems(prev => prev.filter(n => !n.readAt));
        setUnread(Number(data.unreadCount) || 0);
      }
    } finally {
      setLoading(false);
    }
  };

  const clearAll = async () => {
    if (items.length === 0) return;
    const ok = await confirm({
      title: 'Remove all notifications?',
      body: 'This clears both new and viewed alerts. You can’t undo this.',
      confirmLabel: 'Remove all',
      tone: 'danger',
    });
    if (!ok) return;
    setLoading(true);
    try {
      const resp = await apiFetch('/api/notifications', { method: 'DELETE' });
      if (resp.ok) {
        setItems([]);
        setUnread(0);
      }
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
            className="notif-rail__close"
            onClick={() => {
              onMobileOpenChange?.(false);
              onDesktopOpenChange?.(false);
            }}
            aria-label="Close notifications"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {user.usage && <UsageMeters user={user} />}

      <div className="notif-tabs" role="tablist" aria-label="Notification folders">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'new'}
          className={`notif-tabs__btn ${tab === 'new' ? 'is-active' : ''}`}
          onClick={() => setTab('new')}
        >
          New
          {newItems.length > 0 && (
            <span className="notif-tabs__count tabular-nums">{newItems.length}</span>
          )}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'viewed'}
          className={`notif-tabs__btn ${tab === 'viewed' ? 'is-active' : ''}`}
          onClick={() => setTab('viewed')}
        >
          <Archive className="w-3 h-3" strokeWidth={2} />
          Viewed
          {viewedItems.length > 0 && (
            <span className="notif-tabs__count tabular-nums">{viewedItems.length}</span>
          )}
        </button>
      </div>

      <div className="notif-toolbar">
        {tab === 'new' ? (
          <button
            type="button"
            className="notif-panel__mark"
            onClick={() => void markAll()}
            disabled={loading || unread === 0}
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCheck className="w-3.5 h-3.5" />}
            Mark all viewed
          </button>
        ) : (
          <button
            type="button"
            className="notif-panel__mark"
            onClick={() => void clearViewed()}
            disabled={loading || viewedItems.length === 0}
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            Clear viewed
          </button>
        )}
        <button
          type="button"
          className="notif-panel__mark notif-panel__mark--danger"
          onClick={() => void clearAll()}
          disabled={loading || items.length === 0}
        >
          Remove all
        </button>
      </div>

      <div className="notif-rail__scroll">
        <NotificationList
          items={visible}
          emptyCopy={
            tab === 'new'
              ? 'You’re all caught up. New alerts land here.'
              : 'No viewed notifications. Opened alerts move here so New stays clean.'
          }
          onOpen={openItem}
          onDismiss={dismissOne}
        />
      </div>
    </div>
  );

  return (
    <>
      {desktopOpen && (
        <aside className="notif-rail" aria-label="Notifications">
          {panel}
        </aside>
      )}
      {!desktopOpen && (
        <button
          type="button"
          className="notif-rail-tab"
          onClick={() => onDesktopOpenChange?.(true)}
          aria-label={unread ? `Open notifications, ${unread} unread` : 'Open notifications'}
        >
          <Bell className="w-4 h-4" strokeWidth={1.75} />
          {unread > 0 && (
            <span className="notif-rail-tab__badge tabular-nums">{unread > 9 ? '9+' : unread}</span>
          )}
        </button>
      )}

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
