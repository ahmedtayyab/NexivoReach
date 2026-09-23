import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ChevronDown, MapPin } from 'lucide-react';
import { filterOptions } from '../../data/huntTaxonomy';

type Props = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder: string;
  disabled?: boolean;
  icon?: 'pin' | 'none';
  allowCustom?: boolean;
  className?: string;
  /** Controlled open — use so only one hunt dropdown is open at a time. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

/**
 * Searchable dropdown: pick from a long list, or type a custom value.
 * List expands in-flow (no overlay on sections below).
 */
export default function HuntCombobox({
  label,
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
  icon = 'none',
  allowCustom = true,
  className = '',
  open: openProp,
  onOpenChange,
}: Props) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const controlled = typeof openProp === 'boolean';
  const open = controlled ? openProp : uncontrolledOpen;

  const setOpen = (next: boolean) => {
    if (!controlled) setUncontrolledOpen(next);
    onOpenChange?.(next);
  };

  useEffect(() => {
    setQuery(value);
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const filtered = useMemo(
    () => filterOptions(options, open ? query : '', 100),
    [options, query, open],
  );

  const pick = (opt: string) => {
    if (opt.startsWith('Other')) {
      onChange('');
      setQuery('');
      setOpen(true);
      return;
    }
    onChange(opt);
    setQuery(opt);
    setOpen(false);
  };

  const commitCustom = () => {
    const next = query.trim();
    if (!allowCustom) return;
    onChange(next);
  };

  return (
    <div
      className={`hunt-combobox${open ? ' is-open' : ''} ${className}`.trim()}
      ref={rootRef}
    >
      <label className="hunt-search-bar__field">
        <span className="sr-only">{label}</span>
        {icon === 'pin' && (
          <MapPin className="hunt-search-bar__pin" aria-hidden strokeWidth={1.75} />
        )}
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          value={query}
          disabled={disabled}
          placeholder={placeholder}
          autoComplete="off"
          onChange={e => {
            setQuery(e.target.value);
            if (!open) setOpen(true);
            if (allowCustom) onChange(e.target.value);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            window.setTimeout(() => commitCustom(), 120);
          }}
          onKeyDown={e => {
            if (e.key === 'Escape') setOpen(false);
            if (e.key === 'Enter') {
              e.preventDefault();
              if (filtered[0]) pick(filtered[0]);
              else {
                commitCustom();
                setOpen(false);
              }
            }
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              setOpen(true);
            }
          }}
        />
        <button
          type="button"
          className="hunt-combobox__chevron"
          tabIndex={-1}
          disabled={disabled}
          aria-label={`Open ${label} list`}
          onClick={() => setOpen(!open)}
        >
          <ChevronDown className="w-4 h-4" strokeWidth={2} />
        </button>
      </label>
      {open && !disabled && (
        <ul id={listId} className="hunt-combobox__list" role="listbox">
          {filtered.length === 0 ? (
            <li className="hunt-combobox__empty">
              {allowCustom ? 'No matches — keep typing for a custom value' : 'No matches'}
            </li>
          ) : (
            filtered.map(opt => (
              <li key={opt} role="option" aria-selected={opt === value}>
                <button
                  type="button"
                  className={`hunt-combobox__option${opt === value ? ' is-active' : ''}`}
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => pick(opt)}
                >
                  {opt}
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
