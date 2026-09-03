import { csvIncludes, toggleCsvValue } from '../data/suggestions';

interface Props {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  suggestions: string[];
  placeholder: string;
}

export default function SuggestionChips({
  label,
  hint,
  value,
  onChange,
  suggestions,
  placeholder,
}: Props) {
  return (
    <div>
      <label className="block text-[12px] font-medium text-ink-secondary mb-1">{label}</label>
      {hint && <p className="text-[12px] text-ink-muted mb-2">{hint}</p>}
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted"
      />
      <div className="flex flex-wrap gap-1.5 mt-2">
        {suggestions.map(item => {
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
    </div>
  );
}
