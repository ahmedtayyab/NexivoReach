interface Props {
  active?: boolean;
  className?: string;
}

/** Activity vignette — tool steps lighting along a trace. */
export default function TracePulse({ active = false, className = '' }: Props) {
  return (
    <div
      className={`scene-stage trace-stage relative overflow-hidden rounded-lg border border-border bg-panel ${className}`}
      aria-hidden
    >
      <div className="absolute inset-0 scene-grid" />
      <div className={`trace-scene ${active ? 'trace-scene-active' : ''}`}>
        <div className="trace-rail" />
        <div className="trace-pulse" />
        <div className="trace-step trace-step-1">
          <span className="trace-dot" />
          <span className="trace-label" />
        </div>
        <div className="trace-step trace-step-2">
          <span className="trace-dot" />
          <span className="trace-label short" />
        </div>
        <div className="trace-step trace-step-3">
          <span className="trace-dot" />
          <span className="trace-label" />
        </div>
        <div className="trace-step trace-step-4">
          <span className="trace-dot" />
          <span className="trace-label short" />
        </div>
      </div>
      <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between pointer-events-none">
        <span className="text-[11px] font-medium tracking-wide uppercase text-accent/80">
          {active ? 'Run traces' : 'Operational log'}
        </span>
        <span className="text-[11px] tabular-nums text-ink-muted">
          {active ? 'LIVE' : 'IDLE'}
        </span>
      </div>
    </div>
  );
}
