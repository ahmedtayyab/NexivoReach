import { useEffect, useId, useRef, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import {
  activeToken,
  csvIncludes,
  filterMatches,
  toggleCsvValue,
} from '../data/taxonomy';
import { apiFetch } from '../lib/api';

interface Props {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  /** Full pool of chip / dropdown options for this field */
  suggestions: string[];
  placeholder: string;
  /** Sent to light AI when user clicks "Suggest for me" */
  aiContext?: {
    field: 'categories' | 'buyers' | 'markets' | 'discover';
    description?: string;
    catalogCategories?: string[];
  };
  /** Single-value mode (Discover query) — replace instead of CSV toggle */
  single?: boolean;
}

/**
 * Predictive field = typeahead dropdown (as you type) + clickable chips.
 * Optional "Suggest for me" uses light AI when taxonomy is not enough.
 */
export default function PredictiveField({
  label,
  hint,
  value,
  onChange,
  suggestions,
  placeholder,
  aiContext,
  single = false,
}: Props) {
  const listId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');

  const token = single ? value.trim() : activeToken(value);
  const matches = filterMatches(suggestions, token, 8).filter(
    item => single || !csvIncludes(value, item),
  );

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const pick = (item: string) => {
    if (single) {
      onChange(item);
    } else {
      // Replace the incomplete last token with the chosen suggestion
      const parts = value.split(',').map(s => s.trim()).filter(Boolean);
      const incomplete = activeToken(value);
      const base = incomplete
        ? parts.slice(0, -1)
        : parts;
      const withoutDup = base.filter(p => p.toLowerCase() !== item.toLowerCase());
      onChange([...withoutDup, item].join(', '));
    }
    setOpen(false);
  };

  const handleSuggestAi = async () => {
    if (!aiContext || aiLoading) return;
    setAiLoading(true);
    setAiError('');
    try {
      const resp = await apiFetch('/api/suggestions/expand', {
        method: 'POST',
        body: JSON.stringify({
          field: aiContext.field,
          query: value || token,
          description: aiContext.description || '',
          catalogCategories: aiContext.catalogCategories || [],
        }),
      });
      if (!resp.ok) throw new Error('Suggest failed');
      const data = await resp.json();
      const items: string[] = Array.isArray(data.suggestions) ? data.suggestions : [];
      if (!items.length) {
        setAiError('No suggestions yet — try a few more words.');
        return;
      }
      if (single) {
        onChange(items[0]);
      } else {
        let next = value;
        for (const item of items.slice(0, 6)) {
          next = toggleCsvValue(next, item);
        }
        onChange(next);
      }
    } catch {
      setAiError('Could not fetch AI suggestions. Use the chips below.');
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div ref={wrapRef}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <label className="block text-[12px] font-medium text-ink-secondary">{label}</label>
        {aiContext && (
          <button
            type="button"
            onClick={handleSuggestAi}
            disabled={aiLoading}
            className="inline-flex items-center gap-1 text-[11.5px] text-accent hover:underline disabled:opacity-50"
          >
            {aiLoading ? (
              <Loader2 className="w-3 h-3 animate-spin" strokeWidth={1.75} />
            ) : (
              <Sparkles className="w-3 h-3" strokeWidth={1.75} />
            )}
            Suggest for me
          </button>
        )}
      </div>
      {hint && <p className="text-[12px] text-ink-muted mb-2">{hint}</p>}

      <div className="relative">
        {single ? (
          <textarea
            value={value}
            onChange={e => {
              onChange(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            rows={3}
            placeholder={placeholder}
            className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted resize-none"
            aria-autocomplete="list"
            aria-controls={listId}
          />
        ) : (
          <input
            type="text"
            value={value}
            onChange={e => {
              onChange(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            placeholder={placeholder}
            className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted"
            aria-autocomplete="list"
            aria-controls={listId}
          />
        )}

        {open && matches.length > 0 && (
          <ul
            id={listId}
            role="listbox"
            className="absolute z-20 left-0 right-0 mt-1 max-h-48 overflow-auto rounded-md border border-border bg-panel-elevated shadow-md"
          >
            {matches.map(item => (
              <li key={item}>
                <button
                  type="button"
                  role="option"
                  className="w-full text-left px-3 py-2 text-[13px] text-ink-secondary hover:bg-canvas hover:text-ink"
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => pick(item)}
                >
                  {item}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {aiError && <p className="text-[12px] text-amber-600 mt-1">{aiError}</p>}

      {!single && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {suggestions.slice(0, 12).map(item => {
            const selected = csvIncludes(value, item);
            return (
              <button
                key={item}
                type="button"
                onClick={() => onChange(toggleCsvValue(value, item))}
                className={`px-2 py-1 rounded-full text-[12px] border transition-colors ${
                  selected
                    ? 'bg-ink text-panel-elevated border-ink'
                    : 'bg-panel border-border text-ink-secondary hover:border-ink-muted'
                }`}
              >
                {item}
              </button>
            );
          })}
        </div>
      )}

      {single && suggestions.length > 0 && (
        <div className="mt-2 space-y-1.5">
          <p className="text-[11px] text-ink-muted">Suggested scans — click to use:</p>
          <div className="flex flex-col gap-1">
            {suggestions.slice(0, 4).map(item => (
              <button
                key={item}
                type="button"
                onClick={() => onChange(item)}
                className="text-left text-[12.5px] text-ink-secondary hover:text-accent border border-border rounded-md px-3 py-2 bg-panel hover:border-ink-muted transition-colors"
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
