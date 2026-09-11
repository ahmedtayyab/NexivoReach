import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Loader2, Shield, UserPlus, Ban, CheckCircle2, RefreshCw } from 'lucide-react';
import { apiFetch } from '../lib/api';

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

export default function AdminView() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [inviteOnly, setInviteOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteNote, setInviteNote] = useState('');
  const [inviteMsg, setInviteMsg] = useState('');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [o, u, a] = await Promise.all([
        apiFetch('/api/admin/overview'),
        apiFetch('/api/admin/users'),
        apiFetch('/api/admin/allowlist'),
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
      const overviewData = (await o.json()) as Overview;
      const usersData = await u.json();
      const allowData = await a.json();
      setOverview(overviewData);
      setUsers(Array.isArray(usersData.users) ? usersData.users : []);
      setInvites(Array.isArray(allowData.invites) ? allowData.invites : []);
      setInviteOnly(Boolean(allowData.inviteOnly ?? overviewData.inviteOnly));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load admin');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      u =>
        u.email.toLowerCase().includes(q) ||
        (u.name || '').toLowerCase().includes(q) ||
        (u.plan || '').toLowerCase().includes(q),
    );
  }, [users, query]);

  const selected = users.find(u => u.id === selectedId) || null;

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
        return [created, ...without];
      });
      setInviteEmail('');
      setInviteNote('');
      setInviteMsg(`Invited ${created.email} — they can sign in with Google now.`);
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
      <div className="admin-desk flex items-center justify-center min-h-[40vh] text-ink-muted gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading ops…
      </div>
    );
  }

  return (
    <div className="admin-desk">
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
                <p className="text-[13px] text-ink-muted">No usage yet today.</p>
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
                {filtered.map(u => {
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
                })}
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
            {inviteOnly ? 'New signups need an invite' : 'Signup is open — list still useful for tracking'}
          </span>
        </div>
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
            {busyId === 'invite' ? 'Adding…' : 'Invite'}
          </button>
        </form>
        {inviteMsg && (
          <p
            className={`text-[12.5px] mb-3 ${inviteMsg.toLowerCase().includes('invited') ? 'text-[var(--accent)]' : 'text-amber-700'}`}
            role="status"
          >
            {inviteMsg}
          </p>
        )}
        {invites.length === 0 ? (
          <p className="text-[13px] text-ink-muted">No invites yet. Add your first pilot email above.</p>
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
    </div>
  );
}
