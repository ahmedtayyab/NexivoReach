interface Props {
  className?: string;
  title?: string;
}

/** Stylized N→ mark from the NexivoReach brand kit. */
export default function BrandMark({ className = 'w-5 h-5', title }: Props) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      fill="currentColor"
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
    >
      {title ? <title>{title}</title> : null}
      <path d="M6 26.5V5.5h4.8l8.35 13.15V5.5H25.5v21H20.7L12.35 13.35V26.5H6z" />
      <path d="M21.1 5.5H25.5v6.8l-5.6 6.9-2.35-3.7 3.55-10z" />
    </svg>
  );
}
