import { useEffect, useMemo, useRef, useState } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog } from '../types';
import { CheckCircle2, ExternalLink, Loader2, Plus, Trash2, XCircle } from 'lucide-react';
import { apiFetch } from '../lib/api';
import PredictiveField from './PredictiveField';
import FindBuyersPanel from './FindBuyersPanel';
import {
  categoriesFromProducts,
  suggestionsForField,
} from '../data/taxonomy';
import type { SettingsSection } from '../lib/navigation';
import {
  isCatalogSetupComplete,
  isCompanySetupComplete,
  nextWorkspaceSection,
  workspaceSetupProgress,
  workspaceSetupSteps,
} from '../lib/workspace';

async function apiErrorMessage(resp: Response, fallback: string): Promise<string> {
  const text = await resp.text();
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail.trim();
    if (Array.isArray(body.detail)) {
      const first = body.detail[0] as { msg?: string } | undefined;
      if (first?.msg) return String(first.msg);
    }
  } catch {
    // plain text
  }
  return text.trim() || fallback;
}
interface Props {
  businessInfo: BusinessInfo;
  products: Product[];
  icp: IdealCustomerProfile;
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
  onSaveBusiness: (info: BusinessInfo) => void;
  onSaveProducts: (products: Product[]) => void;
  onSaveICP: (icp: IdealCustomerProfile) => void;
  onAddProspects?: (prospects: Prospect[]) => void;
  onAddLog?: (log: AgentRunLog) => void;
  onFindBuyersComplete?: (foundCount: number) => void;
  onRestoredFromSheets?: (payload: {
    company?: BusinessInfo;
    products?: Product[];
    prospects?: Prospect[];
    activeBusinessId?: string;
  }) => void | Promise<void>;
}

export default function SettingsView({
  businessInfo,
  products,
  icp,
  section,
  onSectionChange,
  onSaveBusiness,
  onSaveProducts,
  onSaveICP,
  onAddProspects,
  onAddLog,
  onFindBuyersComplete,
  onRestoredFromSheets,
}: Props) {
  const [connectReady, setConnectReady] = useState(false);
  const [sheetsConnected, setSheetsConnected] = useState(false);
  const tabs: { id: SettingsSection; label: string }[] = [
    { id: 'company', label: 'Company' },
    { id: 'integrations', label: 'Connect' },
    { id: 'catalog', label: 'Catalog' },
    { id: 'icp', label: 'Buyers' },
  ];

  const titles: Record<SettingsSection, string> = {
    company: 'Company',
    catalog: 'Catalog',
    icp: 'Buyers',
    integrations: 'Connect',
  };
  const blurb: Record<SettingsSection, string> = {
    company: 'What you sell and where — used to plan searches and judge fit.',
    catalog: 'Products the agent matches against buyer sites. Requires Google Sheets connected first.',
    icp: 'Who should buy — then run Find buyers below. Markets default to company unless you override.',
    integrations: 'Connect Google Sheets before importing a catalog. Gmail is for sending outreach.',
  };

  const steps = useMemo(
    () => workspaceSetupSteps(businessInfo, products, icp, connectReady),
    [businessInfo, products, icp, connectReady],
  );
  const progress = useMemo(() => workspaceSetupProgress(steps), [steps]);
  const stepComplete = useMemo(() => {
    const map = {} as Record<SettingsSection, boolean>;
    for (const step of steps) map[step.id] = step.complete;
    return map;
  }, [steps]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const sheetsResp = await apiFetch('/api/sheets/status');
        let sheetsOk = false;
        if (sheetsResp.ok) {
          const data = await sheetsResp.json();
          sheetsOk = Boolean(data?.userOauthConnected || data?.oauth?.connected);
        }
        if (!cancelled) {
          setSheetsConnected(sheetsOk);
          setConnectReady(sheetsOk);
        }
      } catch {
        // ignore — progress still works for required steps
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [businessInfo.id, section]);

  const advanceAfter = (from: SettingsSection, complete: boolean, nextBusiness?: BusinessInfo) => {
    if (!complete) return;
    if (from === 'company') {
      onSectionChange('integrations');
      return;
    }
    if (from === 'integrations') {
      const biz = nextBusiness ?? businessInfo;
      onSectionChange(isCatalogSetupComplete(products, biz) ? 'icp' : 'catalog');
      return;
    }
    const next = nextWorkspaceSection(from);
    if (next) onSectionChange(next);
  };

  // Find buyers once — on Buyers tab only (not Company/Catalog too).
  const showFind = Boolean(onAddProspects && onAddLog && section === 'icp');

  return (
    <div className="setup-desk">
      <header className="setup-desk__hero">
        <h1 className="setup-desk__title">Workspace</h1>
        <p className="setup-desk__lede">
          Brief the agent, then find buyers. Leads and Outreach handle what comes next.
        </p>
        <div className="ws-progress" aria-label="Workspace setup progress">
          <div className="ws-progress__row">
            <span className="ws-progress__label">
              {progress.requiredDone >= progress.requiredTotal
                ? connectReady
                  ? 'Workspace ready'
                  : 'Ready to find buyers — Connect is optional'
                : `Setup ${progress.requiredDone} of ${progress.requiredTotal} required`}
            </span>
            <span className="ws-progress__pct tabular-nums">{progress.percent}%</span>
          </div>
          <div
            className="ws-progress__track"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress.percent}
          >
            <div className="ws-progress__fill" style={{ width: `${progress.percent}%` }} />
          </div>
          <ol className="ws-progress__steps">
            {steps.map(step => (
              <li
                key={step.id}
                className={[
                  step.complete ? 'is-done' : '',
                  section === step.id ? 'is-current' : '',
                  step.optional ? 'is-optional' : '',
                ].filter(Boolean).join(' ')}
              >
                <button type="button" onClick={() => onSectionChange(step.id)}>
                  {step.complete ? (
                    <CheckCircle2 className="w-3.5 h-3.5" strokeWidth={2} aria-hidden />
                  ) : (
                    <span className="ws-progress__dot" aria-hidden />
                  )}
                  <span>
                    {step.label}
                    {step.optional ? ' · optional' : ''}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      </header>

      <div className="ws-tabs" role="tablist" aria-label="Workspace sections">
        {tabs.map(t => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={section === t.id}
            className={[
              section === t.id ? 'is-active' : '',
              stepComplete[t.id] ? 'is-complete' : '',
            ].filter(Boolean).join(' ')}
            onClick={() => onSectionChange(t.id)}
          >
            {stepComplete[t.id] && (
              <CheckCircle2 className="w-3.5 h-3.5 ws-tabs__check" strokeWidth={2} aria-hidden />
            )}
            {t.label}
          </button>
        ))}
      </div>

      <div className={section === 'integrations' || section === 'icp' ? 'ws-panel ws-panel--wide' : 'ws-panel'}>
        <div className="mb-4">
          <h2 className="text-[15px] font-semibold text-ink m-0">{titles[section]}</h2>
          <p className="text-[12.5px] text-ink-muted mt-1 mb-0 leading-snug">{blurb[section]}</p>
        </div>

        {section === 'company' && (
          <CompanySection
            key={businessInfo.id ?? 'company'}
            businessInfo={businessInfo}
            products={products}
            onSave={info => {
              const wasComplete = isCompanySetupComplete(businessInfo);
              onSaveBusiness(info);
              const nowComplete = isCompanySetupComplete(info);
              if (!wasComplete && nowComplete) advanceAfter('company', true, info);
            }}
          />
        )}
        {section === 'catalog' && (
          <CatalogSection
            products={products}
            sheetsConnected={sheetsConnected}
            onGoConnect={() => onSectionChange('integrations')}
            onSave={nextProducts => {
              const wasComplete = isCatalogSetupComplete(products, businessInfo);
              onSaveProducts(nextProducts);
              const nowComplete = isCatalogSetupComplete(nextProducts, businessInfo);
              if (!wasComplete && nowComplete) advanceAfter('catalog', true);
            }}
            companyWebsite={businessInfo.website}
          />
        )}
        {section === 'icp' && (
          <ICPSection
            key={icp.companySize + (businessInfo.targetMarkets || []).join('|')}
            icp={icp}
            businessInfo={businessInfo}
            products={products}
            onSave={onSaveICP}
          />
        )}
        {section === 'integrations' && (
          <IntegrationsSection
            companyId={businessInfo.id}
            onRestoredFromSheets={onRestoredFromSheets}
            onConnectReadyChange={ready => {
              setConnectReady(ready);
              setSheetsConnected(ready);
              if (ready) advanceAfter('integrations', true);
            }}
          />
        )}
      </div>

      {showFind && (
        <div className="ws-find">
          <FindBuyersPanel
            businessInfo={businessInfo}
            icp={icp}
            products={products}
            onAddProspects={onAddProspects!}
            onAddLog={onAddLog!}
            onComplete={onFindBuyersComplete}
          />
        </div>
      )}
    </div>
  );
}


function CompanySection({
  businessInfo,
  products,
  onSave,
}: {
  businessInfo: BusinessInfo;
  products: Product[];
  onSave: (b: BusinessInfo) => void;
}) {
  const [name, setName] = useState(businessInfo.name ?? '');
  const [website, setWebsite] = useState(businessInfo.website ?? '');
  const [description, setDescription] = useState(businessInfo.description ?? '');
  const [markets, setMarkets] = useState((businessInfo.targetMarkets ?? []).join(', '));
  const [categories, setCategories] = useState((businessInfo.primaryCategories ?? []).join(', '));
  const [extracting, setExtracting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [liveCategorySuggestions, setLiveCategorySuggestions] = useState<string[]>([]);
  const [categorySuggesting, setCategorySuggesting] = useState(false);

  const catalogCats = useMemo(() => categoriesFromProducts(products), [products]);
  // Taxonomy is a soft fallback only — live AI chips come from the description.
  const suggestionContext = `${name} ${description} ${catalogCats.join(' ')}`;
  const marketSuggestions = useMemo(
    () => suggestionsForField('markets', suggestionContext, catalogCats),
    [suggestionContext, catalogCats],
  );
  const categorySuggestions = useMemo(() => {
    const local = suggestionsForField('categories', suggestionContext, catalogCats);
    const seen = new Set<string>();
    const out: string[] = [];
    for (const item of [...liveCategorySuggestions, ...catalogCats, ...local]) {
      const key = item.trim().toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(item.trim());
      if (out.length >= 16) break;
    }
    return out;
  }, [liveCategorySuggestions, catalogCats, suggestionContext]);

  useEffect(() => {
    const brief = `${name} ${description}`.trim();
    if (brief.length < 16) {
      setLiveCategorySuggestions([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setCategorySuggesting(true);
      try {
        const resp = await apiFetch('/api/suggestions/expand', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            field: 'categories',
            description: brief,
            catalogCategories: catalogCats,
          }),
        });
        if (!resp.ok || cancelled) return;
        const data = await resp.json();
        const items: string[] = Array.isArray(data.suggestions) ? data.suggestions : [];
        if (!cancelled) setLiveCategorySuggestions(items.filter(Boolean).slice(0, 10));
      } catch {
        if (!cancelled) setLiveCategorySuggestions([]);
      } finally {
        if (!cancelled) setCategorySuggesting(false);
      }
    }, 700);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [name, description, catalogCats]);

  const handleExtract = async () => {
    if (!description.trim()) return;
    setExtracting(true);
    setError('');
    try {
      const resp = await apiFetch('/api/onboarding/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      });
      if (!resp.ok) throw new Error('Extract failed');
      const data = await resp.json();
      if (data.name) setName(data.name);
      if (data.website) setWebsite(data.website);
      if (Array.isArray(data.targetMarkets)) setMarkets(data.targetMarkets.join(', '));
      if (Array.isArray(data.primaryCategories) && data.primaryCategories.length) {
        setCategories(data.primaryCategories.join(', '));
      } else if (liveCategorySuggestions.length) {
        setCategories(liveCategorySuggestions.slice(0, 6).join(', '));
      }
    } catch (e) {
      console.warn(e);
      setError('Could not extract profile. Fill the fields manually.');
    } finally {
      setExtracting(false);
    }
  };

  const handleSave = () => {
    onSave({
      ...businessInfo,
      name,
      website,
      description,
      targetMarkets: markets.split(',').map(s => s.trim()).filter(Boolean),
      primaryCategories: categories.split(',').map(s => s.trim()).filter(Boolean),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-5 max-w-lg">
      <p className="text-[13px] text-ink-muted">Brief your company like you would a new salesperson.</p>
      <div>
        <label className="block text-[12px] font-medium text-ink-secondary mb-1">
          Business description <span className="text-ink-muted font-normal">(auto-fill from this)</span>
        </label>
        <div className="flex gap-2 items-start">
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={3}
            placeholder="We manufacture industrial valves in Italy and sell to water utilities in Germany and the UK..."
            className="flex-1 border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted resize-none"
          />
          <button
            onClick={handleExtract}
            disabled={extracting || !description.trim()}
            className="shrink-0 px-3 py-2 border border-border hover:border-ink-muted rounded-md text-[12px] text-ink-secondary hover:text-ink transition-colors disabled:opacity-40"
          >
            {extracting ? <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.75} /> : 'Auto-fill'}
          </button>
        </div>
        {error && <p className="text-[12px] text-amber-600 mt-1">{error}</p>}
        {catalogCats.length > 0 && (
          <p className="text-[12px] text-ink-muted mt-2">
            From your catalog: {catalogCats.slice(0, 5).join(', ')}
            {catalogCats.length > 5 ? '…' : ''} — used to refine suggestions below.
          </p>
        )}
      </div>

      <Field label="Business name" value={name} onChange={setName} placeholder="Acme Manufacturing" />
      <Field label="Website" value={website} onChange={setWebsite} placeholder="https://..." />
      <PredictiveField
        label="Where we sell"
        hint="Markets the company sells into. Buyers reuse this unless you override."
        value={markets}
        onChange={setMarkets}
        suggestions={marketSuggestions}
        placeholder="United States, United Kingdom, UAE"
        aiContext={{
          field: 'markets',
          description,
          catalogCategories: catalogCats,
        }}
      />
      <PredictiveField
        label="Product categories"
        hint={
          categorySuggesting
            ? 'Inferring categories from your description…'
            : 'Inferred from your description (and catalog when available). Click chips or Suggest for me — type any custom category.'
        }
        value={categories}
        onChange={setCategories}
        suggestions={categorySuggestions}
        placeholder="e.g. Sportswear, Industrial Equipment, SaaS"
        aiContext={{
          field: 'categories',
          description,
          catalogCategories: catalogCats,
        }}
      />

      <div className="pt-1">
        <button onClick={handleSave} className="btn btn-primary">
          {saved ? 'Saved' : 'Save company'}
        </button>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div>
      <label className="block text-[12px] font-medium text-ink-secondary mb-1">{label}</label>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted"
      />
    </div>
  );
}

function CatalogSection({
  products,
  onSave,
  companyWebsite = '',
  sheetsConnected = false,
  onGoConnect,
}: {
  products: Product[];
  onSave: (p: Product[]) => void;
  companyWebsite?: string;
  sheetsConnected?: boolean;
  onGoConnect?: () => void;
}) {
  const [inputMode, setInputMode] = useState<'url' | 'file' | 'manual'>('url');
  const [url, setUrl] = useState(companyWebsite || '');
  const [useCompanySite, setUseCompanySite] = useState(Boolean(companyWebsite?.trim()));
  const [scraping, setScraping] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const [manual, setManual] = useState({ name: '', category: '', description: '', price: '' });
  const [pageSize, setPageSize] = useState(5);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (useCompanySite && companyWebsite?.trim()) setUrl(companyWebsite.trim());
  }, [companyWebsite, useCompanySite]);

  const mergeProducts = (incoming: Product[]) => {
    const byKey = new Map(
      products.map(p => [(p.productUrl || p.name).toLowerCase(), p]),
    );
    for (const item of incoming) {
      const key = (item.productUrl || item.name).toLowerCase();
      byKey.set(key, item);
    }
    onSave(Array.from(byKey.values()));
  };

  const handleScrape = async () => {
    if (!sheetsConnected) {
      setError('Connect Google Sheets first (Workspace → Connect), then extract products.');
      return;
    }
    const target = (useCompanySite ? companyWebsite : url).trim();
    if (!target) return;
    setScraping(true);
    setError('');
    setStatus('Reading the website and looking for products...');
    try {
      const resp = await apiFetch('/api/products/extract-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: target }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        let detail = 'Extract failed';
        try {
          const body = JSON.parse(text) as { detail?: string };
          if (typeof body.detail === 'string') detail = body.detail;
        } catch {
          // plain
        }
        throw new Error(detail);
      }
      const data = await resp.json();
      const found = (data.products || []) as Product[];
      mergeProducts(found);
      setStatus(
        found.length
          ? data.message || `Added ${found.length} product${found.length === 1 ? '' : 's'} from the website.`
          : data.message || 'No products were found. Try a product page URL or add items manually.'
      );
    } catch (e) {
      console.warn(e);
      setStatus('');
      setError(
        e instanceof Error && e.message
          ? e.message
          : 'Could not extract products from that URL. Try a product or catalog page, or add items manually.',
      );
    } finally {
      setScraping(false);
    }
  };

  const handleFile = async (file: File) => {
    if (!sheetsConnected) {
      setError('Connect Google Sheets first (Workspace → Connect), then upload a catalog.');
      return;
    }
    setScraping(true);
    setError('');
    try {
      const body = new FormData();
      body.append('file', file);
      const resp = await apiFetch('/api/products/upload-file', { method: 'POST', body });
      if (!resp.ok) {
        const text = await resp.text();
        let detail = 'Upload failed';
        try {
          const bodyJson = JSON.parse(text) as { detail?: string };
          if (typeof bodyJson.detail === 'string') detail = bodyJson.detail;
        } catch {
          // plain
        }
        throw new Error(detail);
      }
      const data = await resp.json();
      mergeProducts((data.products || []) as Product[]);
    } catch (e) {
      console.warn(e);
      setError(e instanceof Error ? e.message : 'Could not parse that file.');
    } finally {
      setScraping(false);
    }
  };

  const handleManualAdd = () => {
    if (!manual.name.trim()) return;
    mergeProducts([{
      id: `prod-manual-${Date.now()}`,
      name: manual.name.trim(),
      category: manual.category.trim() || 'Uncategorized',
      description: manual.description.trim(),
      price: manual.price.trim() || undefined,
    }]);
    setManual({ name: '', category: '', description: '', price: '' });
  };

  const removeProduct = (id: string) => {
    onSave(products.filter(p => p.id !== id));
  };

  const visible = expanded ? products.slice(0, pageSize) : products.slice(0, Math.min(5, pageSize));
  const hiddenCount = Math.max(0, products.length - visible.length);

  return (
    <div className="space-y-5 max-w-xl">
      {!sheetsConnected && (
        <div className="ui-banner ui-banner--warn" role="status">
          <p className="m-0 text-[13px]">
            Connect your Google Sheets account before fetching or uploading a catalog — products sync into your workbook.
          </p>
          {onGoConnect && (
            <button type="button" className="btn btn-secondary mt-2" onClick={onGoConnect}>
              Open Connect
            </button>
          )}
        </div>
      )}

      <div>
        <label className="block text-[12px] font-medium text-ink-secondary mb-2">Import source</label>
        <div className="flex space-x-5">
          {(['url', 'file', 'manual'] as const).map(m => (
            <label key={m} className="flex items-center space-x-1.5 cursor-pointer text-[13px] text-ink-secondary">
              <input
                type="radio"
                name="import-mode"
                checked={inputMode === m}
                onChange={() => setInputMode(m)}
                className="accent-accent"
              />
              <span>{m === 'url' ? 'Website' : m === 'file' ? 'Upload file' : 'Manual entry'}</span>
            </label>
          ))}
        </div>
      </div>

      {inputMode === 'url' && (
        <div className="space-y-2">
          {companyWebsite?.trim() ? (
            <label className="flex items-start gap-2 text-[13px] text-ink-secondary cursor-pointer">
              <input
                type="checkbox"
                className="mt-0.5 accent-accent"
                checked={useCompanySite}
                onChange={e => setUseCompanySite(e.target.checked)}
                disabled={!sheetsConnected}
              />
              <span>
                Use company website{' '}
                <span className="text-ink-muted">({companyWebsite.trim()})</span>
              </span>
            </label>
          ) : (
            <p className="text-[12.5px] text-ink-muted">
              Add a website in Company above, or paste a catalog URL here.
            </p>
          )}
          {!useCompanySite && (
            <input
              type="url"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://…"
              disabled={!sheetsConnected}
              className="w-full border border-border px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted disabled:opacity-50"
            />
          )}
          <button
            onClick={handleScrape}
            disabled={!sheetsConnected || scraping || !(useCompanySite ? companyWebsite : url).trim()}
            className="btn btn-primary"
          >
            {scraping ? <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.75} /> : 'Extract products'}
          </button>
        </div>
      )}
      {status && <p className="text-[12px] text-ink-secondary">{status}</p>}
      {error && (
        <p className="ui-banner ui-banner--warn" role="alert">
          {error}
        </p>
      )}

      {inputMode === 'file' && (
        <div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.csv,.xlsx,.xls"
            className="hidden"
            onChange={e => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
              e.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={!sheetsConnected || scraping}
            className="w-full border border-dashed border-border px-4 py-8 text-center hover:border-ink-muted transition-colors disabled:opacity-50"
          >
            {scraping ? (
              <Loader2 className="w-4 h-4 animate-spin inline text-ink-muted" strokeWidth={1.75} />
            ) : (
              <>
                <p className="text-[13px] text-ink-secondary">Drop a PDF, CSV, or Excel file, or browse</p>
                <p className="text-[12px] text-ink-muted mt-1">Supports .pdf, .csv, .xlsx</p>
              </>
            )}
          </button>
        </div>
      )}

      {inputMode === 'manual' && (
        <div className="space-y-3 border border-border bg-panel p-4">
          <Field label="Product name" value={manual.name} onChange={v => setManual({ ...manual, name: v })} placeholder="Product name" />
          <Field label="Category" value={manual.category} onChange={v => setManual({ ...manual, category: v })} placeholder="Category" />
          <Field label="Price" value={manual.price} onChange={v => setManual({ ...manual, price: v })} placeholder="$1,850" />
          <div>
            <label className="block text-[12px] font-medium text-ink-secondary mb-1">Description</label>
            <textarea
              value={manual.description}
              onChange={e => setManual({ ...manual, description: e.target.value })}
              rows={2}
              className="w-full border border-border px-3 py-2 text-[13px] text-ink-secondary"
            />
          </div>
          <button onClick={handleManualAdd} disabled={!manual.name.trim()} className="btn btn-primary">
            <Plus className="w-3.5 h-3.5" strokeWidth={2} />
            Add product
          </button>
        </div>
      )}

      {error && <p className="text-[12px] text-amber-700">{error}</p>}

      {products.length > 0 && (
        <div className="pt-2">
          <div className="catalog-toolbar">
            <p className="section-label mb-0">{products.length} products</p>
            {expanded && (
              <label className="text-[12px] text-ink-secondary flex items-center gap-2">
                Show
                <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}>
                  {[5, 20, 50, 100].map(n => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <div className="bg-panel border border-border divide-y divide-border-subtle">
            {visible.map(product => (
              <div key={product.id} className="px-4 py-3 flex items-start gap-3">
                {product.imageUrl ? (
                  <img
                    src={product.imageUrl}
                    alt=""
                    className="w-12 h-12 object-cover shrink-0 border border-border bg-canvas"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                ) : (
                  <div className="w-12 h-12 border border-border bg-canvas shrink-0 flex items-center justify-center text-[10px] text-ink-muted">—</div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[13.5px] font-medium text-ink-secondary truncate">{product.name}</p>
                      <p className="text-[12px] text-ink-muted mt-0.5">
                        {product.category}
                        {product.price ? ` · ${product.price}` : ''}
                      </p>
                    </div>
                    <button
                      onClick={() => removeProduct(product.id)}
                      className="text-border hover:text-ink-secondary shrink-0 mt-0.5"
                      aria-label={`Remove ${product.name}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.75} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          {hiddenCount > 0 && !expanded && (
            <button type="button" className="btn btn-secondary mt-2" onClick={() => { setExpanded(true); setPageSize(20); }}>
              View more ({hiddenCount} hidden)
            </button>
          )}
          {expanded && products.length > pageSize && (
            <p className="text-[12px] text-ink-muted mt-2">
              Showing {pageSize} of {products.length}. Increase “Show” to see more.
            </p>
          )}
          {expanded && products.length <= pageSize && products.length > 5 && (
            <button type="button" className="btn btn-ghost mt-2" onClick={() => { setExpanded(false); setPageSize(5); }}>
              Show less
            </button>
          )}
        </div>
      )}
    </div>
  );
}


function ICPSection({
  icp,
  businessInfo,
  products,
  onSave,
}: {
  icp: IdealCustomerProfile;
  businessInfo: BusinessInfo;
  products: Product[];
  onSave: (i: IdealCustomerProfile) => void;
}) {
  const marketList = (businessInfo.targetMarkets ?? []).join(', ');
  const marketsMatch =
    (icp.targetCountries ?? []).join(', ').toLowerCase() === marketList.toLowerCase() ||
    !(icp.targetCountries ?? []).length;
  const [buyerTypes, setBuyerTypes] = useState((icp.targetBuyerTypes ?? []).join(', '));
  const [sameAsMarkets, setSameAsMarkets] = useState(marketsMatch);
  const [countries, setCountries] = useState(
    marketsMatch ? marketList : (icp.targetCountries ?? []).join(', '),
  );
  const [companySize, setCompanySize] = useState(icp.companySize ?? 'Any');
  const [minDealSize, setMinDealSize] = useState(icp.minDealSize || '');
  const [signals] = useState(icp.buyingSignals ?? []);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (sameAsMarkets) setCountries(marketList);
  }, [sameAsMarkets, marketList]);

  const catalogCats = useMemo(() => categoriesFromProducts(products), [products]);
  const context = useMemo(
    () =>
      [
        businessInfo.description,
        ...(businessInfo.primaryCategories ?? []),
        ...(businessInfo.targetMarkets ?? []),
        buyerTypes,
        ...catalogCats,
      ].join(' '),
    [businessInfo, buyerTypes, catalogCats],
  );
  const buyerSuggestions = useMemo(
    () => suggestionsForField('buyers', context, catalogCats),
    [context, catalogCats],
  );
  const countrySuggestions = useMemo(
    () => suggestionsForField('markets', context, catalogCats),
    [context, catalogCats],
  );

  const handleSave = () => {
    const resolvedCountries = sameAsMarkets
      ? (businessInfo.targetMarkets ?? [])
      : countries.split(',').map(s => s.trim()).filter(Boolean);
    onSave({
      ...icp,
      targetBuyerTypes: buyerTypes.split(',').map(s => s.trim()).filter(Boolean),
      targetCountries: resolvedCountries,
      companySize,
      minDealSize: minDealSize || undefined,
      buyingSignals: signals,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-10 max-w-3xl">
      <div className="space-y-4">
        <p className="section-label">Target Buyer Criteria</p>
        <p className="text-[13px] text-ink-muted leading-relaxed">
          Name who you want in the pipeline. Geography defaults to company markets so you are not asked twice.
        </p>
        <PredictiveField
          label="Buyer types"
          hint="Type who you sell to (e.g. “gym”, “hospital”, “distributor”) — options appear as you type."
          value={buyerTypes}
          onChange={setBuyerTypes}
          suggestions={buyerSuggestions}
          placeholder="Distributors, Retailers, Hospitals…"
          aiContext={{
            field: 'buyers',
            description: businessInfo.description,
            catalogCategories: catalogCats.length ? catalogCats : businessInfo.primaryCategories,
          }}
        />
        <label className="flex items-start gap-2 text-[13px] text-ink-secondary cursor-pointer">
          <input
            type="checkbox"
            className="mt-0.5 accent-accent"
            checked={sameAsMarkets}
            onChange={e => setSameAsMarkets(e.target.checked)}
          />
          <span>
            Same markets as company
            {marketList ? <span className="text-ink-muted"> ({marketList})</span> : <span className="text-ink-muted"> — set markets in Company first</span>}
          </span>
        </label>
        {!sameAsMarkets && (
          <PredictiveField
            label="Where we look for buyers"
            hint="Only if different from company markets."
            value={countries}
            onChange={setCountries}
            suggestions={countrySuggestions}
            placeholder="United Arab Emirates, Germany"
            aiContext={{
              field: 'markets',
              description: businessInfo.description,
              catalogCategories: catalogCats,
            }}
          />
        )}
        <div>
          <label className="block text-[12px] font-medium text-ink-secondary mb-1">Company size</label>
          <select
            value={companySize}
            onChange={e => setCompanySize(e.target.value as IdealCustomerProfile['companySize'])}
            className="w-full border border-border px-3 py-2 text-[13px] text-ink-secondary bg-panel"
          >
            {['Any', 'Small', 'Medium', 'Enterprise'].map(size => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </div>
        <Field label="Minimum deal size" value={minDealSize} onChange={setMinDealSize} placeholder="$15,000" />
        <div className="pt-2">
          <button onClick={handleSave} className="btn btn-primary">
            {saved ? 'Saved' : 'Save buyers'}
          </button>
        </div>
      </div>

      <div>
        <p className="section-label mb-1.5">Buying Signal Rules</p>
        <p className="text-[13px] text-ink-muted leading-relaxed mb-3">
          Optional. These are examples of timing the agent may look for on a qualified site (expansion, sourcing, a new line). A company is not a hot lead just because it matches a product keyword.
        </p>
        <div className="space-y-4 divide-y divide-border-subtle">
          {signals.map((sig, i) => (
            <div key={sig.id || i} className="pt-3 first:pt-0">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[13.5px] font-medium text-ink-secondary">{sig.name}</p>
                <span className="text-[12px] text-ink-muted">+{sig.weight} pts</span>
              </div>
              <p className="text-[12px] text-ink-secondary mt-0.5 leading-relaxed">{sig.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Integrations Section ─────────────────────────────────────────────────────

type SheetsStatus = {
  connected: boolean;
  platformReady?: boolean;
  userOauthConnected?: boolean;
  reason?: string;
  spreadsheet_title?: string;
  spreadsheetId?: string;
  url?: string;
  serviceAccountEmail?: string;
  message?: string;
  companyName?: string;
  companyId?: string;
  oauth?: { connected: boolean; email?: string; connectedAt?: string };
};

function GmailConnectCard({ onReadyChange }: { onReadyChange?: (ready: boolean) => void }) {
  const [status, setStatus] = useState<{ connected: boolean; email?: string; connectedAt?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch('/api/auth/gmail/status');
      if (r.ok) {
        const data = await r.json();
        setStatus(data);
        onReadyChange?.(Boolean(data?.connected));
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    const gmail = params.get('gmail');
    if (gmail === 'connected') {
      setMsg('Gmail connected — you can send to any recipient address. Test users only control who can connect the mailbox.');
      window.history.replaceState({}, '', `${window.location.pathname}${window.location.hash}`);
      void load();
    } else if (gmail === 'error') {
      setMsg('Gmail connect failed. Re-try and grant send + read access (offline consent).');
      window.history.replaceState({}, '', `${window.location.pathname}${window.location.hash}`);
    }
  }, []);

  const disconnect = async () => {
    const resp = await apiFetch('/api/auth/gmail/disconnect', { method: 'POST' });
    if (resp.ok) {
      setStatus({ connected: false, email: '', connectedAt: '' });
      setMsg('Gmail disconnected.');
      onReadyChange?.(false);
    }
  };

  return (
    <div className="border border-border bg-panel/80 p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-display text-[15px] font-semibold text-ink">Gmail</h3>
          <p className="text-[12.5px] text-ink-secondary mt-0.5">
            Connect your mailbox to send from Outreach/Leads. Once connected, the To: field can be any email —
            Google “test users” only limit who can authorize this app, not who you can message.
          </p>
        </div>
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin text-ink-secondary shrink-0" />
        ) : status?.connected ? (
          <span className="flex items-center gap-1.5 text-[12px] text-emerald-600 font-medium shrink-0">
            <CheckCircle2 className="w-4 h-4" /> Connected
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-[12px] text-amber-600 font-medium shrink-0">
            <XCircle className="w-4 h-4" /> Not connected
          </span>
        )}
      </div>
      {status?.connected && status.email && (
        <p className="text-[13px] text-ink-secondary">
          Sending as <span className="font-medium text-ink">{status.email}</span>
        </p>
      )}
      {msg && <p className="text-[13px] text-ink-secondary">{msg}</p>}
      <div className="flex flex-wrap gap-2">
        {!status?.connected ? (
          <a
            href="/api/auth/gmail"
            className="inline-flex px-3 py-1.5 text-[13px] bg-accent hover:bg-accent-hover text-white rounded-md nr-btn-press"
          >
            Connect Gmail
          </a>
        ) : (
          <button
            type="button"
            onClick={disconnect}
            className="px-3 py-1.5 text-[13px] border border-border rounded-md text-ink-secondary hover:border-ink-muted"
          >
            Disconnect
          </button>
        )}
      </div>
    </div>
  );
}

function IntegrationsSection({
  companyId,
  onRestoredFromSheets,
  onConnectReadyChange,
}: {
  companyId?: string;
  onRestoredFromSheets?: (payload: {
    company?: BusinessInfo;
    products?: Product[];
    prospects?: Prospect[];
    activeBusinessId?: string;
  }) => void | Promise<void>;
  onConnectReadyChange?: (ready: boolean) => void;
}) {
  const [status, setStatus] = useState<SheetsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [sheetInput, setSheetInput] = useState('');
  const [connectBusy, setConnectBusy] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [connectMsg, setConnectMsg] = useState('');
  const [restoreOptions, setRestoreOptions] = useState<
    Array<{ companyName: string; productsTab?: string; leadsTab?: string }>
  >([]);
  const [restoreCompany, setRestoreCompany] = useState('');
  const [includeLeads, setIncludeLeads] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreMsg, setRestoreMsg] = useState('');
  const [syncingLeads, setSyncingLeads] = useState(false);
  const [syncLeadsMsg, setSyncLeadsMsg] = useState('');

  const sheetsReady = Boolean(status?.userOauthConnected || status?.oauth?.connected);
  useEffect(() => {
    onConnectReadyChange?.(sheetsReady);
  }, [sheetsReady, onConnectReadyChange]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch('/api/sheets/status');
      if (r.ok) {
        const data = await r.json();
        setStatus(data);
        if (data.connected) {
          const opts = await apiFetch('/api/sheets/restore-options');
          if (opts.ok) {
            const body = await opts.json();
            const companies = Array.isArray(body.companies) ? body.companies : [];
            setRestoreOptions(companies);
            if (companies.length && !restoreCompany) {
              setRestoreCompany(companies[0].companyName);
            }
          }
        } else {
          setRestoreOptions([]);
        }
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [companyId]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sheets = params.get('sheets');
    if (sheets === 'connected') {
      setConnectMsg('Google Sheets connected — create or link a spreadsheet for this company.');
      window.history.replaceState({}, '', `${window.location.pathname}${window.location.hash}`);
      void load();
    } else if (sheets === 'error') {
      setConnectMsg('Google Sheets connect failed. Grant Sheets & Drive access and try again.');
      window.history.replaceState({}, '', `${window.location.pathname}${window.location.hash}`);
    }
  }, []);

  const handleConnect = async () => {
    if (!sheetInput.trim() || connectBusy) return;
    setConnectBusy(true);
    setConnectMsg('');
    try {
      const resp = await apiFetch('/api/sheets/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spreadsheet: sheetInput.trim() }),
      });
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Connect failed'));
      setSheetInput('');
      setConnectMsg('Sheet linked to this company.');
      await load();
    } catch (e) {
      setConnectMsg(e instanceof Error ? e.message : 'Connect failed');
    } finally {
      setConnectBusy(false);
    }
  };

  const handleCreate = async () => {
    if (createBusy) return;
    setCreateBusy(true);
    setConnectMsg('');
    try {
      const resp = await apiFetch('/api/sheets/create', { method: 'POST' });
      if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Create failed'));
      const data = await resp.json();
      setConnectMsg(
        data.reused
          ? 'Linked to your existing workbook and added tabs for this company.'
          : data.sharedWith
            ? `Created and shared with ${data.sharedWith}.`
            : 'Spreadsheet created for this company.',
      );
      await load();
    } catch (e) {
      setConnectMsg(e instanceof Error ? e.message : 'Create failed');
    } finally {
      setCreateBusy(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Unlink this company’s Google Sheet? Data in the sheet is kept.')) return;
    const resp = await apiFetch('/api/sheets/disconnect', { method: 'POST' });
    if (resp.ok) {
      setConnectMsg('Sheet unlinked from this company.');
      await load();
    }
  };

  const handleRestore = async () => {
    if (!restoreCompany || restoring) return;
    const ok = window.confirm(
      includeLeads
        ? `Restore catalog and leads for “${restoreCompany}” from Google Sheets into this company?`
        : `Restore the product catalog for “${restoreCompany}” from Google Sheets into this company?`,
    );
    if (!ok) return;
    setRestoring(true);
    setRestoreMsg('');
    try {
      const resp = await apiFetch('/api/sheets/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: restoreCompany,
          include_products: true,
          include_leads: includeLeads,
          replace_products: true,
          replace_leads: includeLeads,
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `Restore failed (${resp.status})`);
      }
      const data = await resp.json();
      setRestoreMsg(
        `Restored company “${data.company?.name || restoreCompany}” with ${data.productsRestored || 0} products`
        + (includeLeads ? ` and ${data.leadsRestored || 0} leads` : '')
        + `.`,
      );
      if (onRestoredFromSheets) {
        await onRestoredFromSheets({
          company: data.company,
          products: data.products,
          prospects: data.prospects,
          activeBusinessId: data.activeBusinessId,
        });
      }
    } catch (e) {
      setRestoreMsg(e instanceof Error ? e.message : 'Restore failed');
    } finally {
      setRestoring(false);
    }
  };

  const platformReady = Boolean(status?.platformReady);
  const userOauth = Boolean(status?.userOauthConnected ?? status?.oauth?.connected);
  const oauthEmail = status?.oauth?.email || '';

  return (
    <div className="space-y-8">
      {/* Gmail card */}
      <GmailConnectCard />

      {/* Google Sheets card */}
      <div className="border border-border bg-panel/80 p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="font-display text-[15px] font-semibold text-ink">Google Sheets</h3>
            <p className="text-[12.5px] text-ink-secondary mt-0.5">
              Connect your Google account once. Companies share one workbook in your Drive; each gets its own Products and Leads tabs.
            </p>
          </div>
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-ink-secondary shrink-0" />
          ) : status?.connected ? (
            <span className="flex items-center gap-1.5 text-[12px] text-emerald-600 font-medium shrink-0">
              <CheckCircle2 className="w-4 h-4" /> Linked
            </span>
          ) : userOauth ? (
            <span className="flex items-center gap-1.5 text-[12px] text-amber-600 font-medium shrink-0">
              <CheckCircle2 className="w-4 h-4" /> Account ready
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[12px] text-amber-600 font-medium shrink-0">
              <XCircle className="w-4 h-4" /> Not connected
            </span>
          )}
        </div>

        {userOauth && oauthEmail && (
          <p className="text-[13px] text-ink-secondary">
            Sheets account <span className="font-medium text-ink">{oauthEmail}</span>
          </p>
        )}

        {!userOauth && platformReady && !loading && (
          <div className="flex flex-wrap gap-2 items-center">
            <a
              href="/api/auth/sheets"
              className="inline-flex px-3 py-1.5 text-[13px] bg-accent hover:bg-accent-hover text-white rounded-md nr-btn-press"
            >
              Connect Google Sheets
            </a>
            <button
              type="button"
              onClick={load}
              className="text-[12.5px] text-ink-secondary hover:text-ink underline-offset-2 hover:underline"
            >
              Refresh status
            </button>
          </div>
        )}

        {userOauth && !status?.connected && !loading && (
          <div className="space-y-3 pt-1">
            <p className="text-[12.5px] text-ink-secondary leading-relaxed">
              Create a spreadsheet (or paste one you already own). Later companies will reuse this workbook and add new tabs.
            </p>
            <div className="flex flex-wrap gap-2 items-center">
              <button
                type="button"
                disabled={createBusy}
                onClick={handleCreate}
                className="px-3 py-2 text-[13px] bg-accent hover:bg-accent-hover disabled:opacity-50 text-white rounded-md"
              >
                {createBusy ? 'Creating…' : 'Create spreadsheet'}
              </button>
              <button
                type="button"
                onClick={async () => {
                  if (!window.confirm('Disconnect Google Sheets from NexivoReach? Company sheet links stay until you unlink them.')) return;
                  await apiFetch('/api/auth/sheets/disconnect', { method: 'POST' });
                  setConnectMsg('Google Sheets disconnected.');
                  await load();
                }}
                className="px-3 py-1.5 text-[12.5px] border border-border rounded-md text-ink-secondary hover:border-ink-muted"
              >
                Disconnect account
              </button>
            </div>
            <div className="flex flex-col sm:flex-row gap-2 max-w-xl">
              <input
                type="text"
                value={sheetInput}
                onChange={e => setSheetInput(e.target.value)}
                placeholder="Or paste spreadsheet URL / ID you own"
                className="flex-1 border border-border rounded-md px-3 py-2 text-[13px] text-ink bg-panel"
              />
              <button
                type="button"
                disabled={connectBusy || !sheetInput.trim()}
                onClick={handleConnect}
                className="btn-secondary text-[13px] py-2 px-3 disabled:opacity-40"
              >
                {connectBusy ? 'Linking…' : 'Link sheet'}
              </button>
            </div>
          </div>
        )}

        {status?.connected && status.url && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <a
              href={status.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-[12.5px] text-accent hover:underline"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              {status.spreadsheet_title || 'Open spreadsheet'}
            </a>
            <button
              type="button"
              disabled={syncingLeads}
              onClick={async () => {
                setSyncingLeads(true);
                setSyncLeadsMsg('');
                try {
                  const resp = await apiFetch('/api/sheets/sync-leads', { method: 'POST' });
                  if (!resp.ok) throw new Error(await apiErrorMessage(resp, 'Sync failed'));
                  const data = await resp.json();
                  setSyncLeadsMsg(
                    `Synced ${data.written || 0} lead(s)`
                    + (data.tab ? ` to “${data.tab}”` : '')
                    + ' — emailed rows should now be blue.',
                  );
                } catch (e) {
                  setSyncLeadsMsg(e instanceof Error ? e.message : 'Sync failed');
                } finally {
                  setSyncingLeads(false);
                }
              }}
              className="btn-secondary text-[12.5px] py-1.5 px-3 disabled:opacity-50"
            >
              {syncingLeads ? 'Coloring…' : 'Sync leads & colors'}
            </button>
            <button
              type="button"
              onClick={handleDisconnect}
              className="px-3 py-1.5 text-[12.5px] border border-border rounded-md text-ink-secondary hover:border-ink-muted"
            >
              Unlink sheet
            </button>
            {userOauth && (
              <button
                type="button"
                onClick={async () => {
                  if (!window.confirm('Disconnect Google Sheets from NexivoReach?')) return;
                  await apiFetch('/api/auth/sheets/disconnect', { method: 'POST' });
                  setConnectMsg('Google Sheets disconnected.');
                  await load();
                }}
                className="px-3 py-1.5 text-[12.5px] text-ink-secondary hover:underline"
              >
                Disconnect account
              </button>
            )}
            {syncLeadsMsg && (
              <p className="w-full text-[12px] text-ink-secondary">{syncLeadsMsg}</p>
            )}
          </div>
        )}

        {!platformReady && !loading && (
          <p className="text-[12.5px] text-ink-secondary leading-relaxed">
            Google sign-in is not configured on the server, so Sheets connect is unavailable.
          </p>
        )}

        {connectMsg && (
          <p className="text-[12.5px] text-ink-secondary">{connectMsg}</p>
        )}
      </div>

      {status?.connected && restoreOptions.length > 0 && (
        <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
          <div>
            <h3 className="text-[14px] font-semibold text-ink">Restore from this company’s sheet</h3>
            <p className="text-[12.5px] text-ink-secondary mt-0.5 leading-relaxed">
              Pull catalog (and optionally leads) from tabs in the spreadsheet linked above into this company.
            </p>
          </div>
          <div>
            <label className="block text-[12px] font-medium text-ink-secondary mb-1">Company tab</label>
            <select
              value={restoreCompany}
              onChange={e => setRestoreCompany(e.target.value)}
              className="w-full max-w-md border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary bg-panel"
            >
              {restoreOptions.map(opt => (
                <option key={opt.companyName} value={opt.companyName}>
                  {opt.companyName}
                  {opt.productsTab ? ' (products)' : ''}
                  {opt.leadsTab ? ' (leads)' : ''}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-[13px] text-ink-secondary">
            <input
              type="checkbox"
              checked={includeLeads}
              onChange={e => setIncludeLeads(e.target.checked)}
            />
            Also restore leads (usually skip — re-run Discover instead)
          </label>
          <button
            type="button"
            onClick={handleRestore}
            disabled={restoring || !restoreCompany}
            className="px-4 py-1.5 bg-accent hover:bg-accent-hover disabled:opacity-40 text-white text-[13px] font-medium rounded-md transition-colors"
          >
            {restoring ? 'Restoring…' : 'Restore company'}
          </button>
          {restoreMsg && (
            <p className="text-[12.5px] text-ink-secondary">{restoreMsg}</p>
          )}
        </div>
      )}

      {/* What syncs */}
      <div className="rounded-xl border border-border bg-surface p-6">
        <h4 className="text-[13px] font-semibold text-ink mb-3">What gets synced</h4>
        <ul className="space-y-2 text-[12.5px] text-ink-secondary">
          <li className="flex gap-2">
            <span className="text-accent font-bold mt-0.5">→</span>
            <span><strong className="text-ink">Product Catalog</strong> — every time you save your catalog, all products are upserted into a per-company tab (e.g. <em>"Acme — Products"</em>).</span>
          </li>
          <li className="flex gap-2">
            <span className="text-accent font-bold mt-0.5">→</span>
            <span><strong className="text-ink">Prospects</strong> — written to your company <em>Leads</em> tab (keyed on website). Status drives row color: white = To contact, blue = Contacted (emailed), green = Replied, amber = Re-contact.</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
