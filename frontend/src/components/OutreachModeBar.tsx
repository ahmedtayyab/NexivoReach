import type { OutreachMode, OutreachTemplate } from '../types';
import { FilePenLine } from 'lucide-react';

type Props = {
  mode: OutreachMode;
  templateCount: number;
  onModeChange: (mode: OutreachMode) => void | Promise<void>;
  onGoTemplates?: () => void;
  busy?: boolean;
  /** Saved templates — shown so the user always knows which copy is active. */
  templates?: OutreachTemplate[];
  /** Name of the template used on the currently open draft (if any). */
  activeDraftTemplateName?: string;
};

/**
 * Draft-mode control for Outreach — selected template mode is always visible.
 */
export default function OutreachModeBar({
  mode,
  templateCount,
  onModeChange,
  onGoTemplates,
  busy = false,
  templates = [],
  activeDraftTemplateName = '',
}: Props) {
  const usingTemplates = mode === 'templates';
  const names = templates
    .map(t => (t.name || '').trim())
    .filter(Boolean)
    .slice(0, 6);

  const selectTemplates = () => {
    if (templateCount <= 0) {
      onGoTemplates?.();
      return;
    }
    void onModeChange('templates');
  };

  return (
    <div className="outreach-mode-bar nr-enter nr-enter-delay-1">
      <div className="outreach-mode-bar__row">
        <span className="outreach-mode-bar__label">Draft mode</span>
        <div className="seg outreach-mode-bar__seg" role="group" aria-label="Draft mode">
          <button
            type="button"
            className={mode === 'ai' ? 'is-active' : ''}
            disabled={busy}
            onClick={() => void onModeChange('ai')}
          >
            AI-generated
          </button>
          <button
            type="button"
            className={usingTemplates ? 'is-active' : ''}
            disabled={busy}
            onClick={selectTemplates}
          >
            Custom email template
          </button>
        </div>
        {onGoTemplates && (
          <button type="button" className="btn btn-ghost outreach-mode-bar__edit" onClick={onGoTemplates}>
            <FilePenLine className="w-3.5 h-3.5" strokeWidth={2} aria-hidden />
            {templateCount > 0 ? `Edit (${templateCount})` : 'Add templates'}
          </button>
        )}
      </div>

      {usingTemplates ? (
        <div className="ui-banner ui-banner--ok outreach-mode-bar__status" role="status">
          <p className="m-0">
            <strong>Custom email templates are active.</strong>{' '}
            Prepare matches each lead by product tags and keywords — not broad categories.
          </p>
          {activeDraftTemplateName ? (
            <p className="m-0 mt-1.5 text-[13px]">
              This draft:{' '}
              <strong>{activeDraftTemplateName}</strong>
            </p>
          ) : null}
          {names.length > 0 ? (
            <p className="m-0 mt-1.5 text-[12.5px] text-ink-secondary">
              Your templates: {names.join(' · ')}
              {templateCount > names.length ? ` · +${templateCount - names.length} more` : ''}
            </p>
          ) : (
            onGoTemplates && (
              <p className="m-0 mt-1.5">
                <button type="button" className="linkish" onClick={onGoTemplates}>
                  Add a template
                </button>
              </p>
            )
          )}
        </div>
      ) : (
        <p className="outreach-mode-bar__hint" role="status">
          AI writes a fresh draft per lead.
          {templateCount > 0 && (
            <>
              {' '}
              Switch to <strong>Custom email template</strong> to send your saved copy instead.
            </>
          )}
        </p>
      )}
    </div>
  );
}
