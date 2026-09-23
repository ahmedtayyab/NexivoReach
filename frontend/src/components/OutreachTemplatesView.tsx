import type { OutreachMode, OutreachTemplate, Product } from '../types';
import PageAmbient from './brand/PageAmbient';
import OutreachTemplatesSection from './workspace/OutreachTemplatesSection';

type Props = {
  templates: OutreachTemplate[];
  outreachMode: OutreachMode;
  products: Product[];
  onSave: (next: OutreachTemplate[], mode: OutreachMode) => void | Promise<void>;
  onBack: () => void;
};

/**
 * Dedicated page to create / edit category-safe outreach email templates.
 */
export default function OutreachTemplatesView({
  templates,
  outreachMode,
  products,
  onSave,
  onBack,
}: Props) {
  const empty = templates.length === 0;

  return (
    <div className="page-shell max-w-2xl w-full">
      <PageAmbient variant="outreach" tone="whisper" />
      <header className="page-header nr-enter">
        <button type="button" className="setup-desk__back" onClick={onBack}>
          ← Back
        </button>
        <h1 className="page-header__title">
          {empty ? 'Add outreach templates' : 'Outreach templates'}
        </h1>
        <p className="page-header__desc">
          {empty
            ? 'Write your emails, or keep AI drafting — pick a mode below.'
            : 'Edit templates or switch back to AI-generated drafts.'}
        </p>
      </header>

      <div className="ws-panel ws-panel--wide nr-enter nr-enter-delay-1">
        <OutreachTemplatesSection
          key={`tpl-page-${templates.length}-${outreachMode}`}
          templates={templates}
          outreachMode={outreachMode}
          products={products}
          onSave={onSave}
          hideIntro
        />
      </div>
    </div>
  );
}
