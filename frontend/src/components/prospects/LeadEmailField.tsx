import { useState } from 'react';
import { ExternalLink, Loader2, Mail, MailWarning } from 'lucide-react';
import type { Prospect } from '../../types';
import { recipientEmail } from '../../lib/leadTone';

interface Props {
  prospect: Prospect;
  onSave: (id: string, email: string) => Promise<void> | void;
  onFind?: (id: string) => Promise<void> | void;
  finding?: boolean;
  showWebsite?: boolean;
}

function websiteHref(raw: string): string {
  const value = raw.trim();
  if (!value) return '';
  if (/^https?:\/\//i.test(value)) return value;
  return `https://${value}`;
}

function websiteLabel(raw: string): string {
  const href = websiteHref(raw);
  try {
    return new URL(href).hostname.replace(/^www\./, '');
  } catch {
    return raw.trim();
  }
}

function looksLikeEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function LeadEmailField({ prospect, onSave, onFind, finding, showWebsite }: Props) {
  const current = recipientEmail(prospect);
  const site = (prospect.website || '').trim();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(current);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const startEdit = () => {
    setValue(recipientEmail(prospect));
    setError('');
    setEditing(true);
  };

  const save = async () => {
    const next = value.trim();
    if (next && !looksLikeEmail(next)) {
      setError('Enter a full email, like name@company.com');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onSave(prospect.id, next);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save that email');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="lead-email-editor" onClick={event => event.stopPropagation()}>
      {showWebsite && site && (
        <a
          className="lead-email-editor__site"
          href={websiteHref(site)}
          target="_blank"
          rel="noreferrer"
          title={`Open ${site}`}
        >
          <span>{websiteLabel(site)}</span>
          <ExternalLink className="w-3 h-3 shrink-0" strokeWidth={1.75} />
        </a>
      )}
      {editing ? (
        <form
          className="lead-email-editor__form"
          onSubmit={event => {
            event.preventDefault();
            void save();
          }}
        >
          <input
            type="email"
            value={value}
            autoFocus
            placeholder="name@company.com"
            aria-label={`Email for ${prospect.companyName}`}
            disabled={saving}
            onChange={event => setValue(event.target.value)}
          />
          <button type="submit" className="btn btn-primary lead-email-editor__btn" disabled={saving}>
            {saving ? 'Saving' : 'Save'}
          </button>
          <button
            type="button"
            className="btn btn-ghost lead-email-editor__btn"
            disabled={saving}
            onClick={() => setEditing(false)}
          >
            Cancel
          </button>
          {error && <p className="lead-email-editor__error">{error}</p>}
        </form>
      ) : (
        <div className={`lead-email ${current ? 'is-ok' : 'is-missing'}`}>
          {current ? <Mail className="w-3 h-3 shrink-0" strokeWidth={1.75} /> : <MailWarning className="w-3 h-3 shrink-0" strokeWidth={1.75} />}
          {current ? (
            <button type="button" className="lead-email-editor__value" title={current} onClick={startEdit}>
              {current}
            </button>
          ) : (
            <span>No email</span>
          )}
          <button type="button" className="linkish lead-email__find" onClick={startEdit}>
            {current ? 'Edit' : 'Add'}
          </button>
          {!current && onFind && (
            <button
              type="button"
              className="linkish lead-email__find"
              title="Search this website for an email"
              disabled={finding}
              onClick={() => void onFind(prospect.id)}
            >
              {finding ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Find'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
