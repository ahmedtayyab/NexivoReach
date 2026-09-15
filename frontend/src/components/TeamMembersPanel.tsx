import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Loader2, UserPlus, Users, X } from 'lucide-react';
import { apiFetch } from '../lib/api';

type Member = {
  id: string;
  email: string;
  userId?: string | null;
  role: string;
  status: string;
  createdAt?: string;
};

type Props = {
  companyId: string;
  companyName?: string;
};

export default function TeamMembersPanel({ companyId, companyName }: Props) {
  const [members, setMembers] = useState<Member[]>([]);
  const [ownerEmail, setOwnerEmail] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    setError('');
    try {
      const resp = await apiFetch(`/api/companies/${companyId}/members`);
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setOwnerEmail(data.owner?.email || '');
      setMembers(Array.isArray(data.members) ? data.members : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load team');
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    void load();
  }, [load]);

  const invite = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setError('');
    setMsg('');
    try {
      const resp = await apiFetch(`/api/companies/${companyId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), role: 'member' }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Invite failed');
      setEmail('');
      setMsg(data.alreadyInvited ? 'Already invited' : `Invited ${data.email}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invite failed');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    setError('');
    try {
      const resp = await apiFetch(`/api/companies/${companyId}/members/${id}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error(await resp.text());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Remove failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="team-panel">
      <div className="team-panel__head">
        <p className="plan-usage__eyebrow">
          <Users className="w-3.5 h-3.5 inline-block mr-1" /> Team seats
        </p>
        <h2 className="plan-usage__title" style={{ fontSize: '1.05rem' }}>
          {companyName || 'This company'}
        </h2>
        <p className="plan-usage__lede">
          Invite teammates to the same workspace. Owner: {ownerEmail || 'you'}.
        </p>
      </div>

      {error && (
        <p className="ui-banner ui-banner--warn" role="alert">
          {error}
        </p>
      )}
      {msg && (
        <p className="ui-banner ui-banner--ok" role="status">
          {msg}
        </p>
      )}

      <form className="team-panel__form" onSubmit={e => void invite(e)}>
        <input
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="teammate@company.com"
          required
        />
        <button type="submit" className="btn btn-secondary" disabled={busy || !email.trim()}>
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UserPlus className="w-3.5 h-3.5" />}
          Invite
        </button>
      </form>

      {loading ? (
        <p className="text-[12.5px] text-ink-muted flex items-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading seats…
        </p>
      ) : (
        <ul className="team-panel__list">
          {members.length === 0 && (
            <li className="text-[12.5px] text-ink-muted">No seats yet — invite someone to collaborate.</li>
          )}
          {members.map(m => (
            <li key={m.id}>
              <div>
                <strong>{m.email}</strong>
                <span>
                  {m.role} · {m.status}
                </span>
              </div>
              <button type="button" className="btn btn-ghost" aria-label="Remove" onClick={() => void remove(m.id)}>
                <X className="w-3.5 h-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
