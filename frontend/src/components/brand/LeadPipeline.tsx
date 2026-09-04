interface Props {
  /** When true, cards move faster (e.g. fresh leads waiting). */
  active?: boolean;
  className?: string;
}

/** Pipeline vignette — lead cards advancing through review stages. */
export default function LeadPipeline({ active = false, className = '' }: Props) {
  return (
    <div
      className={`scene-stage lead-stage relative overflow-hidden rounded-lg border border-border bg-panel ${className}`}
      aria-hidden
    >
      <div className="absolute inset-0 scene-grid" />
      <div className={`lead-track ${active ? 'lead-track-active' : ''}`}>
        <div className="lead-lane" />
        <div className="lead-card lead-card-a">
          <span className="lead-card-bar" />
          <span className="lead-card-line long" />
          <span className="lead-card-line mid" />
        </div>
        <div className="lead-card lead-card-b">
          <span className="lead-card-bar" />
          <span className="lead-card-line mid" />
          <span className="lead-card-line short" />
        </div>
        <div className="lead-card lead-card-c">
          <span className="lead-card-bar" />
          <span className="lead-card-line long" />
          <span className="lead-card-line short" />
        </div>
        <div className="lead-cursor" />
        <div className="lead-nodes">
          <span className="lead-node" />
          <span className="lead-node" />
          <span className="lead-node" />
          <span className="lead-node" />
        </div>
      </div>
      <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between pointer-events-none">
        <span className="text-[11px] font-medium tracking-wide uppercase text-accent/80">
          {active ? 'Queue in motion' : 'Lead pipeline'}
        </span>
        <span className="text-[11px] tabular-nums text-ink-muted">
          {active ? 'LIVE' : 'IDLE'}
        </span>
      </div>
    </div>
  );
}
