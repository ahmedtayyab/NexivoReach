interface Props {
  active?: boolean;
  className?: string;
}

/** Inbox vignette — envelopes cycling through review. */
export default function MailFlow({ active = false, className = '' }: Props) {
  return (
    <div
      className={`scene-stage mail-stage relative overflow-hidden rounded-lg border border-border bg-panel ${className}`}
      aria-hidden
    >
      <div className="absolute inset-0 scene-grid" />
      <div className={`mail-scene ${active ? 'mail-scene-active' : ''}`}>
        <div className="mail-stack">
          <div className="mail-env mail-env-1">
            <span className="mail-flap" />
            <span className="mail-lines">
              <i />
              <i />
              <i />
            </span>
          </div>
          <div className="mail-env mail-env-2">
            <span className="mail-flap" />
            <span className="mail-lines">
              <i />
              <i />
            </span>
          </div>
          <div className="mail-env mail-env-3">
            <span className="mail-flap" />
            <span className="mail-lines">
              <i />
              <i />
              <i />
            </span>
          </div>
        </div>
        <div className="mail-scan" />
        <div className="mail-stamp" />
      </div>
      <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between pointer-events-none">
        <span className="text-[11px] font-medium tracking-wide uppercase text-accent/80">
          {active ? 'Drafts ready' : 'Outreach inbox'}
        </span>
        <span className="text-[11px] tabular-nums text-ink-muted">
          {active ? 'LIVE' : 'IDLE'}
        </span>
      </div>
    </div>
  );
}
