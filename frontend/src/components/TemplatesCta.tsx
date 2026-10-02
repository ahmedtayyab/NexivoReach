import { FilePenLine } from 'lucide-react';

type Props = {
  templateCount: number;
  onClick: () => void;
  className?: string;
};

/**
 * Highlighted entry to outreach templates — pulse when none saved yet.
 */
export default function TemplatesCta({ templateCount, onClick, className = '' }: Props) {
  const empty = templateCount <= 0;
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'btn',
        empty ? 'btn-primary nr-soft-pulse templates-cta' : 'btn-secondary templates-cta',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      title={empty ? 'Write your outreach email templates' : 'Edit your outreach templates'}
    >
      <FilePenLine className="w-3.5 h-3.5" strokeWidth={2} aria-hidden />
      {empty ? 'Add templates' : `Templates (${templateCount})`}
    </button>
  );
}
