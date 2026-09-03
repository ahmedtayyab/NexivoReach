interface Props {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  showWordmark?: boolean;
}

const sizes = {
  sm: { mark: 'w-6 h-6', text: 'text-sm', gap: 'gap-1.5' },
  md: { mark: 'w-9 h-9', text: 'text-base', gap: 'gap-2' },
  lg: { mark: 'w-11 h-11', text: 'text-lg', gap: 'gap-2.5' },
};

/** Uses /brand/* from public/ so images work in Vite and FastAPI static serve. */
export default function BrandLockup({ size = 'sm', className = '', showWordmark = true }: Props) {
  const s = sizes[size];
  return (
    <div className={`flex items-center ${s.gap} ${className}`}>
      <img
        src="/brand/nr-mark.png"
        alt="NexivoReach"
        width={36}
        height={36}
        className={`${s.mark} rounded-md object-cover shrink-0 shadow-sm ring-1 ring-border/60`}
      />
      {showWordmark && (
        <span className={`font-semibold text-ink tracking-tight ${s.text}`}>NexivoReach</span>
      )}
    </div>
  );
}
