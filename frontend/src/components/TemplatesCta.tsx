import { FilePenLine } from 'lucide-react';

type Props = {
  templateCount: number;
  onClick: () => void;
  className?: string;
};

/** Secondary entry to outreach templates — never competes with primary work CTAs. */
export default function TemplatesCta({ templateCount, onClick, className = '' }: Props) {
  const empty = templateCount <= 0;
  return (
    <button
      type="button"
      onClick={onClick}
      className={['btn', 'btn-secondary', 'templates-cta', className].filter(Boolean).join(' ')}
      title={empty ? 'Write your outreach email templates' : 'Edit your outreach templates'}
    >
      <FilePenLine className="w-3.5 h-3.5" strokeWidth={2} aria-hidden />
      {empty ? 'Add templates' : `Templates (${templateCount})`}
    </button>
  );
}
