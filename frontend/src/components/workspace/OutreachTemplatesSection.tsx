import { useMemo, useState } from 'react';
import type { OutreachMode, OutreachTemplate, Product } from '../../types';
import { Plus, Trash2 } from 'lucide-react';
import { categoriesFromProducts, allProductCategories } from '../../data/taxonomy';

const PLACEHOLDER_HINT =
  'Use {{company}}, {{seller}}, {{product}}, {{location}}, {{industry}}, {{website}}, {{specialize}}';

const EMPTY_TEMPLATE = (): OutreachTemplate => ({
  id: `tpl-${Math.random().toString(36).slice(2, 10)}`,
  name: '',
  category: '',
  tags: [],
  subject: 'Introduction — {{seller}}',
  body: [
    'Hey {{company}},',
    '',
    'I hope you are fine. I came across your business and wanted to introduce you to {{seller}}.',
    '',
    '{{specialize}}',
    '',
    'We provide competitive wholesale pricing, reliable quality, customization options, and worldwide shipping.',
    'I would be pleased to share our product catalog, pricing, and MOQ if you are currently sourcing.',
    '',
    'Looking forward to hearing from you.',
    'Best regards,',
    '{{seller}}',
  ].join('\n'),
  specializeLines: [],
});

type Props = {
  templates: OutreachTemplate[];
  outreachMode: OutreachMode;
  products: Product[];
  onSave: (next: OutreachTemplate[], mode: OutreachMode) => void | Promise<void>;
};

export default function OutreachTemplatesSection({
  templates,
  outreachMode,
  products,
  onSave,
}: Props) {
  const [mode, setMode] = useState<OutreachMode>(outreachMode);
  const [rows, setRows] = useState<OutreachTemplate[]>(templates);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(templates[0]?.id || null);

  const categoryOptions = useMemo(() => {
    const fromCatalog = categoriesFromProducts(products);
    const fromTemplates = rows.map(r => r.category).filter(Boolean);
    return Array.from(
      new Set([...fromCatalog, ...fromTemplates, ...allProductCategories()]),
    ).sort((a, b) => a.localeCompare(b));
  }, [products, rows]);

  const updateRow = (id: string, patch: Partial<OutreachTemplate>) => {
    setRows(prev => prev.map(r => (r.id === id ? { ...r, ...patch } : r)));
  };

  const addRow = () => {
    const next = EMPTY_TEMPLATE();
    setRows(prev => [...prev, next]);
    setExpandedId(next.id);
  };

  const removeRow = (id: string) => {
    setRows(prev => prev.filter(r => r.id !== id));
    if (expandedId === id) setExpandedId(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setMsg('');
    try {
      const cleaned = rows
        .map((r, i) => ({
          ...r,
          name: (r.name || '').trim() || `Template ${i + 1}`,
          category: (r.category || '').trim(),
          tags: (r.tags || []).map(t => t.trim()).filter(Boolean),
          subject: (r.subject || '').trim(),
          body: (r.body || '').trim(),
          specializeLines: (r.specializeLines || []).map(s => s.trim()).filter(Boolean),
          sortOrder: i,
        }))
        .filter(r => r.body || r.subject);
      await onSave(cleaned, mode);
      setRows(cleaned);
      setMsg(
        mode === 'templates'
          ? 'Saved. Prepare will pick the best matching template by category.'
          : 'Saved. Prepare will keep using AI-generated drafts.',
      );
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Could not save templates');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="outreach-templates mt-8">
      <div className="outreach-templates__head">
        <div>
          <h2 className="section-label">Outreach templates</h2>
          <p className="text-[13px] text-ink-muted mt-1 max-w-xl">
            Write your own emails (e.g. Boxing vs Weightlifting). When mode is “Use my templates”,
            Prepare matches the lead’s product category and fills placeholders — it will not send the
            wrong category template.
          </p>
        </div>
      </div>
      <div className="h-px bg-muted my-4" />

      <div className="seg outreach-templates__mode" role="group" aria-label="Draft mode">
        <button
          type="button"
          className={mode === 'ai' ? 'is-active' : ''}
          onClick={() => setMode('ai')}
        >
          AI-generated
        </button>
        <button
          type="button"
          className={mode === 'templates' ? 'is-active' : ''}
          onClick={() => setMode('templates')}
        >
          Use my templates
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="text-[13px] text-ink-muted mt-4">
          No templates yet. Add 3–4 category templates (one product family each).
        </p>
      ) : (
        <ul className="outreach-templates__list mt-4">
          {rows.map((row, idx) => {
            const open = expandedId === row.id;
            return (
              <li key={row.id} className="outreach-templates__card">
                <div className="outreach-templates__card-head">
                  <button
                    type="button"
                    className="outreach-templates__toggle"
                    onClick={() => setExpandedId(open ? null : row.id)}
                  >
                    <span className="font-medium text-ink">
                      {row.name || `Template ${idx + 1}`}
                    </span>
                    <span className="text-[12px] text-ink-muted">
                      {row.category || 'No category'}
                      {row.tags?.length ? ` · ${row.tags.slice(0, 3).join(', ')}` : ''}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    aria-label="Delete template"
                    onClick={() => removeRow(row.id)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                {open && (
                  <div className="outreach-templates__fields">
                    <label className="block">
                      <span className="field-label">Name</span>
                      <input
                        className="w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel text-ink"
                        value={row.name}
                        onChange={e => updateRow(row.id, { name: e.target.value })}
                        placeholder="Boxing wholesale intro"
                      />
                    </label>
                    <label className="block">
                      <span className="field-label">Category (required for matching)</span>
                      <input
                        className="w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel text-ink"
                        list={`tpl-cats-${row.id}`}
                        value={row.category}
                        onChange={e => updateRow(row.id, { category: e.target.value })}
                        placeholder="Boxing / Martial arts"
                      />
                      <datalist id={`tpl-cats-${row.id}`}>
                        {categoryOptions.map(c => (
                          <option key={c} value={c} />
                        ))}
                      </datalist>
                    </label>
                    <label className="block">
                      <span className="field-label">Tags (keywords, comma-separated)</span>
                      <input
                        className="w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel text-ink"
                        value={(row.tags || []).join(', ')}
                        onChange={e =>
                          updateRow(row.id, {
                            tags: e.target.value
                              .split(',')
                              .map(t => t.trim())
                              .filter(Boolean),
                          })
                        }
                        placeholder="boxing, MMA, gloves, hand wraps"
                      />
                    </label>
                    <label className="block">
                      <span className="field-label">We specialize in (one product per line → {'{{specialize}}'})</span>
                      <textarea
                        className="w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel text-ink resize-y"
                        rows={4}
                        value={(row.specializeLines || []).join('\n')}
                        onChange={e =>
                          updateRow(row.id, {
                            specializeLines: e.target.value.split(/\r?\n/),
                          })
                        }
                        placeholder={'Boxing gloves\nMMA gloves\nHand wraps'}
                      />
                    </label>
                    <label className="block">
                      <span className="field-label">Subject</span>
                      <input
                        className="w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel text-ink"
                        value={row.subject}
                        onChange={e => updateRow(row.id, { subject: e.target.value })}
                        placeholder="Introduction — {{seller}}"
                      />
                    </label>
                    <label className="block">
                      <span className="field-label">Body</span>
                      <textarea
                        className="w-full border border-border rounded-md px-3 py-2 text-[13px] bg-panel text-ink resize-y min-h-[12rem]"
                        rows={12}
                        value={row.body}
                        onChange={e => updateRow(row.id, { body: e.target.value })}
                        placeholder={PLACEHOLDER_HINT}
                      />
                      <span className="text-[11.5px] text-ink-muted mt-1 block">{PLACEHOLDER_HINT}</span>
                    </label>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div className="outreach-templates__actions mt-4">
        <button type="button" className="btn btn-secondary" onClick={addRow}>
          <Plus className="w-3.5 h-3.5" />
          Add template
        </button>
        <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void handleSave()}>
          {saving ? 'Saving…' : 'Save templates'}
        </button>
      </div>
      {msg && (
        <p className="text-[12.5px] text-ink-muted mt-2" role="status">
          {msg}
        </p>
      )}
    </section>
  );
}
