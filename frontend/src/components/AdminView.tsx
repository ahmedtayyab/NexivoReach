import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Loader2, Shield, UserPlus, Ban, CheckCircle2, RefreshCw, XCircle } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { brandAssets } from '../lib/brandAssets';
import type { ToastKind } from './ToastHost';
import PageAmbient from './brand/PageAmbient';

type Props = {
  onToast?: (kind: ToastKind, title: string, body?: string) => void;
};

const ADMIN_TICKET_SEEN_KEY = 'nr-admin-ticket-seen';

function loadSeenTicketIds(): Set<string> {
  try {
    const raw = localStorage.getItem(ADMIN_TICKET_SEEN_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? new Set(parsed.filter(x => typeof x === 'string')) : new Set();
  } catch {
    return new Set();
  }
}

function persistSeenTicketIds(ids: Set<string>) {
  try {
    localStorage.setItem(ADMIN_TICKET_SEEN_KEY, JSON.stringify([...ids].slice(-200)));
  } catch {
    // ignore
  }
}

type UsageBucket = { hunt: number; extract: number; prepare: number; send: number };

type AdminUser = {
  id: string;
  email: string;
  name: string;
  picture?: string;
  createdAt?: string;
  isAdmin: boolean;
  isSuspended: boolean;
  usageUnlimited?: boolean;
  plan: string;
  companyCount: number;
  leadCount: number;
  companies: { id: string; name: string }[];
  usageToday: {
    day: string;
    used: UsageBucket;
    limits: UsageBucket;
    bypassed?: boolean;
  };
  limitOverrides: {
    hunt: number | null;
    extract: number | null;
    prepare: number | null;
    send: number | null;
  };
};

type Overview = {
  day: string;
  inviteOnly: boolean;
  defaults: UsageBucket;
  huntSettings?: {
    leadsPerRun: number;
    maxPagesPerIntent: number;
    defaults?: { leadsPerRun: number; maxPagesPerIntent: number };
  };
  stats: {
    users: number;
    suspended: number;
    invites: number;
    activeToday: number;
    usageToday: UsageBucket;
  };
  series: Array<{
    day: string;
    hunts: number;
    extracts: number;
    prepares: number;
    sends: number;
    activeUsers: number;
  }>;
  topUsersToday: Array<{
    id: string;
    email: string;
    name: string;
    hunts: number;
    extracts: number;
    prepares: number;
    sends: number;
    total: number;
  }>;
};

type Invite = {
  email: string;
  note: string;
  createdAt: string;
  createdBy: string;
  inviteLink?: string;
  emailSent?: boolean;
  emailError?: string;
};

type SupportTicket = {
  id: string;
  userId: string;
  email?: string;
  name?: string;
  subject: string;
  body: string;
  status: string;
  priority: string;
  category: string;
  adminReply?: string;
  attachments?: { id: string; name: string; mime: string; size: number; url: string }[];
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string | null;
};

type TicketStatusFilter = 'all' | 'new' | 'open' | 'in_progress' | 'resolved' | 'closed';
type TicketCategoryFilter = 'all' | 'general' | 'billing' | 'limits' | 'bug' | 'appeal';
type TicketPriorityFilter = 'all' | 'high' | 'normal' | 'low';
type UserStatusFilter = 'all' | 'active' | 'suspended' | 'admin' | 'unlimited' | 'active_today';

const TICKET_STATUS_FILTERS: { id: TicketStatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'new', label: 'New' },
  { id: 'open', label: 'Open' },
  { id: 'in_progress', label: 'In progress' },
  { id: 'resolved', label: 'Resolved' },
  { id: 'closed', label: 'Closed' },
];

const TICKET_CATEGORY_FILTERS: { id: TicketCategoryFilter; label: string }[] = [
  { id: 'all', label: 'All types' },
  { id: 'general', label: 'General' },
  { id: 'billing', label: 'Billing' },
  { id: 'limits', label: 'Limits' },
  { id: 'bug', label: 'Bug' },
  { id: 'appeal', label: 'Appeal' },
];

const TICKET_PRIORITY_FILTERS: { id: TicketPriorityFilter; label: string }[] = [
  { id: 'all', label: 'Any priority' },
  { id: 'high', label: 'High' },
  { id: 'normal', label: 'Normal' },
  { id: 'low', label: 'Low' },
];

const USER_STATUS_FILTERS: { id: UserStatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'active', label: 'Active' },
  { id: 'suspended', label: 'Suspended' },
  { id: 'admin', label: 'Admins' },
  { id: 'unlimited', label: 'No caps' },
  { id: 'active_today', label: 'Active today' },
];

function ticketIsNew(t: SupportTicket): boolean {
  return t.status === 'open' && !(t.adminReply || '').trim();
}

function statusLabel(status: string): string {
  if (status === 'in_progress') return 'In progress';
  return status.replace(/_/g, ' ');
}

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

function Meter({
  used,
  limit,
  label,
  unlimited,
}: {
  used: number;
  limit: number;
  label: string;
  unlimited?: boolean;
}) {
  if (unlimited) {
    return (
      <div className="admin-meter">
        <div className="admin-meter__row">
          <span>{label}</span>
          <span className="tabular-nums">{used} · unlimited</span>
        </div>
        <div className="admin-meter__track">
          <div className="admin-meter__fill is-open" style={{ width: '100%' }} />
        </div>
      </div>
    );
  }
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const hot = pct >= 85;
  return (
    <div className="admin-meter">
      <div className="admin-meter__row">
        <span>{label}</span>
        <span className="tabular-nums">
          {used}/{limit}
        </span>
      </div>
      <div className="admin-meter__track">
        <div
          className={`admin-meter__fill ${hot ? 'is-hot' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function WeekChart({ series }: { series: Overview['series'] }) {
  const max = Math.max(1, ...series.map(s => s.hunts + s.extracts + s.prepares + s.sends));
  return (
    <div className="admin-chart" role="img" aria-label="Usage over the last 7 days">
      {series.map(s => {
        const total = s.hunts + s.extracts + s.prepares + s.sends;
        const h = Math.max(4, Math.round((total / max) * 100));
        const label = s.day.slice(5);
        return (
          <div key={s.day} className="admin-chart__col" title={`${s.day}: ${total} actions`}>
            <div className="admin-chart__stack" style={{ height: `${h}%` }}>
              <span className="admin-chart__seg is-hunt" style={{ flex: Math.max(s.hunts, 0.01) }} />
              <span className="admin-chart__seg is-extract" style={{ flex: Math.max(s.extracts, 0.01) }} />
              <span className="admin-chart__seg is-prepare" style={{ flex: Math.max(s.prepares, 0.01) }} />
              <span className="admin-chart__seg is-send" style={{ flex: Math.max(s.sends, 0.01) }} />
            </div>
            <span className="admin-chart__label">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function AdminView({ onToast }: Props) {
  const [tab, setTab] = useState<'ops' | 'support'>('ops');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [openTicketCount, setOpenTicketCount] = useState(0);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketReply, setTicketReply] = useState('');
  const [ticketStatusFilter, setTicketStatusFilter] = useState<TicketStatusFilter>('all');
  const [ticketCategoryFilter, setTicketCategoryFilter] = useState<TicketCategoryFilter>('all');
  const [ticketPriorityFilter, setTicketPriorityFilter] = useState<TicketPriorityFilter>('all');
  const [inviteOnly, setInviteOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteNote, setInviteNote] = useState('');
  const [inviteMsg, setInviteMsg] = useState('');
  const [query, setQuery] = useState('');
  const [userStatusFilter, setUserStatusFilter] = useState<UserStatusFilter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [seenTicketIds, setSeenTicketIds] = useState<Set<string>>(() => loadSeenTicketIds());
  const [replyFeedback, setReplyFeedback] = useState<'idle' | 'ok' | 'err'>('idle');
  const [replyFeedbackText, setReplyFeedbackText] = useState('');
  const [huntLeadsPerRun, setHuntLeadsPerRun] = useState(40);
  const [huntMaxPages, setHuntMaxPages] = useState(10);
  const [huntSettingsBusy, setHuntSettingsBusy] = useState(false);
  const [huntSettingsMsg, setHuntSettingsMsg] = useState('');

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) {
      setLoading(true);
      setError('');
    }
    try {
      const [o, u, a, t] = await Promise.all([
        apiFetch('/api/admin/overview'),
        apiFetch('/api/admin/users'),
        apiFetch('/api/admin/allowlist'),
        apiFetch('/api/admin/tickets'),
      ]);
      if (!o.ok) {
        if (o.status === 403) {
          throw new Error(
            'Admin only — set ADMIN_EMAILS to your Google email on Render, redeploy, then sign out and back in.',
          );
        }
        throw new Error(await apiErrorMessage(o, 'Failed to load overview'));
      }
      if (!u.ok) throw new Error(await apiErrorMessage(u, 'Failed to load users'));
      if (!a.ok) throw new Error(await apiErrorMessage(a, 'Failed to load allowlist'));
      if (!t.ok) throw new Error(await apiErrorMessage(t, 'Failed to load tickets'));
      const overviewData = (await o.json()) as Overview;
      const usersData = await u.json();
      const allowData = await a.json();
      const ticketData = await t.json();
      setOverview(overviewData);
      if (overviewData.huntSettings) {
        setHuntLeadsPerRun(Number(overviewData.huntSettings.leadsPerRun) || 40);
        setHuntMaxPages(Number(overviewData.huntSettings.maxPagesPerIntent) || 10);
      }
      setUsers(Array.isArray(usersData.users) ? usersData.users : []);
      setInvites(Array.isArray(allowData.invites) ? allowData.invites : []);
      setInviteOnly(Boolean(allowData.inviteOnly ?? overviewData.inviteOnly));
      setTickets(Array.isArray(ticketData.tickets) ? ticketData.tickets : []);
      setOpenTicketCount(Number(ticketData.openCount) || 0);
    } catch (e) {
      if (!opts?.silent) setError(e instanceof Error ? e.message : 'Failed to load admin');
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Live refresh while Admin is open (tickets, usage, invites).
  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load({ silent: true });
    }, 20000);
    return () => window.clearInterval(id);
  }, [load]);

  const userFilterCounts = useMemo(() => {
    const counts: Record<UserStatusFilter, number> = {
      all: users.length,
      active: 0,
      suspended: 0,
      admin: 0,
      unlimited: 0,
      active_today: 0,
    };
    for (const u of users) {
      if (u.isSuspended) counts.suspended += 1;
      else counts.active += 1;
      if (u.isAdmin) counts.admin += 1;
      if (u.usageUnlimited || u.isAdmin) counts.unlimited += 1;
      const used =
        (u.usageToday?.used?.hunt || 0) +
        (u.usageToday?.used?.extract || 0) +
        (u.usageToday?.used?.prepare || 0) +
        (u.usageToday?.used?.send || 0);
      if (used > 0) counts.active_today += 1;
    }
    return counts;
  }, [users]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return users.filter(u => {
      if (userStatusFilter === 'active' && u.isSuspended) return false;
      if (userStatusFilter === 'suspended' && !u.isSuspended) return false;
      if (userStatusFilter === 'admin' && !u.isAdmin) return false;
      if (userStatusFilter === 'unlimited' && !(u.usageUnlimited || u.isAdmin)) return false;
      if (userStatusFilter === 'active_today') {
        const used =
          (u.usageToday?.used?.hunt || 0) +
          (u.usageToday?.used?.extract || 0) +
          (u.usageToday?.used?.prepare || 0) +
          (u.usageToday?.used?.send || 0);
        if (used <= 0) return false;
      }
      if (!q) return true;
      return (
        u.email.toLowerCase().includes(q) ||
        (u.name || '').toLowerCase().includes(q) ||
        (u.plan || '').toLowerCase().includes(q)
      );
    });
  }, [users, query, userStatusFilter]);

  const selected = users.find(u => u.id === selectedId) || null;

  useEffect(() => {
    if (selectedId && !filtered.some(u => u.id === selectedId)) {
      setSelectedId(null);
    }
  }, [filtered, selectedId]);

  const selectedTicket = tickets.find(t => t.id === selectedTicketId) || null;

  const ticketFilterCounts = useMemo(() => {
    const counts: Record<TicketStatusFilter, number> = {
      all: tickets.length,
      new: 0,
      open: 0,
      in_progress: 0,
      resolved: 0,
      closed: 0,
    };
    for (const t of tickets) {
      if (ticketIsNew(t)) counts.new += 1;
      if (t.status === 'open') counts.open += 1;
      else if (t.status === 'in_progress') counts.in_progress += 1;
      else if (t.status === 'resolved') counts.resolved += 1;
      else if (t.status === 'closed') counts.closed += 1;
    }
    return counts;
  }, [tickets]);

  const filteredTickets = useMemo(() => {
    return tickets.filter(t => {
      if (ticketStatusFilter === 'new') {
        if (!ticketIsNew(t)) return false;
      } else if (ticketStatusFilter !== 'all' && t.status !== ticketStatusFilter) {
        return false;
      }
      if (ticketCategoryFilter !== 'all' && (t.category || 'general') !== ticketCategoryFilter) {
        return false;
      }
      if (ticketPriorityFilter !== 'all' && (t.priority || 'normal') !== ticketPriorityFilter) {
        return false;
      }
      return true;
    });
  }, [tickets, ticketStatusFilter, ticketCategoryFilter, ticketPriorityFilter]);

  useEffect(() => {
    if (selectedTicketId && !filteredTickets.some(t => t.id === selectedTicketId)) {
      setSelectedTicketId(null);
    }
  }, [filteredTickets, selectedTicketId]);

  useEffect(() => {
    if (!selectedTicket) {
      setTicketReply('');
      setReplyFeedback('idle');
      setReplyFeedbackText('');
      return;
    }
    setTicketReply(selectedTicket.adminReply || '');
    setReplyFeedback('idle');
    setReplyFeedbackText('');
  }, [selectedTicket]);

  const markTicketSeen = useCallback((id: string) => {
    setSeenTicketIds(prev => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      persistSeenTicketIds(next);
      return next;
    });
  }, []);

  const patchTicket = async (
    id: string,
    body: Record<string, unknown>,
    opts?: { successTitle?: string; successBody?: string; isReply?: boolean },
  ) => {
    setBusyId(id);
    setError('');
    if (opts?.isReply) {
      setReplyFeedback('idle');
      setReplyFeedbackText('');
    }
    try {
      const resp = await apiFetch(`/api/admin/tickets/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Ticket update failed'));
      const updated = (await resp.json()) as SupportTicket;
      setTickets(prev => prev.map(t => (t.id === id ? updated : t)));
      setOpenTicketCount(prev => {
        const next = tickets.map(t => (t.id === id ? updated : t));
        return next.filter(t => t.status === 'open' || t.status === 'in_progress').length || prev;
      });
      const title = opts?.successTitle || 'Ticket updated';
      const okBody = opts?.successBody;
      onToast?.(opts?.isReply ? 'sent' : 'ok', title, okBody);
      if (opts?.isReply) {
        setReplyFeedback('ok');
        setReplyFeedbackText(title);
        window.setTimeout(() => {
          setReplyFeedback(cur => (cur === 'ok' ? 'idle' : cur));
        }, 2800);
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Ticket update failed';
      setError(message);
      onToast?.('error', opts?.isReply ? 'Could not send reply' : 'Update failed', message);
      if (opts?.isReply) {
        setReplyFeedback('err');
        setReplyFeedbackText(message);
      }
    } finally {
      setBusyId('');
    }
  };

  const patchUser = async (id: string, body: Record<string, unknown>) => {
    setBusyId(id);
    setError('');
    try {
      const resp = await apiFetch(`/api/admin/users/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Update failed'));
      const updated = (await resp.json()) as AdminUser;
      setUsers(prev => prev.map(u => (u.id === id ? updated : u)));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed');
    } finally {
      setBusyId('');
    }
  };

  const saveHuntSettings = async (e?: FormEvent) => {
    e?.preventDefault();
    setHuntSettingsBusy(true);
    setHuntSettingsMsg('');
    try {
      const resp = await apiFetch('/api/admin/hunt-settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          leadsPerRun: huntLeadsPerRun,
          maxPagesPerIntent: huntMaxPages,
        }),
      });
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Could not save hunt settings'));
      const data = await resp.json();
      setHuntLeadsPerRun(Number(data.leadsPerRun) || huntLeadsPerRun);
      setHuntMaxPages(Number(data.maxPagesPerIntent) || huntMaxPages);
      setOverview(prev =>
        prev
          ? {
              ...prev,
              huntSettings: {
                leadsPerRun: Number(data.leadsPerRun) || 40,
                maxPagesPerIntent: Number(data.maxPagesPerIntent) || 10,
                defaults: data.defaults,
              },
            }
          : prev,
      );
      setHuntSettingsMsg(
        `Saved — ${data.leadsPerRun} leads/run, split across hunt lines; next run resumes deeper Google pages.`,
      );
      onToast?.('ok', 'Hunt settings saved', `${data.leadsPerRun} leads per run`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      setHuntSettingsMsg(msg);
      onToast?.('error', 'Hunt settings', msg);
    } finally {
      setHuntSettingsBusy(false);
    }
  };

  const addInvite = async (e?: FormEvent) => {
    e?.preventDefault();
    const email = inviteEmail.trim();
    if (!email) {
      setInviteMsg('Enter an email address first.');
      return;
    }
    if (!email.includes('@')) {
      setInviteMsg('That doesn’t look like a valid email.');
      return;
    }
    setBusyId('invite');
    setError('');
    setInviteMsg('');
    try {
      const resp = await apiFetch('/api/admin/allowlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, note: inviteNote.trim() }),
      });
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Invite failed'));
      const created = (await resp.json()) as Invite;
      setInvites(prev => {
        const without = prev.filter(i => i.email !== created.email);
        return [
          {
            email: created.email,
            note: created.note,
            createdAt: created.createdAt,
            createdBy: created.createdBy,
          },
          ...without,
        ];
      });
      setInviteEmail('');
      setInviteNote('');
      if (created.emailSent) {
        setInviteMsg(`Invited ${created.email} — allowlisted and invite email sent via your Gmail.`);
      } else if (created.emailError) {
        setInviteMsg(`${created.email} is allowlisted. ${created.emailError}`);
      } else {
        setInviteMsg(`Allowlisted ${created.email} — they can sign in with Google now.`);
      }
      // Refresh KPIs in the background; list already updated.
      void load();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Invite failed';
      setError(message);
      setInviteMsg(message);
    } finally {
      setBusyId('');
    }
  };

  const removeInvite = async (email: string) => {
    setBusyId(email);
    setInviteMsg('');
    try {
      const resp = await apiFetch(
        `/api/admin/allowlist?email=${encodeURIComponent(email)}`,
        { method: 'DELETE' },
      );
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Remove failed'));
      setInvites(prev => prev.filter(i => i.email !== email.toLowerCase() && i.email !== email));
      setInviteMsg(`Removed ${email} from the allowlist.`);
      void load();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Remove failed';
      setError(message);
      setInviteMsg(message);
    } finally {
      setBusyId('');
    }
  };

  if (loading && !overview) {
    return (
      <div className="admin-desk page-shell flex items-center justify-center min-h-[40vh] text-ink-muted gap-2">
        <PageAmbient variant="admin" />
        <Loader2 className="w-4 h-4 animate-spin" /> Loading ops…
      </div>
    );
  }

  return (
    <div className="admin-desk page-shell">
      <PageAmbient variant="admin" />
      <header className="admin-desk__hero">
        <div>
          <p className="admin-desk__eyebrow">
            <Shield className="w-3.5 h-3.5" /> Operator
          </p>
          <h1 className="admin-desk__title">Admin</h1>
          <p className="admin-desk__lede">
            Invite pilots, watch daily API burn, suspend abuse. Caps reset at midnight UTC.
          </p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </header>

      {error && (
        <p className="ui-banner ui-banner--warn mb-4" role="alert">
          {error}
        </p>
      )}

      <div className="admin-tabs" role="tablist" aria-label="Admin sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'ops'}
          className={`admin-tabs__btn ${tab === 'ops' ? 'is-active' : ''}`}
          onClick={() => setTab('ops')}
        >
          Ops
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'support'}
          className={`admin-tabs__btn ${tab === 'support' ? 'is-active' : ''} ${
            openTicketCount > 0 ? 'has-attention' : ''
          }`}
          onClick={() => setTab('support')}
        >
          Support
          {openTicketCount > 0 && (
            <span className="admin-tabs__badge" aria-label={`${openTicketCount} open tickets`}>
              {openTicketCount > 99 ? '99+' : openTicketCount}
            </span>
          )}
        </button>
      </div>

      {tab === 'support' && (
        <div className="admin-grid admin-grid--users mb-4">
          <section className="admin-panel admin-panel--stretch">
            <div className="admin-panel__head">
              <h2>Tickets</h2>
              <span className="text-[12px] text-ink-muted">
                {filteredTickets.length}
                {filteredTickets.length !== tickets.length ? ` of ${tickets.length}` : ''} ·{' '}
                {openTicketCount} needing attention
              </span>
            </div>

            <div className="admin-filter-bar" aria-label="Filter tickets">
              <label className="admin-filter-bar__field">
                <span>Status</span>
                <select
                  value={ticketStatusFilter}
                  onChange={e => setTicketStatusFilter(e.target.value as TicketStatusFilter)}
                >
                  {TICKET_STATUS_FILTERS.map(f => (
                    <option key={f.id} value={f.id}>
                      {f.label} ({ticketFilterCounts[f.id]})
                    </option>
                  ))}
                </select>
              </label>
              <label className="admin-filter-bar__field">
                <span>Type</span>
                <select
                  value={ticketCategoryFilter}
                  onChange={e => setTicketCategoryFilter(e.target.value as TicketCategoryFilter)}
                >
                  {TICKET_CATEGORY_FILTERS.map(f => (
                    <option key={f.id} value={f.id}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="admin-filter-bar__field">
                <span>Priority</span>
                <select
                  value={ticketPriorityFilter}
                  onChange={e => setTicketPriorityFilter(e.target.value as TicketPriorityFilter)}
                >
                  {TICKET_PRIORITY_FILTERS.map(f => (
                    <option key={f.id} value={f.id}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </label>
              {(ticketStatusFilter !== 'all' ||
                ticketCategoryFilter !== 'all' ||
                ticketPriorityFilter !== 'all') && (
                <button
                  type="button"
                  className="btn btn-secondary admin-filter-bar__clear"
                  onClick={() => {
                    setTicketStatusFilter('all');
                    setTicketCategoryFilter('all');
                    setTicketPriorityFilter('all');
                  }}
                >
                  Clear filters
                </button>
              )}
            </div>

            {tickets.length === 0 ? (
              <div className="empty-state empty-state--compact">
                <img src={brandAssets.emptyAdmin} alt="" className="empty-state__art" loading="lazy" decoding="async" />
                <div className="empty-state__content">
                  <p className="empty-state__title">No support tickets yet</p>
                  <p className="empty-state__desc">Pilot questions and appeals will land here.</p>
                </div>
              </div>
            ) : filteredTickets.length === 0 ? (
              <div className="empty-state empty-state--compact">
                <img src={brandAssets.emptyAdmin} alt="" className="empty-state__art" loading="lazy" decoding="async" />
                <div className="empty-state__content">
                  <p className="empty-state__title">No tickets match</p>
                  <p className="empty-state__desc">Try clearing filters to see the full queue.</p>
                </div>
              </div>
            ) : (
              <ul className="admin-ticket-list">
                {filteredTickets.map(t => {
                  const isNew = ticketIsNew(t);
                  const isUnread = isNew && !seenTicketIds.has(t.id);
                  return (
                    <li key={t.id}>
                      <button
                        type="button"
                        className={`${selectedTicketId === t.id ? 'is-active' : ''}${
                          isUnread ? ' is-unread' : ''
                        }`}
                        onClick={() => {
                          setSelectedTicketId(t.id);
                          markTicketSeen(t.id);
                        }}
                      >
                        <span className="admin-ticket__top">
                          <span className="admin-ticket__sub">{t.subject}</span>
                          <span className="admin-ticket__pills">
                            {isNew && <span className="admin-ticket-pill is-new">New</span>}
                            <span className={`admin-ticket-pill is-status-${t.status}`}>
                              {statusLabel(t.status)}
                            </span>
                            <span className={`admin-ticket-pill is-cat-${t.category || 'general'}`}>
                              {t.category || 'general'}
                            </span>
                            {(t.priority || 'normal') === 'high' && (
                              <span className="admin-ticket-pill is-pri-high">High</span>
                            )}
                          </span>
                        </span>
                        <span className="admin-ticket__meta">
                          {t.name || t.email || t.userId} · {(t.updatedAt || t.createdAt || '').slice(0, 10)}
                          {(t.attachments?.length || 0) > 0
                            ? ` · ${t.attachments!.length} image${t.attachments!.length === 1 ? '' : 's'}`
                            : ''}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          <section className="admin-panel admin-panel--stretch">
            {!selectedTicket ? (
              <p className="text-[13px] text-ink-muted">Select a ticket to reply.</p>
            ) : (
              <div className="admin-ticket-detail">
                <div className="admin-ticket__pills mb-2">
                  {ticketIsNew(selectedTicket) && <span className="admin-ticket-pill is-new">New</span>}
                  <span className={`admin-ticket-pill is-status-${selectedTicket.status}`}>
                    {statusLabel(selectedTicket.status)}
                  </span>
                  <span className={`admin-ticket-pill is-cat-${selectedTicket.category || 'general'}`}>
                    {selectedTicket.category || 'general'}
                  </span>
                  <span className={`admin-ticket-pill is-pri-${selectedTicket.priority || 'normal'}`}>
                    {(selectedTicket.priority || 'normal')} priority
                  </span>
                </div>
                <h2 className="text-[15px] font-medium mb-1">{selectedTicket.subject}</h2>
                <p className="text-[12px] text-ink-muted mb-3">
                  {selectedTicket.email || selectedTicket.userId}
                </p>
                <p className="text-[13.5px] text-ink-secondary whitespace-pre-wrap mb-3">{selectedTicket.body}</p>
                {(selectedTicket.attachments?.length || 0) > 0 && (
                  <div className="support-detail__atts mb-3">
                    {selectedTicket.attachments!.map(a => (
                      <a key={a.id} href={a.url} target="_blank" rel="noreferrer" className="support-detail__att">
                        <img src={a.url} alt={a.name} loading="lazy" />
                        <span>{a.name}</span>
                      </a>
                    ))}
                  </div>
                )}
                <label>
                  Status
                  <select
                    value={selectedTicket.status}
                    disabled={busyId === selectedTicket.id}
                    onChange={e =>
                      void patchTicket(
                        selectedTicket.id,
                        { status: e.target.value },
                        { successTitle: 'Status updated', successBody: statusLabel(e.target.value) },
                      )
                    }
                  >
                    <option value="open">Open</option>
                    <option value="in_progress">In progress</option>
                    <option value="resolved">Resolved</option>
                    <option value="closed">Closed</option>
                  </select>
                </label>
                <label>
                  Priority
                  <select
                    value={selectedTicket.priority || 'normal'}
                    disabled={busyId === selectedTicket.id}
                    onChange={e =>
                      void patchTicket(
                        selectedTicket.id,
                        { priority: e.target.value },
                        { successTitle: 'Priority updated', successBody: e.target.value },
                      )
                    }
                  >
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                  </select>
                </label>
                <label>
                  Reply to customer
                  <textarea
                    rows={5}
                    value={ticketReply}
                    onChange={e => setTicketReply(e.target.value)}
                    placeholder="What should the customer know?"
                  />
                </label>
                <button
                  type="button"
                  className={`btn btn-primary mt-3${replyFeedback === 'ok' ? ' is-send-ok' : ''}${
                    replyFeedback === 'err' ? ' is-send-err' : ''
                  }`}
                  disabled={busyId === selectedTicket.id || !ticketReply.trim()}
                  onClick={() =>
                    void patchTicket(
                      selectedTicket.id,
                      {
                        adminReply: ticketReply.trim(),
                        status: selectedTicket.status === 'open' ? 'in_progress' : selectedTicket.status,
                      },
                      {
                        successTitle: 'Reply sent',
                        successBody: 'Customer can see it in Support',
                        isReply: true,
                      },
                    )
                  }
                >
                  {busyId === selectedTicket.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : replyFeedback === 'ok' ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : replyFeedback === 'err' ? (
                    <XCircle className="w-3.5 h-3.5" />
                  ) : null}
                  {busyId === selectedTicket.id
                    ? 'Sending…'
                    : replyFeedback === 'ok'
                      ? 'Sent'
                      : replyFeedback === 'err'
                        ? 'Failed — retry'
                        : 'Send reply'}
                </button>
                {replyFeedback !== 'idle' && replyFeedbackText && (
                  <p
                    className={`admin-send-flash ${replyFeedback === 'ok' ? 'is-ok' : 'is-err'}`}
                    role="status"
                  >
                    {replyFeedbackText}
                  </p>
                )}
              </div>
            )}
          </section>
        </div>
      )}

      {tab === 'ops' && (
        <>
      {overview && (
        <>
          <div className="admin-kpis">
            <div className="admin-kpi">
              <span className="admin-kpi__label">Users</span>
              <strong className="admin-kpi__value tabular-nums">{overview.stats.users}</strong>
              <span className="admin-kpi__hint">{overview.stats.suspended} suspended</span>
            </div>
            <div className="admin-kpi">
              <span className="admin-kpi__label">Active today</span>
              <strong className="admin-kpi__value tabular-nums">{overview.stats.activeToday}</strong>
              <span className="admin-kpi__hint">{overview.day}</span>
            </div>
            <div className="admin-kpi">
              <span className="admin-kpi__label">Hunts today</span>
              <strong className="admin-kpi__value tabular-nums">{overview.stats.usageToday.hunt}</strong>
              <span className="admin-kpi__hint">Extracts {overview.stats.usageToday.extract}</span>
            </div>
            <div className="admin-kpi">
              <span className="admin-kpi__label">Invites</span>
              <strong className="admin-kpi__value tabular-nums">{overview.stats.invites}</strong>
              <span className="admin-kpi__hint">
                {inviteOnly ? 'Invite-only on' : 'Open signup'}
              </span>
            </div>
          </div>

          <section className="admin-panel mt-4">
            <div className="admin-panel__head">
              <h2>Find Buyers research</h2>
            </div>
            <p className="text-[13px] text-ink-muted m-0 mb-3">
              Cap leads per hunt run to control Serper/API spend. The budget is split evenly across
              hunt lines (e.g. 40 leads ÷ 5 lines ≈ 8 each). The next hunt on the same workspace
              resumes from the next Google page instead of restarting at page 1.
            </p>
            <form className="admin-inline-form" onSubmit={saveHuntSettings}>
              <label className="admin-filter-bar__field">
                <span>Leads per run</span>
                <input
                  type="number"
                  min={5}
                  max={200}
                  value={huntLeadsPerRun}
                  onChange={e => setHuntLeadsPerRun(Number(e.target.value) || 40)}
                />
              </label>
              <label className="admin-filter-bar__field">
                <span>Max pages / search line</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={huntMaxPages}
                  onChange={e => setHuntMaxPages(Number(e.target.value) || 10)}
                />
              </label>
              <button type="submit" className="btn btn-primary" disabled={huntSettingsBusy}>
                {huntSettingsBusy ? 'Saving…' : 'Save hunt settings'}
              </button>
            </form>
            {huntSettingsMsg ? (
              <p className="admin-panel__foot mt-2" role="status">
                {huntSettingsMsg}
              </p>
            ) : (
              <p className="admin-panel__foot">
                Example: {huntLeadsPerRun} leads ÷ 5 hunt lines ≈{' '}
                {Math.max(1, Math.ceil(huntLeadsPerRun / 5))} leads each this run.
              </p>
            )}
          </section>

          <div className="admin-grid">
            <section className="admin-panel">
              <div className="admin-panel__head">
                <h2>Last 7 days</h2>
                <div className="admin-legend">
                  <span><i className="is-hunt" /> Hunts</span>
                  <span><i className="is-extract" /> Extracts</span>
                  <span><i className="is-prepare" /> Prepares</span>
                  <span><i className="is-send" /> Sends</span>
                </div>
              </div>
              <WeekChart series={overview.series} />
              <p className="admin-panel__foot">
                Defaults: {overview.defaults.hunt} hunts · {overview.defaults.extract} extracts ·{' '}
                {overview.defaults.prepare} prepares · {overview.defaults.send} sends / day
              </p>
            </section>

            <section className="admin-panel">
              <div className="admin-panel__head">
                <h2>Top burn today</h2>
              </div>
              {overview.topUsersToday.length === 0 ? (
                <div className="empty-state empty-state--compact">
                  <img src={brandAssets.emptyAdmin} alt="" className="empty-state__art" loading="lazy" decoding="async" />
                  <div className="empty-state__content">
                    <p className="empty-state__title">No usage yet today</p>
                    <p className="empty-state__desc">API burn will show here once pilots start hunting.</p>
                  </div>
                </div>
              ) : (
                <ul className="admin-top">
                  {overview.topUsersToday.map(u => (
                    <li key={u.id}>
                      <button type="button" onClick={() => setSelectedId(u.id)}>
                        <span className="admin-top__name">{u.name || u.email}</span>
                        <span className="admin-top__meta tabular-nums">
                          {u.hunts}h · {u.extracts}e · {u.prepares}p · {u.sends}s
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}

      <div className="admin-grid admin-grid--users">
        <section className="admin-panel admin-panel--stretch">
          <div className="admin-panel__head">
            <h2>Users</h2>
            <input
              type="search"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search email, name, plan…"
              className="admin-search"
            />
          </div>
          <div className="admin-filter-bar" aria-label="Filter users">
            <label className="admin-filter-bar__field">
              <span>Status</span>
              <select
                value={userStatusFilter}
                onChange={e => setUserStatusFilter(e.target.value as UserStatusFilter)}
              >
                {USER_STATUS_FILTERS.map(f => (
                  <option key={f.id} value={f.id}>
                    {f.label} ({userFilterCounts[f.id]})
                  </option>
                ))}
              </select>
            </label>
            {userStatusFilter !== 'all' && (
              <button
                type="button"
                className="btn btn-secondary admin-filter-bar__clear"
                onClick={() => setUserStatusFilter('all')}
              >
                Clear filter
              </button>
            )}
            <p className="admin-filter-bar__meta">
              Showing {filtered.length}
              {filtered.length !== users.length ? ` of ${users.length}` : ''} users
            </p>
          </div>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Plan</th>
                  <th>Today</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-6">
                      <div className="empty-state empty-state--compact">
                        <img src={brandAssets.emptyAdmin} alt="" className="empty-state__art" loading="lazy" decoding="async" />
                        <div className="empty-state__content">
                          <p className="empty-state__title">No users match</p>
                          <p className="empty-state__desc">Try clearing the status filter.</p>
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filtered.map(u => {
                  const used =
                    u.usageToday.used.hunt +
                    u.usageToday.used.extract +
                    u.usageToday.used.prepare +
                    u.usageToday.used.send;
                  return (
                    <tr
                      key={u.id}
                      className={selectedId === u.id ? 'is-selected' : ''}
                      onClick={() => setSelectedId(u.id)}
                    >
                      <td>
                        <div className="admin-user-cell">
                          {u.picture ? (
                            <img src={u.picture} alt="" className="admin-avatar" />
                          ) : (
                            <span className="admin-avatar admin-avatar--fallback">
                              {(u.name || u.email || '?').slice(0, 1).toUpperCase()}
                            </span>
                          )}
                          <div>
                            <div className="font-medium text-ink">
                              {u.name || '—'}
                              {u.isAdmin && <span className="admin-pill">Admin</span>}
                            </div>
                            <div className="text-[12px] text-ink-muted">{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="capitalize">{u.plan}</td>
                      <td className="tabular-nums text-[12.5px]">{used}</td>
                      <td>
                        {u.isSuspended ? (
                          <span className="admin-status is-bad">Suspended</span>
                        ) : u.usageUnlimited || u.isAdmin ? (
                          <span className="admin-status is-open">No caps</span>
                        ) : (
                          <span className="admin-status is-ok">Active</span>
                        )}
                      </td>
                    </tr>
                  );
                })
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="admin-panel">
          <div className="admin-panel__head">
            <h2>{selected ? 'User detail' : 'Select a user'}</h2>
          </div>
          {!selected ? (
            <p className="text-[13px] text-ink-muted leading-relaxed">
              Click a row to suspend, change plan, or raise daily caps for a pilot.
            </p>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="font-display text-[16px] font-semibold text-ink">{selected.name || '—'}</div>
                <div className="text-[12.5px] text-ink-muted">{selected.email}</div>
                <div className="text-[12px] text-ink-muted mt-1">
                  {selected.companyCount} companies · {selected.leadCount} leads
                </div>
              </div>

              <div className="space-y-2">
                <Meter
                  used={selected.usageToday.used.hunt}
                  limit={selected.usageToday.limits.hunt}
                  label="Hunts"
                  unlimited={Boolean(selected.usageUnlimited || selected.usageToday.bypassed)}
                />
                <Meter
                  used={selected.usageToday.used.extract}
                  limit={selected.usageToday.limits.extract}
                  label="Extracts"
                  unlimited={Boolean(selected.usageUnlimited || selected.usageToday.bypassed)}
                />
                <Meter
                  used={selected.usageToday.used.prepare}
                  limit={selected.usageToday.limits.prepare}
                  label="Prepares"
                  unlimited={Boolean(selected.usageUnlimited || selected.usageToday.bypassed)}
                />
                <Meter
                  used={selected.usageToday.used.send}
                  limit={selected.usageToday.limits.send}
                  label="Sends"
                  unlimited={Boolean(selected.usageUnlimited || selected.usageToday.bypassed)}
                />
              </div>

              <div className="admin-restrict-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busyId === selected.id}
                  onClick={() => void patchUser(selected.id, { liftAllCaps: true })}
                >
                  Lift all caps
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busyId === selected.id}
                  onClick={() => void patchUser(selected.id, { clearRestrictions: true })}
                >
                  Restore default caps
                </button>
              </div>
              <p className="text-[11.5px] text-ink-muted leading-snug m-0">
                Lift removes daily limits (still counts usage). Restore puts them back on the global defaults and unsuspends.
              </p>

              <label className="admin-check">
                <input
                  type="checkbox"
                  checked={Boolean(selected.usageUnlimited)}
                  disabled={busyId === selected.id || selected.isAdmin}
                  onChange={e =>
                    void patchUser(selected.id, { usageUnlimited: e.target.checked })
                  }
                />
                <span>
                  No daily limits
                  {selected.isAdmin ? ' (admins always bypass)' : ''}
                </span>
              </label>

              <label className="block text-[12px] font-medium text-ink-secondary">
                Plan
                <select
                  className="mt-1 w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel"
                  value={selected.plan}
                  disabled={busyId === selected.id}
                  onChange={e => void patchUser(selected.id, { plan: e.target.value })}
                >
                  <option value="pilot">Pilot</option>
                  <option value="free">Free</option>
                  <option value="pro">Pro</option>
                  <option value="growth">Growth</option>
                </select>
              </label>

              <div className="grid grid-cols-2 gap-2">
                {(['hunt', 'extract', 'prepare', 'send'] as const).map(kind => {
                  const key =
                    kind === 'hunt'
                      ? 'dailyHuntLimit'
                      : kind === 'extract'
                        ? 'dailyExtractLimit'
                        : kind === 'prepare'
                          ? 'dailyPrepareLimit'
                          : 'dailySendLimit';
                  const current = selected.limitOverrides[kind];
                  const mode =
                    selected.usageUnlimited || selected.isAdmin
                      ? 'unlimited'
                      : current == null
                        ? 'default'
                        : 'custom';
                  return (
                    <div key={kind} className="space-y-1">
                      <label className="block text-[11px] font-medium text-ink-secondary capitalize">
                        {kind} cap
                      </label>
                      <select
                        className="w-full border border-border rounded-md px-2 py-1.5 text-[13px] bg-panel"
                        value={mode}
                        disabled={busyId === selected.id || selected.usageUnlimited || selected.isAdmin}
                        onChange={e => {
                          const v = e.target.value;
                          if (v === 'default') void patchUser(selected.id, { [key]: -1 });
                          else if (v === 'unlimited') void patchUser(selected.id, { usageUnlimited: true });
                          else if (v === 'custom') {
                            const n = current ?? selected.usageToday.limits[kind] ?? 10;
                            void patchUser(selected.id, { [key]: n });
                          }
                        }}
                      >
                        <option value="default">Default</option>
                        <option value="custom">Custom</option>
                        <option value="unlimited">Unlimited (all)</option>
                      </select>
                      {mode === 'custom' && (
                        <input
                          type="number"
                          min={0}
                          className="w-full border border-border rounded-md px-2 py-1.5 text-[13px]"
                          defaultValue={current ?? ''}
                          key={`${selected.id}-${kind}-${current ?? 'd'}`}
                          disabled={busyId === selected.id}
                          onBlur={e => {
                            const raw = e.target.value.trim();
                            if (raw === '') {
                              void patchUser(selected.id, { [key]: -1 });
                              return;
                            }
                            const val = Number(raw);
                            if (Number.isNaN(val) || val < 0) return;
                            void patchUser(selected.id, { [key]: val });
                          }}
                        />
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busyId === selected.id}
                  onClick={() =>
                    void patchUser(selected.id, { isSuspended: !selected.isSuspended })
                  }
                >
                  <Ban className="w-3.5 h-3.5" />
                  {selected.isSuspended ? 'Unsuspend' : 'Suspend'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busyId === selected.id}
                  onClick={() => void patchUser(selected.id, { isAdmin: !selected.isAdmin })}
                >
                  <Shield className="w-3.5 h-3.5" />
                  {selected.isAdmin ? 'Remove admin' : 'Make admin'}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>

      <section className="admin-panel mt-4">
        <div className="admin-panel__head">
          <h2>Invite allowlist</h2>
          <span className="text-[12px] text-ink-muted">
            {inviteOnly ? 'Gates Google signup' : 'Signup is open — list still useful for tracking'}
          </span>
        </div>
        <p className="text-[12.5px] text-ink-muted mb-3 max-w-2xl">
          Adding an email unlocks sign-in for that Google account. When your admin Gmail is connected
          (Workspace → Connect), we also send them an invite email with the app link.
        </p>
        <form className="flex flex-col sm:flex-row gap-2 mb-3 max-w-2xl" onSubmit={e => void addInvite(e)}>
          <input
            type="email"
            value={inviteEmail}
            onChange={e => {
              setInviteEmail(e.target.value);
              if (inviteMsg) setInviteMsg('');
            }}
            placeholder="pilot@company.com"
            className="flex-1 border border-border rounded-md px-3 py-2 text-[13px]"
            autoComplete="email"
            required
          />
          <input
            type="text"
            value={inviteNote}
            onChange={e => setInviteNote(e.target.value)}
            placeholder="Note (optional)"
            className="sm:w-48 border border-border rounded-md px-3 py-2 text-[13px]"
          />
          <button
            type="submit"
            className="btn btn-primary inline-flex items-center justify-center gap-1.5"
            disabled={busyId === 'invite' || !inviteEmail.trim()}
          >
            {busyId === 'invite' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <UserPlus className="w-3.5 h-3.5" />
            )}
            {busyId === 'invite' ? 'Adding…' : 'Invite & email'}
          </button>
        </form>
        <button
          type="button"
          className="text-[12.5px] text-accent hover:underline mb-3"
          onClick={() => {
            const link = window.location.origin;
            void navigator.clipboard?.writeText(
              `You're invited to NexivoReach.\nSign in with Google at ${link}\n(Ask the operator to allowlist your email first.)`,
            );
            setInviteMsg('Copied a shareable invite blurb to clipboard.');
          }}
        >
          Copy invite blurb
        </button>
        {inviteMsg && (
          <p
            className={`text-[12.5px] mb-3 ${
              inviteMsg.toLowerCase().includes('email sent') || inviteMsg.toLowerCase().includes('allowlisted')
                ? 'text-[var(--accent)]'
                : 'text-amber-700'
            }`}
            role="status"
          >
            {inviteMsg}
          </p>
        )}
        {invites.length === 0 ? (
          <div className="empty-state empty-state--compact">
            <img src={brandAssets.emptyAdmin} alt="" className="empty-state__art" loading="lazy" decoding="async" />
            <div className="empty-state__content">
              <p className="empty-state__title">No invites yet</p>
              <p className="empty-state__desc">Add your first pilot email above to allowlist Google sign-in.</p>
            </div>
          </div>
        ) : (
          <ul className="admin-invites">
            {invites.map(inv => (
              <li key={inv.email}>
                <div>
                  <div className="font-medium text-ink flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--accent)]" />
                    {inv.email}
                  </div>
                  <div className="text-[12px] text-ink-muted">
                    {inv.note || 'No note'}
                    {inv.createdAt ? ` · ${inv.createdAt.slice(0, 10)}` : ''}
                  </div>
                </div>
                <button
                  type="button"
                  className="text-[12.5px] text-ink-secondary hover:text-ink"
                  disabled={busyId === inv.email}
                  onClick={() => void removeInvite(inv.email)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
        </>
      )}
    </div>
  );
}
