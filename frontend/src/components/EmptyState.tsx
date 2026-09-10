interface Props {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  imageSrc?: string;
  imageAlt?: string;
}

/** Shared empty / no-results surface — part of the product, not an afterthought. */
export default function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  imageSrc,
  imageAlt = '',
}: Props) {
  return (
    <div className="empty-state">
      {imageSrc ? (
        <img src={imageSrc} alt={imageAlt} className="empty-state__art" />
      ) : null}
      <p className="empty-state__title">{title}</p>
      <p className="empty-state__desc">{description}</p>
      {actionLabel && onAction ? (
        <button type="button" className="btn btn-primary mt-4" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
