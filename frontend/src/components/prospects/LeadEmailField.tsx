import { useState } from 'react';
import { ExternalLink, Loader2, Mail, MailWarning, X } from 'lucide-react';
import type { Prospect } from '../../types';
import { recipientEmails } from '../../lib/leadTone';

interface Props {
  prospect: Prospect;
  onSave: (id: string, emails: string[]) => Promise<void> | void;
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
  const current = recipientEmails(prospect);
  const site = (prospect.website || '').trim();
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<string[]>(current.length ? current : ['']);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const startEdit = (addBlank = false) => {
    const next = recipientEmails(prospect);
    setRows(addBlank || next.length === 0 ? [...next, ''] : next);
    setError('');
    setEditing(true);
  };

  const save = async () => {
    const next = rows.map(item => item.trim()).filter(Boolean);
    const invalid = next.find(item => !looksLikeEmail(item));
    if (invalid) {
      setError('Enter a full email, like name@company.com');
      return;
    }
    const unique = next.filter((item, index) => next.findIndex(other => other.toLowerCase() === item.toLowerCase()) === index);
    if (unique.length > 8) {
      setError('A company can have up to 8 emails');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onSave(prospect.id, unique);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save those emails');
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
          {rows.map((value, index) => (
            <div className="lead-email-editor__row" key={index}>
              <input
                type="email"
                value={value}
                autoFocus={index === rows.length - 1}
                placeholder="name@company.com"
                aria-label={`Email ${index + 1} for ${prospect.companyName}`}
                disabled={saving}
                onChange={event => {
                  const next = [...rows];
                  next[index] = event.target.value;
                  setRows(next);
                }}
              />
              <button
                type="button"
                className="lead-email-editor__remove"
                aria-label={`Remove email ${index + 1}`}
                disabled={saving}
                onClick={() => setRows(rows.filter((_, item) => item !== index))}
              >
                <X className="w-3 h-3" strokeWidth={1.75} />
              </button>
            </div>
          ))}
          <p className="lead-email-editor__hint">All of these are emailed together.</p>
          {rows.length < 8 && (
            <button
              type="button"
              className="linkish lead-email__find"
              disabled={saving}
              onClick={() => setRows([...rows, ''])}
            >
              Add email
            </button>
          )}
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
        <div className="lead-email-editor__list">
          {current.length ? (
            current.map(email => (
              <div key={email} className="lead-email is-ok">
                <Mail className="w-3 h-3 shrink-0" strokeWidth={1.75} />
                <span className="lead-email-editor__value" title={email}>{email}</span>
              </div>
            ))
          ) : (
            <div className="lead-email is-missing">
              <MailWarning className="w-3 h-3 shrink-0" strokeWidth={1.75} />
              <span>No email</span>
            </div>
          )}
          <div className="lead-email-editor__actions">
            <button type="button" className="linkish lead-email__find" onClick={() => startEdit(false)}>
              {current.length ? 'Edit' : 'Add'}
            </button>
            {current.length > 0 && current.length < 8 && (
              <button type="button" className="linkish lead-email__find" onClick={() => startEdit(true)}>
                Add email
              </button>
            )}
            {!current.length && onFind && (
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
        </div>
      )}
    </div>
  );
}
