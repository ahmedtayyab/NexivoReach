import { brandAssets } from '../../lib/brandAssets';

export type AmbientVariant =
  | 'leads'
  | 'outreach'
  | 'activity'
  | 'support'
  | 'workspace'
  | 'admin'
  | 'notifications';

const VARIANT_SRC: Record<AmbientVariant, string> = {
  leads: brandAssets.emptyQueue,
  outreach: brandAssets.emptyOutreach,
  activity: brandAssets.emptyActivity,
  support: brandAssets.emptySupport,
  workspace: brandAssets.emptySupport,
  admin: brandAssets.emptyAdmin,
  notifications: brandAssets.emptyNotifications,
};

type Props = {
  variant: AmbientVariant;
  /** Quieter mark for dense pages (tables, editors). */
  tone?: 'soft' | 'whisper';
  className?: string;
};

/**
 * Decorative page atmosphere — visual only, no interaction or layout shift for content.
 */
export default function PageAmbient({ variant, tone = 'soft', className = '' }: Props) {
  return (
    <img
      src={VARIANT_SRC[variant]}
      alt=""
      aria-hidden
      className={`page-ambient page-ambient--${tone} ${className}`.trim()}
      loading="lazy"
      decoding="async"
    />
  );
}
