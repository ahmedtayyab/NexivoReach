import { useEffect, useState } from 'react';
import type { AuthUser } from '../types';
import { apiFetch } from '../lib/api';
import { planLabel, usageKinds } from '../lib/outcomes';

type Props = {
  user: AuthUser | null | undefined;
  compact?: boolean;
  onAskSupport?: () => void;
};

export default function PlanUsageCard({ user, compact = false, onAskSupport }: Props) {
  const usage = user?.usage;
  const plan = planLabel(user?.plan);
  const bypassed = Boolean(usage?.bypassed);
  const [billingReady, setBillingReady] = useState(false);
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState('');

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const resp = await apiFetch('/api/billing/status');
        if (!resp.ok) return;
        const data = await resp.json();
        if (!cancelled) setBillingReady(Boolean(data.configured));
      } catch {
        // offline / unconfigured
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const startCheckout = async (nextPlan: 'pro' | 'growth') => {
    setBusy(nextPlan);
    setMsg('');
    try {
      const resp = await apiFetch('/api/billing/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan: nextPlan }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Checkout unavailable');
      }
      if (data.url) {
        window.location.href = data.url as string;
        return;
      }
      throw new Error('No checkout URL returned');
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Checkout failed');
      onAskSupport?.();
    } finally {
      setBusy('');
    }
  };

  const openPortal = async () => {
    setBusy('portal');
    setMsg('');
    try {
      const resp = await apiFetch('/api/billing/portal', { method: 'POST' });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Portal unavailable');
      }
      if (data.url) window.location.href = data.url as string;
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Portal failed');
    } finally {
      setBusy('');
    }
  };

  return (
    <section className={`plan-usage ${compact ? 'plan-usage--compact' : ''}`}>
      <div className="plan-usage__head">
        <div>
          <p className="plan-usage__eyebrow">Plan & usage</p>
          <h2 className="plan-usage__title">{plan}</h2>
          <p className="plan-usage__lede">
            {bypassed
              ? 'Unlimited today — caps do not apply to this account.'
              : usage
                ? `Daily allowances reset at midnight UTC · ${usage.day}`
                : 'Sign in to see today’s remaining hunts and sends.'}
          </p>
        </div>
        <div className="plan-usage__actions">
          {billingReady ? (
            <>
              <button
                type="button"
                className="btn btn-primary"
                disabled={Boolean(busy)}
                onClick={() => void startCheckout('pro')}
              >
                {busy === 'pro' ? 'Opening…' : 'Upgrade to Pro'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={Boolean(busy)}
                onClick={() => void startCheckout('growth')}
              >
                {busy === 'growth' ? 'Opening…' : 'Growth'}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={Boolean(busy)}
                onClick={() => void openPortal()}
              >
                {busy === 'portal' ? 'Opening…' : 'Manage billing'}
              </button>
            </>
          ) : (
            onAskSupport && (
              <button type="button" className="btn btn-secondary" onClick={onAskSupport}>
                Need higher limits?
              </button>
            )
          )}
        </div>
      </div>
      {msg && (
        <p className="ui-banner ui-banner--warn mb-3" role="status">
          {msg}
        </p>
      )}

      {usage && (
        <div className="plan-usage__meters" aria-label="Daily usage">
          {usageKinds().map(({ id, label }) => {
            const used = usage.used[id] ?? 0;
            const limit = bypassed ? Math.max(used, 1) : usage.limits[id] ?? 0;
            const remaining = bypassed ? null : usage.remaining[id] ?? 0;
            const pct = bypassed ? 8 : limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
            const tight = !bypassed && remaining !== null && remaining <= 1;
            return (
              <div key={id} className={`plan-usage__meter${tight ? ' is-tight' : ''}`}>
                <div className="plan-usage__meter-top">
                  <span>{label}</span>
                  <span className="tabular-nums">
                    {bypassed ? `${used} used` : `${used} / ${limit}`}
                  </span>
                </div>
                <div className="plan-usage__track" aria-hidden>
                  <div className="plan-usage__fill" style={{ width: `${pct}%` }} />
                </div>
                {!bypassed && remaining !== null && (
                  <p className="plan-usage__remain">
                    {remaining === 0 ? 'None left today' : `${remaining} left today`}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
