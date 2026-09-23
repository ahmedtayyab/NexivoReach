import type { OutreachMode } from '../types';
import { FilePenLine } from 'lucide-react';

type Props = {
  mode: OutreachMode;
  templateCount: number;
  onModeChange: (mode: OutreachMode) => void | Promise<void>;
  onGoTemplates?: () => void;
  busy?: boolean;
};

/**
 * Draft-mode control for Outreach — makes “Use my templates” visible and active state obvious.
 */
export default function OutreachModeBar({
  mode,
  templateCount,
  onModeChange,
  onGoTemplates,
  busy = false,
}: Props) {
  const usingTemplates = mode === 'templates';

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
            Use my templates
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
        <p className="ui-banner ui-banner--ok outreach-mode-bar__status" role="status">
          <strong>Your templates are active.</strong> Prepare matches each lead by category and uses
          your copy — not AI-written drafts.
          {templateCount <= 0 && onGoTemplates && (
            <>
              {' '}
              <button type="button" className="linkish" onClick={onGoTemplates}>
                Add a template
              </button>
            </>
          )}
        </p>
      ) : (
        <p className="outreach-mode-bar__hint" role="status">
          AI writes a fresh draft per lead.
          {templateCount > 0 && (
            <>
              {' '}
              Switch to <strong>Use my templates</strong> to send your saved copy instead.
            </>
          )}
        </p>
      )}
    </div>
  );
}
