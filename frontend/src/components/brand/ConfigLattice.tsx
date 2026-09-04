interface Props {
  active?: boolean;
  className?: string;
}

/** Settings vignette — connected config nodes. */
export default function ConfigLattice({ active = false, className = '' }: Props) {
  return (
    <div
      className={`scene-stage config-stage relative overflow-hidden rounded-lg border border-border bg-panel ${className}`}
      aria-hidden
    >
      <div className="absolute inset-0 scene-grid" />
      <div className={`config-scene ${active ? 'config-scene-active' : ''}`}>
        <svg className="config-links" viewBox="0 0 320 120" preserveAspectRatio="none">
          <path className="config-link config-link-a" d="M80 60 L160 32 L240 60" fill="none" />
          <path className="config-link config-link-b" d="M80 60 L160 88 L240 60" fill="none" />
          <path className="config-link config-link-c" d="M160 32 L160 88" fill="none" />
        </svg>
        <span className="config-node config-node-l" />
        <span className="config-node config-node-t" />
        <span className="config-node config-node-r" />
        <span className="config-node config-node-b" />
        <span className="config-hub" />
      </div>
      <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between pointer-events-none">
        <span className="text-[11px] font-medium tracking-wide uppercase text-accent/80">
          Workspace config
        </span>
        <span className="text-[11px] tabular-nums text-ink-muted">
          {active ? 'SYNC' : 'SET'}
        </span>
      </div>
    </div>
  );
}
