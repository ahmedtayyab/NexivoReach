import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Loader2, Sparkles, X } from 'lucide-react';
import {
  csvIncludes,
  csvItems,
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
  /** Hide the suggested-scan list once the user has typed a query */
  hideSuggestionsWhenFilled?: boolean;
  /**
   * none — search/typeahead only (countries)
   * rotate — keep ~5 unselected suggestions; selected move to tags
   * pool — classic static chip row (buyers)
   */
  chipDisplay?: 'none' | 'rotate' | 'pool';
  /** Prefer names that start with the typed query (P → Pakistan) */
  prefixSearch?: boolean;
  /** Show selected values as removable tags above the input */
  selectedAsTags?: boolean;
  /**
   * When true with selectedAsTags, the input is a blank search box.
   * Defaults to true whenever selectedAsTags is on (avoids duplicating chips in the field).
   */
  searchOnly?: boolean;
  /** Max selected items (countries / categories). 0 = unlimited */
  maxItems?: number;
  /** How many rotating suggestion chips to show */
  rotateCount?: number;
}

/**
 * Predictive field = typeahead + optional chips / removable selected tags.
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
  hideSuggestionsWhenFilled = false,
  chipDisplay = 'pool',
  prefixSearch = false,
  selectedAsTags = false,
  searchOnly,
  maxItems = 0,
  rotateCount = 5,
}: Props) {
  const listId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');
  const [query, setQuery] = useState('');
  const [capNote, setCapNote] = useState('');

  const selected = useMemo(() => (single ? [] : csvItems(value)), [single, value]);
  const atCap = Boolean(maxItems && selected.length >= maxItems);
  const useSearchBox = selectedAsTags && (searchOnly ?? true) && !single;
  const token = single ? value.trim() : useSearchBox ? query.trim() : activeTokenFallback(value);

  const matches = filterMatches(suggestions, token, prefixSearch ? 10 : 8, {
    prefixFirst: prefixSearch,
  }).filter(item => single || !csvIncludes(value, item));

  const rotateChips = useMemo(() => {
    if (chipDisplay !== 'rotate') return [];
    return suggestions.filter(item => !csvIncludes(value, item)).slice(0, rotateCount);
  }, [chipDisplay, suggestions, value, rotateCount]);

  useEffect(() => {
    if (!maxItems || single) return;
    if (selected.length > maxItems) {
      onChange(selected.slice(0, maxItems).join(', '));
    }
  }, [maxItems, single, selected, onChange]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const addItem = (item: string) => {
    const clean = item.trim();
    if (!clean) return;
    if (single) {
      onChange(clean);
      setOpen(false);
      return;
    }
    if (csvIncludes(value, clean)) {
      setQuery('');
      setOpen(false);
      return;
    }
    if (maxItems && selected.length >= maxItems) {
      setCapNote(`Up to ${maxItems} selections — keep hunts focused.`);
      setQuery('');
      setOpen(false);
      return;
    }
    setCapNote('');
    onChange([...selected, clean].join(', '));
    setQuery('');
    setOpen(false);
  };

  const removeItem = (item: string) => {
    onChange(toggleCsvValue(value, item));
  };

  const pick = (item: string) => addItem(item);

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
      } else if (aiContext.field === 'categories' && (aiContext.description || '').trim()) {
        onChange(items.slice(0, 6).join(', '));
      } else if (aiContext.field === 'markets') {
        const next = [...selected];
        for (const item of items.slice(0, 6)) {
          if (maxItems && next.length >= maxItems) break;
          if (!next.some(s => s.toLowerCase() === item.toLowerCase())) next.push(item);
        }
        onChange(next.join(', '));
      } else {
        let next = value;
        for (const item of items.slice(0, 6)) {
          if (maxItems && csvItems(next).length >= maxItems && !csvIncludes(next, item)) break;
          next = toggleCsvValue(next, item);
        }
        onChange(next);
      }
    } catch {
      setAiError('Could not fetch AI suggestions.');
    } finally {
      setAiLoading(false);
    }
  };

  const onSearchKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (matches[0]) {
        pick(matches[0]);
      } else if (token.length > 1) {
        addItem(token);
      }
    } else if (e.key === 'Backspace' && !query && selected.length) {
      removeItem(selected[selected.length - 1]);
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
            className="ai-action"
          >
            {aiLoading ? (
              <Loader2 className="w-3 h-3 animate-spin ai-action__icon" strokeWidth={1.75} />
            ) : (
              <Sparkles className="w-3 h-3 ai-action__icon" strokeWidth={1.75} />
            )}
            Suggest for me
          </button>
        )}
      </div>
      {hint && <p className="text-[12px] text-ink-muted mb-2">{hint}</p>}
      {maxItems > 0 && (
        <p className="text-[11px] text-ink-muted mb-2">
          {selected.length}/{maxItems} selected
          {atCap ? ' — limit reached' : ''}
        </p>
      )}
      {(capNote || aiError) && (
        <p className="text-[12px] mb-2" style={{ color: 'var(--warning)' }}>
          {capNote || aiError}
        </p>
      )}

      {selectedAsTags && selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selected.map(item => (
            <button
              key={item}
              type="button"
              onClick={() => removeItem(item)}
              className="inline-flex items-center gap-1 max-w-full px-2 py-1 rounded-md text-[12px] border border-border bg-muted text-ink"
              title="Remove"
            >
              <span className="truncate">{item}</span>
              <X className="w-3 h-3 shrink-0 text-ink-muted" strokeWidth={2} />
            </button>
          ))}
        </div>
      )}

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
            className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink placeholder-ink-muted resize-none"
            aria-autocomplete="list"
            aria-controls={listId}
          />
        ) : useSearchBox ? (
          <input
            type="text"
            value={query}
            onChange={e => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onSearchKeyDown}
            placeholder={placeholder}
            className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink placeholder-ink-muted"
            aria-autocomplete="list"
            aria-controls={listId}
            autoComplete="off"
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
            className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink placeholder-ink-muted"
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

      {!single && chipDisplay === 'pool' && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {suggestions.slice(0, 12).map(item => {
            const selectedChip = csvIncludes(value, item);
            return (
              <button
                key={item}
                type="button"
                onClick={() => {
                  if (!selectedChip && atCap) {
                    setCapNote(`Up to ${maxItems} selections — keep hunts focused.`);
                    return;
                  }
                  setCapNote('');
                  onChange(toggleCsvValue(value, item));
                }}
                disabled={!selectedChip && atCap}
                className={`px-2 py-1 rounded-md text-[12px] border transition-colors disabled:opacity-40 ${
                  selectedChip
                    ? 'bg-[var(--sidebar-active)] text-[var(--brand)] border-[var(--brand)]'
                    : 'bg-panel border-border text-ink-secondary hover:border-ink-muted'
                }`}
              >
                {item}
              </button>
            );
          })}
        </div>
      )}

      {!single && chipDisplay === 'rotate' && rotateChips.length > 0 && (
        <div className="mt-2">
          <p className="text-[11px] text-ink-muted mb-1.5">Suggestions</p>
          <div className="flex flex-wrap gap-1.5">
            {rotateChips.map(item => (
              <button
                key={item}
                type="button"
                onClick={() => addItem(item)}
                disabled={atCap}
                className="px-2 py-1 rounded-md text-[12px] border border-border bg-panel text-ink-secondary hover:border-ink-muted hover:text-ink transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      )}

      {single && suggestions.length > 0 && !(hideSuggestionsWhenFilled && value.trim()) && (
        <div className="mt-2 space-y-1.5">
          <p className="text-[11px] text-ink-muted">Try a starter hunt:</p>
          <div className="flex flex-col gap-1">
            {suggestions.slice(0, 3).map(item => (
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

function activeTokenFallback(value: string): string {
  const parts = value.split(',');
  return (parts[parts.length - 1] || '').trim();
}
