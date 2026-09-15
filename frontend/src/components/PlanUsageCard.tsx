import type { AuthUser } from '../types';
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
        {onAskSupport && (
          <button type="button" className="btn btn-secondary" onClick={onAskSupport}>
            Need higher limits?
          </button>
        )}
      </div>

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
