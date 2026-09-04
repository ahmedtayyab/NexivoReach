interface Props {
  active?: boolean;
  className?: string;
}

/** Live radar sweep — CSS animation (lighter and sharper than a video loop). */
export default function RadarSweep({ active = false, className = '' }: Props) {
  return (
    <div
      className={`radar-stage relative overflow-hidden rounded-lg border border-border bg-panel ${className}`}
      aria-hidden
    >
      <div className="absolute inset-0 radar-grid" />
      <div className={`radar-dish ${active ? 'radar-dish-active' : ''}`}>
        <div className="radar-ring radar-ring-1" />
        <div className="radar-ring radar-ring-2" />
        <div className="radar-ring radar-ring-3" />
        <div className="radar-ring radar-ring-4" />
        <div className="radar-sweep" />
        <div className="radar-blip radar-blip-a" />
        <div className="radar-blip radar-blip-b" />
        <div className="radar-blip radar-blip-c" />
        <div className="radar-hub" />
      </div>
      <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between pointer-events-none">
        <span className="text-[11px] font-medium tracking-wide uppercase text-accent/80">
          {active ? 'Scanning markets' : 'Ready to scan'}
        </span>
        <span className="text-[11px] tabular-nums text-ink-muted">
          {active ? 'LIVE' : 'IDLE'}
        </span>
      </div>
    </div>
  );
}
